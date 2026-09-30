"""
otc_feed.py — Live Quotex OTC feed via pyquotex with curl_cffi.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time

import pandas as pd

from config import PAIR_MAP, QUOTEX_EMAIL, QUOTEX_PASSWORD, QUOTEX_PROXY

try:
    from pyquotex.stable_api import Quotex
except ImportError:
    raise SystemExit("pyquotex not installed. Run: pip install 'pyquotex[fast] @ git+https://github.com/cleitonleonel/pyquotex.git'")

log = logging.getLogger("otc_feed")

_cache_lock = threading.Lock()
_candles = {}
_last_tick = {}
_client = None
_state = {"connected": False, "host": "qxbroker.com", "last_error": ""}

STALE_AFTER = 120


def resolved_name(display_pair):
    return PAIR_MAP.get(display_pair)


def _bucket(ts):
    ts = int(ts)
    return ts - ts % 60


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
    asset = resolved_name(display_pair)
    if not asset:
        raise ValueError(f"Pair {display_pair} not mapped in PAIR_MAP")

    with _cache_lock:
        book = {t: list(c) for t, c in _candles.get(asset, {}).items()}
        last = _last_tick.get(asset, 0.0)

    if not book:
        raise RuntimeError(f"No stream data yet for {asset}")
    
    if time.time() - last > STALE_AFTER:
        raise RuntimeError(f"Stream stale for {asset} ({int(time.time() - last)}s)")

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

    lines = [f"{head} | source: Quotex WS (pyquotex)"]
    if _state["last_error"]:
        lines.append(f"Last error: {_state['last_error']}")

    with _cache_lock:
        for disp, asset in PAIR_MAP.items():
            book = _candles.get(asset, {})
            n = len(book)
            last = _last_tick.get(asset)
            age = f"{int(now - last)}s ago" if last else "no ticks"
            lines.append(f"{disp} → {asset}: {n} candles, {age}")

    return "\n".join(lines)


async def _connect():
    global _client
    if _client:
        return True
    
    log.info(f"Connecting to Quotex via {QUOTEX_PROXY or 'direct connection'}...")
    
    proxies = None
    if QUOTEX_PROXY:
        proxies = {"http": QUOTEX_PROXY, "https": QUOTEX_PROXY, "wss": QUOTEX_PROXY}

    try:
        _client = Quotex(
            email=QUOTEX_EMAIL,
            password=QUOTEX_PASSWORD,
            lang="en",
            host="qxbroker.com",
            proxies=proxies,
        )
        ok, reason = await asyncio.wait_for(_client.connect(), timeout=90)
        if not ok:
            _state["last_error"] = f"Login failed: {reason}"
            log.error(_state["last_error"])
            _client = None
            return False
        
        _state["connected"] = True
        _state["last_error"] = ""
        log.info("Quotex connected successfully.")
        return True
    except Exception as exc:
        _state["last_error"] = f"{type(exc).__name__}: {exc}"
        log.error(f"Connection error: {_state['last_error']}")
        _client = None
        return False


async def _stream_one(display_pair, asset):
    while True:
        try:
            await _client.start_realtime_price(asset, 60)
            log.info(f"Subscribed to real-time prices for {asset}")
            while True:
                price = await _client.get_realtime_price(asset)
                if price:
                    _add_tick(asset, time.time(), float(price))
                await asyncio.sleep(0.5)
        except Exception as exc:
            log.warning(f"Stream {asset} crashed: {exc}. Reconnecting in 10s...")
            await asyncio.sleep(10)


async def _watchdog():
    while True:
        await asyncio.sleep(30)
        now = time.time()
        with _cache_lock:
            last = max(_last_tick.values()) if _last_tick else 0
            stale_time = int(now - last) if last > 0 else 0

        if stale_time > 90 and _state["connected"]:
            log.error(f"WATCHDOG: Stream stale for {stale_time}s. Reconnecting...")
            _state["connected"] = False
            if _client:
                try:
                    await _client.close()
                except:
                    pass
                _client = None
            await _connect()


async def stream_loop():
    while not await _connect():
        await asyncio.sleep(10)
    
    for display_pair, asset in PAIR_MAP.items():
        asyncio.create_task(_stream_one(display_pair, asset))
    
    asyncio.create_task(_watchdog())
    
    while True:
        await asyncio.sleep(3600)


async def debug_api():
    lines = ["🔍 <b>Quotex Debug Report</b>"]
    try:
        ok = await _connect()
        if ok:
            balance = await _client.get_balance()
            lines.append(f"✅ Connected! Balance: {balance}")
        else:
            lines.append(f"❌ Connection failed: {_state['last_error']}")
    except Exception as exc:
        lines.append(f"❌ <b>Error:</b> {type(exc).__name__}")
        lines.append(f"<code>{str(exc)}</code>")
    return "\n".join(lines)
