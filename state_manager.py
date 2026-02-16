"""
State management for trading algorithm.
Supports both local file storage (for local/GitHub) and S3 (for Lambda).
"""

import json
import os
from datetime import datetime
import pytz

# Check if running in AWS Lambda
IS_LAMBDA = os.environ.get('AWS_LAMBDA_FUNCTION_NAME') is not None

STATE_FILE = 'trading_state.json'
S3_BUCKET = os.environ.get('STATE_BUCKET_NAME', 'trading-algorithm-state')
S3_KEY = 'trading_state.json'

if IS_LAMBDA:
    import boto3
    s3_client = boto3.client('s3')


def read_state():
    """
    Read the last trading signal state.
    Returns dict with 'signal' and 'date', or None if doesn't exist.
    """
    try:
        if IS_LAMBDA:
            # Read from S3
            response = s3_client.get_object(Bucket=S3_BUCKET, Key=S3_KEY)
            state_json = response['Body'].read().decode('utf-8')
            return json.loads(state_json)
        else:
            # Read from local file
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
    except Exception as e:
        print(f"⚠️  Could not read state: {e}")
    return None


def write_state(signal, notified):
    """
    Write current trading signal state.

    Args:
        signal: The current trading signal
        notified: Whether we sent a notification this time
    """
    try:
        # Get current time in Eastern Time
        et_tz = pytz.timezone('America/New_York')
        et_time = datetime.now(pytz.UTC).astimezone(et_tz)

        state = {
            'signal': signal,
            'date': et_time.strftime('%Y-%m-%d'),
            'timestamp': et_time.strftime('%Y-%m-%d %H:%M:%S'),
            'notified': notified
        }
        state_json = json.dumps(state, indent=2)

        if IS_LAMBDA:
            # Write to S3
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=S3_KEY,
                Body=state_json,
                ContentType='application/json'
            )
            print(f"✓ State saved to S3: s3://{S3_BUCKET}/{S3_KEY}")
        else:
            # Write to local file
            with open(STATE_FILE, 'w') as f:
                f.write(state_json)
            print(f"✓ State saved to local file: {STATE_FILE}")

    except Exception as e:
        print(f"⚠️  Could not write state: {e}")
