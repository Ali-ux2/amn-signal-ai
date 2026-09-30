from __future__ import annotations
import asyncio
import logging
import os
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

def resolved_name(display_pair): return PAIR_MAP.get(display_pair)
def _bucket(ts): ts = int(ts); return ts - ts % 60

def _add_tick(asset, ts, price):
    now = time.time()
    ts = now if ts is None else ts
    if abs(ts - now) > 30: ts = now
    t = _bucket(ts)
    with _cache_lock:
        book = _candles.setdefault(asset, {})
        c = book.get(t)
        if c is None:
            book[t] = [price, price, price, price]
            for old in sorted(book)[:-200]: del book[old]
        else:
            c[1] = max(c[1], price); c[2] = min(c[2], price); c[3] = price
        _last_tick[asset] = now

def get_candles(display_pair, limit=50):
    global _last_error
    asset = resolved_name(display_pair)
    if not asset: raise ValueError(f"Pair {display_pair} not mapped")
    with _cache_lock:
        book = {t: list(c) for t, c in _candles.get(asset, {}).items()}
        last = _last_tick.get(asset, 0.0)
    if not book: _last_error = f"No stream data yet for {asset}"; raise RuntimeError(_last_error)
    if time.time() - last > STALE_AFTER: _last_error = f"Stale {asset}"; raise RuntimeError(_last_error)
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
    with _cache_lock: return any(now - t <= STALE_AFTER for t in _last_tick.values())

def status_text():
    global _last_error
    now = time.time()
    with _cache_lock: has_fresh = any(now - t <= STALE_AFTER for t in _last_tick.values())
    head = "🟢 Stream connected" if has_fresh else "🔴 Stream not connected"
    lines = [f"{head} | source: otcharts"]
    if _last_error: lines.append(f"Last error: {_last_error}")
    with _cache_lock:
        for disp, asset in PAIR_MAP.items():
            n = len(_candles.get(asset, {})); last = _last_tick.get(asset)
            age = f"{int(now - last)}s ago" if last else "no ticks"
            lines.append(f"{disp} → {asset}: {n} candles, {age}")
    return "\n".join(lines)

async def warmup():
    for display_pair, asset in PAIR_MAP.items():
        try:
            bars = await asyncio.to_thread(_client.candles, "quotex", asset, tf=60, limit=50)
            with _cache_lock:
                book = _candles.setdefault(asset, {})
                for b in bars:
                    book[_bucket(b.time)] = [float(b.open), float(b.high), float(b.low), float(b.close)]
                for old in sorted(book)[:-200]: del book[old]
            log.info(f"Warmed up {asset}")
        except Exception as e: log.warning(f"Warmup failed for {asset}: {e}")

async def _stream_one(display_pair, asset):
    log.info(f"Starting fresh stream for {asset}...")
    tick_count = 0
    def _run():
        nonlocal tick_count
        for tick in _client.stream("quotex", asset):
            _add_tick(asset, getattr(tick, 'time', time.time()), tick.price)
            tick_count += 1
            if tick_count % 10 == 0: log.info(f"Stream {asset}: {tick_count} ticks. Price: {tick.price}")
    while True:
        try: await asyncio.to_thread(_run)
        except Exception as exc:
            log.warning(f"Stream {asset} crashed: {exc}. Reconnecting in 10s...")
            await asyncio.sleep(10)

async def stream_loop():
    for dp, asset in PAIR_MAP.items(): asyncio.create_task(_stream_one(dp, asset))
    while True: await asyncio.sleep(3600)

async def debug_api():
    lines = ["🔍 <b>otcharts Debug Report</b>"]
    try:
        test_pair = list(PAIR_MAP.values())[0]
        bars = await asyncio.to_thread(_client.candles, "quotex", test_pair, tf=60, limit=1)
        lines.append(f"✅ API connected! Fetched {len(bars)} candle(s)." if bars else "⚠️ 0 candles.")
    except Exception as exc:
        lines.append(f"❌ <b>API Failed:</b> {type(exc).__name__}\n<code>{str(exc)}</code>")
    return "\n".join(lines)
