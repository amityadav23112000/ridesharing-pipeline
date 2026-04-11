# ── surge_pricing table ───────────────────────────────────────────────────────
# Partition key : zone_id   (e.g. MUM_Z05)
# Sort key      : timestamp (ISO 8601 string, made unique with batch_id + index)
# TTL attribute : ttl       (Unix epoch — auto-expire old records after 24 h)
resource "aws_dynamodb_table" "surge_pricing" {
  name         = var.surge_table_name
  billing_mode = "PAY_PER_REQUEST"   # no capacity planning needed for M.Tech scale

  hash_key  = "zone_id"
  range_key = "timestamp"

  attribute {
    name = "zone_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # DynamoDB Streams → Lambda surge alerts (Phase 4)
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Project = var.project
    Table   = "surge-pricing"
  }
}

# ── driver_status table ───────────────────────────────────────────────────────
# Partition key : driver_id
# TTL           : 5 minutes — keeps only live drivers in the table
resource "aws_dynamodb_table" "driver_status" {
  name         = var.driver_table_name
  billing_mode = "PAY_PER_REQUEST"

  hash_key = "driver_id"

  attribute {
    name = "driver_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Project = var.project
    Table   = "driver-status"
  }
}
