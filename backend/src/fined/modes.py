from enum import Enum


class LearningMode(str, Enum):
    STOCKS = "stocks"
    MUTUAL_FUNDS = "mutual_funds"
    ETFS = "etfs"
    GOLD = "gold"
    FNO = "fno"
    IPOS = "ipos"
    BONDS = "bonds"
    GENERAL = "general"


def parse_learning_mode(value: object) -> LearningMode:
    if not isinstance(value, str):
        return LearningMode.GENERAL
    try:
        return LearningMode(value)
    except ValueError:
        return LearningMode.GENERAL
