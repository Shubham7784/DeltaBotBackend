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
        expiries = sorted(list(set([datetime.strptime(o.get("symbol").split("-")[-1],"%d%m%y") for o in self.btc_options if o.get("symbol")])))
        return expiries[0] if expiries else None

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
        params = {
            'symbol': symbol,
            'resolution': resolution,
            'start': int((datetime.now() - timedelta(hours=20)).timestamp()), # Last 40 candles for 30m resolution
            'end': int((datetime.now() - timedelta(minutes=30)).timestamp())
        }
        ohcl = await self.client.request("GET", "/v2/history/candles", params=params)
        self.ohlc_candles_cache[resolution] = ohcl.get("result", [])
        self.last_ohlc_fetch[resolution] = datetime.now()
        self.ohlc_candles = self.ohlc_candles_cache[resolution]
        return self.ohlc_candles
market_data = MarketDataService()
