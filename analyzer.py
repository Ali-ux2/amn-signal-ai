from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import yfinance as yf
from config import PAIR_MAP, TIMEFRAME_MINUTES

KAMPALA = ZoneInfo("Africa/Kampala")
_POOL = ThreadPoolExecutor(max_workers=4)

@dataclass
class Signal:
    display_pair: str
    yahoo_symbol: str
    direction: str
    trend: str
    confidence: int
    support: float
    resistance: float
    entry_price: float
    entry_time: str
    candles: pd.DataFrame

def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def _ema(close, period):
    return close.ewm(span=period, adjust=False).mean()

def fetch_candles(yahoo_symbol, lookback="1d"):
    interval = "1m" if TIMEFRAME_MINUTES == 1 else f"{TIMEFRAME_MINUTES}m"

    def _download():
        return yf.download(
            yahoo_symbol,
            period=lookback,
            interval=interval,
            progress=False,
            auto_adjust=True,
            threads=False,
        )

    try:
        data = _POOL.submit(_download).result(timeout=10)
    except FuturesTimeout:
        raise RuntimeError(f"Yahoo timeout {yahoo_symbol}")
    if data is None or data.empty:
        raise RuntimeError(f"No candle data for {yahoo_symbol}")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data = data.rename(columns=str.title)
    needed = ["Open", "High", "Low", "Close"]
    missing = [c for c in needed if c not in data.columns]
    if missing:
        raise RuntimeError(f"Unexpected columns: {list(data.columns)}")
    return data.dropna()

def analyze_pair(display_pair):
    yahoo = PAIR_MAP.get(display_pair)
    if not yahoo:
        raise ValueError("Pair not mapped")
    candles = fetch_candles(yahoo)
    if len(candles) < 25:
        return None

    o = candles["Open"]
    h = candles["High"]
    low = candles["Low"]
    c = candles["Close"]
    ema9 = _ema(c, 9)
    ema21 = _ema(c, 21)
    rsi = _rsi(c, 14)

    last_close = float(c.iloc[-1])
    last_open = float(o.iloc[-1])
    last_ema9 = float(ema9.iloc[-1])
    last_ema21 = float(ema21.iloc[-1])
    last_rsi = float(rsi.iloc[-1]) if rsi.notna().iloc[-1] else 50.0
    prev_rsi = float(rsi.iloc[-2]) if rsi.notna().iloc[-2] else last_rsi

    b1 = last_close - last_open
    b2 = float(c.iloc[-2] - o.iloc[-2])
    b3 = float(c.iloc[-3] - o.iloc[-3])
    rng = float(h.tail(20).max() - low.tail(20).min())
    if rng <= 0 or last_close == 0:
        return None
    if abs(b1) / rng < 0.03:
        return None

    bull_ema = last_ema9 > last_ema21 and last_close > last_ema9
    bear_ema = last_ema9 < last_ema21 and last_close < last_ema9
    three_up = b1 > 0 and b2 > 0 and b3 > 0
    three_dn = b1 < 0 and b2 < 0 and b3 < 0
    two_up = b1 > 0 and b2 > 0
    two_dn = b1 < 0 and b2 < 0
    rsi_up = last_rsi >= 52 and last_rsi >= prev_rsi
    rsi_dn = last_rsi <= 48 and last_rsi <= prev_rsi

    call_ok = bull_ema and two_up and (three_up or rsi_up)
    put_ok = bear_ema and two_dn and (three_dn or rsi_dn)
    if call_ok and put_ok:
        return None
    if not call_ok and not put_ok:
        return None

    if call_ok:
        direction = "CALL"
        trend = "BULLISH"
        raw = 3 + (2 if three_up else 0) + (1 if last_rsi > 55 else 0)
    else:
        direction = "PUT"
        trend = "BEARISH"
        raw = 3 + (2 if three_dn else 0) + (1 if last_rsi < 45 else 0)

    confidence = int(min(92, 70 + raw * 3))
    if confidence < 70:
        return None

    recent = candles.tail(30)
    return Signal(
        display_pair=display_pair,
        yahoo_symbol=yahoo,
        direction=direction,
        trend=trend,
        confidence=confidence,
        support=float(recent["Low"].min()),
        resistance=float(recent["High"].max()),
        entry_price=last_close,
        entry_time=datetime.now(KAMPALA).strftime("%H:%M"),
        candles=candles.tail(80).copy(),
    )

def check_result(signal):
    return "SKIP"
