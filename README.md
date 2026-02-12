# Trading Algorithm - VIX Strategy

A robust Python implementation of a multi-asset RSI-based trading algorithm that signals VIX exposure based on market conditions.

## 🎯 Overview

This script analyzes 16 different ETFs using custom RSI calculations (SMA-based, not EMA) and executes a decision tree to determine optimal trading positions focusing on volatility products (VIX).

## 📊 Features

- **Custom RSI Calculation**: Uses Simple Moving Average (SMA) instead of standard EMA-based RSI
- **Multi-Asset Analysis**: Tracks QQQ, SPY, VIXY, IOO, XLP, VTV, XLF, VOX, CURE, RETL, LABU, SOXL, FNGU, TQQQ, TECL, UPRO
- **Decision Tree Logic**: 37-node decision tree for precise signal generation
- **Built-in Verification**: Unit test to validate RSI calculations against spreadsheet
- **Step-by-Step Reporting**: Clear verification prints after each stage

## 🚀 Installation

### Prerequisites
- Python 3.9+
- pip

### Install Dependencies
```bash
cd ~/PycharmProjects/trading_algorithm
python3 -m pip install --user -r requirements.txt
```

## ▶️ Usage

Run the algorithm:
```bash
python3 main.py
```

The script will:
1. **Verify RSI Math** with unit test (should output 73.3333)
2. **Download 3+ months** of market data
3. **Calculate RSI** for all tickers (9, 50, 60-day windows)
4. **Execute Decision Tree** and show the traversal path
5. **Output Trading Signal**

## 📈 Output Example

```
✓ FINAL RESULT:
  1.5x VIX Group (VXX, UVIX)
```

## 🧮 RSI Calculation Method

**Formula:**
1. `Diff = Close - PrevClose`
2. `Up = Diff if > 0 else 0`, `Down = Abs(Diff) if < 0 else 0`
3. `AvgUp = SMA(Up, window)`, `AvgDown = SMA(Down, window)`
4. `RS = AvgUp / AvgDown`
5. `RSI = 100 - (100 / (1 + RS))`

⚠️ **Note**: This uses SMA (Simple Moving Average), NOT the standard EMA-based RSI.

## 🎯 Trading Signals

Possible outputs:
- `1.5x VIX Group (VXX, UVIX)` - Defensive position, markets overbought
- `VIX Blend (VXX=0.45, VIXM=0.2, UVIX=0.35)` - Mixed allocation
- `1x VIX (VIXY)` - Standard volatility exposure
- `LABD` - Inverse biotech
- `SOXL`, `FNGU`, `TECL`, `UPRO` - Leveraged long positions
- `Buy [Ticker1] and [Ticker2]` - Special logic for oversold tech
- `BIL (T-Bill ETF)` - Risk-off, cash equivalent

## 📁 Project Structure

```
trading_algorithm/
├── main.py           # Main algorithm script
├── README.md         # This file
└── requirements.txt  # Python dependencies
```

## ✅ Verification

The unit test uses hardcoded prices:
```
[100, 102, 101, 103, 102, 104, 105, 103, 106, 107]
```

Expected RSI: **73.3333** ✓

## 🔄 Updates

To get the latest market signals, simply run the script again. It fetches real-time data from Yahoo Finance.

## 🤖 Automated Alerts

This algorithm runs **automatically every hour during US market hours** via GitHub Actions and sends trading signals to your Telegram.

**Features:**
- ✅ Hourly execution during market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
- ✅ Automatic market hours detection (skips execution when closed)
- ✅ Real-time Telegram notifications with key RSI values
- ✅ Completely free hosting via GitHub Actions
- ✅ Manual trigger option for testing

## ⚙️ Configuration

### Setting Up Telegram Notifications

1. **Get your Telegram Bot Token** (you should already have this)
   - If you need to create a bot, talk to [@BotFather](https://t.me/botfather) on Telegram
   - Send `/newbot` and follow the instructions
   - Copy the bot token (looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

2. **Get your Telegram Chat ID**

   **Method 1 - Using getUpdates API:**
   - Send any message to your bot on Telegram
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Look for `"chat":{"id":123456789}` in the response
   - Copy that numeric ID

   **Method 2 - Using @userinfobot:**
   - Add [@userinfobot](https://t.me/userinfobot) on Telegram
   - Send it any message
   - It will reply with your chat ID

3. **Configure GitHub Secrets**
   - Go to your GitHub repository
   - Navigate to **Settings** → **Secrets and variables** → **Actions**
   - Click **New repository secret**
   - Add two secrets:
     - Name: `TELEGRAM_BOT_TOKEN`, Value: your bot token
     - Name: `TELEGRAM_CHAT_ID`, Value: your chat ID (numeric)

### Local Environment Variables (Optional)

For local testing, set environment variables:

**macOS/Linux:**
```bash
export TELEGRAM_BOT_TOKEN="your_bot_token_here"
export TELEGRAM_CHAT_ID="your_chat_id_here"
```

**Windows (PowerShell):**
```powershell
$env:TELEGRAM_BOT_TOKEN="your_bot_token_here"
$env:TELEGRAM_CHAT_ID="your_chat_id_here"
```

Alternatively, create a `.env` file (already in `.gitignore`):
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

## 🧪 Local Testing

### Test Market Hours Detection
```bash
python3 market_hours.py
```

This will print whether the market is currently open or closed and exit with code 0 (open) or 1 (closed).

### Test Trading Algorithm with Telegram
```bash
# Set environment variables first (see above)
python3 main.py
```

You should receive a Telegram message with the trading signal. If Telegram is not configured, the script will still run and print results to the console.

### Test Without Telegram
Simply run without setting environment variables:
```bash
python3 main.py
```

You'll see: "ℹ️  Telegram not configured" but the algorithm will still execute normally.

## 📅 Automation Schedule

**GitHub Actions Schedule:**
- Runs every hour at the top of the hour (`:00`)
- Only executes during US market hours (9:30 AM - 4:00 PM ET, Mon-Fri)
- Automatically skips execution on weekends and after hours

**Manual Trigger:**
1. Go to your GitHub repository
2. Click the **Actions** tab
3. Select **Trading Algorithm Hourly** workflow
4. Click **Run workflow** → **Run workflow**

**Viewing Logs:**
- Go to **Actions** tab in your GitHub repository
- Click on any workflow run to see detailed logs
- Useful for debugging and verification

**GitHub Actions Limits:**
- Free tier: 2,000 minutes/month
- This workflow uses ~2-3 minutes per run
- Expected usage: ~100 runs/month (well within limits)

## 📝 License

Personal use only.

---

**Last Updated**: 2026-02-12
**Python Version**: 3.9+
**Author**: Converted from Google Sheets algorithm
