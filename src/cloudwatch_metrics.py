# cloudwatch_metrics.py
# Publishes pipeline metrics to AWS CloudWatch
# Called after every window flush in stream_processor.py

import os
import boto3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

cloudwatch = boto3.client(
    'cloudwatch',
    region_name=os.getenv('AWS_DEFAULT_REGION', 'ap-south-1')
)

NAMESPACE = 'RidesharingPipeline'

def publish(events_per_sec, latency_ms, surge_zones,
            window_sec, flush_ms, total_events, scale_level):
    """
    Push all metrics to CloudWatch in one API call.
    scale_level: '5K', '50K', or '500K' — identifies experiment
    """
    try:
        now = datetime.utcnow()
        cloudwatch.put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[
                {
                    'MetricName': 'EventsPerSecond',
                    'Value':      events_per_sec,
                    'Unit':       'Count/Second',
                    'Timestamp':  now,
                    'Dimensions': [
                        {'Name': 'Scale', 'Value': scale_level}
                    ]
                },
                {
                    'MetricName': 'AvgLatencyMs',
                    'Value':      latency_ms,
                    'Unit':       'Milliseconds',
                    'Timestamp':  now,
                    'Dimensions': [
                        {'Name': 'Scale', 'Value': scale_level}
                    ]
                },
                {
                    'MetricName': 'ActiveSurgeZones',
                    'Value':      surge_zones,
                    'Unit':       'Count',
                    'Timestamp':  now,
                    'Dimensions': [
                        {'Name': 'Scale', 'Value': scale_level}
                    ]
                },
                {
                    'MetricName': 'WindowSizeSeconds',
                    'Value':      window_sec,
                    'Unit':       'Seconds',
                    'Timestamp':  now,
                    'Dimensions': [
                        {'Name': 'Scale', 'Value': scale_level}
                    ]
                },
                {
                    'MetricName': 'FlushTimeMs',
                    'Value':      flush_ms,
                    'Unit':       'Milliseconds',
                    'Timestamp':  now,
                    'Dimensions': [
                        {'Name': 'Scale', 'Value': scale_level}
                    ]
                },
                {
                    'MetricName': 'TotalEventsProcessed',
                    'Value':      total_events,
                    'Unit':       'Count',
                    'Timestamp':  now,
                    'Dimensions': [
                        {'Name': 'Scale', 'Value': scale_level}
                    ]
                },
            ]
        )
        logger.info(
            f"CloudWatch published | "
            f"scale={scale_level} | "
            f"throughput={events_per_sec:.1f}/s | "
            f"latency={latency_ms:.0f}ms | "
            f"surge_zones={surge_zones} | "
            f"window={window_sec}s"
        )
    except Exception as e:
        logger.error(f"CloudWatch error: {e}")
