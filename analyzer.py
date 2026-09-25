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
        data = _POOL.submit(_download).result(timeout=8)
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
    if len(candles) < 15:
        return None
    close = candles["Close"]
    ema9 = _ema(close, 9)
    ema21 = _ema(close, 21)
    rsi = _rsi(close, 14)
    last_close = float(close.iloc[-1])
    last_ema9 = float(ema9.iloc[-1])
    last_ema21 = float(ema21.iloc[-1])
    last_rsi = float(rsi.iloc[-1]) if rsi.notna().iloc[-1] else 50.0
    last_body = float(candles["Close"].iloc[-1] - candles["Open"].iloc[-1])
    prev_body = float(candles["Close"].iloc[-2] - candles["Open"].iloc[-2])
    score_call = 0
    score_put = 0
    if last_ema9 > last_ema21:
        score_call += 2
        trend = "BULLISH"
    else:
        score_put += 2
        trend = "BEARISH"
    if last_close > last_ema9:
        score_call += 1
    else:
        score_put += 1
    if last_rsi < 45:
        score_call += 1
    elif last_rsi > 55:
        score_put += 1
    if last_body > 0:
        score_call += 1
    elif last_body < 0:
        score_put += 1
    if last_body > 0 and prev_body > 0:
        score_call += 2
    elif last_body < 0 and prev_body < 0:
        score_put += 2
    if score_call >= score_put:
        direction = "CALL"
        raw = max(score_call, 1)
    else:
        direction = "PUT"
        raw = max(score_put, 1)
    confidence = int(min(90, 58 + raw * 5))
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
