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


def _adx(high, low, close, period=14):
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    atr = _atr(high, low, close, period).replace(0, np.nan)
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(alpha=1/period, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(alpha=1/period, adjust=False).mean() / atr
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1/period, adjust=False).mean()


def _stochastic(high, low, close, k_period=14, d_period=3):
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


def _bollinger(close, period=20, std_dev=2):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    width = (upper - lower) / mid.replace(0, np.nan)
    return mid, upper, lower, width


def _demarker(high, low, period=14):
    up = (high - high.shift(1)).clip(lower=0)
    down = (low.shift(1) - low).clip(lower=0)
    de_max = up.rolling(period).mean()
    de_min = down.rolling(period).mean()
    denom = (de_max + de_min).replace(0, np.nan)
    return de_max / denom


def _candle_body(row):
    return abs(row["Close"] - row["Open"])


def _upper_wick(row):
    return row["High"] - max(row["Open"], row["Close"])


def _lower_wick(row):
    return min(row["Open"], row["Close"]) - row["Low"]


def _is_bullish_engulfing(prev, curr):
    return (curr["Close"] > curr["Open"] and
            prev["Close"] < prev["Open"] and
            curr["Close"] >= prev["Open"] and
            curr["Open"] <= prev["Close"])


def _is_bearish_engulfing(prev, curr):
    return (curr["Close"] < curr["Open"] and
            prev["Close"] > prev["Open"] and
            curr["Open"] >= prev["Close"] and
            curr["Close"] <= prev["Open"])


def _is_bullish_pin(row, atr):
    body = _candle_body(row)
    lower = _lower_wick(row)
    upper = _upper_wick(row)
    return (lower > body * 1.5 and
            lower > atr * 0.4 and
            upper < body * 0.6 and
            body > 0)


def _is_bearish_pin(row, atr):
    body = _candle_body(row)
    lower = _lower_wick(row)
    upper = _upper_wick(row)
    return (upper > body * 1.5 and
            upper > atr * 0.4 and
            lower < body * 0.6 and
            body > 0)


def _find_swing_levels(high, low, lookback=30):
    recent_high = high.tail(lookback)
    recent_low = low.tail(lookback)
    resistance = float(recent_high.max())
    support = float(recent_low.min())
    return support, resistance


def _is_near_level(price, level, atr, tolerance=0.5):
    return abs(price - level) <= atr * tolerance


