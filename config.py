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
# Set OTCHARTS_API_KEY in Railway Variables (or .env file).
# The otcharts Client reads it automatically. No email/password needed here.
# Example: OTCHARTS_API_KEY=otc_live_xxxxxxxxxxxx

# ─── Pair Mapping ───────────────────────────────────────────────
# display name -> otcharts symbol (Quotex OTC pairs use the "_otc" suffix)
PAIR_MAP = {
    "USDBRL-OTC": "USDBRL_otc",
    "USDMXN-OTC": "USDMXN_otc",
    "USDINR-OTC": "USDINR_otc",
    "USDPKR-OTC": "USDPKR_otc",
    "USDDZD-OTC": "USDDZD_otc",
    "USDARS-OTC": "USDARS_otc",
    "USDBDT-OTC": "USDBDT_otc",
    "USDCOP-OTC": "USDCOP_otc",
    "USDIDR-OTC": "USDIDR_otc",
    "USDPHP-OTC": "USDPHP_otc",
    "USDEGP-OTC": "USDEGP_otc",
    "USDNGN-OTC": "USDNGN_otc",
}

# ─── Trading Parameters ─────────────────────────────────────────
DEFAULT_PAIR = "USDINR-OTC"
TIMEFRAME_MINUTES = 1
PAYOUT_DISPLAY = os.getenv("PAYOUT_DISPLAY", "91%").strip() or "91%"
CONFIDENCE_MIN = 72
