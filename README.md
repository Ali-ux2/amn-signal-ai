# AMN SIGNAL AI

Telegram bot that reads live Quotex OTC candles and posts an M1 signal card to @amnsignalai.

## Railway variables

TELEGRAM_BOT_TOKEN
TELEGRAM_CHANNEL=@amnsignalai
CONTACT_HANDLE=@AMNdesk
BOT_BRAND=AMN SIGNAL AI
QUOTEX_EMAIL
QUOTEX_PASSWORD

Optional: TELEGRAM_ADMIN_ID (your numeric Telegram id), PAYOUT_DISPLAY=91%, QUOTEX_HOSTS

Start command: python bot.py

The bot must be an admin in the channel, with permission to post messages.

Turn off Quotex email PIN / 2FA on the login account. pyquotex cannot answer a PIN prompt, and the feed will die with EOFError.

## Prove the card

Message the bot: /testcard

That posts a chart to the channel even if no pair has a setup. It is labelled TEST. Do not trade it.

/feed shows candles per pair. A real /signal needs the feed connected and at least one pair with 30 closed candles and a 3-vote setup.
