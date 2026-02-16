import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import requests
import pytz
from state_manager import read_state, write_state


def should_notify(current_signal, last_state):
    """
    Determine if we should send a Telegram notification.

    Rules:
    - First run of the day: Always notify
    - Signal changed: Always notify
    - Same signal, same day: Don't notify

    Returns: (should_notify: bool, reason: str)
    """
    # Get today's date in Eastern Time
    et_tz = pytz.timezone('America/New_York')
    today = datetime.now(pytz.UTC).astimezone(et_tz).strftime('%Y-%m-%d')

    # No previous state = first run ever
    if last_state is None:
        return True, "First run ever"

    last_date = last_state.get('date', '')
    last_signal = last_state.get('signal', '')

    # First run of the trading day
    if last_date != today:
        return True, f"First check of trading day ({today})"

    # Signal changed
    if current_signal != last_signal:
        return True, f"Signal changed: '{last_signal}' → '{current_signal}'"

    # Same signal, same day
    return False, f"No change (still '{current_signal}')"

def send_telegram_message(message, bot_token, chat_id):
    """
    Send message to Telegram using Bot API.
    Returns True if successful, False otherwise.
    """
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"⚠️  Telegram send failed: {str(e)}")
        return False

def format_telegram_report(final_decision, rsi_cache, decision_path):
    """
    Format trading signal, decision path, and key RSI values for Telegram.
    Returns formatted message string.
    """
    # Convert UTC to Eastern Time
    et_tz = pytz.timezone('America/New_York')
    et_time = datetime.now(pytz.UTC).astimezone(et_tz)
    timestamp = et_time.strftime('%Y-%m-%d %I:%M %p ET')

    # Format decision path with emojis
    path_lines = []
    for i, step in enumerate(decision_path, 1):
        ticker = step['ticker']
        window = step['window']
        operator = step['operator']
        threshold = step['threshold']
        result = step['result']
        current_rsi = step['current_rsi']

        # Choose emoji based on result
        emoji = "✅" if result else "❌"

        # Format the condition
        condition = f"{ticker} RSI({window}) {operator} {threshold}"
        path_lines.append(f"{emoji} {condition} → {result} ({current_rsi:.1f})")

    decision_path_text = "\n".join(path_lines)

    # Get key RSI values
    qqq_rsi = rsi_cache.get(('QQQ', 9), 0)
    spy_rsi = rsi_cache.get(('SPY', 9), 0)
    xlp_rsi = rsi_cache.get(('XLP', 9), 0)
    vixy_rsi_50 = rsi_cache.get(('VIXY', 50), 0)

    # Determine signal emoji based on signal type
    signal_emoji = "🛡️"  # Default
    if "VIX" in final_decision:
        signal_emoji = "🛡️"  # Defensive
    elif "Buy" in final_decision or any(x in final_decision for x in ["SOXL", "FNGU", "TECL", "TQQQ", "UPRO"]):
        signal_emoji = "🚀"  # Aggressive long
    elif "LABD" in final_decision:
        signal_emoji = "📉"  # Short
    elif "BIL" in final_decision:
        signal_emoji = "💵"  # Cash

    message = f"""🎯 <b>TRADING SIGNAL</b>
━━━━━━━━━━━━━━━━
{signal_emoji} <b>{final_decision}</b>

🔍 <b>DECISION PATH:</b>
{decision_path_text}

📊 <b>KEY RSI VALUES:</b>
📈 QQQ: {qqq_rsi:.1f} | SPY: {spy_rsi:.1f}
📉 XLP: {xlp_rsi:.1f} | VIXY(50): {vixy_rsi_50:.1f}

⏰ {timestamp}"""

    return message

# List of tickers to download
TICKERS = ['QQQ', 'VIXY', 'SPY', 'IOO', 'XLP', 'VTV', 'XLF', 'VOX',
           'CURE', 'RETL', 'LABU', 'SOXL', 'FNGU', 'TQQQ', 'TECL', 'UPRO']

# Global storage for data and RSI values
ticker_data = {}
rsi_cache = {}

