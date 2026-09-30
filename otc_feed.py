"""
otc_feed.py — Live Quotex OTC feed via otcharts (Polling Version).
"""
from __future__ import annotations
import asyncio
import logging
import os
import threading
import time
import pandas as pd
from config import PAIR_MAP, POLL_INTERVAL_SECONDS

try:
    from otcharts import Client
    from otcharts import QuotaExceeded, TooManyStreams, HouseBusy, PlanError
except ImportError:
    raise SystemExit("otcharts not installed. Run: pip install 'otcharts[pandas]'")

log = logging.getLogger("otc_feed")
_client = Client()
_cache_lock = threading.Lock()
_candles = {}
_last_fetch = {}  # asset -> timestamp of last successful fetch
_last_error = ""
STALE_AFTER = 180  # Allow 3 minutes before declaring stale, since polling is slower

def resolved_name(display_pair): return PAIR_MAP.get(display_pair)
def _bucket(ts): ts = int(ts); return ts - ts % 60

def _merge_history(asset, bars):
    """Merge historical bars into the cache."""
    built = {}
    for b in bars:
        try:
            t = _bucket(b.time)
            built[t] = [float(b.open), float(b.high), float(b.low), float(b.close)]
        except Exception:
            continue
    if not built:
        return 0
    with _cache_lock:
        book = _candles.setdefault(asset, {})
        for t, c in built.items():
            book[t] = c
        for old in sorted(book)[:-200]:
            del book[old]
        _last_fetch[asset] = time.time()
    return len(built)

def get_candles(display_pair, limit=50):
    global _last_error
    asset = resolved_name(display_pair)
    if not asset: raise ValueError(f"Pair {display_pair} not mapped")
    with _cache_lock:
        book = {t: list(c) for t, c in _candles.get(asset, {}).items()}
        last = _last_fetch.get(asset, 0.0)
    if not book:
        _last_error = f"No data yet for {asset}"
        raise RuntimeError(_last_error)
    if time.time() - last > STALE_AFTER:
        _last_error = f"Data stale for {asset} ({int(time.time() - last)}s)"
        raise RuntimeError(_last_error)
    keys = sorted(book)[-limit:]
    return pd.DataFrame([book[k] for k in keys], columns=["Open","High","Low","Close"], index=pd.to_datetime(keys, unit="s", utc=True))

def candle_at(display_pair, epoch):
    asset = resolved_name(display_pair)
    if not asset: return None
    t = _bucket(epoch)
    with _cache_lock:
        row = _candles.get(asset, {}).get(t)
        return list(row) if row else None

def is_ready():
    now = time.time()
    with _cache_lock:
        return any(now - t <= STALE_AFTER for t in _last_fetch.values())

def status_text():
    global _last_error
    now = time.time()
    with _cache_lock:
        has_fresh = any(now - t <= STALE_AFTER for t in _last_fetch.values())
    head = "🟢 API connected" if has_fresh else "🔴 API not connected"
    lines = [f"{head} | source: otcharts (POLLING)"]
    if _last_error: lines.append(f"Last error: {_last_error}")
    with _cache_lock:
        for disp, asset in PAIR_MAP.items():
            n = len(_candles.get(asset, {})); last = _last_fetch.get(asset)
            age = f"{int(now - last)}s ago" if last else "not fetched"
            lines.append(f"{disp} → {asset}: {n} candles, {age}")
    return "\n".join(lines)

async def warmup():
    log.info("Warming up with historical candles...")
    for display_pair, asset in PAIR_MAP.items():
        try:
            bars = await asyncio.to_thread(_client.candles, "quotex", asset, tf=60, limit=50)
            count = _merge_history(asset, bars)
            log.info(f"Warmed up {asset}: {count} candles.")
        except Exception as e:
            log.warning(f"Warmup failed for {asset}: {e}")

async def _poll_one(display_pair, asset):
    """Fetch candles for a single asset at a set interval."""
    while True:
        try:
            bars = await asyncio.to_thread(_client.candles, "quotex", asset, tf=60, limit=50)
            _merge_history(asset, bars)
            log.info(f"Polled {asset}: {len(bars)} candles.")
        except Exception as exc:
            log.warning(f"Polling {asset} failed: {exc}")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

async def poll_loop():
    log.info(f"Starting polling loop every {POLL_INTERVAL_SECONDS} seconds...")
    for display_pair, asset in PAIR_MAP.items():
        asyncio.create_task(_poll_one(display_pair, asset))
    while True:
        await asyncio.sleep(3600)

async def debug_api():
    lines = ["🔍 <b>otcharts Debug Report</b>"]
    try:
        test_pair = list(PAIR_MAP.values())[0]
        bars = await asyncio.to_thread(_client.candles, "quotex", test_pair, tf=60, limit=1)
        lines.append(f"✅ API connected! Fetched {len(bars)} candle(s)." if bars else "⚠️ 0 candles.")
    except Exception as exc:
        lines.append(f"❌ <b>API Failed:</b> {type(exc).__name__}\n<code>{str(exc)}</code>")
    return "\n".join(lines)
