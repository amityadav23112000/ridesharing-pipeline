# glue.tf — Glue batch job, crawler, and Data Catalog (FR3.2)

resource "aws_glue_catalog_database" "ridesharing" {
  name        = "ridesharing_pipeline"
  description = "Ridesharing pipeline — batch analytics data catalog"
}

resource "aws_glue_job" "batch_processor" {
  name         = "${var.project_name}-batch-processor"
  role_arn     = aws_iam_role.glue_exec.arn
  glue_version = "4.0"
  worker_type  = "G.1X"
  number_of_workers = 2
  timeout      = 60   # minutes

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.pipeline.bucket}/scripts/glue_batch_job.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--TempDir"                          = "s3://${aws_s3_bucket.pipeline.bucket}/glue-temp/"
    "--S3_BUCKET"                        = aws_s3_bucket.pipeline.bucket
    "--DYNAMO_TABLE"                     = aws_dynamodb_table.surge_pricing.name
  }

  tags = var.common_tags
}

resource "aws_glue_crawler" "parquet" {
  name          = "${var.project_name}-parquet-crawler"
  role          = aws_iam_role.glue_exec.arn
  database_name = aws_glue_catalog_database.ridesharing.name
  description   = "Crawls processed Parquet files and registers tables in Data Catalog"

  s3_target {
    path = "s3://${aws_s3_bucket.pipeline.bucket}/processed/"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  configuration = jsonencode({
    Version = 1.0
    CrawlerOutput = {
      Partitions = { AddOrUpdateBehavior = "InheritFromTable" }
    }
  })

  tags = var.common_tags
}

resource "aws_iam_role" "glue_exec" {
  name = "${var.project_name}-glue-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "glue.amazonaws.com" }
    }]
  })
  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue_s3_dynamo" {
  name = "${var.project_name}-glue-s3-dynamo"
  role = aws_iam_role.glue_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:ListBucket"]
        Resource = ["${aws_s3_bucket.pipeline.arn}","${aws_s3_bucket.pipeline.arn}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Scan","dynamodb:GetItem","dynamodb:Query"]
        Resource = aws_dynamodb_table.surge_pricing.arn
      }
    ]
  })
}
