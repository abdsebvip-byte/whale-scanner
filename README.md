# 🐋 Whale Scanner - Full US Market Scan

Real-time whale/institutional activity scanner for the entire US stock market (5700+ stocks).

## Engines
1. **Short Squeeze** - Detects stocks with high short interest + low float
2. **Volume Anomaly** - Detects unusual volume spikes (Z-score > 2.5)
3. **Price Spike** - Detects stocks moving > 15% daily
4. **Insider Buying** - Detects SEC Form 4 cluster buying (optional, slow)

## Setup

### 1. Create Telegram Bot
1. Open Telegram, search for `@BotFather`
2. Send `/newbot` and follow instructions
3. Copy the bot token
4. Start a chat with your bot, then visit:
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
5. Copy your `chat_id`

### 2. Add GitHub Secrets
Go to your repo → Settings → Secrets and variables → Actions → New repository secret

- `TELEGRAM_BOT_TOKEN` - Your bot token from BotFather
- `TELEGRAM_CHAT_ID` - Your chat ID

### 3. Run
The scanner runs automatically every 4 hours on weekdays (during market hours).

Or trigger manually: Actions → Whale Scanner → Run workflow

## Tech Stack
- Python 3.12
- yfinance (Yahoo Finance)
- edgartools (SEC EDGAR)
- TradingView Scanner API
- GitHub Actions (scheduling)
