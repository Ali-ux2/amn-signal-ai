from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler
from analyzer import analyze_pair
from chart import render_chart
from config import BOT_TOKEN, BRAND, CHANNEL, CONTACT, PAIR_MAP, PAYOUT_DISPLAY

KAMPALA = ZoneInfo("Africa/Kampala")
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("amn")
LEAD_SECONDS = 8
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

async def start(update, context):
    await update.message.reply_text(
        f"{BRAND} online.\n/signal scans {len(PAIR_MAP)} pairs.\nChannel: {CHANNEL}"
    )

async def pairs_cmd(update, context):
    await update.message.reply_text("\n".join(_pretty_pair(p) for p in PAIR_MAP.keys()))

async def wait_for_next_candle():
    now = datetime.now(KAMPALA)
    entry = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    fire_at = entry - timedelta(seconds=LEAD_SECONDS)
    if now >= fire_at:
        entry = entry + timedelta(minutes=1)
        fire_at = entry - timedelta(seconds=LEAD_SECONDS)
    wait = max(1.0, (fire_at - datetime.now(KAMPALA)).total_seconds())
    return wait, entry.strftime("%H:%M")

async def signal_cmd(update, context):
    global _busy
    if _busy:
        await update.message.reply_text("Already scanning. Wait for Sent or No S3.")
        return
    if not BOT_TOKEN or not CHANNEL:
        await update.message.reply_text("Missing token or channel")
        return
    _busy = True
    try:
        wait_s, entry_time = await wait_for_next_candle()
        status = await update.message.reply_text(
            f"Waiting for next M1.\nEntry {entry_time} Kampala.\n{int(wait_s)}s..."
        )
        await asyncio.sleep(wait_s)
        best = None
        names = list(PAIR_MAP.keys())
        for i, pair in enumerate(names, start=1):
            try:
                await status.edit_text(f"Scanning {i}/{len(names)} {_pretty_pair(pair)}")
            except Exception:
                pass
            try:
                cand = await asyncio.to_thread(analyze_pair, pair)
            except Exception:
                continue
            if cand is None:
                continue
            if best is None or cand.confidence > best.confidence:
                best = cand
        if best is None:
            await status.edit_text("No S3 setup. Try next minute.")
            return
        best.entry_time = entry_time
        caption = format_signal_caption(best)
        try:
            chart = render_chart(best)
            await context.bot.send_photo(
                chat_id=CHANNEL,
                photo=chart,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            await context.bot.send_message(
                chat_id=CHANNEL,
                text=caption,
                parse_mode=ParseMode.HTML,
            )
        await status.edit_text(
            f"Sent {best.direction} {_pretty_pair(best.display_pair)} ({best.confidence}%)"
        )
    finally:
        _busy = False

def main():
    if not BOT_TOKEN:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pairs", pairs_cmd))
    app.add_handler(CommandHandler("signal", signal_cmd))
    log.info("Starting %s", BRAND)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
