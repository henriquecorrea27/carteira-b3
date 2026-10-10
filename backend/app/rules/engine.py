"""Rule engine (CLAUDE.md §5). Pure: fundamentals in, explained decision out. Every number comes from
rules_config/stocks.yaml — the engine has no thresholds of its own."""

import calendar
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.config import RULES_CONFIG_DIR
from app.fundamentals.indicators import FundamentalsResult, Indicator


class Decision(StrEnum):
    BUY = "BUY"  # COMPRAR
    WAIT = "WAIT"  # AGUARDAR
    AVOID = "AVOID"  # EVITAR


class Status(StrEnum):
    GOOD = "GOOD"  # ✅
    MID = "MID"  # ⚠️
    BAD = "BAD"  # ❌
    NA = "NA"  # ➖


IMPLAUSIBLE = "valor implausível — conferir nº de ações"


@dataclass
class IndicatorScore:
    key: str
    label: str
    group: str  # QUALITY | PRICE
    value: Decimal | None
    unit: str
    range_label: str
    weight: float
    points: float | None
    status: Status
    note: str | None


@dataclass
class EliminatoryCheck:
    id: str
    label: str
    rule: str
    value_label: str | None
    passed: bool | None  # None = no data (does not eliminate)


@dataclass
class Analysis:
    decision: Decision
    score_final: float | None
    score_quality: float | None
    score_price: float | None  # fundamental price blended with the technical score (F8), after the caps
    quality_inconclusive: bool
    price_inconclusive: bool
    eliminatory: list[EliminatoryCheck]
    indicators: list[IndicatorScore]
    main_reason: str | None
    special_sector: str | None
    warnings: list[str] = field(default_factory=list)
    rules_version: int = 1
    score_price_fundamental: float | None = None
    score_technical: float | None = None
    technical_weight: float = 0.0  # weight actually applied (0 while the technical analysis does not exist)
    stale: bool = False


# --- config ---------------------------------------------------------------------------------------


@lru_cache
def load_rules(path: Path | None = None) -> dict[str, Any]:
    return yaml.safe_load((path or RULES_CONFIG_DIR / "stocks.yaml").read_text(encoding="utf-8"))


def _plain(text: str | None) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return " ".join(text.lower().split())


def classify_sector(
    sector_cvm: str | None, template: str | None, ticker: str | None = None, cfg: dict | None = None
) -> str | None:
    """FINANCIAL | UTILITY | CYCLICAL | None (general), from the CVM SETOR_ATIV (holdings "Emp. Adm. Part. -
    <setor>" follow their main sector). Manual overrides by ticker root win; first match in `order` wins."""
    rules = (cfg or load_rules())["sector_classification"]
    override = (rules.get("overrides") or {}).get((ticker or "")[:4].upper())
    if override:
        return None if override == "GENERAL" else override
    text = _plain(sector_cvm)
    for name in rules["order"]:
        rule = rules[name]
        if rule.get("template") and template == rule["template"]:
            return name
        if re.search(rule["pattern"], text):
            return name
    return None


# --- formatting (pt-BR labels shown in the UI and in Discord) -------------------------------------


def _num(value: float, decimals: int) -> str:
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def fmt(value: Decimal | float | None, unit: str) -> str:
    if value is None:
        return "—"
    v = float(value)
    if unit == "pct":
        return f"{_num(v * 100, 1)}%"
    if unit == "brl":
        if abs(v) >= 1e9:
            return f"R$ {_num(v / 1e9, 1)} bi"
        if abs(v) >= 1e6:
            return f"R$ {_num(v / 1e6, 1)} mi"
        return f"R$ {_num(v, 2)}"
    if unit == "count":
        return _num(v, 0)
    return _num(v, 2)


def _short(value: float, unit: str) -> str:
    """Compact range label: 8%, 12,5%, 25, 0,8."""
    v = round(value * 100, 6) if unit == "pct" else round(value, 6)
    text = _num(v, 0 if float(v).is_integer() else 1)
    return f"{text}%" if unit == "pct" else text


