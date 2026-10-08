"""F3 — provents and corporate events from B3 (real public responses in fixtures/b3_events)."""

import json
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.calendar import next_business_day
from app.corporate_events import service
from app.corporate_events.b3_source import isin_to_ticker, parse_supplement
from app.models import CorporateEvent, Transaction
from app.portfolio import service as ledger
from app.portfolio.types import TransactionSource
from app.schemas.transaction import TransactionIn

FIXTURES = Path(__file__).parent / "fixtures" / "b3_events"
TODAY = date(2026, 10, 8)


def load(issuer):
    return parse_supplement(json.loads((FIXTURES / f"{issuer}_supplement.json").read_text("utf-8")), issuer)


class FakeSource:
    name = "b3"

    def events_for_issuer(self, issuer):
        path = FIXTURES / f"{issuer}_supplement.json"
        return load(issuer) if path.exists() else []


@pytest.fixture
def session(session_factory):
    with session_factory() as s:
        yield s


def tx(**kw):
    return TransactionIn(**kw)


def buy(day, ticker, qty, price="10"):
    return tx(date=day, ticker=ticker, type="BUY", quantity=qty, price=price)


def rows(session, **filters):
    query = select(Transaction)
    for k, v in filters.items():
        query = query.where(getattr(Transaction, k) == v)
    return list(session.scalars(query.order_by(Transaction.date, Transaction.id)))


# --- parsing ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("isin", "issuer", "ticker"),
    [
        ("BRCMIGACNPR3", "CMIG", "CMIG4"),
        ("BRCMIGACNOR6", "CMIG", "CMIG3"),
        ("BRTAEECDAM10", "TAEE", "TAEE11"),
        ("BRHGLGCTF004", "HGLG", "HGLG11"),
        ("BRBBASA04OR8", "BBAS", None),  # other security of the issuer
        ("BRHGLGR26M17", "HGLG", None),  # subscription receipt
        ("BRPETRACNOR9", "CMIG", None),
    ],
)
def test_isin_to_ticker(isin, issuer, ticker):
    assert isin_to_ticker(isin, issuer) == ticker


def test_stock_event_factors_follow_b3_semantics():
    by_label = {(e.ticker, e.label, e.record_date): e for e in load("MGLU") + load("CMIG") + load("BBAS")}
    split = by_label[("MGLU3", "DESDOBRAMENTO", date(2020, 10, 13))]
    assert (split.tx_type, split.factor) == ("SPLIT", D(4))  # 300% new shares → 1:4
    reverse = by_label[("MGLU3", "GRUPAMENTO", date(2024, 5, 24))]
    assert (reverse.tx_type, reverse.factor) == ("REVERSE_SPLIT", D(10))  # 0,1 new/old → 10:1
    bonus = by_label[("CMIG4", "BONIFICACAO", date(2024, 4, 29))]
    assert (bonus.tx_type, bonus.factor) == ("BONUS", D("0.3"))  # published as 30,00000002726
    assert bonus.ex_date == date(2024, 4, 30)
    bbas = by_label[("BBAS3", "DESDOBRAMENTO", date(2024, 4, 15))]
    assert bbas.factor == D(2)


def test_cash_events_keep_one_row_per_instalment():
    cmig = [e for e in load("CMIG") if e.ticker == "CMIG4" and e.record_date == date(2026, 4, 30)]
    assert sorted(e.payment_date for e in cmig) == [date(2026, 6, 30), date(2026, 12, 30)]
    assert {e.tx_type for e in cmig} == {"DIVIDEND"}
    assert all(e.value == D("0.11817794282") for e in cmig)


def test_fii_income_and_empty_etf():
    hglg = [e for e in load("HGLG") if e.ticker == "HGLG11" and e.category == "CASH"]
    assert hglg and {e.tx_type for e in hglg} == {"INCOME"}
    assert load("BOVA") == []


def test_business_day_skips_weekends_and_holidays():
    assert next_business_day(date(2026, 10, 9)) == date(2026, 10, 13)  # Fri → Mon 12/10 is a holiday
    assert next_business_day(date(2024, 2, 9)) == date(2024, 2, 14)  # Carnival Mon/Tue


# --- applying to the ledger ------------------------------------------------------------------


def test_cash_events_generate_auto_provents_from_the_position_on_the_data_com(session):
    ledger.create_transactions(session, [buy(date(2025, 1, 10), "CMIG4", "195")])
    result = service.sync(session, FakeSource(), today=TODAY)
    assert result.issuers == 1

    autos = {(t.type, t.date, t.payment_date): t for t in rows(session, source="AUTO")}
    paid = autos[("DIVIDEND", date(2026, 4, 30), date(2026, 6, 30))]
    # 195 × 0,11817794282 = 23,0447 → truncated to 23,04 ; dividends are exempt
    assert (paid.quantity, paid.gross_amount, paid.tax_withheld, paid.net_amount) == (
        D("195"),
        D("23.04"),
        D("0"),
        D("23.04"),
    )
    assert paid.status == "PAID"
    assert autos[("DIVIDEND", date(2026, 4, 30), date(2026, 12, 30))].status == "ANNOUNCED"
    jcp = autos[("JCP", date(2026, 3, 24), date(2027, 6, 30))]
    # 195 × 0,11500002917 = 22,425 → 22,42 ; JCP paid in 2027 → 17,5% = 3,92
    assert (jcp.gross_amount, jcp.tax_withheld, jcp.net_amount, jcp.status) == (
        D("22.42"),
        D("3.92"),
        D("18.50"),
        "ANNOUNCED",
    )
    # Data-com after today: agenda only, no transaction
    assert all(t.date < TODAY for t in autos.values())


