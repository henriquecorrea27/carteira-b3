"""B3 listed companies data (public, undocumented — the same source the rOpenSci `rb3` package uses).

GET .../listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/{base64 of
{"issuingCompany": "PETR", "language": "pt-br"}} returns a one-element list with:
- cashDividends: last ~12 months only. {isinCode, label (DIVIDENDO | JRS CAP PROPRIO | RENDIMENTO),
  lastDatePrior (data-com), paymentDate, rate (per share, "0,47156696000"), approvedOn, relatedTo}.
  An instalment plan appears as one row per payment date, each with its own rate.
- stockDividends: full history. {label, factor, lastDatePrior}. DESDOBRAMENTO and BONIFICACAO factors
  are % of new shares (100 = 1:2); GRUPAMENTO is the new/old ratio (0,1 = 10:1). No bonus cost.
- subscriptions: rights offers (informative only).
Real responses are saved in tests/fixtures/b3_events/.
"""

import base64
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

import httpx

from app.core.calendar import next_business_day
from app.corporate_events.base import CorporateEventsError, ParsedEvent
from app.portfolio.types import TransactionType as T

URL = (
    "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetListedSupplementCompany/{}"
)
SOURCE = "b3"
CASH_LABELS = {"DIVIDENDO": T.DIVIDEND, "JRS CAP PROPRIO": T.JCP, "RENDIMENTO": T.INCOME}
HUNDRED = Decimal(100)

# ISIN = BR + issuer (4) + security type + check digits. Share classes map to the ticker suffix.
_ISIN_CLASSES = {
    "ACNOR": "3",
    "ACNPR": "4",
    "ACNPA": "5",
    "ACNPB": "6",
    "ACNPC": "7",
    "ACNPD": "8",
    "CDAM": "11",  # units
    "CTF": "11",  # FII shares
}


def isin_to_ticker(isin: str, issuer: str) -> str | None:
    if not isin.startswith("BR") or isin[2:6] != issuer:
        return None
    rest = isin[6:]
    for prefix, suffix in _ISIN_CLASSES.items():
        if rest.startswith(prefix):
            return issuer + suffix
    return None


def _dec(text: str) -> Decimal:
    return Decimal(text.strip().replace(".", "").replace(",", "."))


def _date(text: str | None) -> date | None:
    if not text or not text.strip():
        return None
    parsed = datetime.strptime(text.strip(), "%d/%m/%Y").date()
    # Placeholders used by B3 for "no date"
    return None if parsed.year in (1900, 9999) else parsed


def _key(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def _stock_mapping(label: str, value: Decimal) -> tuple[str | None, Decimal | None]:
    if label == "DESDOBRAMENTO":
        return T.SPLIT.value, 1 + value / HUNDRED
    if label == "GRUPAMENTO" and value > 0:
        return T.REVERSE_SPLIT.value, 1 / value
    if label == "BONIFICACAO":
        return T.BONUS.value, value / HUNDRED
    return None, None


def parse_supplement(payload: list[dict], issuer: str) -> list[ParsedEvent]:
    if not payload:
        return []
    company = payload[0]
    events: list[ParsedEvent] = []
    for row in company.get("cashDividends") or []:
        record = _date(row.get("lastDatePrior"))
        if record is None:
            continue
        label = row["label"].strip()
        value = _dec(row["rate"])
        payment = _date(row.get("paymentDate"))
        mapped = CASH_LABELS.get(label)
        events.append(
            ParsedEvent(
                event_key=_key(SOURCE, row["isinCode"], label, record, payment, value),
                issuer=issuer,
                isin=row["isinCode"],
                ticker=isin_to_ticker(row["isinCode"], issuer),
                category="CASH" if mapped else "OTHER",
                label=label,
                tx_type=mapped.value if mapped else None,
                record_date=record,
                ex_date=next_business_day(record),
                payment_date=payment,
                value=value,
                factor=None,
                approved_on=_date(row.get("approvedOn")),
                related_to=(row.get("relatedTo") or "").strip() or None,
                remarks=(row.get("remarks") or "").strip() or None,
            )
        )
    for group, category in (("stockDividends", "STOCK"), ("subscriptions", "OTHER")):
        for row in company.get(group) or []:
            record = _date(row.get("lastDatePrior"))
            if record is None:
                continue
            label = row["label"].strip()
            raw = row.get("factor") or row.get("percentage") or "0"
            # Published numbers carry float noise (CEMIG 2024 bonus: "30,00000002726")
            value = _dec(raw).quantize(Decimal("0.000001")).normalize()
            tx_type, factor = _stock_mapping(label, value) if category == "STOCK" else (None, None)
            events.append(
                ParsedEvent(
                    event_key=_key(SOURCE, row["isinCode"], label, record, value),
                    issuer=issuer,
                    isin=row["isinCode"],
                    ticker=isin_to_ticker(row["isinCode"], issuer),
                    category=category if tx_type else "OTHER",
                    label=label,
                    tx_type=tx_type,
                    record_date=record,
                    ex_date=next_business_day(record),
                    payment_date=None,
                    value=value,
                    factor=factor,
                    approved_on=_date(row.get("approvedOn")),
                    related_to=None,
                    remarks=(row.get("remarks") or "").strip() or None,
                )
            )
    return events


class B3CorporateEventsSource:
    name = SOURCE

    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=30, headers={"User-Agent": "Mozilla/5.0"})

    def events_for_issuer(self, issuer: str) -> list[ParsedEvent]:
        return parse_supplement(self.supplement(issuer), issuer)

    def supplement(self, issuer: str) -> list[dict]:
        """Raw company payload (also used for share counts by app.fundamentals.shares)."""
        token = base64.b64encode(
            json.dumps({"issuingCompany": issuer, "language": "pt-br"}, separators=(",", ":")).encode()
        ).decode()
        try:
            response = self._client.get(URL.format(token))
        except httpx.HTTPError as err:
            raise CorporateEventsError(f"B3 indisponível: {err}") from err
        if response.status_code != 200:
            raise CorporateEventsError(f"B3 respondeu {response.status_code} para {issuer}")
        # An issuer no longer listed (delisted, renamed like VIIA → BHIA) or a fund (FIIs are on another B3
        # page) comes back as 200 with an empty body: nothing to fetch, not a failure
        if not response.text.strip():
            return []
        try:
            payload = response.json()
        except ValueError as err:
            raise CorporateEventsError(f"resposta inesperada da B3 para {issuer}") from err
        if not isinstance(payload, list):
            raise CorporateEventsError(f"formato inesperado da B3 para {issuer}")
        return payload