def calculate_rsi_sma(prices, window=9):
    """
    Calculate RSI using Simple Moving Average (SMA) method.
    This matches the Google Sheet calculation.

    Formula:
    1. Diff = Close - PrevClose
    2. Up = Diff if > 0 else 0, Down = Abs(Diff) if < 0 else 0
    3. AvgUp = SMA(Up, window), AvgDown = SMA(Down, window)
    4. RS = AvgUp / AvgDown
    5. RSI = 100 - (100 / (1 + RS))
    """
    if len(prices) < window + 1:
        return None

    # Calculate price differences
    diffs = np.diff(prices)

    # Separate ups and downs
    ups = np.where(diffs > 0, diffs, 0)
    downs = np.where(diffs < 0, np.abs(diffs), 0)

    # Calculate SMA of ups and downs (last 'window' values)
    avg_up = np.mean(ups[-(window):])
    avg_down = np.mean(downs[-(window):])

    # Avoid division by zero
    if avg_down == 0:
        return 100.0

    # Calculate RS and RSI
    rs = avg_up / avg_down
    rsi = 100 - (100 / (1 + rs))

    return rsi

def test_rsi_calculation():
    """
    Unit test for RSI calculation using hardcoded dummy data.
    This allows manual verification against the spreadsheet.
    """
    print("\n" + "="*80)
    print("UNIT TEST: RSI Calculation Verification")
    print("="*80)

    # Hardcoded test data
    test_prices = [100, 102, 101, 103, 102, 104, 105, 103, 106, 107]

    print(f"Test Prices: {test_prices}")
    print(f"Window: 9 days")

    rsi_result = calculate_rsi_sma(test_prices, window=9)

    print(f"\nCalculated RSI: {rsi_result:.4f}")
    print("\n⚠️  Please verify this result matches your Google Sheet calculation!")
    print("="*80 + "\n")

    return rsi_result

def download_data():
    """
    Step 1: Data Acquisition & Verification
    Downloads at least 3 months of OHLCV data for all tickers.
    """
    print("\n" + "="*80)
    print("STEP 1: DATA ACQUISITION & VERIFICATION")
    print("="*80 + "\n")

    # Calculate date range (3 months back, using 120 days to ensure coverage)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=120)

    print(f"Downloading data from {start_date.date()} to {end_date.date()}\n")

    all_success = True

    for ticker in TICKERS:
        try:
            print(f"Fetching {ticker}...", end=" ")
            df = yf.download(ticker, start=start_date, end=end_date, progress=False)

            if df.empty or len(df) < 60:  # Need at least 60 days for calculations
                print(f"❌ FAILED - Insufficient data (only {len(df)} rows)")
                all_success = False
                continue

            ticker_data[ticker] = df
            last_date = df.index[-1].strftime('%Y-%m-%d')

            print(f"✓ Data Check: Successfully downloaded {len(df)} rows. Last date: {last_date}")

        except Exception as e:
            print(f"❌ FAILED - Error: {str(e)}")
            all_success = False

    print("\n" + "="*80)

    if not all_success:
        print("\n❌ DATA ACQUISITION FAILED - Some tickers could not be downloaded!")
        print("Script will now stop. Please check the failed tickers and try again.")
        print("="*80 + "\n")
        exit(1)
    else:
        print("\n✓ All tickers downloaded successfully!")
        print("="*80 + "\n")

def calculate_all_rsi():
    """
    Step 2: Math Calculation & Verification
    Calculates RSI for all tickers with various windows.
    """
    print("\n" + "="*80)
    print("STEP 2: MATH CALCULATION & VERIFICATION")
    print("="*80 + "\n")

    # Standard RSI calculations with 9-day window
    for ticker in TICKERS:
        if ticker not in ticker_data:
            continue

        df = ticker_data[ticker]

        # Handle multi-level columns from yfinance and extract Close prices
        if isinstance(df.columns, pd.MultiIndex):
            prices = df['Close'].iloc[:, 0].values
        else:
            prices = df['Close'].values

        # Remove any NaN values
        prices = prices[~np.isnan(prices)]

        # Default 9-day RSI
        rsi_9 = calculate_rsi_sma(prices, window=9)
        rsi_cache[(ticker, 9)] = rsi_9

        print(f"{ticker:6s} - RSI(9):  {rsi_9:.2f}")

    # Special calculations for VIXY (windows 50 and 60)
    if 'VIXY' in ticker_data:
        df = ticker_data['VIXY']

        # Handle multi-level columns from yfinance
        if isinstance(df.columns, pd.MultiIndex):
            prices = df['Close'].iloc[:, 0].values
        else:
            prices = df['Close'].values

        # Remove any NaN values
        prices = prices[~np.isnan(prices)]

        rsi_50 = calculate_rsi_sma(prices, window=50)
        rsi_60 = calculate_rsi_sma(prices, window=60)

        rsi_cache[('VIXY', 50)] = rsi_50
        rsi_cache[('VIXY', 60)] = rsi_60

        print(f"\nVIXY   - RSI(50): {rsi_50:.2f}")
        print(f"VIXY   - RSI(60): {rsi_60:.2f}")

    print("\n" + "="*80)
    print("✓ All RSI calculations completed!")
    print("="*80 + "\n")

