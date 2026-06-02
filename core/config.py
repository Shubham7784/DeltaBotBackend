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
    
    # Telegram bot configuration
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

config = Config()
