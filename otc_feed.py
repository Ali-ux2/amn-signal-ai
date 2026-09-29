"""
otc_feed.py — Live Quotex OTC candle feed via otcharts.
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

_cache_lock = threading.Lock()
_api_lock = threading.Lock()

_candles = {}      
_last_fetch = {}   
_last_error = ""   # <-- NEW: Capture errors for /feed
STALE_AFTER = 45   # 45 seconds


def resolved_name(display_pair):
    return PAIR_MAP.get(display_pair)


def get_candles(display_pair, limit=50):  # <-- CHANGED: 50 instead of 200
    global _last_error
    asset = resolved_name(display_pair)
    if not asset:
        raise ValueError(f"Pair {display_pair} not mapped in PAIR_MAP")

    with _cache_lock:
        df = _candles.get(asset)
        last = _last_fetch.get(asset, 0.0)
        if df is not None and (time.time() - last) < STALE_AFTER:
            return df.copy()

    with _api_lock:
        try:
            bars = _client.candles("quotex", asset, tf=60, limit=limit)
            _last_error = ""  # Clear error on success
        except QuotaExceeded:
            _last_error = "otcharts daily quota exceeded"
            raise RuntimeError(_last_error)
        except TooManyStreams:
            _last_error = "otcharts too many concurrent streams"
            raise RuntimeError(_last_error)
        except HouseBusy:
            _last_error = "otcharts venue busy, retry shortly"
            raise RuntimeError(_last_error)
        except PlanError:
            _last_error = "otcharts plan does not cover Quotex"
            raise RuntimeError(_last_error)
        except Exception as exc:
            _last_error = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(f"otcharts API error: {_last_error}")

    if not bars:
        _last_error = f"otcharts returned no candles for {asset}"
        raise RuntimeError(_last_error)

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

    with _cache_lock:
        _candles[asset] = new_df
        _last_fetch[asset] = time.time()

    return new_df.copy()


def is_ready():
    now = time.time()
    with _cache_lock:
        return any(now - t <= STALE_AFTER for t in _last_fetch.values())


def candle_at(display_pair, epoch):
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
    global _last_error
    now = time.time()
    with _cache_lock:
        has_fresh = any(now - t <= STALE_AFTER for t in _last_fetch.values())

    head = "🟢 Feed connected" if has_fresh else "🔴 Feed not connected"
    lines = [f"{head} | source: otcharts (HTTP)"]
    
    if _last_error:
        lines.append(f"Last error: {_last_error}")  # <-- NEW: Shows error in /feed

    with _cache_lock:
        for disp, asset in PAIR_MAP.items():
            df = _candles.get(asset)
            n = len(df) if df is not None else 0
            last = _last_fetch.get(asset)
            age = f"{int(now - last)}s ago" if last else "not fetched"
            lines.append(f"{disp} → {asset}: {n} candles, {age}")

    return "\n".join(lines)


async def warmup():
    log.info("Starting otcharts warmup...")
    for display_pair in PAIR_MAP:
        try:
            await asyncio.to_thread(get_candles, display_pair)
            log.info("Warmed up %s", display_pair)
            await asyncio.sleep(1.5)  # <-- NEW: 1.5s delay to avoid rate limits
        except Exception as exc:
            log.warning("Warmup failed for %s: %s", display_pair, exc)


async def debug_api():
    """Test the API connection and return the exact error message."""
    lines = ["🔍 <b>otcharts Debug Report</b>"]
    try:
        test_pair = list(PAIR_MAP.values())[0]
        lines.append(f"Testing API with symbol: <code>{test_pair}</code>")
        
        bars = await asyncio.to_thread(_client.candles, "quotex", test_pair, tf=60, limit=1)
        
        if not bars:
            lines.append("⚠️ API connected, but returned <b>0 candles</b>.")
        else:
            lines.append(f"✅ API connected! Fetched {len(bars)} candle(s).")
            lines.append(f"Price: {bars[0].close}")
            
    except Exception as exc:
        lines.append(f"❌ <b>API Failed:</b> {type(exc).__name__}")
        lines.append(f"<code>{str(exc)}</code>")
        
    return "\n".join(lines)
