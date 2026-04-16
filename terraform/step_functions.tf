# step_functions.tf — Step Functions state machine for batch pipeline (FR3.2)

resource "aws_sfn_state_machine" "batch_pipeline" {
  name     = "${var.project_name}-batch-pipeline"
  role_arn = aws_iam_role.sfn_exec.arn

  definition = jsonencode({
    Comment = "Ridesharing batch pipeline: Glue ETL → Crawler → Athena → Notify"
    StartAt = "RunGlueJob"
    States = {
      RunGlueJob = {
        Type     = "Task"
        Resource = "arn:aws:states:::glue:startJobRun.sync"
        Parameters = {
          JobName = aws_glue_job.batch_processor.name
        }
        Retry = [{
          ErrorEquals     = ["States.TaskFailed"]
          IntervalSeconds = 60
          MaxAttempts     = 2
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "NotifyFailure"
        }]
        Next = "StartCrawler"
      }

      StartCrawler = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:glue:startCrawler"
        Parameters = {
          Name = aws_glue_crawler.parquet.name
        }
        Next = "WaitForCrawler"
      }

      WaitForCrawler = {
        Type    = "Wait"
        Seconds = 60
        Next    = "CheckCrawlerStatus"
      }

      CheckCrawlerStatus = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:glue:getCrawler"
        Parameters = {
          Name = aws_glue_crawler.parquet.name
        }
        Next = "IsCrawlerReady"
      }

      IsCrawlerReady = {
        Type = "Choice"
        Choices = [{
          Variable      = "$.Crawler.State"
          StringEquals  = "READY"
          Next          = "RunAthenaQuery"
        }]
        Default = "WaitForCrawler"
      }

      RunAthenaQuery = {
        Type     = "Task"
        Resource = "arn:aws:states:::athena:startQueryExecution.sync"
        Parameters = {
          QueryString = "SELECT city_id, COUNT(*) as trips FROM ridesharing_pipeline.zone_demand_summary GROUP BY city_id"
          QueryExecutionContext = { Database = "ridesharing_pipeline" }
          ResultConfiguration = {
            OutputLocation = "s3://${aws_s3_bucket.pipeline.bucket}/athena-results/"
          }
          WorkGroup = aws_athena_workgroup.analytics.name
        }
        Next = "NotifySuccess"
      }

      NotifySuccess = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn = aws_sns_topic.surge_alerts.arn
          Message  = "Ridesharing batch pipeline completed successfully"
          Subject  = "Pipeline OK"
        }
        End = true
      }

      NotifyFailure = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"
        Parameters = {
          TopicArn = aws_sns_topic.surge_alerts.arn
          "Message.$" = "$.Cause"
          Subject  = "Pipeline FAILED"
        }
        End = true
      }
    }
  })

  tags = var.common_tags
}

# EventBridge rule to trigger pipeline hourly
resource "aws_cloudwatch_event_rule" "hourly_batch" {
  name                = "${var.project_name}-hourly-batch"
  description         = "Trigger ridesharing batch pipeline every hour"
  schedule_expression = "rate(1 hour)"
  tags                = var.common_tags
}

resource "aws_cloudwatch_event_target" "batch_sfn" {
  rule     = aws_cloudwatch_event_rule.hourly_batch.name
  arn      = aws_sfn_state_machine.batch_pipeline.arn
  role_arn = aws_iam_role.sfn_exec.arn
}

resource "aws_iam_role" "sfn_exec" {
  name = "${var.project_name}-sfn-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = {
        Service = ["states.amazonaws.com", "events.amazonaws.com"]
      }
    }]
  })
  tags = var.common_tags
}

resource "aws_iam_role_policy" "sfn_policy" {
  name = "${var.project_name}-sfn-policy"
  role = aws_iam_role.sfn_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["glue:StartJobRun","glue:GetJobRun","glue:StartCrawler","glue:GetCrawler"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["athena:StartQueryExecution","athena:GetQueryExecution"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "sns:Publish"
        Resource = aws_sns_topic.surge_alerts.arn
      },
      {
        Effect   = "Allow"
        Action   = "states:StartExecution"
        Resource = aws_sfn_state_machine.batch_pipeline.arn
      }
    ]
  })
}
