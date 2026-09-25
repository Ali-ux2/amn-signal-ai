import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL = os.getenv("TELEGRAM_CHANNEL", "@signalprobots").strip()
CONTACT = os.getenv("CONTACT_HANDLE", "@verihon").strip()
BRAND = os.getenv("BOT_BRAND", "AMN SIGNAL AI").strip()
ADMIN_USER_ID = 0

PAIR_MAP = {
    "USDBRL-OTC": "USDBRL=X",
    "USDMXN-OTC": "USDMXN=X",
    "USDINR-OTC": "USDINR=X",
    "USDPKR-OTC": "USDPKR=X",
    "USDDZD-OTC": "USDDZD=X",
    "USDARS-OTC": "USDARS=X",
    "USDBDT-OTC": "USDBDT=X",
    "USDCOP-OTC": "USDCOP=X",
    "USDIDR-OTC": "USDIDR=X",
    "USDPHP-OTC": "USDPHP=X",
    "USDEGP-OTC": "USDEGP=X",
    "USDNGN-OTC": "USDNGN=X",
}

DEFAULT_PAIR = "USDINR-OTC"
TIMEFRAME_MINUTES = 1
PAYOUT_DISPLAY = "91%"
CONFIDENCE_MIN = 68
