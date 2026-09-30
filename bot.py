from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler

import otc_feed as quotex_feed
from analyzer import Signal, analyze_pair, grade
from config import (ADMIN_USER_ID, BOT_TOKEN, BRAND, CHANNEL, CONTACT, 
                    PAIR_MAP, PAYOUT_DISPLAY)

KAMPALA = ZoneInfo("Africa/Kampala")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("amn")
LEAD_SECONDS = 8
PAUSE_AFTER_SEND = 120
SCAN_CAP = 90
_busy_until = 0.0
NOTIFY_CHAT = None
AUTO_ON = True

LIVE_MODE = False
LIVE_SESSION_END = 0.0


def _pretty_pair(display_pair):
    raw = display_pair.replace("-OTC", "")
    if raw.startswith("USD") and "/" not in raw and len(raw) > 3:
        return "USD/" + raw[3:] + "-OTC"
    return display_pair


def format_signal_caption(sig, test=False):
    arrow = "🟢 CALL ↑" if sig.direction == "CALL" else "🔴 PUT ↓"
    name = _pretty_pair(sig.display_pair)
    head = "🧪 <b>TEST card</b> — do not trade" if test else "🚀 <b>Signal ready</b>"
    return (
        f"{head}\n"
        f"<b>{name}</b>\n\n"
        f"———— {{ {BRAND} }} ————\n\n"
        f"📊 Asset        : {name}\n"
        f"📈 Trend        : {sig.trend}\n"
        f"Direction       : {arrow}\n"
        f"⏳ Timeframe    : M1\n"
        f"🕒 Entry Time   : {sig.entry_time}\n"
        f"💰 Payout       : {PAYOUT_DISPLAY}\n\n"
        f"———————\n"
        f"✨ AI Confidence : {sig.confidence}%\n"
        f"🚨 MTG           : FLAT BET ONLY\n"
        f"———————\n"
        f"💬 CONTACT : {CONTACT}"
    )


def _mark_busy():
    global _busy_until
    _busy_until = time.time() + SCAN_CAP


def _clear_busy():
    global _busy_until
    _busy_until = 0.0


def _is_busy():
    return time.time() < _busy_until


def _allowed(update):
    if not ADMIN_USER_ID:
        return True
    user = update.effective_user
    return bool(user and user.id == ADMIN_USER_ID)


async def wait_for_next_candle():
    now = datetime.now(KAMPALA)
    entry = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    fire_at = entry - timedelta(seconds=LEAD_SECONDS)
    if now >= fire_at:
        entry = entry + timedelta(minutes=1)
        fire_at = entry - timedelta(seconds=LEAD_SECONDS)
    wait = max(1.0, (fire_at - datetime.now(KAMPALA)).total_seconds())
    return wait, entry


async def pick_best(live_mode=False):
    best = None
    for pair in PAIR_MAP.keys():
        try:
            cand = await asyncio.wait_for(asyncio.to_thread(analyze_pair, pair, live_mode), timeout=12)
        except Exception:
            continue
        if cand is None:
            continue
        if best is None or cand.confidence > best.confidence:
            best = cand
    return best


async def notify(bot, text):
    if not NOTIFY_CHAT:
        return
    try:
        await bot.send_message(chat_id=NOTIFY_CHAT, text=text)
    except Exception as exc:
        log.warning("notify failed: %s", exc)


async def post_card(bot, sig, entry_time, test=False):
    sig.entry_time = entry_time
    caption = format_signal_caption(sig, test=test)
    from chart import render_chart
    photo = await asyncio.to_thread(render_chart, sig, test)
    msg = await bot.send_photo(
        chat_id=CHANNEL, photo=photo, caption=caption, parse_mode=ParseMode.HTML
    )
    return msg


def _result_text(sig, open_price, close_price):
    name = _pretty_pair(sig.display_pair)
    verdict = grade(sig.direction, open_price, close_price)
    mark = {"WIN": "✅ WIN", "LOSS": "❌ LOSS", "DOJI": "⚪ DOJI"}.get(verdict, "⚪ SKIP")
    arrow = "CALL ↑" if sig.direction == "CALL" else "PUT ↓"
    return (
        f"{mark}  <b>{name}</b>\n"
        f"{arrow}  ·  {sig.entry_time}\n"
        f"Open {open_price:.5f}  →  Close {close_price:.5f}"
    )


