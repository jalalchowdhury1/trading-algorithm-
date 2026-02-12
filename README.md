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

## 📝 License

Personal use only.

---

**Last Updated**: 2026-02-12
**Python Version**: 3.9+
**Author**: Converted from Google Sheets algorithm
