import asyncio
import json
import logging
import random
from datetime import datetime
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
from core.config import config
from core.logging import configure_logging, log_manager
from core.telegram_bot import telegram_bot
from paper_trading.engine import paper_engine
from risk.manager import risk_manager
from risk.hedge_manager import hedge_manager
from exchange.client import DeltaClient
from exchange.market_data import market_data
from strategies.ironfly import iron_fly
from strategies.directional import directional_strategy
from strategies.poor_mans_covered import poor_mans_covered_strategy
from zoneinfo import ZoneInfo

configure_logging()
logger = logging.getLogger(__name__)

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
last_scheduler_check_time = None

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
    logger.debug("Checking if bot is running: Iron Fly Active: %s", active)
    return active

@app.get("/api/is-directional-enabled")
async def is_directional_enabled():
    active = await paper_engine.is_directional_active()
    logger.debug("Checking if directional strategy is enabled: %s", active)
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

@app.post("/api/strategy1/disable")
async def disable_strategy1():
    await paper_engine.close_position("Strategy 1")
    risk_manager.iron_fly_enabled = False
    await iron_fly.reset()
    return {"status": "disabled"}

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
    await paper_engine.close_position("Strategy 2")
    risk_manager.directional_enabled = False
    directional_strategy.reset()
    return {"status": "disabled"}

@app.post("/api/strategy3/run")
async def run_poor_mans_covered_call():
    success, msg = await poor_mans_covered_strategy.execute("CALL", paper_engine.btc_price)
    if success:
        return {"status": "success", "message": msg}
    return {"status": "error", "message": msg}

@app.post("/api/strategy4/run")
async def run_poor_mans_covered_put():
    success, msg = await poor_mans_covered_strategy.execute("PUT", paper_engine.btc_price)
    if success:
        return {"status": "success", "message": msg}
    return {"status": "error", "message": msg}

@app.post("/api/positions/close-all")
async def close_all_endpoint():
    await paper_engine.close_all()
    iron_fly.reset()
    hedge_manager.reset()
    risk_manager.directional_enabled = False
    risk_manager.iron_fly_enabled = False
    await directional_strategy.reset()

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

async def run_scheduler_checks(now: datetime | None = None):
    global last_scheduler_run_date

    if now is None:
        now = datetime.now(ZoneInfo("Asia/Kolkata"))

    current_hour = now.hour
    current_minute = now.minute
    current_date_str = now.strftime("%Y-%m-%d")

    logger.info("Scheduler check time: %s:%s", current_hour, current_minute)
    if (7 <= current_hour <9) and (30<= current_minute<55):
        is_active = len(await paper_engine.get_positions()) > 0 and len(iron_fly.active_legs) == 4

        if not is_active and last_scheduler_run_date != current_date_str:
            logger.info("Scheduler auto-deploy trigger hit at %s. Auto-deploying Iron Fly strategy.", now.strftime('%Y-%m-%d %H:%M:%S'))

            success, msg = await iron_fly.execute(paper_engine.btc_price)
            if success:
                logger.info("Auto-deployment successful: %s", msg)
                last_scheduler_run_date = current_date_str

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
                logger.warning("Auto-deployment failed or skipped: %s", msg)
    elif (17 <= current_hour < 18) and (15<= current_minute < 30):
        is_active = len(iron_fly.active_legs) == 4
        if is_active:
            logger.info("Evening auto-close trigger hit at %s. Closing positions to avoid overnight risk.", now.strftime('%Y-%m-%d %H:%M:%S'))
            await paper_engine.close_position("Strategy 1")
            iron_fly.reset()
            hedge_manager.reset()

async def market_loop():
    global last_scheduler_check_time

    # Use async httpx to avoid blocking the event loop when fetching public IP
    ip = "unknown"
    try:
        async with httpx.AsyncClient(timeout=10.0) as _client:
            resp = await _client.get("https://api.ipify.org")
            ip = resp.text
    except Exception:
        logger.debug("Unable to fetch public IP")

    logger.info("Public IP: %s", ip)
    
    while True:
        try:
            await iron_fly.get_active_legs()  # Initialize active legs from DB on startup
            await directional_strategy.get_active_position()  # Initialize active position from DB on startup
            try:
                balances = await delta_client.get_wallet_balances()
                if balances:
                    paper_engine.update_real_wallet(balances)
            except Exception as e:
                logger.exception("Error syncing real wallet")
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            if last_scheduler_check_time is None or (now - last_scheduler_check_time).total_seconds() >= 30:
                last_scheduler_check_time = now
                await run_scheduler_checks(now)

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
            

            #5. Run directional strategy logic to check for any new signals and manage positions accordingly
            risk_manager.directional_enabled = await directional_strategy.generate_signal(paper_engine.btc_price)

            # Execute automated Poor Man's Covered based on directional trend
            # if directional_strategy.last_signal == "BULLISH":
            #     if not await poor_mans_covered_strategy.is_active("CALL"):
            #         success, msg = await poor_mans_covered_strategy.execute("CALL", paper_engine.btc_price)
            #         if success:
            #             logger.info("Auto-executed Poor Man's Covered Call: %s", msg)
            #         else:
            #             logger.warning("Poor Man's Covered Call execution skipped: %s", msg)
            # elif directional_strategy.last_signal == "BEARISH":
            #     if not await poor_mans_covered_strategy.is_active("PUT"):
            #         success, msg = await poor_mans_covered_strategy.execute("PUT", paper_engine.btc_price)
            #         if success:
            #             logger.info("Auto-executed Poor Man's Covered Put: %s", msg)
            #         else:
            #             logger.warning("Poor Man's Covered Put execution skipped: %s", msg)

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
            logger.exception("Error in market loop")
        
        await asyncio.sleep(8)


@app.on_event("startup")
async def startup():
    await market_data.initialize()
    await telegram_bot.initialize()
    logger.info("Starting merged market and scheduler loop")
    asyncio.create_task(market_loop())


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
