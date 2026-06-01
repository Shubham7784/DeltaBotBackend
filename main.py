import uvicorn
import os
import asyncio
import json
import random
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import requests
from core.config import config
from core.logging import configure_logging, log_manager
from paper_trading.engine import paper_engine
from risk.manager import risk_manager
from risk.hedge_manager import hedge_manager
from exchange.client import DeltaClient
from exchange.market_data import market_data
from strategies.ironfly import iron_fly
from strategies.directional import directional_strategy
from zoneinfo import ZoneInfo

configure_logging()

app = FastAPI()
delta_client = DeltaClient()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state to prevent duplicate triggering of scheduler in the same 7-9 AM hour window per calendar day
last_scheduler_run_date = None

@app.get("/api/health")
async def health():
    return {"status": "ok", "backend": "python/fastapi"}

@app.get("/api/wallet")
async def get_wallet():
    return await paper_engine.get_wallet()

@app.get("/api/positions")
async def get_positions():
    return await paper_engine.get_positions()

@app.get("/api/is-bot-running")
async def is_bot_running():
    active = await paper_engine.is_ironfly_active()
    print(f"Checking if bot is running: Iron Fly Active: {active}")
    return active

@app.get("/api/is-directional-enabled")
async def is_directional_enabled():
    active = await paper_engine.is_directional_active()
    print(f"Checking if directional strategy is enabled: {active}")
    return active

@app.get("/api/risk")
async def get_risk():
    return {
        "netDelta": await risk_manager.get_greeks().get("delta", 0.0),
        "threshold": 0.5,
        "isSafe": await risk_manager.check_safety()[0]
    }

@app.get("/api/options/chain")
async def get_options_chain(expiry: str = None):
    chain = await market_data.fetch_option_chain(expiry)
    return chain

@app.get("/api/trade-history")
async def get_trade_history():
    return paper_engine.get_trade_history()

@app.get("/api/scheduler")
async def get_scheduler_status():
    global last_scheduler_run_date
    now = datetime.now()
    current_hour = now.hour
    in_window = 7 <= current_hour < 9
    return {
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "current_hour": current_hour,
        "is_inside_window": in_window,
        "active_window": "07:00 AM - 09:00 AM",
        "last_run_date": last_scheduler_run_date,
        "status": "Active & checking"
    }

@app.post("/api/strategy1/run")
async def run_strategy1():
    success, msg = await iron_fly.execute(paper_engine.btc_price)
    if success:
        return {"status": "success", "message": msg}
    return {"status": "error", "message": msg}

@app.post("/api/strategy2/enable")
async def enable_strategy2():
    risk_manager.directional_enabled = True
    trade_placed = await directional_strategy.generate_signal(paper_engine.btc_price)
    if trade_placed:
        return {"status": "enabled"}
    risk_manager.directional_enabled = False
    return {"status": "no trade placed"}

@app.post("/api/strategy2/disable")
async def disable_strategy2():
    risk_manager.directional_enabled = False
    directional_strategy.reset()
    return {"status": "disabled"}

@app.post("/api/positions/close-all")
async def close_all_endpoint():
    await paper_engine.close_all()
    iron_fly.reset()
    hedge_manager.reset()
    risk_manager.directional_enabled = False
    directional_strategy.reset()

    # Broadcast empty update to instantly refresh frontends
    payload = {
        "type": "MARKET_UPDATE",
        "data": {"symbol": "BTC", "price": paper_engine.btc_price},
        "wallet": await paper_engine.get_wallet(),
        "positions": [],
        "risk": {
            "netDelta": 0.0,
            "netGamma": 0.001,
            "netTheta": 42.80,
            "directionalEnabled": False
        }
    }
    await log_manager.broadcast(payload)
    return {"status": "success"}

@app.get("/api/logs")
async def get_logs():
    return log_manager.get_recent_messages(message_type="LOG")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await log_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log_manager.disconnect(websocket)

