output "s3_bucket_name" {
  description = "S3 bucket used for checkpoints, batch data, and scripts"
  value       = aws_s3_bucket.pipeline.bucket
}

output "surge_table_name" {
  description = "DynamoDB surge pricing table name"
  value       = aws_dynamodb_table.surge_pricing.name
}

output "surge_table_stream_arn" {
  description = "DynamoDB Streams ARN — connect Lambda surge alerts here"
  value       = aws_dynamodb_table.surge_pricing.stream_arn
}

output "driver_table_name" {
  description = "DynamoDB driver status table name"
  value       = aws_dynamodb_table.driver_status.name
}

output "spark_ec2_instance_profile" {
  description = "EC2 instance profile to attach when launching Spark nodes"
  value       = aws_iam_instance_profile.spark_ec2.name
}

output "lambda_surge_role_arn" {
  description = "IAM role ARN for the surge alert Lambda"
  value       = aws_iam_role.lambda_surge.arn
}

output "cloudwatch_dashboard_url" {
  description = "Direct link to the CloudWatch dashboard"
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=RidesharingPipeline"
}

output "spark_log_group" {
  description = "CloudWatch log group for Spark streaming job"
  value       = aws_cloudwatch_log_group.spark.name
}
