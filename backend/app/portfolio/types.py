from enum import StrEnum


class AssetClass(StrEnum):
    STOCK = "STOCK"
    FII = "FII"
    ETF = "ETF"
    BDR = "BDR"


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    FRACTION_AUCTION = "FRACTION_AUCTION"
    BONUS = "BONUS"
    TICKER_CHANGE = "TICKER_CHANGE"
    DIVIDEND = "DIVIDEND"
    JCP = "JCP"
    INCOME = "INCOME"


class TransactionSource(StrEnum):
    MANUAL = "MANUAL"
    B3 = "B3"
    AUTO = "AUTO"


class ProventStatus(StrEnum):
    ANNOUNCED = "ANNOUNCED"
    PAID = "PAID"
    CONFIRMED = "CONFIRMED"


PROVENT_TYPES = frozenset({TransactionType.DIVIDEND, TransactionType.JCP, TransactionType.INCOME})
TRADE_TYPES = frozenset({TransactionType.BUY, TransactionType.SELL})
CORPORATE_EVENT_TYPES = frozenset(
    {
        TransactionType.SPLIT,
        TransactionType.REVERSE_SPLIT,
        TransactionType.BONUS,
        TransactionType.TICKER_CHANGE,
        TransactionType.FRACTION_AUCTION,
    }
)
