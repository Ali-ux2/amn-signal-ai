from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import yfinance as yf
from config import PAIR_MAP, TIMEFRAME_MINUTES

KAMPALA = ZoneInfo("Africa/Kampala")

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

def fetch_candles(yahoo_symbol, lookback="2d"):
    interval = "1m" if TIMEFRAME_MINUTES == 1 else f"{TIMEFRAME_MINUTES}m"
    data = yf.download(yahoo_symbol, period=lookback, interval=interval, progress=False, auto_adjust=True)
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
    if len(candles) < 20:
        return None
    close = candles["Close"]
    ema9 = _ema(close, 9)
    ema21 = _ema(close, 21)
    rsi = _rsi(close, 14)
    last_close = float(close.iloc[-1])
    last_ema9 = float(ema9.iloc[-1])
    last_ema21 = float(ema21.iloc[-1])
    last_rsi = float(rsi.iloc[-1]) if rsi.notna().iloc[-1] else 50.0
    recent = candles.tail(30)
    support = float(recent["Low"].min())
    resistance = float(recent["High"].max())
    rng = resistance - support
    if rng <= 0 or abs(rng / last_close) < 0.00015:
        return None
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
    if last_rsi < 35:
        score_call += 2
    elif last_rsi > 65:
        score_put += 2
    elif last_rsi < 50:
        score_call += 1
    else:
        score_put += 1
    last_body = float(candles["Close"].iloc[-1] - candles["Open"].iloc[-1])
    prev_body = float(candles["Close"].iloc[-2] - candles["Open"].iloc[-2])
    if last_body > 0:
        score_call += 1
    elif last_body < 0:
        score_put += 1
    if last_body > 0 and prev_body > 0:
        score_call += 2
    elif last_body < 0 and prev_body < 0:
        score
