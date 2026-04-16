# athena.tf — Athena workgroup and saved queries (FR3.2 / FR4.3)

resource "aws_athena_workgroup" "analytics" {
  name        = "${var.project_name}-analytics"
  description = "Ridesharing pipeline analytical queries"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.pipeline.bucket}/athena-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }

    bytes_scanned_cutoff_per_query = 10737418240  # 10 GB safety limit
  }

  tags = var.common_tags
}

# Saved analytical queries
resource "aws_athena_named_query" "surge_zones" {
  name        = "top-surge-zones"
  workgroup   = aws_athena_workgroup.analytics.id
  database    = aws_glue_catalog_database.ridesharing.name
  description = "Top 20 surge zones by event count"
  query       = <<-SQL
    SELECT city_id, zone_id,
           COUNT(*) AS surge_events,
           ROUND(AVG(demand_ratio), 2) AS avg_demand,
           ROUND(MAX(demand_ratio), 2) AS peak_demand
    FROM ridesharing_pipeline.zone_demand_summary
    WHERE surge_multiplier >= 2.0
    GROUP BY city_id, zone_id
    ORDER BY surge_events DESC
    LIMIT 20;
  SQL
}

resource "aws_athena_named_query" "latency_percentiles" {
  name        = "latency-percentiles"
  workgroup   = aws_athena_workgroup.analytics.id
  database    = aws_glue_catalog_database.ridesharing.name
  description = "Processing latency percentiles by experiment"
  query       = <<-SQL
    SELECT experiment_name,
           ROUND(AVG(processing_latency_ms), 0)                        AS avg_ms,
           ROUND(APPROX_PERCENTILE(processing_latency_ms, 0.5),  0)    AS p50_ms,
           ROUND(APPROX_PERCENTILE(processing_latency_ms, 0.95), 0)    AS p95_ms,
           ROUND(APPROX_PERCENTILE(processing_latency_ms, 0.99), 0)    AS p99_ms,
           COUNT(*)                                                      AS sample_count
    FROM ridesharing_pipeline.pipeline_metrics
    GROUP BY experiment_name
    ORDER BY avg_ms ASC;
  SQL
}

resource "aws_athena_named_query" "cost_per_gb" {
  name        = "cost-per-gb"
  workgroup   = aws_athena_workgroup.analytics.id
  database    = aws_glue_catalog_database.ridesharing.name
  description = "Cost efficiency: USD per GB processed"
  query       = <<-SQL
    SELECT experiment_name,
           infrastructure,
           ROUND(total_cost_usd, 4)                                          AS total_cost,
           ROUND(total_bytes_processed / 1073741824.0, 3)                    AS gb_processed,
           ROUND(total_cost_usd / NULLIF(total_bytes_processed/1073741824.0, 0), 4) AS cost_per_gb
    FROM ridesharing_pipeline.cost_metrics
    ORDER BY cost_per_gb ASC;
  SQL
}

resource "aws_athena_named_query" "city_heatmap" {
  name        = "city-utilization-heatmap"
  workgroup   = aws_athena_workgroup.analytics.id
  database    = aws_glue_catalog_database.ridesharing.name
  description = "Driver utilization rate and surge frequency by city"
  query       = <<-SQL
    SELECT city_id,
           COUNT(*)                                                        AS total_trips,
           ROUND(AVG(on_trip_count * 1.0 / NULLIF(total_count, 0)), 3)   AS avg_utilization,
           SUM(CASE WHEN surge_multiplier >= 2.0 THEN 1 ELSE 0 END)       AS surge_periods,
           ROUND(AVG(demand_ratio), 3)                                     AS avg_demand
    FROM ridesharing_pipeline.zone_demand_summary
    GROUP BY city_id
    ORDER BY total_trips DESC;
  SQL
}
