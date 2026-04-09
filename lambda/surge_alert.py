# surge_alert.py
# AWS Lambda function — triggered by DynamoDB Streams
# Sends SNS email when surge > 2.0x or speed > 100kmh

import os
import json
import boto3
from decimal import Decimal

sns = boto3.client('sns', region_name='ap-south-1')
SNS_TOPIC = 'arn:aws:sns:ap-south-1:276209672013:ridesharing-alerts'

def lambda_handler(event, context):
    """
    Triggered by DynamoDB Streams on surge_pricing table.
    Every new surge record → this function runs.
    Checks if surge > threshold → sends alert.
    """
    alerts_sent = 0

    for record in event['Records']:
        # Only process new records (INSERT or MODIFY)
        if record['eventName'] not in ['INSERT', 'MODIFY']:
            continue

        # Get new record data
        new_image = record['dynamodb'].get('NewImage', {})
        if not new_image:
            continue

        zone_id    = new_image.get('zone_id',    {}).get('S', 'UNKNOWN')
        city_id    = new_image.get('city_id',    {}).get('S', 'UNKNOWN')
        surge      = float(new_image.get('surge_multiplier', {}).get('N', '1.0'))
        waiting    = int(new_image.get('waiting_riders',     {}).get('N', '0'))
        available  = int(new_image.get('available_drivers',  {}).get('N', '0'))
        latency    = float(new_image.get('processing_latency_ms', {}).get('N', '0'))
        scale      = new_image.get('scale_level', {}).get('S', 'unknown')

        # ALERT 1: High surge pricing
        if surge >= 2.5:
            message = f"""
SURGE PRICING ALERT

Zone:       {zone_id}
City:       {city_id}
Surge:      {surge}x
Waiting:    {waiting} riders
Available:  {available} drivers
Latency:    {latency:.0f}ms
Scale:      {scale}

Action: Consider repositioning drivers to {zone_id}
            """
            try:
                sns.publish(
                    TopicArn=SNS_TOPIC,
                    Subject=f'SURGE {surge}x — {zone_id}',
                    Message=message
                )
                alerts_sent += 1
                print(f"Alert sent: SURGE {surge}x in {zone_id}")
            except Exception as e:
                print(f"SNS error: {e}")

    print(f"Processed {len(event['Records'])} records, sent {alerts_sent} alerts")
    return {'statusCode': 200, 'alerts_sent': alerts_sent}
