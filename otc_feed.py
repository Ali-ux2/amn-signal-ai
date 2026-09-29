"""
otc_feed.py — Live Quotex OTC candle feed via otcharts.
Drop-in replacement for the quotex_feed.py data-fetching layer.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time

import pandas as pd

from config import PAIR_MAP

try:
    from otcharts import Client
    from otcharts import QuotaExceeded, TooManyStreams, HouseBusy, PlanError
except ImportError:
    raise SystemExit("otcharts not installed. Run: pip install 'otcharts[pandas]'")

log = logging.getLogger("otc_feed")

# Client reads OTCHARTS_API_KEY from environment automatically.
_client = Client()

# Locks
_cache_lock = threading.Lock()
_api_lock = threading.Lock()

_candles = {}      # asset -> DataFrame
_last_fetch = {}   # asset -> timestamp
STALE_AFTER = 45   # seconds


def resolved_name(display_pair):
    """Your config.py maps display pairs to otcharts symbols."""
    return PAIR_MAP.get(display_pair)


def get_candles(display_pair, limit=200):
    """
    Fetch the most recent closed 1-minute candles for a Quotex OTC pair.
    Returns a pandas DataFrame with Open, High, Low, Close and a DatetimeIndex.
    Uses a short-lived cache to avoid hammering the API.
    """
    asset = resolved_name(display_pair)
    if not asset:
        raise ValueError(f"Pair {display_pair} not mapped in PAIR_MAP")

    # 1. Check cache first
    with _cache_lock:
        df = _candles.get(asset)
        last = _last_fetch.get(asset, 0.0)
        if df is not None and (time.time() - last) < STALE_AFTER:
            return df.copy()

    # 2. Fetch from API (only one thread at a time)
    with _api_lock:
        try:
            bars = _client.candles("quotex", asset, tf=60, limit=limit)
        except QuotaExceeded:
            raise RuntimeError("otcharts daily quota exceeded")
        except TooManyStreams:
            raise RuntimeError("otcharts too many concurrent streams")
        except HouseBusy:
            raise RuntimeError("otcharts venue busy, retry shortly")
        except PlanError:
            raise RuntimeError("otcharts plan does not cover Quotex")
        except Exception as exc:
            raise RuntimeError(f"otcharts API error: {type(exc).__name__}: {exc}")

    if not bars:
        raise RuntimeError(f"otcharts returned no candles for {asset}")

    # 3. Build DataFrame
    rows = [
        {
            "time": pd.Timestamp(b.time, unit="s", tz="UTC"),
            "Open": float(b.open),
            "High": float(b.high),
            "Low": float(b.low),
            "Close": float(b.close),
        }
        for b in bars
    ]
    new_df = pd.DataFrame(rows).set_index("time").sort_index()

    # 4. Update cache
    with _cache_lock:
        _candles[asset] = new_df
        _last_fetch[asset] = time.time()

    return new_df.copy()


def is_ready():
    """True if at least one pair has fresh data."""
    now = time.time()
    with _cache_lock:
        return any(now - t <= STALE_AFTER for t in _last_fetch.values())


def candle_at(display_pair, epoch):
    """
    Return (open, high, low, close) for the minute starting at epoch, or None.
    Used by bot.py's follow_result() to grade a signal.
    """
    asset = resolved_name(display_pair)
    if not asset:
        return None

    with _cache_lock:
        df = _candles.get(asset)

    if df is None or df.empty:
        try:
            df = get_candles(display_pair)
        except Exception:
            return None

    ts = pd.Timestamp(epoch, unit="s", tz="UTC").floor("min")
    if ts not in df.index:
        try:
            df = get_candles(display_pair)
        except Exception:
            return None
        if ts not in df.index:
            return None

    row = df.loc[ts]
    return [float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])]


def status_text():
    """Status for /feed command."""
    now = time.time()
    with _cache_lock:
        has_fresh = any(now - t <= STALE_AFTER for t in _last_fetch.values())

    head = "🟢 Feed connected" if has_fresh else "🔴 Feed not connected"
    lines = [f"{head} | source: otcharts (HTTP)"]

    with _cache_lock:
        for disp, asset in PAIR_MAP.items():
            df = _candles.get(asset)
            n = len(df) if df is not None else 0
            last = _last_fetch.get(asset)
            age = f"{int(now - last)}s ago" if last else "not fetched"
            lines.append(f"{disp} → {asset}: {n} candles, {age}")

    return "\n".join(lines)


async def warmup():
    """Force a fetch for all pairs on startup to populate the cache."""
    log.info("Starting otcharts warmup...")
    for display_pair in PAIR_MAP:
        try:
            await asyncio.to_thread(get_candles, display_pair)
            log.info("Warmed up %s", display_pair)
        except Exception as exc:
            log.warning("Warmup failed for %s: %s", display_pair, exc)
