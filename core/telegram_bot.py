import logging
import asyncio
from typing import Optional
from telegram import Bot
from telegram.error import TelegramError
from core.config import config

logger = logging.getLogger(__name__)


class TelegramAlertBot:
    def __init__(self):
        self.bot: Optional[Bot] = None
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.token = config.TELEGRAM_BOT_TOKEN
        self.enabled = bool(self.token and self.chat_id)

    async def initialize(self):
        """Initialize the Telegram bot if credentials are configured."""
        if not self.enabled:
            logger.debug("Telegram bot not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
            return

        try:
            self.bot = Bot(token=self.token)
            await self.bot.get_me()
            logger.info("Telegram bot initialized successfully")
        except TelegramError as e:
            logger.error("Failed to initialize Telegram bot: %s", e)
            self.bot = None
            self.enabled = False

    async def send_message(self, message: str) -> bool:
        """Send a message to the configured Telegram chat."""
        if not self.enabled or not self.bot:
            return False

        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode="HTML")
            return True
        except TelegramError as e:
            logger.warning("Failed to send Telegram message: %s", e)
            return False

    async def send_position_opened(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
        leverage: float,
        strategy: str,
    ):
        """Send alert when a position is opened."""
        message = (
            f"<b>📈 Position Opened</b>\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Side:</b> {side}\n"
            f"<b>Size:</b> {size}\n"
            f"<b>Entry Price:</b> {price}\n"
            f"<b>Leverage:</b> {leverage}x\n"
            f"<b>Strategy:</b> {strategy}"
        )
        await self.send_message(message)

    async def send_position_closed(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        close_price: float,
        pnl: float,
        strategy: str,
    ):
        """Send alert when a position is closed."""
        pnl_symbol = "📈" if pnl >= 0 else "📉"
        pnl_color = "green" if pnl >= 0 else "red"
        
        message = (
            f"<b>{pnl_symbol} Position Closed</b>\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Side:</b> {side}\n"
            f"<b>Size:</b> {size}\n"
            f"<b>Entry Price:</b> {entry_price}\n"
            f"<b>Close Price:</b> {close_price}\n"
            f"<b>PnL:</b> <code>{pnl:.2f}</code> ({pnl_color})\n"
            f"<b>Strategy:</b> {strategy}"
        )
        await self.send_message(message)

    async def send_liquidation_alert(
        self,
        symbol: str,
        side: str,
        leverage: float,
        entry_price: float,
        current_price: float,
        liquidation_price: float,
        pnl: float,
        strategy: str = "",
    ):
        """Send alert when a position is at or beyond its leverage-based liquidation threshold."""
        message = (
            f"<b>🚨 Liquidation Alert</b>\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Side:</b> {side}\n"
            f"<b>Leverage:</b> {leverage}x\n"
            f"<b>Entry Price:</b> {entry_price:.2f}\n"
            f"<b>Current Price:</b> {current_price:.2f}\n"
            f"<b>Liquidation Price:</b> {liquidation_price:.2f}\n"
            f"<b>PnL:</b> {pnl:.2f}"
        )
        if strategy:
            message += f"\n<b>Strategy:</b> {strategy}"
        await self.send_message(message)

    async def send_error_alert(self, error_msg: str, context: str = ""):
        """Send alert for critical errors."""
        message = (
            f"<b>⚠️ Error Alert</b>\n"
            f"<b>Context:</b> {context}\n"
            f"<b>Error:</b> <code>{error_msg}</code>"
        )
        await self.send_message(message)

    async def send_strategy_alert(self, strategy_name: str, event: str, details: str = ""):
        """Send alert for strategy events."""
        message = (
            f"<b>🤖 {strategy_name}</b>\n"
            f"<b>Event:</b> {event}\n"
        )
        if details:
            message += f"<b>Details:</b> {details}"
        await self.send_message(message)


# Global telegram bot instance
telegram_bot = TelegramAlertBot()
