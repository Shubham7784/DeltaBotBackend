import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    ENV = os.getenv("NODE_ENV", "development")
    PORT = int(os.getenv("PORT", 3000))
    IS_PAPER_TRADING = os.getenv("IS_PAPER_TRADING", "true").lower() == "true"
    
    DELTA_API_KEY = os.getenv("DELTA_EXCHANGE_API_KEY", "")
    DELTA_API_SECRET = os.getenv("DELTA_EXCHANGE_API_SECRET", "")
    
    BASE_URL = "https://cdn-ind.testnet.deltaex.org"
    DATABASE_URL = os.getenv("DATABASE_URL", "")

    FUTURE_LEVERAGE = int(os.getenv("FUTURE_LEVERAGE", 100))
    OPTION_LEVERAGE = int(os.getenv("OPTION_LEVERAGE", 100))
    LOT_SIZE = float(os.getenv("LOT_SIZE", 0.1))

    POOR_MANS_LOT_SIZE = float(os.getenv("POOR_MANS_LOT_SIZE", 0.05))

    # Adaptive options engine. Defaults are intentionally conservative.
    ADAPTIVE_TRADING_ENABLED = os.getenv("ADAPTIVE_TRADING_ENABLED", "false").lower() == "true"
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
    
    # Telegram bot configuration
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # Minimum log level to broadcast over websocket (DEBUG/INFO/WARNING/ERROR/CRITICAL)
    BROADCAST_MIN_LOG_LEVEL = os.getenv("BROADCAST_MIN_LOG_LEVEL", "WARNING")

config = Config()
