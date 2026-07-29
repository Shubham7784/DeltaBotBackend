from datetime import datetime

from core.expiry import IST, is_expiry_close_due, option_expiry_from_symbol


def test_reads_expiry_from_delta_option_symbol():
    assert option_expiry_from_symbol("C-BTC-70000-300726") == datetime(2026, 7, 30)
    assert option_expiry_from_symbol("BTCUSD") is None


def test_expiry_cutoff_is_520_pm_ist():
    expiry = datetime(2026, 7, 30)
    assert not is_expiry_close_due(expiry, datetime(2026, 7, 30, 17, 19, tzinfo=IST))
    assert is_expiry_close_due(expiry, datetime(2026, 7, 30, 17, 20, tzinfo=IST))
