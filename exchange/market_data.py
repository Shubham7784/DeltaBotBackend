import logging
from exchange.client import DeltaClient
from core.config import config
import asyncio
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class MarketDataService:
    def __init__(self):
        self.client = DeltaClient()
        self.instruments = []
        self.btc_options = []
        self.btc_futures = []
        self.eth_futures = []
        self.eth_options = []
        self.btc_daily_straddle = []
        self.ohlc_candles = []
        self.ohlc_candles_cache = {
            "30m": [],
            "5m": []
        }
        self.last_ohlc_fetch = {
            "30m": None,
            "5m": None
        }

    async def initialize(self):
        try:
            products = await self.client.get_all_tickers()
            self.instruments = products.get("result", [])
            self.btc_futures = [i for i in self.instruments if i.get("symbol","") == "BTCUSD"]
            self.btc_options = [i for i in self.instruments if ("P-BTC-" in i.get("symbol","") or "C-BTC-" in i.get("symbol",""))]
            self.eth_futures = [i for i in self.instruments if i.get("symbol") == "ETHUSD"]
            self.eth_options = [i for i in self.instruments if ("P-ETH-" in i.get("symbol","") or "C-ETH-" in i.get("symbol",""))]
            self.btc_daily_straddle = [i for i in self.instruments if i.get("description","") == "BTC Daily Straddle"]
            historical_candles = await self.get_historical_ohlc_candles("BTCUSD","30m", force=True)
            self.ohlc_candles = historical_candles
        except Exception as e:
            logger.exception("Error initializing market data")

    async def fetch_option_chain(self, settlement_time: str = None):
        try:
            chain = await self.client.get_option_chain("BTC", settlement_time)
            return chain
        except Exception as e:
            logger.exception("Error fetching option chain")
            return []

    def get_nearest_expiry(self):
        expiries = self.get_option_expiries()
        return expiries[0] if expiries else None

    def get_option_expiries(self):
        expiries = []
        for option in self.btc_options:
            try:
                expiries.append(datetime.strptime(option.get("symbol").split("-")[-1], "%d%m%y"))
            except (AttributeError, ValueError):
                continue
        return sorted(set(expiries))

    def get_options_by_expiry(self, expiry: str):
        return [o for o in self.btc_options if o.get("symbol").endswith(datetime.strftime(expiry,"%d%m%y"))]

    async def get_live_price(self, symbol: str = "BTCUSD"):
        try:
            ticker = await self.client.get_ticker(symbol)
            # Delta V2 ticker usually has 'mark_price' or 'last_price'
            return float(ticker.get("result").get("mark_price") or ticker.get("result").get("last_price") or 0)
        except Exception as e:
            logger.exception("Error fetching live price for %s", symbol)
            return None
        
    async def get_all_tickers(self):
        try:
            tickers = await self.client.request("GET", "/v2/tickers")
            return tickers.get("result", [])
        except Exception as e:
            logger.exception("Error fetching all tickers")
            return []
        

    async def get_historical_ohlc_candles(self,symbol:str, resolution:str, force: bool = False):
        # Use cached data for recent requests to avoid repeated historical candle fetches.
        if resolution not in self.ohlc_candles_cache:
            self.ohlc_candles_cache[resolution] = []
            self.last_ohlc_fetch[resolution] = None

        if not force and self.last_ohlc_fetch.get(resolution):
            elapsed = (datetime.now() - self.last_ohlc_fetch[resolution]).total_seconds()
            cache_timeout = 300 if resolution == "30m" else 60
            if elapsed < cache_timeout and self.ohlc_candles_cache.get(resolution):
                self.ohlc_candles = self.ohlc_candles_cache[resolution]
                return self.ohlc_candles

        # Delta API V2: GET /v2/candles
        # EMA-200 on four-hour candles needs at least 800 hours of history.
        # Keep a small buffer so the indicator remains stable at the boundary.
        lookback_hours = {"1h": 260, "4h": 900}.get(resolution, 120)
        params = {
            'symbol': symbol,
            'resolution': resolution,
            'start': int((datetime.now() - timedelta(hours=lookback_hours)).timestamp()),
            'end': int(datetime.now().timestamp())
        }
        ohcl = await self.client.request("GET", "/v2/history/candles", params=params)
        # Delta's REST endpoint returns newest-first candles.  Every consumer
        # expects chronological order for EMA, RSI, ATR and structure checks.
        self.ohlc_candles_cache[resolution] = sorted(
            ohcl.get("result", []), key=lambda candle: float(candle.get("time", 0))
        )
        self.last_ohlc_fetch[resolution] = datetime.now()
        self.ohlc_candles = self.ohlc_candles_cache[resolution]
        return self.ohlc_candles
market_data = MarketDataService()
