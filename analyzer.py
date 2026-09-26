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

def _demarker(high, low, period=14):
    up = (high - high.shift(1)).clip(lower=0)
    down = (low.shift(1) - low).clip(lower=0)
    de_max = up.rolling(period).mean()
    de_min = down.rolling(period).mean()
    denom = (de_max + de_min).replace(0, np.nan)
    return de_max / denom

def _last_swing(high, low, depth=12):
    if len(high) < depth * 2:
        return None
    h = high.iloc[-depth:]
    l = low.iloc[-depth:]
    if float(l.iloc[-1]) <= float(l.min()) * 1.0002:
        return "LOW"
    if float(h.iloc[-1]) >= float(h.max()) * 0.9998:
        return "HIGH"
    mid = depth // 2
    if float(l.iloc[mid]) == float(l.min()):
        return "LOW"
    if float(h.iloc[mid]) == float(h.max()):
        return "HIGH"
    return None

def fetch_candles(yahoo_symbol, lookback="1d"):
    interval = "1m" if TIMEFRAME_MINUTES == 1 else f"{TIMEFRAME_MINUTES}m"
    def _download():
        return yf.download(yahoo_symbol, period=lookback, interval=interval, progress=False, auto_adjust=True, threads=False)
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
    if len(candles) < 55:
        return None
    o, high, low, close = candles["Open"], candles["High"], candles["Low"], candles["Close"]
    ema9, ema21, ema50 = _ema(close, 9), _ema(close, 21), _ema(close, 50)
    rsi, dem = _rsi(close, 14), _demarker(high, low, 14)
    last_o, last_h, last_l, last_c = float(o.iloc[-1]), float(high.iloc[-1]), float(low.iloc[-1]), float(close.iloc[-1])
    prev_o, prev_c = float(o.iloc[-2]), float(close.iloc[-2])
    last_ema9, last_ema21, last_ema50 = float(ema9.iloc[-1]), float(ema21.iloc[-1]), float(ema50.iloc[-1])
    prev_ema9, prev_ema21 = float(ema9.iloc[-2]), float(ema21.iloc[-2])
    last_rsi = float(rsi.iloc[-1]) if rsi.notna().iloc[-1] else 50.0
    last_dem = float(dem.iloc[-1]) if dem.notna().iloc[-1] else 0.5
    prev_dem = float(dem.iloc[-2]) if dem.notna().iloc[-2] else last_dem
    support, resistance = float(low.tail(30).min()), float(high.tail(30).max())
    rng = resistance - support
    if rng <= 0 or last_c == 0:
        return None
    sides = [1 if float(close.iloc[-i]) > float(ema50.iloc[-i]) else -1 for i in range(1, 7)]
    if abs(sum(sides)) <= 1:
        return None
    body = abs(last_c - last_o)
    upper_wick = last_h - max(last_c, last_o)
    lower_wick = min(last_c, last_o) - last_l
    candle_range = last_h - last_l
    if candle_range <= 0:
        return None
    if max(upper_wick, lower_wick) > 3 * max(body, candle_range * 0.05):
        return None
    near_sup = (last_c - support) / rng <= 0.18 or (last_l - support) / rng <= 0.12
    near_res = (resistance - last_c) / rng <= 0.18 or (resistance - last_h) / rng <= 0.12
    above50 = last_c > last_ema50 and last_o > last_ema50
    below50 = last_c < last_ema50 and last_o < last_ema50
    pin_call = lower_wick >= 1.6 * max(body, candle_range * 0.04) and lower_wick > upper_wick
    pin_put = upper_wick >= 1.6 * max(body, candle_range * 0.04) and upper_wick > lower_wick
    eng_call = last_c > last_o and prev_c < prev_o and last_c >= prev_o and last_o <= prev_c
    eng_put = last_c < last_o and prev_c > prev_o and last_c <= prev_o and last_o >= prev_c
    swing = _last_swing(high, low, 12)
    votes_call = votes_put = 0
    if swing == "LOW" and last_dem <= 0.30 and last_dem >= prev_dem:
        votes_call += 2
    if swing == "HIGH" and last_dem >= 0.70 and last_dem <= prev_dem:
        votes_put += 2
    if last_dem < 0.30 and last_dem > prev_dem:
        votes_call += 1
    if last_dem > 0.70 and last_dem < prev_dem:
        votes_put += 1
    if prev_ema9 <= prev_ema21 and last_ema9 > last_ema21:
        votes_call += 2
    if prev_ema9 >= prev_ema21 and last_ema9 < last_ema21:
        votes_put += 2
    if last_ema9 > last_ema21 and last_c > last_ema9:
        votes_call += 1
    if last_ema9 < last_ema21 and last_c < last_ema9:
        votes_put += 1
    if near_sup and last_rsi <= 30:
        votes_call += 2
    if near_res and last_rsi >= 70:
        votes_put += 2
    if last_rsi < 35:
        votes_call += 1
    if last_rsi > 65:
        votes_put += 1
    if above50 and near_sup and (pin_call or eng_call):
        votes_call += 3
    if below50 and near_res and (pin_put or eng_put):
        votes_put += 3
    if above50 and near_sup:
        votes_call += 1
    if below50 and near_res:
        votes_put += 1
    if votes_call < 3 and votes_put < 3:
        return None
    if abs(votes_call - votes_put) < 2:
        return None
    if votes_call > votes_put:
        direction, trend, raw = "CALL", "BULLISH", votes_call
    else:
        direction, trend, raw = "PUT", "BEARISH", votes_put
    confidence = int(min(92, 64 + raw * 4))
    if confidence < 68:
        return None
    return Signal(
        display_pair=display_pair, yahoo_symbol=yahoo, direction=direction, trend=trend,
        confidence=confidence, support=support, resistance=resistance, entry_price=last_c,
        entry_time=datetime.now(KAMPALA).strftime("%H:%M"), candles=candles.tail(80).copy(),
    )

def check_result(signal):
    return "SKIP"
