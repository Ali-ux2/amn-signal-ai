from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import otc_feed as quotex_feed
from config import CONFIDENCE_MIN, PAIR_MAP, LIVE_SESSION_SCORE, PASSIVE_SCORE

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


def _ema(close, period):
    return close.ewm(span=period, adjust=False).mean()


def _rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _candle_body(row):
    return abs(row["Close"] - row["Open"])


def _upper_wick(row):
    return row["High"] - max(row["Open"], row["Close"])


def _lower_wick(row):
    return min(row["Open"], row["Close"]) - row["Low"]


def _is_long_lower_rejection(row):
    """Long lower rejection wick (Hammer/Pin Bar)."""
    body = _candle_body(row)
    lower = _lower_wick(row)
    upper = _upper_wick(row)
    total_range = row["High"] - row["Low"]
    if total_range == 0:
        return False
    # Lower wick is at least 50% of total range, and larger than upper wick and body
    return (lower > total_range * 0.5 and 
            lower > upper * 1.5 and 
            lower > body)


def _is_long_upper_rejection(row):
    """Long upper rejection wick (Shooting Star/Pin Bar)."""
    body = _candle_body(row)
    lower = _lower_wick(row)
    upper = _upper_wick(row)
    total_range = row["High"] - row["Low"]
    if total_range == 0:
        return False
    # Upper wick is at least 50% of total range, and larger than lower wick and body
    return (upper > total_range * 0.5 and 
            upper > lower * 1.5 and 
            upper > body)


def _find_swing_levels(high, low, lookback=20):
    """Identify the nearest significant support and resistance zones."""
    recent_high = high.tail(lookback)
    recent_low = low.tail(lookback)
    resistance = float(recent_high.max())
    support = float(recent_low.min())
    return support, resistance


def _is_near_level(price, level, atr, tolerance=0.5):
    """Check if price is within tolerance * ATR of a key level."""
    return abs(price - level) <= atr * tolerance


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


def analyze_pair(display_pair, live_mode=False):
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

    # Indicators
    ema5 = _ema(close, 5)
    ema20 = _ema(close, 20)
    rsi = _rsi(close, 14)
    atr = _atr(high, low, close, 14)

    # Latest values
    last_close = float(close.iloc[-1])
    last_ema5 = float(ema5.iloc[-1])
    last_ema20 = float(ema20.iloc[-1])
    last_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
    prev_rsi = float(rsi.iloc[-2]) if not pd.isna(rsi.iloc[-2]) else 50.0
    last_atr = float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.0001

    # Support & Resistance
    support, resistance = _find_swing_levels(high, low, 20)
    rng = resistance - support
    if rng <= 0 or last_close == 0:
        return None

    near_support = _is_near_level(last_close, support, last_atr, 0.5)
    near_resistance = _is_near_level(last_close, resistance, last_atr, 0.5)

    # Candle Patterns
    curr_row = candles.iloc[-1]
    bull_rejection = _is_long_lower_rejection(curr_row)
    bear_rejection = _is_long_upper_rejection(curr_row)

    # ── 3-POINT REJECTION STRATEGY ───────────────────────────────────
    
    # CALL Entry Checklist:
    # 1. Price touches a key manual Support level.
    # 2. RSI is below 30 (Oversold) OR rising between 30-50.
    # 3. A long lower rejection wick forms on the 1-minute candle.
    # + EMA Trend Confirmation: Price > EMA 20 (Bullish context)
    
    call_conditions = 0
    if near_support: call_conditions += 1
    if last_rsi < 30 or (30 <= last_rsi <= 50 and last_rsi > prev_rsi):
        call_conditions += 1
    if bull_rejection: call_conditions += 1
    if last_close > last_ema20: call_conditions += 1

    # PUT Entry Checklist:
    # 1. Price touches a key manual Resistance level.
    # 2. RSI is above 70 (Overbought) OR falling between 50-70.
    # 3. A long upper rejection wick forms on the 1-minute candle.
    # + EMA Trend Confirmation: Price < EMA 20 (Bearish context)
    
    put_conditions = 0
    if near_resistance: put_conditions += 1
    if last_rsi > 70 or (50 <= last_rsi <= 70 and last_rsi < prev_rsi):
        put_conditions += 1
    if bear_rejection: put_conditions += 1
    if last_close < last_ema20: put_conditions += 1

    # ── DECISION THRESHOLD ──────────────────────────────────────────
    # Require all 3 primary conditions (S/R, RSI, Wick). 
    # The EMA confirmation is a bonus/trend filter.
    # In Live Mode, we allow 2 out of 3 if the EMA confirms strongly.
    
    required_base = 2 if live_mode else 3
    
    direction = None
    trend = None
    raw_score = 0

    if call_conditions >= required_base and call_conditions > put_conditions:
        direction = "CALL"
        trend = "BULLISH"
        raw_score = call_conditions
    elif put_conditions >= required_base and put_conditions > call_conditions:
        direction = "PUT"
        trend = "BEARISH"
        raw_score = put_conditions

    if direction is None:
        return None

    # ── CONFIDENCE CALCULATION ──────────────────────────────────────
    # Max score is 4 (S/R + RSI + Wick + EMA Trend)
    # We map 3/4 to 80% and 4/4 to 95%
    confidence = int(min(95, 65 + (raw_score - 3) * 15))
    if confidence < CONFIDENCE_MIN:
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
