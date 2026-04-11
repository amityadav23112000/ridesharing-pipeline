variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "ap-south-1"
}

variable "project" {
  description = "Project name prefix used in all resource names"
  type        = string
  default     = "ridesharing-pipeline"
}

variable "student_id" {
  description = "BITS Pilani student ID — used in S3 bucket name to ensure global uniqueness"
  type        = string
  default     = "h20250060"
}

variable "surge_table_name" {
  description = "DynamoDB table for surge pricing results"
  type        = string
  default     = "surge_pricing"
}

variable "driver_table_name" {
  description = "DynamoDB table for real-time driver locations"
  type        = string
  default     = "driver_status"
}

variable "window_seconds" {
  description = "Spark streaming window size in seconds"
  type        = number
  default     = 10
}
