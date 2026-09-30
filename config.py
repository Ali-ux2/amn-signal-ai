import os

from dotenv import load_dotenv

load_dotenv()

# ─── Telegram Settings ──────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL = os.getenv("TELEGRAM_CHANNEL", "@amnsignalai").strip()
CONTACT = os.getenv("CONTACT_HANDLE", "@AMNdesk").strip()
BRAND = os.getenv("BOT_BRAND", "AMN SIGNAL AI").strip()
ADMIN_USER_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0") or "0")

# ─── Active Pair Selection ──────────────────────────────────────
# Set this in Railway Variables. Change it any time without editing code.
ACTIVE_PAIR = os.getenv("ACTIVE_PAIR", "BTCUSD-OTC").strip()

# ── THE CRITICAL LINE ──
# This takes "BTCUSD-OTC" from Railway and converts it to "BTCUSD_otc" for the API.
api_symbol = ACTIVE_PAIR.replace("-OTC", "_otc")

PAIR_MAP = {
    ACTIVE_PAIR: api_symbol,
}

# ─── Trading Parameters ─────────────────────────────────────────
DEFAULT_PAIR = ACTIVE_PAIR
TIMEFRAME_MINUTES = 1
PAYOUT_DISPLAY = os.getenv("PAYOUT_DISPLAY", "89%").strip() or "89%" # Updated to 89% for BTC
CONFIDENCE_MIN = 70
