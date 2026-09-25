from __future__ import annotations
import asyncio
import logging
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
_busy = False

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
            cand = await asyncio.to_thread(analyze_pair, pair)
        except Exception:
            continue
        if cand is None:
            continue
        if best is None or cand.confidence > best.confidence:
            best = cand
    return best

async def post_signal(bot, sig, entry_time):
    sig.entry_time = entry_time
    caption = format_signal_caption(sig)
    await bot.send_message(
        chat_id=CHANNEL,
        text=caption,
        parse_mode=ParseMode.HTML,
    )
    return sig

async def start(update, context):
    await update.message.reply_text(
        f"{BRAND} online.\n"
        f"Auto every 2 minutes after a card.\n"
        f"/signal still works.\n"
        f"Channel: {CHANNEL}"
    )

async def pairs_cmd(update, context):
    await update.message.reply_text("\n".join(_pretty_pair(p) for p in PAIR_MAP.keys()))

async def signal_cmd(update, context):
    global _busy
    if _busy:
        await update.message.reply_text("Already scanning. Wait.")
        return
    _busy = True
    try:
        wait_s, entry_time = await wait_for_next_candle()
        status = await update.message.reply_text(
            f"Waiting for next M1.\nEntry {entry_time} Kampala.\n{int(wait_s)}s..."
        )
        await asyncio.sleep(wait_s)
        best = await pick_best()
        if best is None:
            await status.edit_text("No high-conviction setup. Auto will try again.")
            return
        try:
            await post_signal(context.bot, best, entry_time)
            await status.edit_text(
                f"Sent {best.direction} {_pretty_pair(best.display_pair)} ({best.confidence}%)"
            )
        except Exception as exc:
            await status.edit_text(f"Channel post failed: {type(exc).__name__}")
    finally:
        _busy = False

async def auto_loop(app):
    await asyncio.sleep(8)
    while True:
        global _busy
        if _busy:
            await asyncio.sleep(5)
            continue
        _busy = True
        sent = False
        try:
            wait_s, entry_time = await wait_for_next_candle()
            await asyncio.sleep(wait_s)
            best = await pick_best()
            if best is not None:
                try:
                    await post_signal(app.bot, best, entry_time)
                    sent = True
                    log.info("Auto sent %s %s", best.direction, best.display_pair)
                except Exception as exc:
                    log.warning("Auto post failed: %s", exc)
        except Exception as exc:
            log.warning("Auto loop error: %s", exc)
        finally:
            _busy = False
        await asyncio.sleep(PAUSE_AFTER_SEND if sent else 60)

async def on_start(app):
    asyncio.create_task(auto_loop(app))

def main():
    if not BOT_TOKEN:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN")
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(on_start)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pairs", pairs_cmd))
    app.add_handler(CommandHandler("signal", signal_cmd))
    log.info("Starting %s auto=2min", BRAND)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
