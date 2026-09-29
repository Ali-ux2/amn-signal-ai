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
# The otcharts Client reads it automatically.

# ─── Pair Mapping ───────────────────────────────────────────────
# Updated to only use the 5 pairs allowed on the OTCharts Free Tier.
# If you upgrade to a paid plan, you can add your exotic pairs back.
PAIR_MAP = {
    "EURUSD-OTC": "EURUSD_otc",
    "GBPUSD-OTC": "GBPUSD_otc",
    "USDJPY-OTC": "USDJPY_otc",
    "BTCUSD-OTC": "BTCUSD_otc",
    "AUDUSD-OTC": "AUDUSD_otc",
}

# ─── Trading Parameters ─────────────────────────────────────────
DEFAULT_PAIR = "EURUSD-OTC"
TIMEFRAME_MINUTES = 1
PAYOUT_DISPLAY = os.getenv("PAYOUT_DISPLAY", "91%").strip() or "91%"
CONFIDENCE_MIN = 72