async def follow_result(bot, sig, entry):
    try:
        close_at = entry + timedelta(seconds=68)
        wait = (close_at - datetime.now(KAMPALA)).total_seconds()
        if wait > 0:
            await asyncio.sleep(wait)
        row = quotex_feed.candle_at(sig.display_pair, entry.timestamp())
        if not row:
            await bot.send_message(
                chat_id=CHANNEL,
                text=f"⚪ Result missed for {_pretty_pair(sig.display_pair)} {sig.entry_time}. Feed had no close.",
            )
            return
        open_price, _, _, close_price = row
        await bot.send_message(
            chat_id=CHANNEL,
            text=_result_text(sig, open_price, close_price),
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        log.warning("result follow-up failed: %s", exc)


async def start(update, context):
    global NOTIFY_CHAT
    NOTIFY_CHAT = update.effective_chat.id
    state = "ON" if AUTO_ON else "PAUSED"
    live_state = "ACTIVE" if LIVE_MODE else "OFF"
    await update.message.reply_text(
        f"{BRAND} online.\nChannel: {CHANNEL}\nAuto: {state}\nLive Mode: {live_state}\n"
        "/pause  /resume  /live  /signal  /testcard  /feed  /debug  /pairs"
    )


async def pause_cmd(update, context):
    global AUTO_ON, NOTIFY_CHAT
    NOTIFY_CHAT = update.effective_chat.id
    if not _allowed(update):
        await update.message.reply_text("Not allowed.")
        return
    AUTO_ON = False
    await update.message.reply_text("Auto PAUSED. /signal still works. /resume to start auto.")


async def resume_cmd(update, context):
    global AUTO_ON, NOTIFY_CHAT
    NOTIFY_CHAT = update.effective_chat.id
    if not _allowed(update):
        await update.message.reply_text("Not allowed.")
        return
    AUTO_ON = True
    await update.message.reply_text("Auto ON. Next scan in about 1–2 minutes.")


async def live_cmd(update, context):
    global LIVE_MODE, LIVE_SESSION_END, NOTIFY_CHAT
    NOTIFY_CHAT = update.effective_chat.id
    if not _allowed(update):
        await update.message.reply_text("Not allowed.")
        return
    try:
        duration_min = int(context.args[0]) if context.args else 60
    except ValueError:
        duration_min = 60
    LIVE_MODE = True
    LIVE_SESSION_END = time.time() + (duration_min * 60)
    await update.message.reply_text(
        f"🔴 LIVE SESSION STARTED.\n"
        f"Duration: {duration_min} minutes.\n"
        f"Threshold lowered to 6/10. Scanning all pairs every 90 seconds.\n"
        f"Bot will automatically revert to Sniper mode when time is up."
    )


async def pairs_cmd(update, context):
    global NOTIFY_CHAT
    NOTIFY_CHAT = update.effective_chat.id
    lines = []
    for p in PAIR_MAP:
        live = quotex_feed.resolved_name(p)
        lines.append(f"{_pretty_pair(p)}  ({live})")
    await update.message.reply_text("\n".join(lines))


async def feed_cmd(update, context):
    global NOTIFY_CHAT
    NOTIFY_CHAT = update.effective_chat.id
    await update.message.reply_text(quotex_feed.status_text())


async def debug_cmd(update, context):
    global NOTIFY_CHAT
    NOTIFY_CHAT = update.effective_chat.id
    if not _allowed(update):
        await update.message.reply_text("Not allowed.")
        return
    msg = await update.message.reply_text("Testing otcharts API...")
    report = await quotex_feed.debug_api()
    await msg.edit_text(report, parse_mode=ParseMode.HTML)


async def _sample_signal():
    for pair in PAIR_MAP:
        try:
            candles = quotex_feed.get_candles(pair)
        except Exception:
            continue
        if len(candles) < 5:
            continue
        closed = candles.iloc[:-1] if len(candles) > 8 else candles
        last = float(closed["Close"].iloc[-1])
        prev = float(closed["Close"].iloc[-2])
        direction = "CALL" if last >= prev else "PUT"
        return Signal(
            display_pair=pair,
            feed_symbol=quotex_feed.resolved_name(pair),
            direction=direction,
            trend="BULLISH" if direction == "CALL" else "BEARISH",
            confidence=74,
            support=float(closed["Low"].tail(30).min()),
            resistance=float(closed["High"].tail(30).max()),
            entry_price=last,
            entry_time=datetime.now(KAMPALA).strftime("%H:%M"),
            candles=closed.tail(80).copy(),
        )
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(7)
    price = 83.4 + rng.normal(0, 0.04, 40).cumsum()
    frame = pd.DataFrame(
        {
            "Open": price,
            "High": price + 0.03,
            "Low": price - 0.03,
            "Close": price + rng.normal(0, 0.01, 40),
        },
        index=pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=40, freq="min"),
    )
    return Signal(
        display_pair="EURUSD-OTC",
        feed_symbol="EURUSD_otc",
        direction="CALL",
        trend="BULLISH",
        confidence=74,
        support=float(frame["Low"].min()),
        resistance=float(frame["High"].max()),
        entry_price=float(frame["Close"].iloc[-1]),
        entry_time=datetime.now(KAMPALA).strftime("%H:%M"),
        candles=frame,
    )


