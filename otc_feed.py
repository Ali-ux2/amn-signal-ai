"""
otc_feed.py — Live Quotex OTC feed via otcharts STREAM.
Includes historical warmup: fetches 50 candles on startup to eliminate the 30-minute wait.
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

_client = Client()

_cache_lock = threading.Lock()
_candles = {}      
_last_tick = {}    
_last_error = ""   
STALE_AFTER = 120


def resolved_name(display_pair):
    return PAIR_MAP.get(display_pair)


def _bucket(ts):
    ts = int(ts)
    return ts - ts % 60


def _merge_history(asset, bars):
    """Merge historical bars into the cache on startup."""
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
    return len(built)


def _add_tick(asset, ts, price):
    now = time.time()
    if ts is None:
        ts = now
    if abs(ts - now) > 30:
        ts = now
    t = _bucket(ts)
    with _cache_lock:
        book = _candles.setdefault(asset, {})
        c = book.get(t)
        if c is None:
            book[t] = [price, price, price, price]
            for old in sorted(book)[:-200]:
                del book[old]
        else:
            c[1] = max(c[1], price)
            c[2] = min(c[2], price)
            c[3] = price
        _last_tick[asset] = now


def get_candles(display_pair, limit=50):
    global _last_error
    asset = resolved_name(display_pair)
    if not asset:
        raise ValueError(f"Pair {display_pair} not mapped in PAIR_MAP")

    with _cache_lock:
        book = {t: list(c) for t, c in _candles.get(asset, {}).items()}
        last = _last_tick.get(asset, 0.0)

    if not book:
        _last_error = f"No stream data yet for {asset}"
        raise RuntimeError(_last_error)
    
    if time.time() - last > STALE_AFTER:
        _last_error = f"Stream stale for {asset} ({int(time.time() - last)}s)"
        raise RuntimeError(_last_error)

    keys = sorted(book)[-limit:]
    return pd.DataFrame(
        [book[k] for k in keys],
        columns=["Open", "High", "Low", "Close"],
        index=pd.to_datetime(keys, unit="s", utc=True),
    )


def candle_at(display_pair, epoch):
    asset = resolved_name(display_pair)
    if not asset:
        return None
    t = _bucket(epoch)
    with _cache_lock:
        row = _candles.get(asset, {}).get(t)
        return list(row) if row else None


def is_ready():
    now = time.time()
    with _cache_lock:
        return any(now - t <= STALE_AFTER for t in _last_tick.values())


def status_text():
    global _last_error
    now = time.time()
    with _cache_lock:
        has_fresh = any(now - t <= STALE_AFTER for t in _last_tick.values())
        has_data = any(len(df) > 0 for df in _candles.values())

    if has_fresh:
        head = "🟢 Stream connected"
    elif has_data:
        head = "🟡 Stream stale (data older than 120s)"
    else:
        head = "🔴 Stream not connected"

    lines = [f"{head} | source: otcharts STREAM"]
    
    if _last_error:
        lines.append(f"Last error: {_last_error}")

    with _cache_lock:
        for disp, asset in PAIR_MAP.items():
            book = _candles.get(asset, {})
            n = len(book)
            last = _last_tick.get(asset)
            age = f"{int(now - last)}s ago" if last else "no ticks"
            lines.append(f"{disp} → {asset}: {n} candles, {age}")

    return "\n".join(lines)


async def warmup():
    """Fetch historical candles on startup so the analyzer has data immediately."""
    log.info("Warming up with historical candles...")
    for display_pair, asset in PAIR_MAP.items():
        try:
            bars = await asyncio.to_thread(
                _client.candles, "quotex", asset, tf=60, limit=50
            )
            count = _merge_history(asset, bars)
            log.info(f"Warmed up {asset}: {count} historical candles loaded.")
        except Exception as exc:
            log.warning(f"Warmup failed for {asset}: {exc}")


async def _stream_one(display_pair, asset):
    """Run one background stream for a single instrument with auto-reconnect."""
    log.info(f"Starting stream for {display_pair} ({asset})...")
    tick_count = 0
    
    def _run():
        nonlocal tick_count
        for tick in _client.stream("quotex", asset):
            ts = getattr(tick, 'time', time.time())
            _add_tick(asset, ts, tick.price)
            tick_count += 1
            if tick_count % 10 == 0:
                log.info(f"Stream {asset}: {tick_count} ticks received. Last price: {tick.price}")

    while True:
        try:
            await asyncio.to_thread(_run)
        except TooManyStreams:
            log.error(f"TooManyStreams for {asset}. Free tier allows only 1 stream.")
            await asyncio.sleep(30)
        except Exception as exc:
            log.warning(f"Stream {asset} crashed: {exc}. Reconnecting in 10s...")
            await asyncio.sleep(10)


async def stream_loop():
    """Starts a background stream for every pair in PAIR_MAP."""
    log.info("Starting otcharts stream loop...")
    for display_pair, asset in PAIR_MAP.items():
        asyncio.create_task(_stream_one(display_pair, asset))
    while True:
        await asyncio.sleep(3600)


async def debug_api():
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
