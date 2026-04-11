locals {
  namespace = "RidesharingPipeline"
  scales    = ["5K", "50K", "500K"]
}

# ── CloudWatch Log Group for Spark ────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "spark" {
  name              = "/ridesharing/spark-streaming"
  retention_in_days = 14
  tags              = { Project = var.project }
}

# ── Alarms ────────────────────────────────────────────────────────────────────

# High latency alarm — fires when avg E2E latency > 10 s for 2 consecutive minutes
resource "aws_cloudwatch_metric_alarm" "high_latency" {
  for_each = toset(local.scales)

  alarm_name          = "ridesharing-high-latency-${each.value}"
  alarm_description   = "E2E latency > 10 000 ms for scale ${each.value}"
  namespace           = local.namespace
  metric_name         = "AvgLatencyMs"
  dimensions          = { Scale = each.value }
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 2
  threshold           = 10000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  tags = { Project = var.project }
}

# Low throughput alarm — fires when events/s drops below 10 for 3 minutes
resource "aws_cloudwatch_metric_alarm" "low_throughput" {
  for_each = toset(local.scales)

  alarm_name          = "ridesharing-low-throughput-${each.value}"
  alarm_description   = "Kafka events/s < 10 for scale ${each.value}"
  namespace           = local.namespace
  metric_name         = "KafkaEventsPerSecond"
  dimensions          = { Scale = each.value }
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 3
  threshold           = 10
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"

  tags = { Project = var.project }
}

# ── Dashboard ─────────────────────────────────────────────────────────────────
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "RidesharingPipeline"

  dashboard_body = jsonencode({
    widgets = [
      # ── Header ──────────────────────────────────────────────────────────
      {
        type   = "text"
        width  = 24
        height = 1
        properties = { markdown = "## Throughput" }
      },
      # ── KafkaEventsPerSecond ─────────────────────────────────────────────
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title   = "Kafka Events per Second"
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          metrics = [
            for s in local.scales : [local.namespace, "KafkaEventsPerSecond", "Scale", s]
          ]
          yAxis = { left = { min = 0, label = "events/s" } }
          period = 60
        }
      },
      # ── KafkaEventsPerBatch ──────────────────────────────────────────────
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title   = "Kafka Events per Batch"
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          metrics = [
            for s in local.scales : [local.namespace, "KafkaEventsPerBatch", "Scale", s]
          ]
          yAxis = { left = { min = 0, label = "events" } }
          period = 60
        }
      },
      # ── Latency header ───────────────────────────────────────────────────
      {
        type   = "text"
        width  = 24
        height = 1
        properties = { markdown = "## End-to-End Latency (event creation → DynamoDB write)" }
      },
      # ── AvgLatencyMs ─────────────────────────────────────────────────────
      {
        type   = "metric"
        width  = 8
        height = 6
        properties = {
          title   = "Avg E2E Latency"
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          metrics = [
            for s in local.scales : [local.namespace, "AvgLatencyMs", "Scale", s]
          ]
          yAxis = { left = { min = 0, label = "ms" } }
          period = 60
        }
      },
      # ── P95LatencyMs ─────────────────────────────────────────────────────
      {
        type   = "metric"
        width  = 8
        height = 6
        properties = {
          title   = "P95 E2E Latency"
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          metrics = [
            for s in local.scales : [local.namespace, "P95LatencyMs", "Scale", s]
          ]
          yAxis = { left = { min = 0, label = "ms" } }
          period = 60
        }
      },
      # ── P99LatencyMs ─────────────────────────────────────────────────────
      {
        type   = "metric"
        width  = 8
        height = 6
        properties = {
          title   = "P99 E2E Latency"
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          metrics = [
            for s in local.scales : [local.namespace, "P99LatencyMs", "Scale", s]
          ]
          yAxis = { left = { min = 0, label = "ms" } }
          period = 60
        }
      },
      # ── Surge header ─────────────────────────────────────────────────────
      {
        type   = "text"
        width  = 24
        height = 1
        properties = { markdown = "## Surge Activity" }
      },
      # ── ActiveSurgeZones ─────────────────────────────────────────────────
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title   = "Active Surge Zones"
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          metrics = [
            for s in local.scales : [local.namespace, "ActiveSurgeZones", "Scale", s]
          ]
          yAxis = { left = { min = 0, label = "zones" } }
          period = 60
        }
      },
      # ── ZonesProcessedPerBatch ───────────────────────────────────────────
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title   = "Zones Processed per Batch"
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          metrics = [
            for s in local.scales : [local.namespace, "ZonesProcessedPerBatch", "Scale", s]
          ]
          yAxis = { left = { min = 0, label = "zones" } }
          period = 60
        }
      },
      # ── Demand header ────────────────────────────────────────────────────
      {
        type   = "text"
        width  = 24
        height = 1
        properties = { markdown = "## Demand" }
      },
      # ── AvgDemandRatio ───────────────────────────────────────────────────
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title   = "Avg Demand Ratio (on_trip / available)"
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          metrics = [
            for s in local.scales : [local.namespace, "AvgDemandRatio", "Scale", s]
          ]
          yAxis = { left = { min = 0, label = "ratio" } }
          period = 60
        }
      },
      # ── TotalWaitingRiders ───────────────────────────────────────────────
      {
        type   = "metric"
        width  = 12
        height = 6
        properties = {
          title   = "Total Waiting Riders"
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          metrics = [
            for s in local.scales : [local.namespace, "TotalWaitingRiders", "Scale", s]
          ]
          yAxis = { left = { min = 0, label = "riders" } }
          period = 60
        }
      },
    ]
  })
}
