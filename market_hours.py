import sys
from datetime import datetime
import pytz

def is_market_open():
    """
    Returns True if US stock market is currently open.
    Market hours: Monday-Friday, 9:30 AM - 4:00 PM ET
    """
    et_tz = pytz.timezone('US/Eastern')
    now_et = datetime.now(et_tz)

    # Check if weekday (0=Monday, 6=Sunday)
    if now_et.weekday() > 4:  # Saturday or Sunday
        return False

    # Check if within market hours (9:30 AM - 4:00 PM)
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= now_et <= market_close

if __name__ == "__main__":
    if is_market_open():
        print("✓ Market is OPEN - proceeding with execution")
        sys.exit(0)
    else:
        print("⏸ Market is CLOSED - skipping execution")
        sys.exit(1)
