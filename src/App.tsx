/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect } from "react";
import { 
  TrendingUp, 
  Wallet, 
  Activity, 
  Terminal, 
  ShieldCheck, 
  Settings, 
  Play, 
  Square,
  AlertTriangle,
  Zap,
  BarChart3,
  History,
  X
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export default function App() {
  const [isBotRunning, setIsBotRunning] = useState(false);
  const [isDirectionalEnabled, setIsDirectionalEnabled] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [tradeHistory, setTradeHistory] = useState<any[]>([]);
  const [btcPrice, setBtcPrice] = useState(65000);
  const [netDelta, setNetDelta] = useState(0);
  const [netTheta, setNetTheta] = useState(0);
  const [netGamma, setNetGamma] = useState(0);
  const [wallet, setWallet] = useState({ balance: 50000, usedMargin: 0, availableBalance: 50000, totalEquity: 50000, totalUnrealizedPnL: 0 });
  const [positions, setPositions] = useState<any[]>([]);
  const [logs, setLogs] = useState<{msg: string, type: 'info' | 'warn' | 'error' | 'trade'}[]>([
    { msg: "DeltaBot System Initialized", type: "info" },
    { msg: "Connecting to WebSocket...", type: "info" }
  ]);

  useEffect(() => {
    // Initial fetch
    fetch("/api/wallet").then(res => res.json()).then(setWallet);
    fetch("/api/positions").then(res => res.json()).then(setPositions);
    fetch("/api/is-bot-running").then(res => res.json()).then(data => setIsBotRunning(data));
    fetch("/api/is-directional-enabled").then(res => res.json()).then(data => setIsDirectionalEnabled(data));

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);

    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "MARKET_UPDATE") {
        setBtcPrice(payload.data.price);
        setWallet(payload.wallet);
        setPositions(payload.positions);
        if (payload.risk) {
          setNetDelta(payload.risk.netDelta);
          setNetTheta(payload.risk.netTheta);
          setNetGamma(payload.risk.netGamma);
          setIsDirectionalEnabled(payload.risk.directionalEnabled);
        }
      }
    };

    socket.onopen = () => addLog("WebSocket Connected", "info");
    socket.onerror = () => addLog("WebSocket Connection Error", "error");

    return () => socket.close();
  }, []);

  const fetchHistory = async () => {
    const res = await fetch("/api/trade-history");
    const data = await res.json();
    setTradeHistory(data);
    setShowHistory(true);
  };

  const addLog = (msg: string, type: 'info' | 'warn' | 'error' | 'trade' = 'info') => {
    setLogs(prev => [{ msg, type }, ...prev].slice(0, 50));
  };

  const toggleBot = async () => {
    if (isBotRunning) {
      await fetch("/api/positions/close-all", { method: "POST" });
      setIsBotRunning(false);
      addLog("Emergency shutdown: All trades closed.", "error");
    } else {
      setIsBotRunning(true);
      await fetch("/api/strategy1/run", { method: "POST" });
      addLog("Iron Fly Strategy deployed.", "trade");
    }
  };

  const toggleDirectional = async () => {
    const endpoint = isDirectionalEnabled ? "/api/strategy2/disable" : "/api/strategy2/enable";
    await fetch(endpoint, { method: "POST" });
    setIsDirectionalEnabled(!isDirectionalEnabled);
    addLog(`Directional Strategy ${!isDirectionalEnabled ? 'Enabled' : 'Disabled'}`, "info");
  };

  const closeAll = async () => {
    await fetch("/api/positions/close-all", { method: "POST" });
    addLog("Manual Close All triggered.", "warn");
  };

  return (
    <div className="bg-[#0A0A0B] text-[#E4E3E0] min-h-screen h-screen flex flex-col font-sans overflow-hidden selection:bg-[#F27D26] selection:text-white">
      {/* Trade History Modal */}
      <AnimatePresence>
        {showHistory && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
          >
            <motion.div 
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-[#0E0E10] border border-[#1F1F22] w-full max-w-4xl max-h-[80vh] flex flex-col rounded-lg overflow-hidden shadow-2xl"
            >
              <div className="p-4 border-b border-[#1F1F22] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <History className="w-4 h-4 text-[#F27D26]" />
                  <h2 className="text-sm font-bold uppercase tracking-widest">Trade History</h2>
                </div>
                <button onClick={() => setShowHistory(false)} className="hover:bg-[#1F1F22] p-1 rounded transition-colors text-slate-500 hover:text-white">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="flex-1 overflow-auto p-4">
                <table className="w-full text-left">
                  <thead>
                    <tr className="text-[10px] text-slate-500 uppercase border-b border-[#1F1F22]">
                      <th className="pb-2 font-semibold">Instrument</th>
                      <th className="pb-2 font-semibold">Side</th>
                      <th className="pb-2 font-semibold text-right">Size</th>
                      <th className="pb-2 font-semibold text-right">Entry</th>
                      <th className="pb-2 font-semibold text-right">Close</th>
                      <th className="pb-2 font-semibold text-right">PnL</th>
                      <th className="pb-2 font-semibold text-right">Time</th>
                    </tr>
                  </thead>
                  <tbody className="text-xs font-mono">
                    {tradeHistory.length === 0 && (
                      <tr>
                        <td colSpan={7} className="py-12 text-center text-slate-600 italic">No trade history found</td>
                      </tr>
                    )}
                    {tradeHistory.map((trade) => (
                      <tr key={trade.id} className="border-b border-[#1F1F22]/50 hover:bg-[#1F1F22]/20 transition-colors">
                        <td className="py-3 text-slate-300">{trade.symbol}</td>
                        <td className={cn(
                          "py-3 font-bold",
                          trade.side === "LONG" ? "text-green-400" : "text-red-400"
                        )}>{trade.side}</td>
                        <td className="py-3 text-right text-slate-300">{trade.size}</td>
                        <td className="py-3 text-right text-slate-400">${trade.entryprice?.toLocaleString()}</td>
                        <td className="py-3 text-right text-slate-400">${trade.closeprice?.toLocaleString()}</td>
                        <td className={cn(
                          "py-3 text-right font-bold",
                          trade.pnl >= 0 ? "text-green-400" : "text-red-400"
                        )}>
                          {trade.pnl >= 0 ? "+" : ""}${trade.pnl?.toFixed(2)}
                        </td>
                        <td className="py-3 text-right text-slate-500 text-[10px]">
                          {new Date(trade.timestamp * 1000).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Top Navigation / Header */}
      <header className="h-14 border-b border-[#1F1F22] flex items-center justify-between px-6 bg-[#0E0E10] shrink-0">
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-[#F27D26] rounded-sm flex items-center justify-center font-bold text-black text-xs italic">Δ</div>
            <h1 className="text-lg font-bold tracking-tight uppercase">DELTABOT <span className="text-[10px] font-normal text-slate-500 uppercase tracking-widest ml-1">v1.0.4 Paper</span></h1>
          </div>
          <div className="flex gap-6 border-l border-[#1F1F22] pl-8">
            <div className="flex flex-col">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">BTC/USD</span>
              <span className={cn(
                "text-sm font-mono transition-colors",
                btcPrice > 65000 ? "text-green-400" : "text-red-400"
              )}>${(btcPrice ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">Funding</span>
              <span className="text-sm font-mono text-slate-300 italic">0.0100%</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">Net Delta</span>
              <span className={cn(
                "text-sm font-mono",
                Math.abs(netDelta ?? 0) > 0.5 ? "text-orange-400" : "text-blue-400"
              )}>{(netDelta ?? 0).toFixed(3)}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <button 
            onClick={fetchHistory}
            className="flex items-center gap-2 bg-[#16161A] hover:bg-[#1F1F22] border border-[#2A2A2E] px-3 py-1.5 rounded transition-colors group"
          >
            <History className="w-3.5 h-3.5 text-slate-500 group-hover:text-[#F27D26] transition-colors" />
            <span className="text-xs font-bold uppercase tracking-wider">History</span>
          </button>
          <div className="bg-[#16161A] border border-[#2A2A2E] px-4 py-1 rounded flex items-center gap-4">
            <div className="text-right">
              <span className="block text-[9px] text-slate-500 uppercase">Equity</span>
              <span className="block text-sm font-mono font-bold">${(wallet?.totalEquity ?? 0).toLocaleString(undefined, { minimumFractionDigits: 0 })}</span>
            </div>
            <div className="w-px h-6 bg-[#2A2A2E]"></div>
            <div className="text-right">
              <span className="block text-[9px] text-slate-500 uppercase">Margin Used</span>
              <span className="block text-sm font-mono text-orange-400">
                {wallet?.balance ? ((wallet.usedMargin / wallet.balance) * 100).toFixed(1) : "0.0"}%
              </span>
            </div>
          </div>
          <button 
            onClick={toggleBot}
            className={cn(
              "px-4 py-1.5 rounded text-xs font-bold uppercase tracking-widest transition-all",
              isBotRunning 
              ? "bg-red-900/30 border border-red-500/50 text-red-500 hover:bg-red-600 hover:text-white"
              : "bg-green-900/30 border border-green-500/50 text-green-500 hover:bg-green-600 hover:text-white"
            )}
          >
            {isBotRunning ? "Kill Switch" : "Run Iron Fly"}
          </button>
        </div>
      </header>

      {/* Main Content Grid */}
      <main className="flex-1 grid grid-cols-12 gap-1 p-1 bg-[#1F1F22] overflow-hidden">
        {/* Left Sidebar: Market & Wallet Details */}
        <section className="col-span-3 flex flex-col gap-1 overflow-hidden">
          <div className="flex-1 bg-[#0E0E10] p-4 overflow-y-auto">
            <h3 className="text-[11px] text-slate-500 uppercase font-bold tracking-widest mb-4 border-b border-[#1F1F22] pb-2">Wallet & Risk</h3>
            <div className="space-y-4">
              <div className="flex justify-between items-end">
                <span className="text-xs text-slate-400">Available Bal.</span>
                <span className="text-lg font-mono font-semibold">${(wallet?.availableBalance ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
              </div>
              <div className="flex justify-between items-end border-b border-[#1F1F22] pb-3">
                <span className="text-xs text-slate-400">Unrealized PnL</span>
                <span className={cn(
                  "text-lg font-mono font-semibold",
                  (wallet?.totalUnrealizedPnL ?? 0) >= 0 ? "text-green-400" : "text-red-400"
                )}>{(wallet?.totalUnrealizedPnL ?? 0) >= 0 ? "+" : ""}${(wallet?.totalUnrealizedPnL ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
              </div>
              <div className="space-y-2 pt-2">
                <div className="flex justify-between text-[10px] text-slate-500 uppercase">
                  <span>Margin Usage</span>
                  <span>{wallet?.balance ? ((wallet.usedMargin / wallet.balance) * 100).toFixed(1) : "0.0"}% / 80%</span>
                </div>
                <div className="w-full bg-[#1F1F22] h-1">
                  <div 
                    className="bg-orange-500 h-full transition-all duration-1000" 
                    style={{ width: `${Math.min(100, wallet?.balance ? (wallet.usedMargin / wallet.balance) * 100 : 0)}%` }}
                  ></div>
                </div>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-[10px] text-slate-500 uppercase">
                  <span>Drawdown (SIM)</span>
                  <span>0.00% / 2.0%</span>
                </div>
                <div className="w-full bg-[#1F1F22] h-1">
                  <div className="bg-blue-500 h-full w-[5%]"></div>
                </div>
              </div>
            </div>
          </div>
          <div className="h-40 bg-[#0E0E10] p-4 shrink-0">
            <h3 className="text-[11px] text-slate-500 uppercase font-bold tracking-widest mb-3">Signals (V1 SIM)</h3>
            <div className="space-y-2">
              <div className="flex justify-between">
                <span className="text-[11px] text-slate-400">Trend (EMA 20)</span>
                <span className={cn(
                  "text-[11px] font-bold uppercase",
                  btcPrice > 65000 ? "text-green-400" : "text-red-400"
                )}>{btcPrice > 65000 ? "Bullish" : "Bearish"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[11px] text-slate-400">Directional</span>
                <span className="text-[11px] text-white font-mono italic">{isDirectionalEnabled ? "SCANNING" : "OFF"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[11px] text-slate-400">Mode</span>
                <span className="text-[11px] text-orange-500 font-bold uppercase">Paper</span>
              </div>
            </div>
          </div>
        </section>

        {/* Middle: Position Monitor & Strategy Focus */}
        <section className="col-span-6 flex flex-col gap-1 overflow-hidden">
          <div className="flex-1 bg-[#0E0E10] p-4 flex flex-col overflow-hidden">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-[11px] text-slate-500 uppercase font-bold tracking-widest">Active Positions</h3>
              <div className="flex gap-4">
                <span className="text-[11px] font-mono"><span className="text-slate-500">DELTA:</span> {netDelta.toFixed(3)}</span>
                <span className="text-[11px] font-mono"><span className="text-slate-500">GAMMA:</span> {netGamma.toFixed(3)}</span>
                <span className="text-[11px] font-mono"><span className="text-slate-500">THETA:</span> {netTheta.toFixed(2)}</span>
              </div>
            </div>
            <div className="flex-1 overflow-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-[10px] text-slate-500 uppercase border-b border-[#1F1F22]">
                    <th className="pb-2 font-semibold">Instrument</th>
                    <th className="pb-2 font-semibold text-right">Side/Size</th>
                    <th className="pb-2 font-semibold text-right">Entry</th>
                    <th className="pb-2 font-semibold text-right">Current</th>
                    <th className="pb-2 font-semibold text-right">PnL (ROE)</th>
                  </tr>
                </thead>
                <tbody className="text-xs font-mono">
                  {positions.length === 0 && (
                    <tr>
                      <td colSpan={4} className="py-12 text-center text-slate-600 italic">No working positions</td>
                    </tr>
                  )}
                  {positions.map((pos) => (
                    <tr key={pos.id} className="border-b border-[#1F1F22]/50 hover:bg-[#1F1F22]/20 transition-colors">
                      <td className="py-3 text-slate-300">{pos.symbol}</td>
                      <td className={cn(
                        "py-3 text-right font-bold",
                        pos.side === "LONG" ? "text-green-400" : "text-red-400"
                      )}>{pos.side} {pos.size}</td>
                      <td className="py-3 text-right text-slate-400">${(pos.entryPrice ?? 0).toLocaleString()}</td>
                      <td className="py-3 text-right text-slate-400">${(pos.currentPrice ?? 0).toLocaleString()}</td>
                      <td className={cn(
                        "py-3 text-right",
                        (pos.unrealizedPnL ?? 0) >= 0 ? "text-green-400" : "text-red-400"
                      )}>
                        {(pos.unrealizedPnL ?? 0) >= 0 ? "+" : ""}${(pos.unrealizedPnL ?? 0).toFixed(2)}
                        <span className="text-[9px] ml-1 opacity-70">
                          ({pos.margin ? (((pos.unrealizedPnL ?? 0) / pos.margin) * 100).toFixed(1) : "0.0"}%)
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="h-40 bg-[#0E0E10] p-4 flex gap-4 shrink-0 overflow-hidden">
            <div className={cn(
              "flex-1 rounded p-3 border transition-all",
              isBotRunning ? "bg-[#16161A] border-[#2A2A2E]" : "bg-black/20 border-white/5 opacity-50"
            )}>
              <span className="text-[10px] text-slate-500 uppercase font-bold block mb-1">Strategy 1: Iron Fly</span>
              <div className="flex items-center gap-2 mb-2">
                <div className={cn(
                  "w-2 h-2 rounded-full",
                  isBotRunning ? "bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]" : "bg-slate-700"
                )}></div>
                <span className="text-xs font-bold">{isBotRunning ? "Hedged Neutrally" : "Idle"}</span>
              </div>
              <span className="text-[10px] text-slate-400">Targeting: <span className="text-white font-mono">{(Math.round(btcPrice / 100) * 100) + 300}</span></span>
            </div>
            <div className={cn(
              "flex-1 rounded p-3 border transition-all",
              isDirectionalEnabled ? "bg-[#16161A] border-[#2A2A2E] opacity-100" : "bg-black/20 border-white/5 opacity-50"
            )}>
              <span className="text-[10px] text-slate-500 uppercase font-bold block mb-1">Strategy 2: Directional</span>
              <div className="flex items-center gap-2 mb-2">
                <div className={cn(
                  "w-2 h-2 rounded-full shadow-[0_0_8px_rgba(59,130,246,0.5)]",
                  isDirectionalEnabled ? "bg-blue-500" : "bg-slate-700"
                )}></div>
                <span className="text-xs font-bold">{isDirectionalEnabled ? "Monitoring" : "Disabled"}</span>
              </div>
              <span className="text-[10px] text-slate-400 italic">Waiting for signal...</span>
            </div>
          </div>
        </section>

        {/* Right Sidebar: Controls & Actions */}
        <section className="col-span-3 flex flex-col gap-1 overflow-hidden">
          <div className="flex-1 bg-[#0E0E10] p-4 overflow-y-auto">
            <h3 className="text-[11px] text-slate-500 uppercase font-bold tracking-widest mb-4">Manual Controls</h3>
            <div className="grid grid-cols-1 gap-3">
              <button 
                onClick={toggleBot}
                className="w-full bg-[#1F1F22] hover:bg-[#2A2A2E] border border-[#2A2A2E] py-3 rounded text-xs font-bold uppercase tracking-wider transition-colors"
              >
                {isBotRunning ? "Close Strategy" : "Deploy Iron Fly"}
              </button>
              <button 
                onClick={() => addLog("Manual hedge rebalance triggered", "info")}
                className="w-full bg-blue-600 hover:bg-blue-500 text-white py-3 rounded text-xs font-bold uppercase tracking-wider transition-colors shadow-lg shadow-blue-500/20"
              >
                Adjust Hedge
              </button>
              <button 
                onClick={toggleDirectional}
                className="w-full bg-[#1F1F22] hover:bg-[#2A2A2E] border border-[#2A2A2E] py-3 rounded text-xs font-bold uppercase tracking-wider transition-colors"
              >
                {isDirectionalEnabled ? "Disable Trend" : "Enable Trend Signal"}
              </button>
              <div className="pt-4 border-t border-[#1F1F22] mt-2">
                <button 
                  onClick={closeAll}
                  className="w-full bg-red-600/10 hover:bg-red-600/20 border border-red-500/50 text-red-500 py-3 rounded text-xs font-bold uppercase tracking-wider transition-colors"
                >
                  Flatten Portfolio
                </button>
              </div>
            </div>
          </div>
          <div className="h-40 bg-[#0E0E10] p-4 shrink-0 overflow-hidden">
            <h3 className="text-[11px] text-slate-500 uppercase font-bold tracking-widest mb-3">Hedge Engine</h3>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-[11px] text-slate-400">Delta Threshold</span>
                <span className="text-[11px] font-mono">0.50</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[11px] text-slate-400">Current Drift</span>
                <span className={cn(
                  "text-[11px] font-bold uppercase",
                  Math.abs(netDelta) < 0.5 ? "text-green-400" : "text-orange-400"
                )}>{Math.abs(netDelta) < 0.5 ? "NEUTRAL" : "DRIFTING"}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[11px] text-slate-400">Instrument</span>
                <span className="text-[11px] font-mono italic">BTC-FUT-PERP</span>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* Bottom Console / Logs */}
      <footer className="h-[180px] bg-[#0A0A0B] border-t border-[#1F1F22] flex flex-col shrink-0">
        <div className="h-8 border-b border-[#1F1F22] flex items-center px-4 justify-between bg-[#0E0E10]">
          <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">System Console</span>
          <div className="flex gap-4">
            <span className="text-[9px] text-green-500 uppercase">WebSocket: Connected</span>
            <span className="text-[9px] text-slate-500 uppercase">Mode: Paper Trading</span>
          </div>
        </div>
        <div className="flex-1 p-4 font-mono text-[11px] leading-relaxed overflow-y-auto bg-black/40">
          <AnimatePresence>
            {logs.map((log, i) => (
               <motion.div 
                key={i} 
                initial={{ opacity: 0 }} 
                animate={{ opacity: 1 }} 
                className="text-slate-500 italic mb-1"
              >
                [{new Date().toLocaleTimeString()}] 
                <span className={cn(
                  "mx-2 uppercase font-bold",
                  log.type === 'error' ? "text-red-500" : 
                  log.type === 'warn' ? "text-orange-500" : 
                  log.type === 'trade' ? "text-green-400" : "text-blue-400"
                )}>{log.type}</span> 
                <span className="text-slate-300">{log.msg}</span>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </footer>
    </div>
  );
}
