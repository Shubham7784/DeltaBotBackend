import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    ENV = os.getenv("NODE_ENV", "development")
    PORT = int(os.getenv("PORT", 3000))
    IS_PAPER_TRADING = os.getenv("IS_PAPER_TRADING", "true").lower() == "true"
    ALLOW_REAL_ORDER_EXECUTION = os.getenv("ALLOW_REAL_ORDER_EXECUTION", "false").lower() == "true"
    
    DELTA_API_KEY = os.getenv("DELTA_EXCHANGE_API_KEY", "")
    DELTA_API_SECRET = os.getenv("DELTA_EXCHANGE_API_SECRET", "")
    
    BASE_URL = os.getenv("DELTA_BASE_URL", os.getenv("DELTA_API_BASE_URL", "https://api.india.delta.exchange"))
    DATABASE_URL = os.getenv("DATABASE_URL", "")

    FUTURE_LEVERAGE = int(os.getenv("FUTURE_LEVERAGE", 100))
    FUTURES_SYMBOL = os.getenv("FUTURES_SYMBOL", "BTCUSD")
    POSITION_CACHE_TTL_SECONDS = int(os.getenv("POSITION_CACHE_TTL_SECONDS", "3600"))
    OPTION_LEVERAGE = int(os.getenv("OPTION_LEVERAGE", 100))
    LOT_SIZE = float(os.getenv("LOT_SIZE", 0.05))
    PAPER_WALLET_BALANCE = float(os.getenv("PAPER_WALLET_BALANCE", "10000"))
    TIME_FRAME = os.getenv("TIME_FRAME", "1h")

    POOR_MANS_LOT_SIZE = float(os.getenv("POOR_MANS_LOT_SIZE", 0.05))

    # The adaptive selector runs automatically whenever the backend is up.
    # The disable endpoint remains available as an explicit emergency stop.
    ADAPTIVE_TRADING_ENABLED = True
    MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.02"))
    MAX_STRATEGY_LOSS_PCT = float(os.getenv("MAX_STRATEGY_LOSS_PCT", "0.01"))
    MAX_PORTFOLIO_EXPOSURE_PCT = float(os.getenv("MAX_PORTFOLIO_EXPOSURE_PCT", "0.50"))
    MAX_MARGIN_USAGE_PCT = float(os.getenv("MAX_MARGIN_USAGE_PCT", "0.80"))
    MAX_CONCURRENT_OPTIONS_POSITIONS = int(os.getenv("MAX_CONCURRENT_OPTIONS_POSITIONS", "1"))
    ADAPTIVE_RISK_PER_TRADE_PCT = float(os.getenv("ADAPTIVE_RISK_PER_TRADE_PCT", "0.005"))
    INTRADAY_EXPIRY_DAYS = int(os.getenv("INTRADAY_EXPIRY_DAYS", "0"))
    BUTTERFLY_EXPIRY_DAYS = int(os.getenv("BUTTERFLY_EXPIRY_DAYS", "1"))
    LONG_VOL_MIN_EXPIRY_DAYS = int(os.getenv("LONG_VOL_MIN_EXPIRY_DAYS", "1"))
    LONG_VOL_MAX_EXPIRY_DAYS = int(os.getenv("LONG_VOL_MAX_EXPIRY_DAYS", "3"))
    HIGH_VOL_ATR_PCT = float(os.getenv("HIGH_VOL_ATR_PCT", "1.5"))
    HIGH_VOL_IV_PCT = float(os.getenv("HIGH_VOL_IV_PCT", "75"))
    # BTC funding around +/-0.1% is normal and should not affect the regime.
    # Only unusually extreme funding can contribute, and it still requires an
    # ATR or IV confirmation in the analyzer.
    HIGH_FUNDING_RATE_PCT = float(os.getenv("HIGH_FUNDING_RATE_PCT", "0.25"))
    FUNDING_CONFIRM_ATR_PCT = float(os.getenv("FUNDING_CONFIRM_ATR_PCT", "0.8"))
    FUNDING_CONFIRM_IV_PCT = float(os.getenv("FUNDING_CONFIRM_IV_PCT", "60"))
    
    # Telegram bot configuration
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # Minimum log level to broadcast over websocket (DEBUG/INFO/WARNING/ERROR/CRITICAL)
    BROADCAST_MIN_LOG_LEVEL = os.getenv("BROADCAST_MIN_LOG_LEVEL", "WARNING")

config = Config()
