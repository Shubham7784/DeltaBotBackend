from exchange.client import DeltaClient
from core.config import config
import asyncio
import time
import datetime

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

    async def initialize(self):
        try:
            products = await self.client.get_all_tickers()
            self.instruments = products.get("result", [])
            self.btc_futures = [i for i in self.instruments if i.get("symbol","") == "BTCUSD"]
            self.btc_options = [i for i in self.instruments if ("P-BTC-" in i.get("symbol","") or "C-BTC-" in i.get("symbol",""))]
            self.eth_futures = [i for i in self.instruments if i.get("symbol","") == "ETHUSD"]
            self.eth_options = [i for i in self.instruments if ("P-ETH-" in i.get("symbol","") or "C-ETH-" in i.get("symbol",""))]
            self.btc_daily_straddle = [i for i in self.instruments if i.get("description","") == "BTC Daily Straddle"]
            historical_candles = await self.get_historical_ohlc_candles("BTCUSD","1h")
            self.ohlc_candles = historical_candles
        except Exception as e:
            print(f"Error initializing market data: {e}")

    async def fetch_option_chain(self, settlement_time: str = None):
        try:
            chain = await self.client.get_option_chain("BTC", settlement_time)
            return chain
        except Exception as e:
            print(f"Error fetching option chain: {e}")
            return []

    def get_nearest_expiry(self):
        expiries = sorted(list(set([datetime.datetime.strptime(o.get("symbol").split("-")[-1],"%d%m%y") for o in self.btc_options if o.get("symbol")])))
        return expiries[0] if expiries else None

    def get_options_by_expiry(self, expiry: str):
        return [o for o in self.btc_options if o.get("symbol").endswith(datetime.datetime.strftime(expiry,"%d%m%y"))]

    async def get_live_price(self, symbol: str = "BTCUSD"):
        try:
            ticker = await self.client.get_ticker(symbol)
            # Delta V2 ticker usually has 'mark_price' or 'last_price'
            return float(ticker.get("result").get("mark_price") or ticker.get("result").get("last_price") or 0)
        except Exception as e:
            print(f"Error fetching live price for {symbol}: {e}")
            return None
        
    async def get_all_tickers(self):
        try:
            tickers = await self.client.request("GET", "/v2/tickers")
            return tickers.get("result", [])
        except Exception as e:
            print(f"Error fetching all tickers: {e}")
            return []
        

    async def get_historical_ohlc_candles(self,symbol:str, resolution:str):
        # Delta API V2: GET /v2/candles
        params = {
            'symbol': symbol,
            'resolution': resolution,
            'start': int(time.time()) - 40*1*60*60, # Last 40 candles for 1h resolution
            'end': int(time.time())
        }
        ohcl = await self.client.request("GET", "/v2/history/candles", params=params)
        self.ohlc_candles = ohcl.get("result", [])
        return self.ohlc_candles
market_data = MarketDataService()
