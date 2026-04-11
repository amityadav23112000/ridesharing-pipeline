terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # ── Remote state in S3 (uncomment after the bucket exists) ──
  # backend "s3" {
  #   bucket = "ridesharing-pipeline-h20250060"
  #   key    = "terraform/state.tfstate"
  #   region = "ap-south-1"
  # }
}

provider "aws" {
  region = var.aws_region
}

# Convenient local: project-prefixed name helper
locals {
  prefix = "${var.project}-${var.student_id}"
}
