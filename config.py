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
PAIR_MAP = {"BTCUSD-OTC": "BTCUSD_otc"}
DEFAULT_PAIR = "BTCUSD-OTC"
TIMEFRAME_MINUTES = 1
PAYOUT_DISPLAY = "89%"
CONFIDENCE_MIN = 70

# ─── Risk Management (MTG) ──────────────────────────────────────
MTG_ENABLED = True
MTG_MAX_STEPS = 2
COOLDOWN_MINUTES = 3
