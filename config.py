import os

from dotenv import load_dotenv

load_dotenv()

# ─── Telegram Settings ──────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL = os.getenv("TELEGRAM_CHANNEL", "@amnsignalai").strip()
CONTACT = os.getenv("CONTACT_HANDLE", "@AMNdesk").strip()
BRAND = os.getenv("BOT_BRAND", "AMN SIGNAL AI").strip()
ADMIN_USER_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0") or "0")

# ─── Data Feed Settings (otcharts) ──────────────────────────────
# Set OTCHARTS_API_KEY in Railway Variables.

# ─── Pair Mapping ───────────────────────────────────────────────
# Switched to BTCUSD-OTC for today's live session (90% payout).
# This is allowed on the OTCharts free tier.
PAIR_MAP = {
    "BTCUSD-OTC": "BTCUSD_otc",
}

# ─── Trading Parameters ─────────────────────────────────────────
DEFAULT_PAIR = "BTCUSD-OTC"
TIMEFRAME_MINUTES = 1
PAYOUT_DISPLAY = os.getenv("PAYOUT_DISPLAY", "90%").strip() or "90%"
CONFIDENCE_MIN = 72

# ─── Live Session Settings ──────────────────────────────────────
# Sniper mode requires 3/3 conditions. Live mode requires 2/3.
LIVE_SESSION_SCORE = 6
PASSIVE_SCORE = 8
