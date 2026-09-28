import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL = os.getenv("TELEGRAM_CHANNEL", "@signalprobots").strip()
CONTACT = os.getenv("CONTACT_HANDLE", "@verihon").strip()
BRAND = os.getenv("BOT_BRAND", "AMN SIGNAL AI").strip()
ADMIN_USER_ID = 0

# Set these in Railway > worker > Variables (never in code)
QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL", "").strip()
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD", "").strip()

# display name -> Quotex asset name
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

DEFAULT_PAIR = "USDINR-OTC"
TIMEFRAME_MINUTES = 1
PAYOUT_DISPLAY = "91%"
CONFIDENCE_MIN = 68
