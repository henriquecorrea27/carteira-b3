"""Locates the key accounts in one company's statements (CVM standardized chart of accounts).

Codes differ between templates (net income is 3.11 for companies and banks but 3.13 for insurers;
equity is 2.03 for companies and 2.07 for banks), so accounts are found by code *level* plus a
description pattern, never by a fixed code alone. Layout validated against real DFP/ITR files
(see tests/fixtures/cvm/README.md)."""

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal(0)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


@dataclass(frozen=True)
class Account:
    code: str
    description: str
    value: Decimal

    @property
    def depth(self) -> int:
        return self.code.count(".")

    @property
    def text(self) -> str:
        return _norm(self.description)


class Statement:
    """Accounts of one statement (BPA, BPP, DRE or DFC) for one company and one period column."""

    def __init__(self, accounts: list[Account]):
        self.by_code = {a.code: a for a in accounts}
        self.accounts = sorted(accounts, key=lambda a: [int(p) for p in a.code.split(".")])

    def get(self, code: str, pattern: str | None = None) -> Account | None:
        acc = self.by_code.get(code)
        if acc is None or (pattern and not re.search(pattern, acc.text)):
            return None
        return acc

    def children(self, code: str) -> list[Account]:
        prefix, depth = code + ".", code.count(".") + 1
        return [a for a in self.accounts if a.code.startswith(prefix) and a.depth == depth]

    def level1(self, root: str, pattern: str, last: bool = False) -> Account | None:
        matches = [
            a
            for a in self.accounts
            if a.depth == 1 and a.code.startswith(root + ".") and re.search(pattern, a.text)
        ]
        if not matches:
            return None
        return matches[-1] if last else matches[0]


@dataclass
class Figures:
    template: str
    revenue: Decimal | None = None
    ebit: Decimal | None = None
    net_income: Decimal | None = None
    net_income_controlling: Decimal | None = None
    d_and_a: Decimal | None = None
    dividends_paid: Decimal | None = None
    total_assets: Decimal | None = None
    current_assets: Decimal | None = None
    current_liabilities: Decimal | None = None
    cash: Decimal | None = None
    gross_debt: Decimal | None = None
    leases: Decimal | None = None
    equity: Decimal | None = None
    equity_controlling: Decimal | None = None
    eps: Decimal | None = None  # basic EPS of the first class, as reported (used to infer share scale)
    missing: list[str] = field(default_factory=list)


_CONTROLLING = r"controlador"
_MINORITY = r"nao controlador"
_DEBT = r"emprestimos e financiamentos"
_LEASE = r"arrendamento"
_DA = r"deprecia|exaust|amortizac"
_DA_EXCLUDE = r"transac|emprestimo|financiamento|debenture|agio|captac|custo de emiss"
_DIVIDENDS = r"dividend|juros sobre (o )?capital|\bjcp\b"
_DIVIDENDS_EXCLUDE = r"nao controlador|recebid"


def detect_template(bpa: Statement) -> str:
    return "INDUSTRIAL" if bpa.get("1.01", r"^ativo circulante") else "BANK"


def _sum(accounts: list[Account]) -> Decimal | None:
    return sum((a.value for a in accounts), ZERO) if accounts else None


def extract(bpa: Statement, bpp: Statement, dre: Statement, dfc: Statement | None) -> Figures:
    fig = Figures(template=detect_template(bpa))

    # --- income statement ---
    revenue = dre.get("3.01")
    fig.revenue = revenue.value if revenue else None
    ebit = dre.level1("3", r"antes do resultado financeiro")
    fig.ebit = ebit.value if ebit else None
    net = dre.level1("3", r"^lucro.*(do|no) periodo", last=True)
    if net is None:
        fig.missing.append("lucro líquido")
    else:
        fig.net_income = net.value
        ctrl = [
            c
            for c in dre.children(net.code)
            if re.search(_CONTROLLING, c.text) and not re.search(_MINORITY, c.text)
        ]
        fig.net_income_controlling = ctrl[0].value if ctrl else net.value

    basic = dre.children("3.99")
    first_class = dre.children(basic[0].code) if basic else []
    eps = first_class[0].value if first_class else None
    # Some filings carry garbage here (e.g. -2.7e16); EPS is only a hint for the share-count scale
    fig.eps = eps if eps and abs(eps) < 100_000 else None

    # --- balance sheet ---
    total = bpa.get("1")
    fig.total_assets = total.value if total else None
    equity = bpp.level1("2", r"patrimonio liquido")
    if equity is None:
        fig.missing.append("patrimônio líquido")
    else:
        fig.equity = equity.value
        kids = bpp.children(equity.code)
        attributed = [k for k in kids if re.search(r"atribuido ao controlador", k.text)]
        minority = [k for k in kids if re.search(_MINORITY, k.text)]
        if attributed:
            fig.equity_controlling = attributed[0].value
        else:
            fig.equity_controlling = equity.value - (minority[0].value if minority else ZERO)

    if fig.template == "INDUSTRIAL":
        fig.current_assets = bpa.get("1.01").value
        liabilities = bpp.get("2.01", r"^passivo circulante")
        fig.current_liabilities = liabilities.value if liabilities else None
        cash = [a for a in bpa.children("1.01") if re.search(r"^caixa|^aplicacoes financeiras", a.text)]
        fig.cash = _sum(cash)
        debt_roots = [a for a in (bpp.get("2.01.04", _DEBT), bpp.get("2.02.01", _DEBT)) if a is not None]
        if debt_roots:
            leases = [c for root in debt_roots for c in bpp.children(root.code) if re.search(_LEASE, c.text)]
            fig.leases = _sum(leases) or ZERO
            fig.gross_debt = sum((r.value for r in debt_roots), ZERO) - fig.leases
        else:
            fig.missing.append("dívida bruta")

    # --- cash flow ---
    if dfc is None:
        fig.missing.append("fluxo de caixa")
        return fig
    generated = dfc.get("6.01.01")
    if generated is not None:
        da = [
            c
            for c in dfc.children("6.01.01")
            if re.search(_DA, c.text) and not re.search(_DA_EXCLUDE, c.text)
        ]
        fig.d_and_a = _sum(da)
    if fig.d_and_a is None and fig.template == "INDUSTRIAL":
        fig.missing.append("depreciação e amortização")
    fig.dividends_paid = dividends_paid(dfc)
    return fig


def dividends_paid(dfc: Statement) -> Decimal:
    """Dividends + JCP paid (financing activities). Use the parent-only (individual) statement when
    available: the consolidated one also includes what subsidiaries pay to their minority holders."""
    paid = [
        c
        for c in dfc.children("6.03")
        if re.search(_DIVIDENDS, c.text) and not re.search(_DIVIDENDS_EXCLUDE, c.text)
    ]
    return abs(_sum(paid)) if paid else ZERO
