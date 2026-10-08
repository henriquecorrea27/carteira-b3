"""Rule engine (CLAUDE.md §5). Pure: fundamentals in, explained decision out. Every number comes from
rules_config/stocks.yaml — the engine has no thresholds of its own."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.config import RULES_CONFIG_DIR
from app.fundamentals.indicators import FundamentalsResult


class Decision(StrEnum):
    BUY = "BUY"  # COMPRAR
    WAIT = "WAIT"  # AGUARDAR
    AVOID = "AVOID"  # EVITAR


class Status(StrEnum):
    GOOD = "GOOD"  # ✅
    MID = "MID"  # ⚠️
    BAD = "BAD"  # ❌
    NA = "NA"  # ➖


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
    score_price: float | None
    quality_inconclusive: bool
    price_inconclusive: bool
    eliminatory: list[EliminatoryCheck]
    indicators: list[IndicatorScore]
    main_reason: str | None
    special_sector: str | None
    warnings: list[str] = field(default_factory=list)
    rules_version: int = 1


# --- config ---------------------------------------------------------------------------------------


@lru_cache
def load_rules(path: Path | None = None) -> dict[str, Any]:
    return yaml.safe_load((path or RULES_CONFIG_DIR / "stocks.yaml").read_text(encoding="utf-8"))


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


def _score_group(
    group: str, rules: list[dict], fundamentals: FundamentalsResult, cfg: dict
) -> tuple[list[IndicatorScore], float | None, bool]:
    scored: list[IndicatorScore] = []
    earned = evaluated = missing = 0.0
    for rule in rules:
        indicator = fundamentals.indicators[rule["key"]]
        weight = float(rule["weight"])
        fraction = None if indicator.value is None else score_fraction(rule, float(indicator.value))
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
                note=indicator.note,
            )
        )
    total = evaluated + missing
    inconclusive = total > 0 and missing / total > cfg["decision"]["inconclusive_na_weight"]
    score = round(earned / evaluated * 100, 1) if evaluated else None
    return scored, score, inconclusive or score is None


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
        limit = r["max_utility"] if fundamentals.special_sector == "UTILITY" else r["max"]
        indicator = fundamentals.indicators["net_debt_ebitda"]
        if indicator.value is not None:
            passed, label = float(indicator.value) <= limit, fmt(indicator.value, "x")
        elif indicator.note == "EBITDA negativo":
            passed, label = False, "EBITDA negativo"
        else:
            passed, label = None, None
        checks.append(EliminatoryCheck("E3", r["label"], f"≤ {_num(limit, 1)}", label, passed))
    if "E4" in enabled:
        r = rules["E4"]
        liquidity = fundamentals.value("daily_liquidity")
        label = fmt(liquidity, "brl") if liquidity is not None else None
        passed = None if liquidity is None else float(liquidity) >= r["min_brl"]
        checks.append(EliminatoryCheck("E4", r["label"], f"≥ {fmt(r['min_brl'], 'brl')}", label, passed))
    return checks


def _main_reason(
    decision: Decision, checks: list[EliminatoryCheck], scored: list[IndicatorScore]
) -> str | None:
    failed = [c for c in checks if c.passed is False]
    if failed:
        c = failed[0]
        return f"{c.label}: {c.value_label or 'sem dados'} (exige {c.rule})"
    with_points = [s for s in scored if s.points is not None]
    if not with_points:
        return None
    if decision == Decision.BUY:
        best = max(with_points, key=lambda s: (s.points, -s.weight))
        return f"{best.label} {fmt(best.value, best.unit)} a favor (faixa {best.range_label})"
    worst = max(with_points, key=lambda s: (s.weight - s.points, s.weight))
    return f"{worst.label} {fmt(worst.value, worst.unit)} contra (faixa {worst.range_label})"


def evaluate(fundamentals: FundamentalsResult, cfg: dict | None = None) -> Analysis:
    cfg = cfg or load_rules()
    sector = fundamentals.special_sector
    override = (cfg.get("sectors") or {}).get(sector) or {}
    quality_rules = cfg["quality"]
    price_rules = cfg["price"]
    enabled = ["E1", "E2", "E3", "E4"]
    if "quality" in override:
        quality_rules = [r for r in quality_rules if r["key"] in override["quality"]]
    if "price" in override:
        price_rules = [r for r in price_rules if r["key"] in override["price"]]
    if "eliminatory" in override:
        enabled = override["eliminatory"]

    quality, q_score, q_inconclusive = _score_group("QUALITY", quality_rules, fundamentals, cfg)
    price, p_score, p_inconclusive = _score_group("PRICE", price_rules, fundamentals, cfg)
    checks = _eliminatory(fundamentals, cfg, enabled)
    d = cfg["decision"]

    if any(c.passed is False for c in checks):
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
        w = d["final_weights"]
        final = round(w["quality"] * q_score + w["price"] * p_score, 1)
    warnings = [override["warning"]] if override.get("warning") else []
    if q_inconclusive or p_inconclusive:
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
    )
