# AMN SIGNAL AI

Telegram bot that reads live Quotex OTC candles via **otcharts** and posts an M1 signal card to `@amnsignalai`.

## Why otcharts?
Direct Quotex API connections are frequently blocked by Cloudflare (HTTP 403) when running from datacenter IPs (like Railway). `otcharts` provides a reliable, server-side HTTP API that fetches authentic Quotex OTC price data. This eliminates the need for residential proxies, Quotex logins, or WebSocket management, and ensures your bot analyzes the exact prices Quotex uses to settle trades.

## Railway Variables

**Required:**
- `TELEGRAM_BOT_TOKEN` — From @BotFather
- `TELEGRAM_CHANNEL` — e.g., `@amnsignalai`
- `CONTACT_HANDLE` — e.g., `@AMNdesk`
- `BOT_BRAND` — e.g., `AMN SIGNAL AI`
- `OTCHARTS_API_KEY` — Your API key from [otcharts.com](https://otcharts.com)

**Optional:**
- `TELEGRAM_ADMIN_ID` — Your numeric Telegram ID (restricts commands to you)
- `PAYOUT_DISPLAY` — e.g., `91%` (display only)

> **Note:** You no longer need `QUOTEX_EMAIL`, `QUOTEX_PASSWORD`, `QUOTEX_PROXY`, or `QUOTEX_HOSTS`. You can safely delete those from Railway.

## Setup

1. **Get an otcharts API Key:**
   - Sign up at [otcharts.com/pricing](https://otcharts.com/pricing.html#api)
   - Generate a key on your [account page](https://otcharts.com/account.html)
   - Add it to Railway as `OTCHARTS_API_KEY` (e.g., `otc_live_...`)

2. **Deploy to Railway:**
   - Start command: `python bot.py`
   - Ensure the bot is an admin in your Telegram channel with permission to post messages.

3. **No 2FA / PIN required:**
   - Since the bot no longer logs into your Quotex account directly, you do not need to disable 2FA or worry about PIN prompts.

## Commands

- `/start` — Check bot status
- `/pause` — Pause the auto-signal loop
- `/resume` — Resume the auto-signal loop
- `/pairs` — List all mapped OTC pairs
- `/feed` — Show feed connection status and candle counts
- `/probe` — Test API connectivity (useful for debugging)
- `/signal` — Force a manual scan for the next M1 candle
- `/testcard` — Post a sample TEST card to the channel (do not trade)

## How it Works

1. `otc_feed.py` fetches the last 200 M1 candles from `otcharts` for each pair in `PAIR_MAP`.
2. `analyzer.py` runs technical analysis (RSI, EMA, DeMarker, Support/Resistance) on the closed candles.
3. If a setup meets the `CONFIDENCE_MIN` threshold (72%), `chart.py` renders a signal card.
4. `bot.py` posts the card to your channel at the start of the next M1 candle.

## Notes

- The bot only uses **closed** candles for analysis to prevent signal flipping.
- `/feed` will show `🟢 Feed connected` once otcharts data is successfully fetched.
- If a pair is closed on Quotex, `otcharts` will not return candles for it, and the bot will skip it.
