"""
AWS Lambda handler for trading algorithm.
This function is triggered by EventBridge on a schedule.
"""

import json
import os
from main import main

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
        print(f"Error executing trading algorithm: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Error executing trading algorithm',
                'error': str(e)
            })
        }
