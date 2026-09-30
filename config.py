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
ACTIVE_PAIR = os.getenv("ACTIVE_PAIR", "EURUSD-OTC").strip()

# Build the PAIR_MAP automatically from the chosen pair
PAIR_MAP = {
    ACTIVE_PAIR: ACTIVE_PAIR.replace("-OTC", "_otc").lower(),
}

# ─── Trading Parameters ─────────────────────────────────────────
DEFAULT_PAIR = ACTIVE_PAIR
TIMEFRAME_MINUTES = 1
PAYOUT_DISPLAY = os.getenv("PAYOUT_DISPLAY", "91%").strip() or "91%"
CONFIDENCE_MIN = 70
