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
            cand = await asyncio.wait_for(
                asyncio.to_thread(analyze_pair, pair),
                timeout=12,
            )
        except Exception:
            continue
        if cand is None:
            continue
        if best is None or cand.confidence > best.confidence:
            best = cand
    return
