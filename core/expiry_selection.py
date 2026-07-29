"""Configurable option expiry selection shared by adaptive strategies."""
from core.config import config
from core.expiry import is_expiry_close_due
from datetime import datetime


class ExpirySelectionEngine:
    def select(self, available_expiries, strategy_family: str):
        # Do not open a new position in an expiry after its 5:20 PM IST
        # forced-close cutoff.  This also prevents immediate re-entry after
        # the expiry-close job has flattened a position.  Comparing the
        # parsed expiry timestamp to ``datetime.now()`` would incorrectly
        # exclude today's expiry from midnight onward.
        expiries = sorted(
            expiry for expiry in available_expiries
            if not is_expiry_close_due(expiry)
        )
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
