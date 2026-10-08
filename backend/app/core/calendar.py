"""B3 trading calendar: weekends, national holidays (fixed and Easter-based) and the 24/12 and 31/12
closures. São Paulo city holidays are not listed because B3 trades on them."""

from datetime import date, timedelta
from functools import lru_cache


def _easter(year: int) -> date:
    # Anonymous Gregorian algorithm
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache
def b3_holidays(year: int) -> frozenset[date]:
    easter = _easter(year)
    fixed = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 24), (12, 25), (12, 31)]
    days = {date(year, m, d) for m, d in fixed}
    if year >= 2024:
        days.add(date(year, 11, 20))  # Consciência Negra, national holiday since 2024
    days |= {
        easter - timedelta(days=48),  # Carnival Monday
        easter - timedelta(days=47),  # Carnival Tuesday
        easter - timedelta(days=2),  # Good Friday
        easter + timedelta(days=60),  # Corpus Christi
    }
    return frozenset(days)


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in b3_holidays(day.year)


def next_business_day(day: date) -> date:
    nxt = day + timedelta(days=1)
    while not is_business_day(nxt):
        nxt += timedelta(days=1)
    return nxt