def _range_label(rule: dict, unit: str) -> str:
    if "band" in rule:
        # Zero outside band[0]–band[3] (documented in stocks.yaml); the table shows the great range
        _, good_low, good_high, _ = rule["band"]
        return f"ótimo {_short(good_low, unit)}–{_short(good_high, unit)}"
    return f"{_short(rule['bad'], unit)} → {_short(rule['good'], unit)}"


# --- scoring --------------------------------------------------------------------------------------


def score_fraction(rule: dict, value: float) -> float:
    """Fraction of the weight earned, in [0, 1]."""
    if "band" in rule:
        zero_low, good_low, good_high, zero_high = rule["band"]
        if value <= zero_low or value >= zero_high:
            return 0.0
        if good_low <= value <= good_high:
            return 1.0
        if value < good_low:
            return (value - zero_low) / (good_low - zero_low)
        return (zero_high - value) / (zero_high - good_high)
    bad, good = rule["bad"], rule["good"]
    return min(1.0, max(0.0, (value - bad) / (good - bad)))


def _status(fraction: float | None, cfg: dict) -> Status:
    if fraction is None:
        return Status.NA
    if fraction >= cfg["status"]["good"]:
        return Status.GOOD
    if fraction >= cfg["status"]["mid"]:
        return Status.MID
    return Status.BAD


def _implausible(key: str, value: float, cfg: dict) -> bool:
    """Values that only a wrong share count (scale) or a broken filing produce."""
    p = cfg.get("plausibility") or {}
    if key in ("pe", "pe_norm") and "pe_min" in p:
        return 0 < value < p["pe_min"]
    if key == "pb" and "pb_min" in p:
        return 0 < value < p["pb_min"]
    if key == "dy_5y" and "dy_5y_max" in p:
        return value > p["dy_5y_max"]
    if key in ("ev_ebit", "ev_ebit_norm") and "ev_ebit_min" in p:
        return 0 < value < p["ev_ebit_min"]
    return False


def _score_group(
    group: str, rules: list[dict], fundamentals: FundamentalsResult, cfg: dict, warnings: list[str]
) -> tuple[list[IndicatorScore], float | None, bool]:
    scored: list[IndicatorScore] = []
    earned = evaluated = missing = 0.0
    for rule in rules:
        indicator = fundamentals.indicators.get(rule["key"])
        if indicator is None:
            continue  # indicator not implemented: the rule is skipped and the weights renormalize
        template = rule.get("applies_to_template")
        if template and fundamentals.template != template:
            continue
        weight = float(rule["weight"])
        note = indicator.note
        if indicator.value is not None and _implausible(rule["key"], float(indicator.value), cfg):
            fraction, note = None, IMPLAUSIBLE
            if IMPLAUSIBLE not in warnings:
                warnings.append(IMPLAUSIBLE)
        elif indicator.value is not None:
            fraction = score_fraction(rule, float(indicator.value))
        elif indicator.invalid and rule.get("if_invalid") == "zero":
            fraction = 0.0  # e.g. P/L with a loss: worst score, not "no data"
        else:
            fraction = None
        points = None if fraction is None else round(fraction * weight, 2)
        if points is None:
            missing += weight
        else:
            earned += points
            evaluated += weight
        scored.append(
            IndicatorScore(
                key=rule["key"],
                label=rule["label"],
                group=group,
                value=indicator.value,
                unit=indicator.unit,
                range_label=_range_label(rule, indicator.unit),
                weight=weight,
                points=points,
                status=_status(fraction, cfg),
                note=note,
            )
        )
    total = evaluated + missing
    inconclusive = total > 0 and missing / total > cfg["decision"]["inconclusive_na_weight"]
    score = round(earned / evaluated * 100, 1) if evaluated else None
    return scored, score, inconclusive or score is None


def _rules_for(group: str, cfg: dict, override: dict) -> list[dict]:
    """Sector rules: a list of keys filters the general rules; a list of rule dicts replaces them."""
    rules = override.get(group)
    if rules is None:
        return cfg[group]
    if all(isinstance(r, str) for r in rules):
        return [r for r in cfg[group] if r["key"] in rules]
    return rules