async def testcard_cmd(update, context):
    global NOTIFY_CHAT
    NOTIFY_CHAT = update.effective_chat.id
    if not _allowed(update):
        await update.message.reply_text("Not allowed.")
        return
    msg = await update.message.reply_text("Building test card...")
    try:
        sig = await _sample_signal()
        entry = datetime.now(KAMPALA).strftime("%H:%M")
        await post_card(context.bot, sig, entry, test=True)
        await msg.edit_text(f"Test card sent to {CHANNEL}. Do not trade it.")
    except Exception as exc:
        await msg.edit_text(f"Test card failed: {type(exc).__name__}: {exc}")


async def signal_cmd(update, context):
    global NOTIFY_CHAT
    NOTIFY_CHAT = update.effective_chat.id
    if not _allowed(update):
        await update.message.reply_text("Not allowed.")
        return
    if _is_busy():
        left = int(_busy_until - time.time())
        await update.message.reply_text(f"Scan running. Wait ~{max(1, left)}s.")
        return
    _mark_busy()
    try:
        wait_s, entry = await wait_for_next_candle()
        status = await update.message.reply_text(
            f"Waiting for next M1.\nEntry {entry.strftime('%H:%M')}.\n{int(wait_s)}s..."
        )
        await asyncio.sleep(wait_s)
        if not quotex_feed.is_ready():
            await status.edit_text("🔴 Feed is offline. No ticks received yet. Check /feed.")
            return
        best = await pick_best(live_mode=LIVE_MODE)
        if best is None:
            await status.edit_text(f"No setup {entry.strftime('%H:%M')}. Feed is up, but no pair scored.")
            return
        try:
            await post_card(context.bot, best, entry.strftime("%H:%M"))
            asyncio.create_task(follow_result(context.bot, best, entry))
            await status.edit_text(
                f"Sent {best.direction} {_pretty_pair(best.display_pair)} ({best.confidence}%)"
            )
        except Exception as exc:
            await status.edit_text(f"Channel post failed: {type(exc).__name__}: {exc}")
    finally:
        _clear_busy()


async def auto_loop(app):
    global LIVE_MODE
    await asyncio.sleep(8)
    while True:
        if LIVE_MODE and time.time() > LIVE_SESSION_END:
            LIVE_MODE = False
            await notify(app.bot, "⏰ Live session ended. Reverting to Sniper mode.")
        if not AUTO_ON:
            await asyncio.sleep(5)
            continue
        if _is_busy():
            await asyncio.sleep(3)
            continue
        _mark_busy()
        sent = False
        try:
            wait_s, entry = await wait_for_next_candle()
            await asyncio.sleep(wait_s)
            if not AUTO_ON:
                continue
            best = await pick_best(live_mode=LIVE_MODE)
            if best is None:
                if LIVE_MODE:
                    await notify(app.bot, f"Live: No setup {entry.strftime('%H:%M')}")
            else:
                try:
                    await post_card(app.bot, best, entry.strftime("%H:%M"))
                    asyncio.create_task(follow_result(app.bot, best, entry))
                    sent = True
                    await notify(
                        app.bot,
                        f"Sent {best.direction} {_pretty_pair(best.display_pair)} {entry.strftime('%H:%M')}",
                    )
                except Exception as exc:
                    await notify(app.bot, f"Channel post failed: {type(exc).__name__}: {exc}")
        except Exception as exc:
            await notify(app.bot, f"Auto error: {type(exc).__name__}")
        finally:
            _clear_busy()
        await asyncio.sleep(90 if LIVE_MODE else 60)


async def on_start(app):
    app.bot_data["tasks"] = [
        asyncio.create_task(quotex_feed.stream_loop()),
        asyncio.create_task(auto_loop(app)),
    ]


def main():
    if not BOT_TOKEN:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pause", pause_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("live", live_cmd))
    app.add_handler(CommandHandler("pairs", pairs_cmd))
    app.add_handler(CommandHandler("feed", feed_cmd))
    app.add_handler(CommandHandler("debug", debug_cmd))
    app.add_handler(CommandHandler("signal", signal_cmd))
    app.add_handler(CommandHandler("testcard", testcard_cmd))
    log.info("Starting %s -> %s", BRAND, CHANNEL)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
