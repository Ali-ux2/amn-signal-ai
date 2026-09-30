from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import otc_feed as quotex_feed
from config import CONFIDENCE_MIN, PAIR_MAP

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


def _rsi(close, period=9):
    """RSI with period 9 as specified in the strategy."""
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


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

    # ── Indicators ──────────────────────────────────────────────
    ema5 = _ema(close, 5)
    ema20 = _ema(close, 20)
    rsi9 = _rsi(close, 9)

    # Latest values
    curr_close = float(close.iloc[-1])
    curr_open = float(open_.iloc[-1])
    curr_ema5 = float(ema5.iloc[-1])
    curr_ema20 = float(ema20.iloc[-1])
    curr_rsi = float(rsi9.iloc[-1]) if not pd.isna(rsi9.iloc[-1]) else 50.0

    # Previous values for cross detection
    prev_ema5 = float(ema5.iloc[-2])
    prev_ema20 = float(ema20.iloc[-2])
    prev_rsi = float(rsi9.iloc[-2]) if not pd.isna(rsi9.iloc[-2]) else 50.0

    # For S/R fields in the dataclass (not used for entry, just for the chart)
    support = float(low.tail(20).min())
    resistance = float(high.tail(20).max())

    # ═══════════════════════════════════════════════════════════
    #  STRATEGY RULES
    # ═══════════════════════════════════════════════════════════

    # ── CALL (BUY) RULES ──────────────────────────────────────
    # 1. Trend: EMA 5 crosses cleanly above EMA 20.
    call_trend = (curr_ema5 > curr_ema20) and (prev_ema5 <= prev_ema20)
    
    # 2. Momentum: RSI (9) pointing upward and crossing above 50, but not yet overbought (>70).
    call_momentum = (curr_rsi > 50) and (prev_rsi <= 50) and (curr_rsi > prev_rsi) and (curr_rsi < 70)
    
    # 3. Entry: Green candle closes cleanly above both EMAs.
    call_entry = (curr_close > curr_open) and (curr_close > curr_ema5) and (curr_close > curr_ema20)

    # ── PUT (SELL) RULES ──────────────────────────────────────
    # 1. Trend: EMA 5 crosses cleanly below EMA 20.
    put_trend = (curr_ema5 < curr_ema20) and (prev_ema5 >= prev_ema20)
    
    # 2. Momentum: RSI (9) pointing downward and crossing below 50, but not yet oversold (<30).
    put_momentum = (curr_rsi < 50) and (prev_rsi >= 50) and (curr_rsi < prev_rsi) and (curr_rsi > 30)
    
    # 3. Entry: Red candle closes cleanly below both EMAs.
    put_entry = (curr_close < curr_open) and (curr_close < curr_ema5) and (curr_close < curr_ema20)

    # ═══════════════════════════════════════════════════════════
    #  DECISION THRESHOLD
    # ═══════════════════════════════════════════════════════════
    direction = None
    trend = None

    # CALL requires all 3 conditions to align perfectly.
    if call_trend and call_momentum and call_entry:
        direction = "CALL"
        trend = "BULLISH"
    
    # PUT requires all 3 conditions to align perfectly.
    elif put_trend and put_momentum and put_entry:
        direction = "PUT"
        trend = "BEARISH"

    if direction is None:
        return None

    # ── CONFIDENCE CALCULATION ────────────────────────────────
    # Since this is a strict 3-rule strategy, a match earns a high base confidence.
    # We boost confidence slightly based on how strong the momentum is.
    base_confidence = 82
    
    if direction == "CALL":
        # Bonus if RSI is strongly rising or EMA cross is very recent
        if curr_rsi - prev_rsi > 5: base_confidence += 5
        if curr_ema5 - curr_ema20 > (curr_close * 0.0005): base_confidence += 5
    else:
        # Bonus if RSI is strongly falling
        if prev_rsi - curr_rsi > 5: base_confidence += 5
        if curr_ema20 - curr_ema5 > (curr_close * 0.0005): base_confidence += 5

    confidence = int(min(95, base_confidence))
    
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
        entry_price=curr_close,
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