def get_rsi(ticker, window=9):
    """Helper function to get cached RSI value."""
    return rsi_cache.get((ticker, window), 0)

def execute_logic():
    """
    Step 3: Logic Execution (The Decision Tree)
    Traverses the decision tree based on RSI conditions.
    Returns: (final_decision, decision_path)
    """
    print("\n" + "="*80)
    print("STEP 3: LOGIC EXECUTION (DECISION TREE)")
    print("="*80 + "\n")

    decision_path = []

    # Define the logic tree as a dictionary
    logic_tree = {
        1: {
            'condition': lambda: get_rsi('QQQ', 9) > 79,
            'ticker': 'QQQ',
            'window': 9,
            'threshold': 79,
            'operator': '>',
            'true': 2,
            'false': 3
        },
        2: {
            'condition': lambda: get_rsi('VIXY', 50) > 40,
            'ticker': 'VIXY',
            'window': 50,
            'threshold': 40,
            'operator': '>',
            'true': "1.5x VIX Group (VXX, UVIX)",
            'false': 4
        },
        3: {
            'condition': lambda: get_rsi('SPY', 9) > 79,
            'ticker': 'SPY',
            'window': 9,
            'threshold': 79,
            'operator': '>',
            'true': 5,
            'false': 8
        },
        4: {
            'condition': lambda: get_rsi('SPY', 9) > 82.5,
            'ticker': 'SPY',
            'window': 9,
            'threshold': 82.5,
            'operator': '>',
            'true': "1.5x VIX Group (VXX, UVIX)",
            'false': "VIX Blend (VXX=0.45, VIXM=0.2, UVIX=0.35)"
        },
        5: {
            'condition': lambda: get_rsi('VIXY', 60) > 40,
            'ticker': 'VIXY',
            'window': 60,
            'threshold': 40,
            'operator': '>',
            'true': "1.5x VIX Group (VXX, UVIX)",
            'false': 6
        },
        6: {
            'condition': lambda: get_rsi('QQQ', 9) > 82.5,
            'ticker': 'QQQ',
            'window': 9,
            'threshold': 82.5,
            'operator': '>',
            'true': "1.5x VIX Group (VXX, UVIX)",
            'false': "VIX Blend (VXX=0.45, VIXM=0.2, UVIX=0.35)"
        },
        8: {
            'condition': lambda: get_rsi('IOO', 9) > 80,
            'ticker': 'IOO',
            'window': 9,
            'threshold': 80,
            'operator': '>',
            'true': 9,
            'false': 12
        },
        9: {
            'condition': lambda: get_rsi('VIXY', 60) > 40,
            'ticker': 'VIXY',
            'window': 60,
            'threshold': 40,
            'operator': '>',
            'true': "1.5x VIX Group (VXX, UVIX)",
            'false': 10
        },
        10: {
            'condition': lambda: get_rsi('IOO', 9) > 82.5,
            'ticker': 'IOO',
            'window': 9,
            'threshold': 82.5,
            'operator': '>',
            'true': "1.5x VIX Group (VXX, UVIX)",
            'false': "1x VIX (VIXY)"
        },
        12: {
            'condition': lambda: get_rsi('XLP', 9) > 77,
            'ticker': 'XLP',
            'window': 9,
            'threshold': 77,
            'operator': '>',
            'true': 13,
            'false': 16
        },
        13: {
            'condition': lambda: get_rsi('XLP', 9) > 82.5,
            'ticker': 'XLP',
            'window': 9,
            'threshold': 82.5,
            'operator': '>',
            'true': "1.5x VIX Group (VXX, UVIX)",
            'false': "1x VIX (VIXY)"
        },
        16: {
            'condition': lambda: get_rsi('VTV', 9) > 79,
            'ticker': 'VTV',
            'window': 9,
            'threshold': 79,
            'operator': '>',
            'true': 17,
            'false': 18
        },
        17: {
            'condition': lambda: get_rsi('VTV', 9) > 82.5,
            'ticker': 'VTV',
            'window': 9,
            'threshold': 82.5,
            'operator': '>',
            'true': "1.5x VIX Group (VXX, UVIX)",
            'false': "1x VIX (VIXY)"
        },
        18: {
            'condition': lambda: get_rsi('XLF', 9) > 81,
            'ticker': 'XLF',
            'window': 9,
            'threshold': 81,
            'operator': '>',
            'true': 19,
            'false': 22
        },
        19: {
            'condition': lambda: get_rsi('XLF', 9) > 85,
            'ticker': 'XLF',
            'window': 9,
            'threshold': 85,
            'operator': '>',
            'true': "1.5x VIX Group (VXX, UVIX)",
            'false': "1x VIX (VIXY)"
        },
        22: {
            'condition': lambda: get_rsi('VOX', 9) > 79,
            'ticker': 'VOX',
            'window': 9,
            'threshold': 79,
            'operator': '>',
            'true': 23,
            'false': 24
        },
        23: {
            'condition': lambda: get_rsi('VOX', 9) > 82.5,
            'ticker': 'VOX',
            'window': 9,
            'threshold': 82.5,
            'operator': '>',
            'true': "1.5x VIX Group (VXX, UVIX)",
            'false': "1x VIX (VIXY)"
        },
        24: {
            'condition': lambda: get_rsi('CURE', 9) > 82,
            'ticker': 'CURE',
            'window': 9,
            'threshold': 82,
            'operator': '>',
            'true': 25,
            'false': 28
        },
        25: {
            'condition': lambda: get_rsi('CURE', 9) > 85,
            'ticker': 'CURE',
            'window': 9,
            'threshold': 85,
            'operator': '>',
            'true': "1.5x VIX Group (VXX, UVIX)",
            'false': "1x VIX (VIXY)"
        },
        28: {
            'condition': lambda: get_rsi('RETL', 9) > 82,
            'ticker': 'RETL',
            'window': 9,
            'threshold': 82,
            'operator': '>',
            'true': 29,
            'false': 32
        },
        29: {
            'condition': lambda: get_rsi('RETL', 9) > 85,
            'ticker': 'RETL',
            'window': 9,
            'threshold': 85,
            'operator': '>',
            'true': "1.5x VIX Group (VXX, UVIX)",
            'false': "1x VIX (VIXY)"
        },
        32: {
            'condition': lambda: get_rsi('LABU', 9) > 79,
            'ticker': 'LABU',
            'window': 9,
            'threshold': 79,
            'operator': '>',
            'true': "LABD",
            'false': 33
        },
        33: {
            'condition': lambda: get_rsi('SOXL', 9) < 25,
            'ticker': 'SOXL',
            'window': 9,
            'threshold': 25,
            'operator': '<',
            'true': "SOXL",
            'false': 34
        },
        34: {
            'condition': lambda: get_rsi('FNGU', 9) < 25,
            'ticker': 'FNGU',
            'window': 9,
            'threshold': 25,
            'operator': '<',
            'true': "FNGU",
            'false': 35
        },
        35: {
            'condition': lambda: get_rsi('TQQQ', 9) < 28,
            'ticker': 'TQQQ',
            'window': 9,
            'threshold': 28,
            'operator': '<',
            'true': 'SPECIAL_LOGIC',
            'false': 36
        },
        36: {
            'condition': lambda: get_rsi('TECL', 9) < 25,
            'ticker': 'TECL',
            'window': 9,
            'threshold': 25,
            'operator': '<',
            'true': "TECL",
            'false': 37
        },
        37: {
            'condition': lambda: get_rsi('UPRO', 9) < 25,
            'ticker': 'UPRO',
            'window': 9,
            'threshold': 25,
            'operator': '<',
            'true': "UPRO",
            'false': "BIL (T-Bill ETF)"
        }
    }

    # Start traversal at ID 1
    current_id = 1
    step_count = 0

    while True:
        step_count += 1
        node = logic_tree[current_id]

        # Evaluate condition
        result = node['condition']()
        current_rsi = get_rsi(node['ticker'], node['window'])
        operator = node.get('operator', '>')

        print(f"Step {step_count}: ID {current_id} ({node['ticker']} RSI({node['window']}) {operator} {node['threshold']}?) -> ", end="")
        print(f"Result: {result} (Current RSI: {current_rsi:.2f})")

        # Record this step in decision path
        decision_path.append({
            'ticker': node['ticker'],
            'window': node['window'],
            'operator': operator,
            'threshold': node['threshold'],
            'result': result,
            'current_rsi': current_rsi
        })

        # Determine next step
        next_step = node['true'] if result else node['false']

        # Check if we've reached a terminal result
        if isinstance(next_step, str):
            if next_step == 'SPECIAL_LOGIC':
                print(f"  → Executing Special Logic (ID 35)...")
                final_result = execute_special_logic_35()
            else:
                final_result = next_step

            print("\n" + "="*80)
            print("✓ FINAL RESULT:")
            print(f"  {final_result}")
            print("="*80 + "\n")
            return final_result, decision_path
        else:
            print(f"  → Going to ID {next_step}\n")
            current_id = next_step

