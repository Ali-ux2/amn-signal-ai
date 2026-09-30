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
# Examples: EURUSD-OTC, GBPUSD-OTC, USDJPY-OTC, BTCUSD-OTC, AUDUSD-OTC
# We use .upper() to fix any accidental lowercase typing.
ACTIVE_PAIR = os.getenv("ACTIVE_PAIR", "EURUSD-OTC").strip().upper()

# Build the PAIR_MAP automatically from the chosen pair.
# This takes "BTCUSD-OTC" and converts it to "BTCUSD_otc" for the OTCharts API.
api_symbol = ACTIVE_PAIR.replace("-OTC", "_otc")

PAIR_MAP = {
    ACTIVE_PAIR: api_symbol,
}

# ─── Trading Parameters ─────────────────────────────────────────
DEFAULT_PAIR = ACTIVE_PAIR
TIMEFRAME_MINUTES = 1

# Payout display can also be changed via Railway Variables.
PAYOUT_DISPLAY = os.getenv("PAYOUT_DISPLAY", "91%").strip() or "91%"
CONFIDENCE_MIN = 70
