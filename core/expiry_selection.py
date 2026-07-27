"""Configurable option expiry selection shared by adaptive strategies."""
from datetime import datetime
from core.config import config


class ExpirySelectionEngine:
    def select(self, available_expiries, strategy_family: str):
        expiries = sorted(expiry for expiry in available_expiries if expiry >= datetime.now())
        if not expiries:
            return None
        if strategy_family == "premium_selling":
            target = config.INTRADAY_EXPIRY_DAYS
        elif strategy_family == "butterfly":
            target = config.BUTTERFLY_EXPIRY_DAYS
        elif strategy_family == "long_volatility":
            eligible = [e for e in expiries if config.LONG_VOL_MIN_EXPIRY_DAYS <= (e - datetime.now()).total_seconds() / 86400 <= config.LONG_VOL_MAX_EXPIRY_DAYS]
            return eligible[0] if eligible else expiries[0]
        else:
            return expiries[0]
        return min(expiries, key=lambda e: abs((e - datetime.now()).total_seconds() / 86400 - target))


expiry_selector = ExpirySelectionEngine()
