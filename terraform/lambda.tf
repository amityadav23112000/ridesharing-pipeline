# lambda.tf — Lambda function for DynamoDB Stream → SNS surge alerts (FR3.2)

data "archive_file" "surge_alert_zip" {
  type        = "zip"
  source_file = "${path.module}/../lambda/surge_alert.py"
  output_path = "${path.module}/../lambda/surge_alert.zip"
}

resource "aws_lambda_function" "surge_alert" {
  function_name    = "${var.project_name}-surge-alert"
  filename         = data.archive_file.surge_alert_zip.output_path
  source_code_hash = data.archive_file.surge_alert_zip.output_base64sha256
  handler          = "surge_alert.lambda_handler"
  runtime          = "python3.11"
  role             = aws_iam_role.lambda_exec.arn
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      SNS_TOPIC_ARN = aws_sns_topic.surge_alerts.arn
      ALERT_THRESHOLD = "2.0"
    }
  }

  tags = var.common_tags
}

resource "aws_sns_topic" "surge_alerts" {
  name = "${var.project_name}-surge-alerts"
  tags = var.common_tags
}

resource "aws_sns_topic_subscription" "surge_email" {
  count     = var.alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.surge_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_lambda_event_source_mapping" "dynamo_stream" {
  event_source_arn  = aws_dynamodb_table.surge_pricing.stream_arn
  function_name     = aws_lambda_function.surge_alert.arn
  starting_position = "LATEST"
  batch_size        = 100
  filter_criteria {
    filter {
      pattern = jsonencode({ dynamodb = { NewImage = { surge_multiplier = { N = [{ numeric = [">=", 2] }] } } } })
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name = "${var.project_name}-lambda-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_dynamo_sns" {
  name = "${var.project_name}-lambda-dynamo-sns"
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetRecords", "dynamodb:GetShardIterator",
                    "dynamodb:DescribeStream", "dynamodb:ListStreams"]
        Resource = "${aws_dynamodb_table.surge_pricing.arn}/stream/*"
      },
      {
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = aws_sns_topic.surge_alerts.arn
      }
    ]
  })
}