def execute_special_logic_35():
    """
    Step 4: Special Logic for ID 35
    If RSI(TQQQ, 9) < 28 is TRUE:
    1. Fetch current 9-day RSI for: SOXL, TECL, TQQQ, FNGU
    2. Sort them ascending (lowest RSI first)
    3. Result: "Buy [Name1] and [Name2] (Bottom 2 RSIs)"
    """
    print("\n" + "-"*80)
    print("SPECIAL LOGIC (ID 35): Finding Bottom 2 RSIs")
    print("-"*80 + "\n")

    tickers_to_check = ['SOXL', 'TECL', 'TQQQ', 'FNGU']
    rsi_values = []

    for ticker in tickers_to_check:
        rsi = get_rsi(ticker, 9)
        rsi_values.append((ticker, rsi))
        print(f"{ticker:6s} - RSI(9): {rsi:.2f}")

    # Sort by RSI ascending (lowest first)
    rsi_values.sort(key=lambda x: x[1])

    bottom_2 = rsi_values[:2]

    print(f"\nBottom 2 RSIs:")
    print(f"  1. {bottom_2[0][0]} (RSI: {bottom_2[0][1]:.2f})")
    print(f"  2. {bottom_2[1][0]} (RSI: {bottom_2[1][1]:.2f})")
    print("-"*80 + "\n")

    result = f"Buy {bottom_2[0][0]} and {bottom_2[1][0]} (Bottom 2 RSIs: {bottom_2[0][1]:.2f}, {bottom_2[1][1]:.2f})"
    return result

