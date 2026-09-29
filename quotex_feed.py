"""Live Quotex OTC candle feed.

Runs inside the bot process. Keeps the last ~200 one-minute candles per pair
in memory so analyze_pair() never downloads anything.

Only _session() talks to pyquotex. Asset names are resolved after login,
because Quotex sometimes lists these pairs as XXXUSD_otc instead of USDXXX_otc.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import random
import threading
import time

import pandas as pd

from config import PAIR_MAP, QUOTEX_EMAIL, QUOTEX_PASSWORD, QUOTEX_PROXY

log = logging.getLogger("quotex")

PERIOD = 60
KEEP = 200
HISTORY_SECONDS = 6000
STALE_AFTER = 45
DEAD_AFTER = 70
SESSION_MAX = 2 * 3600

HOSTS = [
    h.strip()
    for h in os.getenv(
        "QUOTEX_HOSTS", "qxbroker.com,quotex.io,qxbroker.io,quotex.com,qxbroker.sqldb.tc"
    ).split(",")
    if h.strip()
]
HOST_SWITCH_DELAY = 8
CYCLE_DELAY_START = 30

_lock = threading.Lock()
_candles = {}
_last_tick = {}
_resolved = {}  # display_pair -> live asset name
_state = {"connected": False, "reconnects": 0, "last_error": "", "host": "", "open": ""}


def _bucket(ts):
    ts = int(ts)
    return ts - ts % PERIOD


def resolved_name(display_pair):
    with _lock:
        return _resolved.get(display_pair) or PAIR_MAP.get(display_pair)


def _asset(display_pair):
    return resolved_name(display_pair)


def _add_tick(asset, ts, price):
    now = time.time()
    if abs(ts - now) > 30:
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
    built = {}
    ticks = []
    for r in rows or []:
        try:
            if isinstance(r, dict) and all(k in r for k in ("open", "high", "low", "close")):
                built[_bucket(float(r.get("time") or r.get("from") or 0))] = [
                    float(r["open"]),
                    float(r["high"]),
                    float(r["low"]),
                    float(r["close"]),
                ]
            elif isinstance(r, dict) and "price" in r:
                ticks.append((float(r.get("time") or r.get("from") or 0), float(r["price"])))
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
    if abs(off) > 300:
        off = round(off / PERIOD) * PERIOD
        built = {t - off: c for t, c in built.items()}
        log.warning("history for %s was shifted by %ss, realigned", asset, off)

    with _lock:
        book = _candles.setdefault(asset, {})
        for t, c in built.items():
            old = book.get(t)
            if old is None or t < now_bucket:
                book[t] = c
            else:
                book[t] = [c[0], max(c[1], old[1]), min(c[2], old[2]), old[3]]
        for old_t in sorted(book)[:-KEEP]:
            del book[old_t]
    return len(built)


def get_candles(display_pair):
    asset = _asset(display_pair)
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


def candle_at(display_pair, epoch):
    """Return (open, high, low, close) for the minute starting at epoch, or None."""
    asset = _asset(display_pair)
    t = _bucket(epoch)
    with _lock:
        row = _candles.get(asset, {}).get(t)
        return list(row) if row else None


def is_ready():
    now = time.time()
    with _lock:
        return _state["connected"] and any(now - t <= STALE_AFTER for t in _last_tick.values())


def status_text():
    now = time.time()
    head = "🟢 Feed connected" if _state["connected"] else "🔴 Feed not connected"
    proxy = "on" if QUOTEX_PROXY else "off"
    lines = [
        f"{head} | host: {_state['host'] or '-'} | proxy: {proxy} | reconnects: {_state['reconnects']}"
    ]
    if _state["last_error"]:
        lines.append(f"Last error: {_state['last_error'][:220]}")
    if _state["open"]:
        lines.append(f"Open: {_state['open'][:220]}")
    with _lock:
        for disp, asset in PAIR_MAP.items():
            live = _resolved.get(disp, asset)
            n = len(_candles.get(live, {}))
            seen = _last_tick.get(live)
            tick = f"{int(now - seen)}s ago" if seen else "no ticks"
            tag = "" if live == asset else f" → {live}"
            lines.append(f"{disp}{tag}: {n} candles, {tick}")
    return "\n".join(lines)


def _probe_one(url, impersonate):
    try:
        if impersonate:
            from curl_cffi import requests as cffi
            r = cffi.get(url, impersonate=impersonate, timeout=15)
        else:
            import httpx
            r = httpx.get(url, timeout=15, follow_redirects=True)
        challenge = r.headers.get("cf-mitigated") == "challenge" or "just a moment" in r.text[:4000].lower()
        note = "Cloudflare challenge" if challenge else ("page loaded" if r.status_code == 200 else "")
        return f"HTTP {r.status_code} {note}".strip()
    except ImportError as exc:
        return f"{exc.name or 'a module'} not installed"
    except Exception as exc:
        return f"{type(exc).__name__}: {str(exc)[:60]}"


async def probe_text():
    hosts = HOSTS[:3]
    jobs = []
    for h in hosts:
        url = f"https://{h}/en/sign-in"
        jobs.append(asyncio.to_thread(_probe_one, url, None))
        jobs.append(asyncio.to_thread(_probe_one, url, "chrome"))
    res = await asyncio.gather(*jobs)
    lines = ["Can this server load Quotex's sign-in page?"]
    for n, h in enumerate(hosts):
        lines.append(f"{h}\n  plain : {res[2 * n]}\n  chrome: {res[2 * n + 1]}")
    return "\n".join(lines)


async def _call(fn, *args, **kwargs):
    res = fn(*args, **kwargs)
    if inspect.isawaitable(res):
        res = await res
    return res


def _ticks_from(obj, tail=50):
    if obj is None:
        return []
    if isinstance(obj, dict):
        # start_realtime_price sometimes returns {asset: [ticks]}
        if "price" in obj or "time" in obj:
            obj = [obj]
        else:
            flat = []
            for value in obj.values():
                if isinstance(value, (list, tuple)):
                    flat.extend(value)
                elif isinstance(value, dict):
                    flat.append(value)
            obj = flat[-tail:]
    elif isinstance(obj, (list, tuple)):
        obj = obj[-tail:]
    else:
        return []
    out = []
    for tk in obj:
        try:
            if isinstance(tk, dict):
                price = tk.get("price", tk.get("close"))
                ts = tk.get("time", tk.get("from"))
                if price is None or ts is None:
                    continue
                out.append((float(ts), float(price)))
            else:
                out.append((float(tk[-2]), float(tk[-1])))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return out


def _candidates(asset):
    names = [asset]
    if asset.endswith("_otc") and len(asset) >= 10:
        base = asset[:-4]
        if len(base) == 6:
            names.append(base[3:] + base[:3] + "_otc")
    return names


async def _resolve_one(client, display, asset):
    for name in _candidates(asset):
        try:
            found = await asyncio.wait_for(
                _call(client.get_available_asset, name, True), timeout=20
            )
        except Exception as exc:
            log.warning("resolve %s via %s failed: %r", display, name, exc)
            continue
        if not found:
            continue
        live, data = found[0], found[1] if len(found) > 1 else None
        open_ok = False
        if isinstance(data, (list, tuple)) and len(data) >= 3:
            open_ok = bool(data[2])
        elif isinstance(data, dict):
            open_ok = bool(data.get("open", data.get("is_open", True)))
        if live:
            return str(live), open_ok or True
    return asset, False


async def _session(host):
    try:
        from pyquotex.stable_api import Quotex
    except ImportError:
        from quotexapi.stable_api import Quotex

    proxies = None
    if QUOTEX_PROXY:
        proxies = {"http": QUOTEX_PROXY, "https": QUOTEX_PROXY, "wss": QUOTEX_PROXY}
    try:
        client = Quotex(
            email=QUOTEX_EMAIL,
            password=QUOTEX_PASSWORD,
            lang="en",
            host=host,
            proxies=proxies,
        )
    except TypeError:
        client = Quotex(email=QUOTEX_EMAIL, password=QUOTEX_PASSWORD, lang="en")
        if proxies:
            log.warning("this pyquotex build has no proxies argument")
    ok, reason = await asyncio.wait_for(_call(client.connect), timeout=90)
    if not ok:
        raise RuntimeError(f"login failed: {reason}")
    _state["connected"] = True
    _state["last_error"] = ""
    log.info("Quotex connected via %s", host)

    started = time.time()
    try:
        opened = []
        for display, asset in PAIR_MAP.items():
            live, is_open = await _resolve_one(client, display, asset)
            with _lock:
                _resolved[display] = live
            if is_open:
                opened.append(display.replace("-OTC", ""))
            log.info("asset %s -> %s open=%s", display, live, is_open)
        _state["open"] = ", ".join(opened) if opened else "none resolved"

        assets = []
        for display in PAIR_MAP:
            live = resolved_name(display)
            if live not in assets:
                assets.append(live)

        for a in assets:
            try:
                rows = await asyncio.wait_for(
                    _call(client.get_candles, a, time.time(), HISTORY_SECONDS, PERIOD),
                    timeout=25,
                )
                log.info("history %s: %d candles", a, _merge_history(a, rows))
            except Exception as exc:
                log.warning("history %s failed: %r", a, exc)

        for a in assets:
            try:
                await asyncio.wait_for(_call(client.start_realtime_price, a, PERIOD), timeout=25)
            except Exception as exc:
                log.warning("subscribe %s failed: %r", a, exc)

        last_seen = {}
        last_new = time.time()
        while time.time() - started < SESSION_MAX:
            for a in assets:
                try:
                    raw = await _call(client.get_realtime_price, a)
                except Exception as exc:
                    log.warning("tick read %s failed: %r", a, exc)
                    continue
                ticks = _ticks_from(raw)
                new = []
                for ts, price in reversed(ticks):
                    if ts <= last_seen.get(a, 0.0):
                        break
                    new.append((ts, price))
                for ts, price in reversed(new):
                    _add_tick(a, ts, price)
                if new:
                    last_seen[a] = new[0][0]
                    last_new = time.time()
            if time.time() - last_new > DEAD_AFTER:
                raise RuntimeError("no ticks for 70s, socket looks dead")
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
    i = 0
    cycle_delay = CYCLE_DELAY_START
    while True:
        host = HOSTS[i % len(HOSTS)]
        _state["host"] = host
        started = time.time()
        try:
            await _session(host)
        except asyncio.CancelledError:
            raise
        except (Exception, SystemExit) as exc:
            _state["last_error"] = f"{host}: {type(exc).__name__}: {exc}"
            log.warning("feed error on %s: %r", host, exc)
        _state["connected"] = False
        _state["reconnects"] += 1

        if time.time() - started > 120:
            cycle_delay = CYCLE_DELAY_START
            await asyncio.sleep(5 + random.random())
            continue

        i += 1
        if i % len(HOSTS) == 0:
            await asyncio.sleep(cycle_delay + random.random())
            cycle_delay = min(cycle_delay * 2, 300)
        else:
            await asyncio.sleep(HOST_SWITCH_DELAY + random.random())
