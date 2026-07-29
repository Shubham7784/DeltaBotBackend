"""Multi-confirmation market analysis for the adaptive strategy engine."""
from dataclasses import asdict, dataclass
from core.config import config


@dataclass
class MarketAnalysis:
    price: float
    ema20: float = 0.0; ema50: float = 0.0; ema200: float = 0.0; vwap: float = 0.0
    atr: float = 0.0; atr_pct: float = 0.0; adx: float = 0.0; rsi: float = 50.0
    volume_ratio: float = 1.0; iv: float = 0.0; open_interest: float = 0.0
    put_call_ratio: float = 1.0; funding_rate: float = 0.0; bos: str = "NONE"
    choch: str = "NONE"; liquidity_sweep: bool = False; volatility_regime: str = "NORMAL"
    regime: str = "UNKNOWN"; confidence: float = 0.0; reasons: list | None = None

    def to_dict(self): return asdict(self)


class MarketAnalyzer:
    @staticmethod
    def _ema(values, length):
        value, factor = values[0], 2 / (length + 1)
        for price in values[1:]: value = price * factor + value * (1 - factor)
        return value

    @staticmethod
    def _rsi(values, length=14):
        if len(values) <= length: return 50.0
        moves = [values[i] - values[i - 1] for i in range(1, len(values))][-length:]
        gain, loss = sum(max(x, 0) for x in moves) / length, sum(abs(min(x, 0)) for x in moves) / length
        return 100.0 if not loss else 100 - 100 / (1 + gain / loss)

    @staticmethod
    def _atr(candles, length=14):
        values = [max(float(candles[i]['high']) - float(candles[i]['low']), abs(float(candles[i]['high']) - float(candles[i-1]['close'])), abs(float(candles[i]['low']) - float(candles[i-1]['close']))) for i in range(1, len(candles))]
        return sum(values[-length:]) / min(len(values), length) if values else 0.0

    @staticmethod
    def _adx(candles, length=14):
        if len(candles) < length + 1: return 0.0
        plus, minus, tr = [], [], []
        for i in range(1, len(candles)):
            up, down = float(candles[i]['high']) - float(candles[i-1]['high']), float(candles[i-1]['low']) - float(candles[i]['low'])
            plus.append(max(up, 0) if up > down else 0); minus.append(max(down, 0) if down > up else 0)
            tr.append(max(float(candles[i]['high']) - float(candles[i]['low']), abs(float(candles[i]['high']) - float(candles[i-1]['close'])), abs(float(candles[i]['low']) - float(candles[i-1]['close']))))
        denominator = sum(tr[-length:])
        if not denominator: return 0.0
        pdi, mdi = 100 * sum(plus[-length:]) / denominator, 100 * sum(minus[-length:]) / denominator
        return 0.0 if pdi + mdi == 0 else 100 * abs(pdi - mdi) / (pdi + mdi)

    def analyze(self, price, candles, tickers=None, options=None):
        if not candles or price <= 0: return MarketAnalysis(price=price, reasons=['Insufficient market data'])
        # Be defensive when callers pass raw Delta candles rather than the
        # normalized MarketDataService cache.
        candles = sorted(candles, key=lambda candle: float(candle.get('time', 0)))
        closes = [float(c['close']) for c in candles]; highs = [float(c['high']) for c in candles]; lows = [float(c['low']) for c in candles]
        volumes = [float(c.get('volume', 0) or 0) for c in candles]; avg_volume = sum(volumes[-20:]) / max(1, len(volumes[-20:]))
        typical = [(float(c['high']) + float(c['low']) + float(c['close'])) / 3 for c in candles[-50:]]; vol = volumes[-len(typical):]
        vwap = sum(p * v for p, v in zip(typical, vol)) / sum(vol) if sum(vol) else closes[-1]
        ticker = next((t for t in (tickers or []) if t.get('symbol') == 'BTCUSD'), {})
        calls = [o for o in (options or []) if o.get('contract_type') == 'call_options']; puts = [o for o in (options or []) if o.get('contract_type') == 'put_options']
        raw_ivs = [
            float(
                option.get('implied_volatility') or option.get('iv') or
                option.get('mark_vol') or option.get('quotes', {}).get('mark_iv') or 0
            )
            for option in (options or [])
        ]
        # Delta option IV is normally a decimal (0.176 = 17.6%).  Preserve
        # already-percent values from other compatible feeds.
        ivs = [value * 100 if 0 < value <= 3 else value for value in raw_ivs if value > 0]
        ema20, ema50, ema200 = self._ema(closes, 20), self._ema(closes, 50), self._ema(closes, 200)
        atr, adx, rsi = self._atr(candles), self._adx(candles), self._rsi(closes); atr_pct = atr / price * 100
        prior_high, prior_low = max(highs[-21:-1]), min(lows[-21:-1]); bos = 'BULLISH' if price > prior_high else 'BEARISH' if price < prior_low else 'NONE'
        choch = 'BULLISH' if lows[-1] > lows[-6] and closes[-1] > closes[-6] else 'BEARISH' if highs[-1] < highs[-6] and closes[-1] < closes[-6] else 'NONE'
        bullish, bearish = price > ema20 > ema50 > ema200, price < ema20 < ema50 < ema200
        volume_ratio = volumes[-1] / avg_volume if avg_volume else 1.0; funding = float(ticker.get('funding_rate') or ticker.get('funding') or 0)
        iv = sum(ivs) / len(ivs) if ivs else 0.0
        elevated_funding = abs(funding) >= config.HIGH_FUNDING_RATE_PCT
        funding_confirmed = elevated_funding and (
            atr_pct >= config.FUNDING_CONFIRM_ATR_PCT or iv >= config.FUNDING_CONFIRM_IV_PCT
        )
        high_vol = (
            atr_pct >= config.HIGH_VOL_ATR_PCT or
            iv >= config.HIGH_VOL_IV_PCT or
            funding_confirmed
        )
        if high_vol: regime, confidence = 'HIGH_VOLATILITY_EVENT', min(.95, .6 + max(atr_pct / 10, iv / 200))
        elif adx < 18 and atr_pct < 1 and abs(price - vwap) / price < .004: regime, confidence = 'SIDEWAYS', .65
        elif bullish and adx >= 28 and volume_ratio >= 1.1 and bos == 'BULLISH': regime, confidence = 'STRONG_BULLISH', min(.95, .55 + adx / 100)
        elif bearish and adx >= 28 and (bos == 'BEARISH' or choch == 'BEARISH'): regime, confidence = 'STRONG_BEARISH', min(.95, .55 + adx / 100)
        elif price > ema20 > ema50 and rsi >= 52: regime, confidence = 'MILD_BULLISH', .55 + min(adx, 25) / 100
        elif price < ema20 < ema50 and rsi <= 48: regime, confidence = 'MILD_BEARISH', .55 + min(adx, 25) / 100
        else: regime, confidence = 'UNKNOWN', 0.0
        return MarketAnalysis(price, ema20, ema50, ema200, vwap, atr, atr_pct, adx, rsi, volume_ratio, iv, float(ticker.get('open_interest') or ticker.get('oi') or 0), len(puts)/len(calls) if calls else 1, funding, bos, choch, (highs[-1] > prior_high and closes[-1] < prior_high) or (lows[-1] < prior_low and closes[-1] > prior_low), 'HIGH' if high_vol else 'LOW' if atr_pct < .8 else 'NORMAL', regime, confidence, [f'EMA alignment: {"bullish" if bullish else "bearish" if bearish else "mixed"}', f'ADX {adx:.1f}', f'RSI {rsi:.1f}', f'BOS {bos}', f'Volatility: ATR {atr_pct:.2f}%, IV {iv:.1f}%, funding {funding:.4f}'])


market_analyzer = MarketAnalyzer()
