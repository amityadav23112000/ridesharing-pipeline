# ── EC2 instance role (for Spark on EC2 / EMR bootstrap) ─────────────────────
data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "spark_ec2" {
  name               = "${local.prefix}-spark-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
  tags               = { Project = var.project }
}

resource "aws_iam_instance_profile" "spark_ec2" {
  name = "${local.prefix}-spark-ec2-profile"
  role = aws_iam_role.spark_ec2.name
}

# Inline policy: DynamoDB + S3 + CloudWatch
data "aws_iam_policy_document" "spark_permissions" {
  statement {
    sid    = "DynamoDB"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:BatchWriteItem",
    ]
    resources = [
      aws_dynamodb_table.surge_pricing.arn,
      aws_dynamodb_table.driver_status.arn,
    ]
  }

  statement {
    sid    = "S3Pipeline"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.pipeline.arn,
      "${aws_s3_bucket.pipeline.arn}/*",
    ]
  }

  statement {
    sid    = "CloudWatch"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData",
      "cloudwatch:GetMetricStatistics",
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "spark_ec2" {
  name   = "spark-pipeline-access"
  role   = aws_iam_role.spark_ec2.id
  policy = data.aws_iam_policy_document.spark_permissions.json
}

# ── Lambda execution role (for surge alert Lambda) ────────────────────────────
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_surge" {
  name               = "${local.prefix}-lambda-surge-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = { Project = var.project }
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_surge.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid    = "DynamoDBStreams"
    effect = "Allow"
    actions = [
      "dynamodb:GetRecords",
      "dynamodb:GetShardIterator",
      "dynamodb:DescribeStream",
      "dynamodb:ListStreams",
    ]
    resources = ["${aws_dynamodb_table.surge_pricing.arn}/stream/*"]
  }

  statement {
    sid    = "SNS"
    effect = "Allow"
    actions = ["sns:Publish"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_surge" {
  name   = "surge-alert-access"
  role   = aws_iam_role.lambda_surge.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}