def test_sync_is_idempotent(session):
    ledger.create_transactions(session, [buy(date(2025, 1, 10), "CMIG4", "195")])
    service.sync(session, FakeSource(), today=TODAY)
    count = len(rows(session, source="AUTO"))
    again = service.sync(session, FakeSource(), today=TODAY)
    assert (again.applied.created, again.applied.updated, again.applied.removed) == (0, 0, 0)
    assert len(rows(session, source="AUTO")) == count


def test_stock_events_apply_on_ex_date_and_bonus_stays_pending(session):
    ledger.create_transactions(session, [buy(date(2024, 1, 10), "CMIG4", "150")])
    service.sync(session, FakeSource(), today=TODAY)
    (bonus,) = rows(session, source="AUTO", type="BONUS")
    assert (bonus.date, bonus.quantity, bonus.price) == (date(2024, 4, 30), D("45"), None)
    position = ledger.current_portfolio(session).position("CMIG4")
    assert position.quantity == D("195")
    assert position.pending_bonus_cost
    pending = service.pending(session, today=TODAY)
    assert [(p.kind, p.ticker, p.transaction_id) for p in pending] == [("BONUS_NO_COST", "CMIG4", bonus.id)]
    # Provents after the bonus are computed on 195 shares
    after = [t for t in rows(session, source="AUTO", type="DIVIDEND") if t.date > bonus.date]
    assert after and all(t.quantity == D("195") for t in after)


def test_imported_rows_are_not_duplicated_and_get_the_event_dates(session):
    ledger.create_transactions(session, [buy(date(2024, 3, 1), "BBAS3", "5", "55")])
    imported = [
        # B3 credits the split two days after the data-com (factor computed by the importer)
        tx(date=date(2024, 4, 17), ticker="BBAS3", type="SPLIT", factor="2"),
    ]
    ledger.create_transactions(session, imported, source=TransactionSource.B3)
    service.sync(session, FakeSource(), today=TODAY)
    splits = rows(session, type="SPLIT")
    assert [(s.source, s.date) for s in splits] == [("B3", date(2024, 4, 16))]  # moved to the ex-date


def test_imported_provent_confirms_the_event(session):
    ledger.create_transactions(session, [buy(date(2025, 1, 10), "CMIG4", "195")])
    confirmed = tx(
        date=date(2026, 6, 30),
        ticker="CMIG4",
        type="DIVIDEND",
        quantity="195",
        price="0.118",
        gross_amount="23.04",
        tax_withheld="0",
        payment_date=date(2026, 6, 30),
        status="CONFIRMED",
    )
    ledger.create_transactions(session, [confirmed], source=TransactionSource.B3)
    service.sync(session, FakeSource(), today=TODAY)
    june = [t for t in rows(session, type="DIVIDEND") if t.payment_date == date(2026, 6, 30)]
    assert [(t.source, t.date) for t in june] == [("B3", date(2026, 4, 30))]  # data-com filled in


def test_retroactive_sale_removes_provents_and_deletion_dismisses(session):
    ledger.create_transactions(session, [buy(date(2025, 1, 10), "CMIG4", "195")])
    service.sync(session, FakeSource(), today=TODAY)
    assert rows(session, source="AUTO")

    # Sold everything before the 2026 data-com dates: 2026 provents disappear
    ledger.create_transactions(
        session, [tx(date=date(2026, 1, 5), ticker="CMIG4", type="SELL", quantity="195", price="12")]
    )
    service.apply_events(session, today=TODAY)
    assert all(t.date < date(2026, 1, 5) for t in rows(session, source="AUTO"))

    # Deleting an AUTO row is final
    victim = rows(session, source="AUTO")[0]
    ledger.delete_transaction(session, victim.id)
    service.apply_events(session, today=TODAY)
    assert victim.dedup_hash not in {t.dedup_hash for t in rows(session, source="AUTO")}
    event = session.scalar(select(CorporateEvent).where(CorporateEvent.event_key == victim.dedup_hash))
    assert event.dismissed


def test_user_edit_wins_over_the_job(session):
    ledger.create_transactions(session, [buy(date(2025, 1, 10), "CMIG4", "195")])
    service.sync(session, FakeSource(), today=TODAY)
    auto = rows(session, source="AUTO", type="DIVIDEND")[0]
    edited = ledger.update_transaction(
        session,
        auto.id,
        tx(
            date=auto.date,
            ticker="CMIG4",
            type="DIVIDEND",
            quantity="195",
            price=str(auto.price),
            gross_amount="99",
            tax_withheld="0",
            payment_date=auto.payment_date,
        ),
    )
    service.apply_events(session, today=TODAY)
    session.refresh(edited)
    assert (edited.user_edited, edited.gross_amount) == (True, D("99"))


def test_agenda_lists_future_data_com_with_estimate(session):
    ledger.create_transactions(session, [buy(date(2025, 1, 10), "HGLG11", "10", "150")])
    service.sync(session, FakeSource(), today=date(2026, 9, 20))
    items = service.agenda(session, today=date(2026, 9, 20))
    future = [i for i in items if i.record_date == date(2026, 9, 30) and i.ticker == "HGLG11"]
    assert future and not future[0].in_ledger
    # 10 × 1,17 = 11,70, income is exempt
    assert future[0].estimated_net == D("11.70")
