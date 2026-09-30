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
# Free tier limit: 1 live stream, carrying 1 instrument.
# EURUSD_otc is the best pair for M1 technical analysis.
PAIR_MAP = {
    "EURUSD-OTC": "EURUSD_otc",
}

# ─── Trading Parameters ─────────────────────────────────────────
DEFAULT_PAIR = "EURUSD-OTC"
TIMEFRAME_MINUTES = 1
PAYOUT_DISPLAY = os.getenv("PAYOUT_DISPLAY", "91%").strip() or "91%"
CONFIDENCE_MIN = 72

# ─── Live Session Settings ──────────────────────────────────────
# Sniper mode requires 8/10 confluence. Live mode requires 6/10.
LIVE_SESSION_SCORE = 6
PASSIVE_SCORE = 8