def _closed_only(candles: pd.DataFrame) -> pd.DataFrame:
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
    if candles is None or len(candles) < 50:
        return None

    high = candles["High"]
    low = candles["Low"]
    close = candles["Close"]
    open_ = candles["Open"]

    ema9 = _ema(close, 9)
    ema21 = _ema(close, 21)
    ema50 = _ema(close, 50)
    rsi = _rsi(close, 14)
    atr = _atr(high, low, close, 14)
    adx = _adx(high, low, close, 14)
    stoch_k, stoch_d = _stochastic(high, low, close, 14, 3)
    bb_mid, bb_upper, bb_lower, bb_width = _bollinger(close, 20, 2)
    dem = _demarker(high, low, 14)

    last_close = float(close.iloc[-1])
    last_open = float(open_.iloc[-1])
    last_high = float(high.iloc[-1])
    last_low = float(low.iloc[-1])
    last_ema9 = float(ema9.iloc[-1])
    last_ema21 = float(ema21.iloc[-1])
    last_ema50 = float(ema50.iloc[-1])
    prev_ema9 = float(ema9.iloc[-2])
    prev_ema21 = float(ema21.iloc[-2])
    last_rsi = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
    last_atr = float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.0001
    last_adx = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 0.0
    last_stoch_k = float(stoch_k.iloc[-1]) if not pd.isna(stoch_k.iloc[-1]) else 50.0
    last_stoch_d = float(stoch_d.iloc[-1]) if not pd.isna(stoch_d.iloc[-1]) else 50.0
    last_bb_upper = float(bb_upper.iloc[-1]) if not pd.isna(bb_upper.iloc[-1]) else last_close
    last_bb_lower = float(bb_lower.iloc[-1]) if not pd.isna(bb_lower.iloc[-1]) else last_close
    last_bb_width = float(bb_width.iloc[-1]) if not pd.isna(bb_width.iloc[-1]) else 0.01
    last_dem = float(dem.iloc[-1]) if not pd.isna(dem.iloc[-1]) else 0.5
    prev_dem = float(dem.iloc[-2]) if not pd.isna(dem.iloc[-2]) else last_dem

    support, resistance = _find_swing_levels(high, low, 30)
    rng = resistance - support
    if rng <= 0 or last_close == 0:
        return None

    near_support = _is_near_level(last_close, support, last_atr, 0.5)
    near_resistance = _is_near_level(last_close, resistance, last_atr, 0.5)

    prev_row = candles.iloc[-2]
    curr_row = candles.iloc[-1]
    bull_engulf = _is_bullish_engulfing(prev_row, curr_row)
    bear_engulf = _is_bearish_engulfing(prev_row, curr_row)
    bull_pin = _is_bullish_pin(curr_row, last_atr)
    bear_pin = _is_bearish_pin(curr_row, last_atr)

    # LAYER 1: TREND FILTER (MANDATORY)
    if last_adx <= 20.0:
        return None

    # LAYER 2: DIRECTIONAL BIAS (MANDATORY)
    ema_bull_stack = last_ema9 > last_ema21 > last_ema50
    ema_bear_stack = last_ema9 < last_ema21 < last_ema50
    if not (ema_bull_stack or ema_bear_stack):
        return None

    # LAYER 3: MOMENTUM (MANDATORY)
    call_momentum = last_rsi < 45 and last_stoch_k < 35
    put_momentum = last_rsi > 55 and last_stoch_k > 65

    call_dem = last_dem < 0.40 and last_dem > prev_dem
    put_dem = last_dem > 0.60 and last_dem < prev_dem

    # LAYER 4: VOLATILITY (MANDATORY)
    if not (0.0005 < last_bb_width < 0.05):
        return None

    # LAYER 5: PRICE ACTION (RELAXED IN LIVE MODE)
    call_price_action = bull_engulf or bull_pin
    put_price_action = bear_engulf or bear_pin

    # LAYER 6: SUPPORT/RESISTANCE (RELAXED IN LIVE MODE)
    call_sr = near_support
    put_sr = near_resistance

    # ── FINAL VOTING ──────────────────────────────────────────
    call_score = 0
    if ema_bull_stack: call_score += 2
    if call_momentum: call_score += 2
    if call_dem: call_score += 2
    if call_price_action: call_score += 2
    if call_sr: call_score += 1
    if last_close <= last_bb_lower * 1.001: call_score += 1

    put_score = 0
    if ema_bear_stack: put_score += 2
    if put_momentum: put_score += 2
    if put_dem: put_score += 2
    if put_price_action: put_score += 2
    if put_sr: put_score += 1
    if last_close >= last_bb_upper * 0.999: put_score += 1

    # ── DECISION THRESHOLD (DYNAMIC) ──────────────────────────
    required_score = LIVE_SESSION_SCORE if live_mode else PASSIVE_SCORE
    
    if call_score >= required_score and call_score > put_score:
        direction = "CALL"
        trend = "BULLISH"
        raw = call_score
    elif put_score >= required_score and put_score > call_score:
        direction = "PUT"
        trend = "BEARISH"
        raw = put_score
    else:
        return None

    # ── CONFIDENCE CALCULATION ────────────────────────────────
    if live_mode:
        confidence = int(min(92, 64 + (raw - 6) * 7))
    else:
        confidence = int(min(92, 64 + (raw - 8) * 10))
        
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