def _debt_check(fundamentals: FundamentalsResult, rule: dict) -> tuple[float, Indicator | None]:
    sector = fundamentals.special_sector
    ttm = fundamentals.indicators.get("net_debt_ebitda")
    if sector == "CYCLICAL" and "max_cyclical" in rule:
        # Cyclicals: net debt over the 5-year average EBITDA (a peak or trough year misleads); fallback TTM
        norm = fundamentals.indicators.get("net_debt_ebitda_norm")
        usable = norm is not None and (norm.value is not None or norm.invalid)
        return rule["max_cyclical"], norm if usable else ttm
    if sector == "UTILITY":
        return rule["max_utility"], ttm
    return rule["max"], ttm


def _eliminatory(fundamentals: FundamentalsResult, cfg: dict, enabled: list[str]) -> list[EliminatoryCheck]:
    rules = cfg["eliminatory"]
    checks: list[EliminatoryCheck] = []
    if "E1" in enabled:
        r = rules["E1"]
        years, positive = fundamentals.years_available, fundamentals.profitable_years
        if years >= r["window_years"]:
            passed: bool | None = positive >= r["min_profitable_years"]
        elif years >= 3:
            # Fewer DFPs than the window: allow the same number of losses
            passed = positive >= years - (r["window_years"] - r["min_profitable_years"])
        else:
            passed = None
        rule = f"≥ {r['min_profitable_years']} de {r['window_years']} anos"
        checks.append(EliminatoryCheck("E1", r["label"], rule, f"{positive} de {years} anos", passed))
    if "E2" in enabled:
        bvps = fundamentals.value("bvps")
        checks.append(EliminatoryCheck("E2", rules["E2"]["label"], "> 0",
                                       fmt(bvps, "brl") + " por ação" if bvps is not None else None,
                                       None if bvps is None else bvps > 0))  # fmt: skip
    if "E3" in enabled:
        r = rules["E3"]
        limit, indicator = _debt_check(fundamentals, r)
        if indicator is not None and indicator.value is not None:
            passed, label = float(indicator.value) <= limit, fmt(indicator.value, "x")
            if indicator.key == "net_debt_ebitda_norm":
                label += " (EBITDA médio 5a)"
        elif indicator is not None and indicator.invalid:
            passed, label = False, indicator.note or "EBITDA negativo"
        else:
            passed, label = None, None
        checks.append(EliminatoryCheck("E3", r["label"], f"≤ {_num(limit, 1)}", label, passed))
    if "E4" in enabled:
        r = rules["E4"]
        liquidity = fundamentals.value("daily_liquidity")
        label = fmt(liquidity, "brl") if liquidity is not None else None
        passed = None if liquidity is None else float(liquidity) >= r["min_brl"]
        checks.append(EliminatoryCheck("E4", r["label"], f"≥ {fmt(r['min_brl'], 'brl')}", label, passed))
    if "E5" in enabled and "E5" in rules:
        r = rules["E5"]
        blocked = {_plain(s) for s in r.get("blocked_status") or []}
        status = fundamentals.issuer_status
        if (fundamentals.issuer or "") in (r.get("manual") or []):
            passed, label = False, "em recuperação judicial"
        elif status:
            passed, label = _plain(status) not in blocked, status.capitalize()
        else:
            passed, label = None, None
        checks.append(EliminatoryCheck("E5", r["label"], "situação normal", label, passed))
    return checks


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


def _stale(fundamentals: FundamentalsResult, cfg: dict) -> str | None:
    """Warning when the statements are too old to judge the company today (scores become inconclusive):
    balance older than `max_balance_age_months`, or no DFP of the last closed year after the deadline."""
    rule, today = cfg.get("staleness"), fundamentals.as_of
    if not rule or today is None:
        return None
    latest = fundamentals.last_itr or fundamentals.last_dfp
    if latest is None:
        return None
    if today > _add_months(latest, rule["max_balance_age_months"]):
        return f"dados contábeis defasados: último balanço de {latest:%d/%m/%Y}"
    deadline = date(today.year, *rule.get("dfp_deadline", [5, 15]))
    last_dfp_year = fundamentals.last_dfp.year if fundamentals.last_dfp else 0
    if today >= deadline and last_dfp_year < today.year - 1:
        return f"dados contábeis defasados: sem DFP de {today.year - 1}"
    return None