async def market_loop():
    ip = requests.get("https://api.ipify.org").text
    print(f"Public IP: {ip}")
    while True:
        try:
            # 1. Fetch all tickers from Delta to get prices for all symbols
            tickers = await market_data.get_all_tickers()
            price_map = {}

            for t in tickers:
                symbol = t.get("symbol")
                price_val = t.get("mark_price") or t.get("last_price") or t.get("price") or t.get("close")
                if price_val is not None:
                    price_map[symbol] = float(price_val)
            
            # 2. Update BTC price global state if available
            if "BTCUSD" in price_map:
                paper_engine.btc_price = price_map["BTCUSD"]
            
            # 3. Update all positions in paper engine
            await paper_engine.update_prices(price_map)

            # 4. Fetch real Wallet Balance from Delta API
            try:
                balances = await delta_client.get_wallet_balances()
                if balances:
                    paper_engine.update_real_wallet(balances)
            except Exception as e:
                print(f"Error syncing real wallet: {e}")

            #5. Run directional strategy logic to check for any new signals and manage positions accordingly
            risk_manager.directional_enabled = await directional_strategy.generate_signal(paper_engine.btc_price)
            # 5. Risk & Hedge rebalance
            greeks = await risk_manager.get_greeks()
            await hedge_manager.rebalance(greeks.get("delta", 0.0), paper_engine.btc_price)
            
            positions = await paper_engine.get_positions()
            # 6. Broadcast updates
            payload = {
                "type": "MARKET_UPDATE",
                "data": {"symbol": "BTC", "price": paper_engine.btc_price},
                "wallet": await paper_engine.get_wallet(),
                "positions": positions,
                "risk": {
                    "netDelta": greeks.get("delta", 0.0),
                    "netGamma": greeks.get("gamma", 0.0),
                    "netTheta": greeks.get("theta", 0.0),
                },
                "isPaperTrading":config.IS_PAPER_TRADING,
                "marketTrend":directional_strategy.last_signal,
                "logs":log_manager.get_recent_messages(message_type="LOG")
            }
            await log_manager.broadcast(payload)
        except Exception as e:
            print(f"Error in market loop: {e}")
        
        await asyncio.sleep(8)

async def scheduler_loop():
    global last_scheduler_run_date
    print("Auto-Scheduler started. Monitoring to auto-deploy Iron Fly between 07:00 AM and 09:00 AM daily.")
    
    while True:
        try:
            now = datetime.now(ZoneInfo("Asia/Kolkata")) # Use exchange's timezone
            current_hour = now.hour
            current_minute = now.minute
            current_date_str = now.strftime("%Y-%m-%d")
            
            # Active time window: 07:00 AM to 09:00 AM (inclusive of 7 and 8 hours)
            print(current_hour, current_minute)
            if (7 <= current_hour < 9) and (30 <= current_minute < 45): # Adding a minute buffer to avoid multiple triggers at the exact hour
                is_active = len(await paper_engine.get_positions()) > 0 or len(iron_fly.active_legs) > 0
                
                # Only deploy if NOT already active and not already triggered today
                if not is_active and last_scheduler_run_date != current_date_str:
                    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Time trigger hit ({current_hour}h). Auto-deploying Iron Fly strategy...")
                    
                    # Run Strategy 1
                    success, msg = await iron_fly.execute(paper_engine.btc_price)
                    if success:
                        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Auto-deployment successful: {msg}")
                        last_scheduler_run_date = current_date_str
                        
                        # Immediately push update to WebSocket so the UI changes instantly
                        wallet = await paper_engine.get_wallet()
                        positions = await paper_engine.get_positions()
                        greeks = await risk_manager.get_greeks()
                        payload = {
                            "type": "MARKET_UPDATE",
                            "data": {"symbol": "BTC", "price": paper_engine.btc_price},
                            "wallet": wallet,
                            "positions": positions,
                            "risk": {
                                "netDelta": greeks.get("delta", 0.0),
                                "netGamma": greeks.get("gamma", 0.0),
                                "netTheta": greeks.get("theta", 0.0),
                                "directionalEnabled": False
                            }
                        }
                        await log_manager.broadcast(payload)
                    else:
                        print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Auto-deployment failed/skipped: {msg}")
            elif(17<=current_hour<18) and (25<=current_minute<30):
                # Auto-close all positions between 5:25 PM and 5:30 PM to avoid overnight risk
                is_active = len(iron_fly.active_legs) > 0
                if is_active:
                    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] Evening time trigger hit ({current_hour}h). Auto-closing all positions to avoid overnight risk...")
                    await paper_engine.close_all()
                    iron_fly.reset()
                    hedge_manager.reset()
                    # Broadcast empty update to instantly refresh frontends
        except Exception as e:
            print(f"Error in scheduler loop: {e}")
            
        await asyncio.sleep(30) # Check every 30 seconds

@app.on_event("startup")
async def startup():
    await market_data.initialize()
    asyncio.create_task(market_loop())
    asyncio.create_task(scheduler_loop())


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