def main():
    """
    Main execution function.
    Runs all steps in order with verification.
    """
    print("\n" + "╔" + "="*78 + "╗")
    print("║" + " "*20 + "TRADING ALGORITHM EXECUTOR" + " "*32 + "║")
    print("╚" + "="*78 + "╝")

    # Run unit test first
    test_rsi_calculation()

    # Step 1: Download data
    download_data()

    # Step 2: Calculate RSI
    calculate_all_rsi()

    # Step 3: Execute logic tree
    final_decision, decision_path = execute_logic()

    # Step 4: Check if we should notify
    print("\n" + "="*80)
    print("STEP 4: NOTIFICATION DECISION")
    print("="*80 + "\n")

    last_state = read_state()
    notify, reason = should_notify(final_decision, last_state)

    print(f"Current Signal: {final_decision}")
    if last_state:
        print(f"Last Signal: {last_state.get('signal', 'N/A')} (on {last_state.get('date', 'N/A')})")
    else:
        print("Last Signal: None (first run)")

    print(f"\nDecision: {'NOTIFY' if notify else 'SKIP'}")
    print(f"Reason: {reason}")

    print("\n" + "="*80 + "\n")

    # Step 5: Send Telegram notification (if needed and configured)
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    notified = False

    if notify and bot_token and chat_id:
        print("\n" + "="*80)
        print("STEP 5: SENDING TELEGRAM NOTIFICATION")
        print("="*80 + "\n")

        telegram_message = format_telegram_report(final_decision, rsi_cache, decision_path)
        success = send_telegram_message(telegram_message, bot_token, chat_id)

        if success:
            print("✓ Telegram message sent successfully!")
            notified = True
        else:
            print("⚠️  Failed to send Telegram message (see error above)")

        print("\n" + "="*80 + "\n")
    elif not notify:
        print("\n" + "="*80)
        print("ℹ️  Skipping Telegram notification (no change)")
        print("="*80 + "\n")
    else:
        print("\n" + "="*80)
        print("ℹ️  Telegram not configured (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID not set)")
        print("="*80 + "\n")

    # Step 6: Save state for next run
    write_state(final_decision, notified)

    print("\n" + "╔" + "="*78 + "╗")
    print("║" + " "*25 + "EXECUTION COMPLETE" + " "*35 + "║")
    print("╚" + "="*78 + "╝" + "\n")

    return final_decision

if __name__ == "__main__":
    main()
