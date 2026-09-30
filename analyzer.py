from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import otc_feed as quotex_feed
from config import PAIR_MAP

KAMPALA = ZoneInfo("Africa/Kampala")


@dataclass
class Signal:
    display_pair: str
    feed_symbol: str
    direction: str
    trend: str
    confidence: int
    support: float
    resistance: float
    entry_price: float
    entry_time: str
    candles: pd.DataFrame


# ──────────────────────────────────────────────────────────────
#  INDICATOR MATH
# ──────────────────────────────────────────────────────────────

def _ema(close, period):
    return close.ewm(span=period, adjust=False).mean()


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _demarker(high, low, period=14):
    up = (high - high.shift(1)).clip(lower=0)
    down = (low.shift(1) - low).clip(lower=0)
    de_max = up.rolling(period).mean()
    de_min = down.rolling(period).mean()
    denom = (de_max + de_min).replace(0, np.nan)
    return de_max / denom


def _last_swing(high, low, depth=12):
    """ZigZag-style swing detection: finds if the last candle is a recent swing high or low."""
    if len(high) < depth:
        return None
    h = high.iloc[-depth:]
    l = low.iloc[-depth:]
    
    # Check for swing low (current low is the lowest in the window)
    if float(l.iloc[-1]) <= float(l.min()) * 1.0002:
        return "LOW"
    # Check for swing high (current high is the highest in the window)
    if float(h.iloc[-1]) >= float(h.max()) * 0.9998:
        return "HIGH"
    return None


def _find_swing_levels(high, low, lookback=30):
    """Identify the nearest significant support and resistance zones."""
    recent_high = high.tail(lookback)
    recent_low = low.tail(lookback)
    resistance = float(recent_high.max())
    support = float(recent_low.min())
    return support, resistance


def _closed_only(candles: pd.DataFrame) -> pd.DataFrame:
    """Drop the minute that is still forming so indicators cannot flip after the card is queued."""
    if candles is None or candles.empty:
        return candles
    now_bucket = pd.Timestamp.now(tz="UTC").floor("min")
    last = candles.index[-1]
    if getattr(last, "tzinfo", None) is None:
        last = last.tz_localize("UTC")
    if last >= now_bucket - pd.Timedelta(seconds=2):
        return candles.iloc[:-1]
    return candles


def fetch_candles(display_pair):
    return quotex_feed.get_candles(display_pair).dropna()


# ──────────────────────────────────────────────────────────────
#  MAIN ANALYZER
# ──────────────────────────────────────────────────────────────

def analyze_pair(display_pair):
    feed_symbol = quotex_feed.resolved_name(display_pair) or PAIR_MAP.get(display_pair)
    if not feed_symbol:
        raise ValueError("Pair not mapped")

    candles = _closed_only(fetch_candles(display_pair))
    if candles is None or len(candles) < 30:
        return None

    high = candles["High"]
    low = candles["Low"]
    close = candles["Close"]
    open_ = candles["Open"]

    # ── Calculate all indicators ──────────────────────────────
    ema9 = _ema(close, 9)
    ema21 = _ema(close, 21)
    rsi = _rsi(close, 14)
    dem = _demarker(high, low, 14)

    # ── Latest values ─────────────────────────────────────────
    last_close = float(close.iloc[-1])
    last_ema9 = float(ema9.iloc[-1])
    last_ema21 = float(ema21.iloc[-1])
    prev_ema9 = float(ema9.iloc[-2])
    prev_ema21 = float(ema21.iloc[-2])
    last_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
    last_dem = float(dem.iloc[-1]) if not pd.isna(dem.iloc[-1]) else 0.5
    prev_dem = float(dem.iloc[-2]) if not pd.isna(dem.iloc[-2]) else last_dem

    # ── Support / Resistance ──────────────────────────────────
    support, resistance = _find_swing_levels(high, low, 30)
    rng = resistance - support
    if rng <= 0 or last_close == 0:
        return None

    near_support = (last_close - support) / rng <= 0.18
    near_resistance = (resistance - last_close) / rng <= 0.18

    # ═══════════════════════════════════════════════════════════
    #  VOTING SYSTEM
    # ═══════════════════════════════════════════════════════════
    votes_call = 0
    votes_put = 0

    # ── 1. ZigZag swing + DeMarker 14 ─────────────────────────
    swing = _last_swing(high, low, 12)

    if swing == "LOW" and last_dem <= 0.30 and last_dem > prev_dem:
        votes_call += 2
    if swing == "HIGH" and last_dem >= 0.70 and last_dem < prev_dem:
        votes_put += 2
    if last_dem < 0.30 and last_dem > prev_dem:
        votes_call += 1
    if last_dem > 0.70 and last_dem < prev_dem:
        votes_put += 1

    # ── 2. EMA 9 / EMA 21 ─────────────────────────────────────
    if prev_ema9 <= prev_ema21 and last_ema9 > last_ema21:
        votes_call += 2
    if prev_ema9 >= prev_ema21 and last_ema9 < last_ema21:
        votes_put += 2
    if last_ema9 > last_ema21 and last_close > last_ema9:
        votes_call += 1
    if last_ema9 < last_ema21 and last_close < last_ema9:
        votes_put += 1

    # ── 3. RSI 14 + 30-candle support / resistance ────────────
    if near_support and last_rsi <= 30:
        votes_call += 2
    if near_resistance and last_rsi >= 70:
        votes_put += 2
    if last_rsi < 35:
        votes_call += 1
    if last_rsi > 65:
        votes_put += 1

    # ═══════════════════════════════════════════════════════════
    #  GATE RULES
    # ═══════════════════════════════════════════════════════════
    
    # Best side must have >= 3 votes
    best_votes = max(votes_call, votes_put)
    if best_votes < 3:
        return None

    # Gap must be >= 2
    if abs(votes_call - votes_put) < 2:
        return None

    # Determine Direction
    if votes_call > votes_put:
        direction = "CALL"
        trend = "BULLISH"
        raw_votes = votes_call
    else:
        direction = "PUT"
        trend = "BEARISH"
        raw_votes = votes_put

    # Confidence = min(92, 64 + votes * 4)
    confidence = int(min(92, 64 + raw_votes * 4))
    
    # Must be >= 68
    if confidence < 68:
        return None

    return Signal(
        display_pair=display_pair,
        feed_symbol=feed_symbol,
        direction=direction,
        trend=trend,
        confidence=confidence,
        support=support,
        resistance=resistance,
        entry_price=last_close,
        entry_time=datetime.now(KAMPALA).strftime("%H:%M"),
        candles=candles.tail(80).copy(),
    )


def grade(direction, open_price, close_price):
    if open_price is None or close_price is None or open_price == close_price:
        return "DOJI"
    up = close_price > open_price
    if direction == "CALL":
        return "WIN" if up else "LOSS"
    return "WIN" if not up else "LOSS"
