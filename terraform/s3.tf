# ── Main pipeline bucket ──────────────────────────────────────────────────────
# Stores: Spark checkpoints, batch data (Parquet), Glue scripts, Lambda ZIPs
resource "aws_s3_bucket" "pipeline" {
  bucket = "${var.project}-${var.student_id}"

  tags = {
    Project = var.project
  }
}

resource "aws_s3_bucket_versioning" "pipeline" {
  bucket = aws_s3_bucket.pipeline.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "pipeline" {
  bucket = aws_s3_bucket.pipeline.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "pipeline" {
  bucket = aws_s3_bucket.pipeline.id

  rule {
    id     = "expire-checkpoints"
    status = "Enabled"
    filter { prefix = "checkpoints/" }
    expiration { days = 7 }
  }

  rule {
    id     = "transition-batch-data"
    status = "Enabled"
    filter { prefix = "data/" }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "pipeline" {
  bucket                  = aws_s3_bucket.pipeline.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── Folder structure (zero-byte objects as prefix markers) ────────────────────
resource "aws_s3_object" "prefixes" {
  for_each = toset(["checkpoints/", "data/raw/", "data/processed/", "scripts/", "lambda/"])
  bucket   = aws_s3_bucket.pipeline.id
  key      = each.value
  content  = ""
}
