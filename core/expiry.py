"""Shared option-expiry timing helpers.

Delta option symbols encode their expiry as ``DDMMYY``.  Trading operations
use India Standard Time because the configured expiry-management cutoff is
5:20 PM IST.
"""
from datetime import datetime, time, timedelta, timezone
from typing import Optional, Union


# India does not observe daylight-saving time.  A fixed offset avoids requiring
# the optional ``tzdata`` package on Windows deployments.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")
EXPIRY_CLOSE_TIME = time(17, 20)


def option_expiry_from_symbol(symbol: object) -> Optional[datetime]:
    """Return the expiry embedded in an option symbol, if it has one."""
    if not isinstance(symbol, str):
        return None
    try:
        return datetime.strptime(symbol.rsplit("-", 1)[-1], "%d%m%y")
    except ValueError:
        return None


def expiry_close_at(expiry: Union[datetime, object]) -> datetime:
    """Return the 5:20 PM IST close timestamp for an expiry date."""
    expiry_date = expiry.date() if isinstance(expiry, datetime) else expiry
    return datetime.combine(expiry_date, EXPIRY_CLOSE_TIME, tzinfo=IST)


def is_expiry_close_due(expiry: Union[datetime, object], now: Optional[datetime] = None) -> bool:
    """Whether an option has reached its expiry-day forced-close cutoff."""
    current = now or datetime.now(IST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=IST)
    else:
        current = current.astimezone(IST)
    return current >= expiry_close_at(expiry)
