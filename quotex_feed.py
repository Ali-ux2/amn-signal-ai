"""Live Quotex OTC candle feed.

Runs inside the bot process as a background task. Keeps the last ~200
one-minute candles for every pair in memory, so analyze_pair() reads them
instantly instead of downloading anything.

Only _session() talks to pyquotex. If a pyquotex method name differs in
your installed version, that is the one place to fix.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import random
import threading
import time

import pandas as pd

from config import PAIR_MAP, QUOTEX_EMAIL, QUOTEX_PASSWORD

log = logging.getLogger("quotex")

PERIOD = 60             # candle size in seconds
KEEP = 200              # candles kept per pair
HISTORY_SECONDS = 6000  # ~100 candles of history fetched at start
STALE_AFTER = 30        # no tick for this long = pair is stale
DEAD_AFTER = 60         # no ticks on ANY pair for this long = reconnect
SESSION_MAX = 2 * 3600  # planned reconnect (pyquotex keeps every tick in memory)

_lock = threading.Lock()
_candles = {}    # asset -> {bucket_start: [open, high, low, close]}
_last_tick = {}  # asset -> time.time() when the last tick arrived
_state = {"connected": False, "reconnects": 0, "last_error": ""}


# ---------- candle store ----------

def _bucket(ts):
    ts = int(ts)
    return ts - ts % PERIOD


def _add_tick(asset, ts, price):
    now = time.time()
    if abs(ts - now) > 30:  # server clock or timezone oddity: trust our own clock
        ts = now
    t = _bucket(ts)
    with _lock:
        book = _candles.setdefault(asset, {})
        c = book.get(t)
        if c is None:
            book[t] = [price, price, price, price]
            for old in sorted(book)[:-KEEP]:
                del book[old]
        else:
            c[1] = max(c[1], price)
            c[2] = min(c[2], price)
            c[3] = price
        _last_tick[asset] = now


def _merge_history(asset, rows):
    """Turn whatever get_candles() returns into candles and merge them in."""
    built = {}
    ticks = []
    for r in rows or []:
        try:
            if isinstance(r, dict) and all(k in r for k in ("open", "high", "low", "close")):
                built[_bucket(float(r["time"]))] = [
                    float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
                ]
            elif isinstance(r, dict):
                ticks.append((float(r["time"]), float(r["price"])))
            elif len(r) in (2, 3):
                ticks.append((float(r[-2]), float(r[-1])))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    for ts, price in sorted(ticks):
        t = _bucket(ts)
        c = built.get(t)
        if c is None:
            built[t] = [price, price, price, price]
        else:
            c[1] = max(c[1], price)
            c[2] = min(c[2], price)
            c[3] = price
    if not built:
        return 0

    now_bucket = _bucket(time.time())
    off = max(built) - now_bucket
    if abs(off) > 300:  # history stamped in another timezone: realign it
        off = round(off / PERIOD) * PERIOD
        built = {t - off: c for t, c in built.items()}
        log.warning("history for %s was shifted by %ss, realigned", asset, off)

    with _lock:
        book = _candles.setdefault(asset, {})
        for t, c in built.items():
            old = book.get(t)
            if old is None or t < now_bucket:
                book[t] = c
            else:  # candle still forming: keep live close, widen the range
                book[t] = [c[0], max(c[1], old[1]), min(c[2], old[2]), old[3]]
        for old_t in sorted(book)[:-KEEP]:
            del book[old_t]
    return len(built)


# ---------- what the analyzer and bot use ----------

def get_candles(display_pair):
    """DataFrame with Open/High/Low/Close, oldest to newest (last one is still forming)."""
    asset = PAIR_MAP[display_pair]
    with _lock:
        book = {t: list(c) for t, c in _candles.get(asset, {}).items()}
        last = _last_tick.get(asset, 0.0)
    if not book:
        raise RuntimeError(f"no data for {asset}")
    if time.time() - last > STALE_AFTER:
        raise RuntimeError(f"stale feed for {asset}")
    keys = sorted(book)
    return pd.DataFrame(
        [book[k] for k in keys],
        columns=["Open", "High", "Low", "Close"],
        index=pd.to_datetime(keys, unit="s", utc=True),
    )


def is_ready():
    now = time.time()
    with _lock:
        return _state["connected"] and any(now - t <= STALE_AFTER for t in _last_tick.values())


def status_text():
    now = time.time()
    head = "🟢 Feed connected" if _state["connected"] else "🔴 Feed not connected"
    lines = [f"{head} (reconnects: {_state['reconnects']})"]
    if _state["last_error"]:
        lines.append(f"Last error: {_state['last_error'][:160]}")
    with _lock:
        for disp, asset in PAIR_MAP.items():
            n = len(_candles.get(asset, {}))
            seen = _last_tick.get(asset)
            tick = f"{int(now - seen)}s ago" if seen else "no ticks"
            lines.append(f"{disp}: {n} candles, {tick}")
    return "\n".join(lines)


# ---------- talking to Quotex ----------

async def _call(fn, *args):
    """pyquotex methods are sync in some versions and async in others. Handle both."""
    res = fn(*args)
    if inspect.isawaitable(res):
        res = await res
    return res


async def _session():
    try:
        from pyquotex.stable_api import Quotex
    except ImportError:
        from quotexapi.stable_api import Quotex  # older package name

    client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD, lang="en")
    ok, reason = await asyncio.wait_for(_call(client.connect), timeout=90)
    if not ok:
        raise RuntimeError(f"login failed: {reason}")
    _state["connected"] = True
    _state["last_error"] = ""
    log.info("Quotex connected")

    started = time.time()
    try:
        assets = list(PAIR_MAP.values())

        for a in assets:  # 1) history, so the analyzer has 30+ candles immediately
            try:
                rows = await asyncio.wait_for(
                    _call(client.get_candles, a, time.time(), HISTORY_SECONDS, PERIOD), timeout=20
                )
                log.info("history %s: %d candles", a, _merge_history(a, rows))
            except Exception as exc:
                log.warning("history %s failed: %r", a, exc)

        for a in assets:  # 2) live ticks
            try:
                await _call(client.start_realtime_price, a, PERIOD)
            except Exception as exc:
                log.warning("subscribe %s failed: %r", a, exc)

        last_seen = {}
        last_new = time.time()
        while time.time() - started < SESSION_MAX:
            for a in assets:
                ticks = await _call(client.get_realtime_price, a)
                new = []
                for tk in reversed(ticks or []):  # newest first, stop at what we already have
                    ts = float(tk["time"])
                    if ts <= last_seen.get(a, 0.0):
                        break
                    new.append((ts, float(tk["price"])))
                for ts, price in reversed(new):
                    _add_tick(a, ts, price)
                if new:
                    last_seen[a] = new[0][0]
                    last_new = time.time()
            if time.time() - last_new > DEAD_AFTER:
                raise RuntimeError("no ticks for 60s, socket looks dead")
            await asyncio.sleep(0.25)
    finally:
        _state["connected"] = False
        try:
            await asyncio.wait_for(_call(client.close), timeout=10)
        except Exception:
            pass


async def run_forever():
    if not (QUOTEX_EMAIL and QUOTEX_PASSWORD):
        _state["last_error"] = "QUOTEX_EMAIL / QUOTEX_PASSWORD not set in Railway Variables"
        log.error(_state["last_error"])
        return
    delay = 5
    while True:
        started = time.time()
        try:
            await _session()
        except asyncio.CancelledError:
            raise
        except (Exception, SystemExit) as exc:  # e.g. EOFError if login asks for a PIN
            _state["last_error"] = f"{type(exc).__name__}: {exc}"
            log.warning("feed error: %r", exc)
        _state["connected"] = False
        _state["reconnects"] += 1
        if time.time() - started > 120:
            delay = 5  # it was stable for a while, reset the backoff
        await asyncio.sleep(delay + random.random())
        delay = min(delay * 2, 120)