def _main_reason(
    decision: Decision, checks: list[EliminatoryCheck], scored: list[IndicatorScore]
) -> str | None:
    failed = [c for c in checks if c.passed is False]
    if failed:
        c = failed[0]
        return f"{c.label}: {c.value_label or 'sem dados'} (exige {c.rule})"
    with_points = [s for s in scored if s.points is not None and s.weight > 0]
    if not with_points:
        return None
    if decision == Decision.BUY:
        best = max(with_points, key=lambda s: (s.points, -s.weight))
        return f"{best.label} {fmt(best.value, best.unit)} a favor (faixa {best.range_label})"
    worst = max(with_points, key=lambda s: (s.weight - s.points, s.weight))
    value = fmt(worst.value, worst.unit) if worst.value is not None else (worst.note or "sem valor")
    return f"{worst.label} {value} contra (faixa {worst.range_label})"


def evaluate(
    fundamentals: FundamentalsResult, cfg: dict | None = None, technical: float | None = None
) -> Analysis:
    """`technical` is the chart-analysis score 0–100 (F8); it only counts when enabled in stocks.yaml."""
    cfg = cfg or load_rules()
    sector = fundamentals.special_sector
    override = (cfg.get("sectors") or {}).get(sector) or {}
    enabled = override.get("eliminatory") or list(cfg["eliminatory"])
    warnings: list[str] = [override["warning"]] if override.get("warning") else []

    quality, q_score, q_inconclusive = _score_group(
        "QUALITY", _rules_for("quality", cfg, override), fundamentals, cfg, warnings
    )
    price, p_fundamental, p_inconclusive = _score_group(
        "PRICE", _rules_for("price", cfg, override), fundamentals, cfg, warnings
    )
    checks = _eliminatory(fundamentals, cfg, enabled)
    d = cfg["decision"]

    stale = _stale(fundamentals, cfg)
    if stale:
        q_inconclusive = p_inconclusive = True
        warnings.append(stale)

    # Technical component inside the price score: price = (1 − w) × fundamental + w × technical
    tech_cfg = cfg.get("technical") or {}
    w = float(tech_cfg.get("weight") or 0) if tech_cfg.get("enabled") else 0.0
    applied = w if technical is not None and p_fundamental is not None else 0.0
    p_score = p_fundamental
    if applied:
        p_score = round((1 - applied) * p_fundamental + applied * technical, 1)

    eps = fundamentals.indicators.get("eps")
    cap = d.get("loss_price_cap")
    loss = eps is not None and eps.value is not None and eps.value <= 0
    if p_score is not None and cap is not None and loss and p_score > cap:
        p_score = float(cap)
        warnings.append(f"prejuízo nos últimos 12 meses: nota de preço limitada a {cap}")

    vetoed = any(c.passed is False for c in checks)
    if vetoed:
        decision = Decision.AVOID
    elif q_inconclusive or p_inconclusive:
        decision = Decision.WAIT
    elif q_score >= d["quality_buy_min"]:
        decision = Decision.BUY if p_score >= d["price_buy_min"] else Decision.WAIT
    elif q_score >= d["quality_watch_min"]:
        decision = Decision.WAIT
    else:
        decision = Decision.AVOID

    final = None
    if q_score is not None and p_score is not None:
        fw = d["final_weights"]
        final = round(fw["quality"] * q_score + fw["price"] * p_score, 1)
        if vetoed and d.get("veto_score_cap") is not None:
            final = min(final, float(d["veto_score_cap"]))
    if (q_inconclusive or p_inconclusive) and not stale:
        warnings.append("nota inconclusiva: mais de 30% do peso sem dados")
    return Analysis(
        decision=decision,
        score_final=final,
        score_quality=q_score,
        score_price=p_score,
        quality_inconclusive=q_inconclusive,
        price_inconclusive=p_inconclusive,
        eliminatory=checks,
        indicators=quality + price,
        main_reason=_main_reason(decision, checks, quality + price),
        special_sector=sector,
        warnings=warnings + fundamentals.notes,
        rules_version=cfg.get("version", 1),
        score_price_fundamental=p_fundamental,
        score_technical=technical if applied else None,
        technical_weight=applied,
        stale=stale is not None,
    )
