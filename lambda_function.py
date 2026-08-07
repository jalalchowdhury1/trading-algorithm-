"""
AWS Lambda handler for trading algorithm.
This function is triggered by EventBridge on a schedule.
"""

import json
import os
from main import main
from market_hours import is_market_open

def lambda_handler(event, context):
    """
    Lambda handler function called by AWS.

    Args:
        event: EventBridge event data
        context: Lambda context object

    Returns:
        Response with status code and result
    """
    print("="*80)
    print("Lambda function started")
    print(f"Event: {json.dumps(event)}")
    print("="*80)

    # Gate on market hours exactly as the GitHub Actions path does (that workflow
    # runs market_hours.py and skips the step when it exits non-zero). Without this
    # the `cron(0/10 10-16 ? * MON-FRI)` schedule fires FIVE times after the 16:00
    # close (16:10-16:50 ET) and recomputes the signal on after-hours data — which is
    # how the S3 state came to read "1.5x VIX Group" at 16:50 on 2026-08-06 while the
    # Actions state, written at 11:59 during the session, read "1x VIX". Same day,
    # same algorithm, two different answers.
    if not is_market_open():
        print("Market is CLOSED — skipping execution (no signal recomputed).")
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Market closed — skipped', 'signal': None})
        }

    try:
        # Run the trading algorithm
        result = main()

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Trading algorithm executed successfully',
                'signal': result
            })
        }

    except Exception as e:
        # RE-RAISE. Returning a 500 *inside the body* is still a SUCCESSFUL Lambda
        # invocation, so AWS/Lambda `Errors` stays 0.0 and any alarm built on it is
        # blind. The only error ever recorded for this function got through solely
        # because download_data() calls exit(1) and SystemExit bypasses `except
        # Exception`. Let AWS see real failures.
        print(f"Error executing trading algorithm: {str(e)}")
        raise
