#!/usr/bin/env python3
# cloudwatch_dashboard.py
# Creates / updates the CloudWatch dashboard for the ride-sharing pipeline.
# Usage:
#   python infrastructure/cloudwatch_dashboard.py
#   python infrastructure/cloudwatch_dashboard.py --region ap-south-1

import json
import boto3
import argparse
import os

DASHBOARD_NAME = 'RidesharingPipeline'
NAMESPACE      = 'RidesharingPipeline'
SCALES         = ['5K', '50K', '500K']
COLORS         = {'5K': '#1f77b4', '50K': '#ff7f0e', '500K': '#2ca02c'}
REGION         = os.getenv('AWS_DEFAULT_REGION', 'ap-south-1')


def _metric(name, scale, stat='Average', period=60, label=None):
    """Build a single CloudWatch metric spec."""
    return [
        NAMESPACE, name,
        'Scale', scale,
        {
            'stat':   stat,
            'period': period,
            'label':  label or f'{name} ({scale})',
            'color':  COLORS.get(scale, '#aec7e8'),
        }
    ]


def build_dashboard():
    """Return the CloudWatch dashboard body as a JSON string."""

    def timeseries(title, metrics, y_label='', y_left=None):
        """A single time-series widget."""
        widget_metrics = []
        for name, scale, stat in metrics:
            widget_metrics.append(_metric(name, scale, stat))
        props = {
            'view':    'timeSeries',
            'stacked': False,
            'title':   title,
            'metrics': widget_metrics,
            'yAxis':   {'left': y_left or {'min': 0}},
        }
        if y_label:
            props['yAxis']['left']['label'] = y_label
        return {'type': 'metric', 'properties': props}

    def alarm_widget(title, alarm_names):
        return {
            'type': 'alarm',
            'properties': {
                'title': title,
                'alarms': alarm_names,
            }
        }

    # ── Row 1: Throughput ──────────────────────────────────────────────────
    throughput = {
        'type': 'metric',
        'width': 12,
        'height': 6,
        'properties': {
            'title': 'Kafka Events per Second (all scales)',
            'view': 'timeSeries',
            'stacked': False,
            'metrics': [_metric('KafkaEventsPerSecond', s) for s in SCALES],
            'yAxis': {'left': {'min': 0, 'label': 'events/s'}},
            'period': 60,
        }
    }

    events_per_batch = {
        'type': 'metric',
        'width': 12,
        'height': 6,
        'properties': {
            'title': 'Kafka Events per Batch',
            'view': 'timeSeries',
            'stacked': False,
            'metrics': [_metric('KafkaEventsPerBatch', s) for s in SCALES],
            'yAxis': {'left': {'min': 0, 'label': 'events'}},
            'period': 60,
        }
    }

    # ── Row 2: Latency ─────────────────────────────────────────────────────
    avg_latency = {
        'type': 'metric',
        'width': 8,
        'height': 6,
        'properties': {
            'title': 'Avg E2E Latency (event → DynamoDB)',
            'view': 'timeSeries',
            'stacked': False,
            'metrics': [_metric('AvgLatencyMs', s) for s in SCALES],
            'yAxis': {'left': {'min': 0, 'label': 'ms'}},
            'period': 60,
        }
    }

    p95_latency = {
        'type': 'metric',
        'width': 8,
        'height': 6,
        'properties': {
            'title': 'P95 E2E Latency',
            'view': 'timeSeries',
            'stacked': False,
            'metrics': [_metric('P95LatencyMs', s) for s in SCALES],
            'yAxis': {'left': {'min': 0, 'label': 'ms'}},
            'period': 60,
        }
    }

    p99_latency = {
        'type': 'metric',
        'width': 8,
        'height': 6,
        'properties': {
            'title': 'P99 E2E Latency',
            'view': 'timeSeries',
            'stacked': False,
            'metrics': [_metric('P99LatencyMs', s) for s in SCALES],
            'yAxis': {'left': {'min': 0, 'label': 'ms'}},
            'period': 60,
        }
    }

    # ── Row 3: Surge activity ──────────────────────────────────────────────
    surge_zones = {
        'type': 'metric',
        'width': 12,
        'height': 6,
        'properties': {
            'title': 'Active Surge Zones',
            'view': 'timeSeries',
            'stacked': False,
            'metrics': [_metric('ActiveSurgeZones', s) for s in SCALES],
            'yAxis': {'left': {'min': 0, 'label': 'zones'}},
            'period': 60,
        }
    }

    zones_processed = {
        'type': 'metric',
        'width': 12,
        'height': 6,
        'properties': {
            'title': 'Zones Processed per Batch',
            'view': 'timeSeries',
            'stacked': False,
            'metrics': [_metric('ZonesProcessedPerBatch', s) for s in SCALES],
            'yAxis': {'left': {'min': 0, 'label': 'zones'}},
            'period': 60,
        }
    }

    # ── Row 4: Demand ──────────────────────────────────────────────────────
    demand_ratio = {
        'type': 'metric',
        'width': 12,
        'height': 6,
        'properties': {
            'title': 'Avg Demand Ratio (on_trip / available)',
            'view': 'timeSeries',
            'stacked': False,
            'metrics': [_metric('AvgDemandRatio', s) for s in SCALES],
            'yAxis': {'left': {'min': 0, 'label': 'ratio'}},
            'period': 60,
        }
    }

    waiting_riders = {
        'type': 'metric',
        'width': 12,
        'height': 6,
        'properties': {
            'title': 'Total Waiting Riders',
            'view': 'timeSeries',
            'stacked': False,
            'metrics': [_metric('TotalWaitingRiders', s) for s in SCALES],
            'yAxis': {'left': {'min': 0, 'label': 'riders'}},
            'period': 60,
        }
    }

    # ── Section headers ────────────────────────────────────────────────────
    def header(text):
        return {
            'type': 'text',
            'width': 24,
            'height': 1,
            'properties': {'markdown': f'## {text}'},
        }

    widgets = [
        header('Throughput'),
        throughput, events_per_batch,
        header('End-to-End Latency (event creation → DynamoDB write)'),
        avg_latency, p95_latency, p99_latency,
        header('Surge Activity'),
        surge_zones, zones_processed,
        header('Demand'),
        demand_ratio, waiting_riders,
    ]

    return json.dumps({'widgets': widgets})


def deploy(region):
    cw   = boto3.client('cloudwatch', region_name=region)
    body = build_dashboard()
    cw.put_dashboard(DashboardName=DASHBOARD_NAME, DashboardBody=body)
    print(f"Dashboard '{DASHBOARD_NAME}' deployed to {region}")
    url = (
        f"https://{region}.console.aws.amazon.com/cloudwatch/home"
        f"?region={region}#dashboards:name={DASHBOARD_NAME}"
    )
    print(f"URL: {url}")

    # Also write the JSON body to disk for reference / version control
    out = 'infrastructure/cloudwatch_dashboard.json'
    with open(out, 'w') as f:
        json.dump(json.loads(body), f, indent=2)
    print(f"Dashboard JSON saved to {out}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Deploy CloudWatch dashboard for the ridesharing pipeline'
    )
    parser.add_argument('--region', default=REGION,
                        help='AWS region (default: ap-south-1)')
    args = parser.parse_args()
    deploy(args.region)
