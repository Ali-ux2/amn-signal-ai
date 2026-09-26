from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler
from analyzer import analyze_pair
from config import BOT_TOKEN, BRAND, CHANNEL, CONTACT, PAIR_MAP, PAYOUT_DISPLAY

KAMPALA = ZoneInfo("Africa/Kampala")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("amn")
LEAD_SECONDS = 8
PAUSE_AFTER_SEND = 120
SCAN_CAP = 90
_busy_until = 0.0
NOTIFY_CHAT = None

def _pretty_pair(display_pair):
    raw = display_pair.replace("-OTC", "")
    if raw.startswith("USD") and "/" not in raw:
        return "USD/" + raw[3:] + "-OTC"
    return display_pair

def format_signal_caption(sig):
    arrow = "🟢 CALL ↑" if sig.direction == "CALL" else "🔴 PUT ↓"
    name = _pretty_pair(sig.display_pair)
    return (
        f"🚀 <b>Signal ready</b>\n"
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
        f"🚨 MTG           : STEP 1 IF LOSS\n"
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

async def wait_for_next_candle():
    now = datetime.now(KAMPALA)
    entry = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    fire_at = entry - timedelta(seconds=LEAD_SECONDS)
    if now >= fire_at:
        entry = entry + timedelta(minutes=1)
        fire_at = entry - timedelta(seconds=LEAD_SECONDS)
    wait = max(1.0, (fire_at - datetime.now(KAMPALA)).total_seconds())
    return wait, entry.strftime("%H:%M")

async def pick_best():
    best = None
    for pair in PAIR_MAP.keys():
        try:
            cand = await asyncio.wait_for(asyncio.to_thread(analyze_pair, pair), timeout=12)
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

async def post_card(bot, sig, entry_time):
    sig.entry_time = entry_time
    caption = format_signal_caption(sig)
    try:
        from chart import render_chart
        photo = render_chart(sig)
        await bot.send_photo(chat_id=CHANNEL, photo=photo, caption=caption, parse_mode=ParseMode.HTML)
    except Exception:
        await bot.send_message(chat_id=CHANNEL, text=caption, parse_mode=ParseMode.HTML)

async def start(update, context):
    global NOTIFY_CHAT
    NOTIFY_CHAT = update.effective_chat.id
    await update.message.reply_text(
        f"{BRAND} online.\nAuto ON every 2 minutes after a card.\n/signal still works."
    )

async def pairs_cmd(update, context):
    global NOTIFY_CHAT
    NOTIFY_CHAT = update.effective_chat.id
    await update.message.reply_text("\n".join(_pretty_pair(p) for p in PAIR_MAP.keys()))

async def signal_cmd(update, context):
    global NOTIFY_CHAT
    NOTIFY_CHAT = update.effective_chat.id
    if _is_busy():
        left = int(_busy_until - time.time())
        await update.message.reply_text(f"Scan running. Wait ~{max(1, left)}s.")
        return
    _mark_busy()
    try:
        wait_s, entry_time = await wait_for_next_candle()
        status = await update.message.reply_text(
            f"Waiting for next M1.\nEntry {entry_time}.\n{int(wait_s)}s..."
        )
        await asyncio.sleep(wait_s)
        best = await pick_best()
        if best is None:
            await status.edit_text(f"No setup {entry_time}.")
            return
        try:
            await post_card(context.bot, best, entry_time)
            await status.edit_text(
                f"Sent {best.direction} {_pretty_pair(best.display_pair)} ({best.confidence}%)"
            )
        except Exception as exc:
            await status.edit_text(f"Channel post failed: {type(exc).__name__}: {exc}")
    finally:
        _clear_busy()

async def auto_loop(app):
    await asyncio.sleep(5)
    while True:
        if _is_busy():
            await asyncio.sleep(3)
            continue
        _mark_busy()
        sent = False
        try:
            wait_s, entry_time = await wait_for_next_candle()
            await asyncio.sleep(wait_s)
            best = await pick_best()
            if best is None:
                await notify(app.bot, f"No setup {entry_time}")
            else:
                try:
                    await post_card(app.bot, best, entry_time)
                    sent = True
                    await notify(
                        app.bot,
                        f"Sent {best.direction} {_pretty_pair(best.display_pair)} {entry_time}",
                    )
                except Exception as exc:
                    await notify(app.bot, f"Channel post failed: {type(exc).__name__}: {exc}")
        except Exception as exc:
            await notify(app.bot, f"Auto error: {type(exc).__name__}")
        finally:
            _clear_busy()
        await asyncio.sleep(PAUSE_AFTER_SEND if sent else 60)

async def on_start(app):
    asyncio.create_task(auto_loop(app))

def main():
    if not BOT_TOKEN:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(BOT_TOKEN).post_init(on_start).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pairs", pairs_cmd))
    app.add_handler(CommandHandler("signal", signal_cmd))
    log.info("Starting %s auto=2min", BRAND)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
