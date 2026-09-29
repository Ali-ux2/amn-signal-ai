import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL = os.getenv("TELEGRAM_CHANNEL", "@amnsignalai").strip()
CONTACT = os.getenv("CONTACT_HANDLE", "@AMNdesk").strip()
BRAND = os.getenv("BOT_BRAND", "AMN SIGNAL AI").strip()
ADMIN_USER_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0") or "0")

# Set these in Railway > worker > Variables (never in code)
QUOTEX_EMAIL = os.getenv("QUOTEX_EMAIL", "").strip()
QUOTEX_PASSWORD = os.getenv("QUOTEX_PASSWORD", "").strip()
# Optional. Railway's own address is refused at login. A normal proxy you control:
# http://user:pass@host:port  or  socks5://user:pass@host:port
QUOTEX_PROXY = os.getenv("QUOTEX_PROXY", "").strip()

# display name -> Quotex asset name. Feed may swap to XXXUSD_otc if this name is closed.
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
PAYOUT_DISPLAY = os.getenv("PAYOUT_DISPLAY", "91%").strip() or "91%"
CONFIDENCE_MIN = 72
