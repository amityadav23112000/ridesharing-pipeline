"""
ridesharing_pipeline_dag.py — Airflow DAG for batch pipeline (FR3.3)

Runs hourly:
  1. Check S3 for new raw data
  2. Trigger Glue batch processor
  3. Run Glue crawler to update Data Catalog
  4. Run Athena summary queries
  5. Send SNS success notification

Deploy on Amazon MWAA:
    aws s3 cp dags/ridesharing_pipeline_dag.py s3://$S3_BUCKET/dags/
    MWAA will auto-discover and schedule the DAG.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

# Optional AWS providers — gracefully absent in local dev
try:
    from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
    from airflow.providers.amazon.aws.operators.s3 import S3ListOperator
    HAS_AWS = True
except ImportError:
    HAS_AWS = False

# ── DEFAULT ARGS ──────────────────────────────────────────────────────────────
default_args = {
    "owner":            "ridesharing-pipeline",
    "retries":          2,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,   # set to True with real email in production
    "depends_on_past":  False,
}

# ── DAG ───────────────────────────────────────────────────────────────────────
with DAG(
    dag_id="ridesharing_batch_pipeline",
    default_args=default_args,
    description="Hourly batch processing: Glue → Crawler → Athena → SNS",
    schedule_interval="@hourly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["ridesharing", "batch", "analytics"],
    doc_md="""
## Ridesharing Batch Pipeline

Orchestrates the batch analytics tier of the ridesharing data pipeline.

**Flow:** S3 check → Glue ETL job → Glue crawler → Athena queries → SNS notify

**Infrastructure:**
- Glue job: `ridesharing-batch-processor` (glue_batch_job.py)
- S3 bucket: set via Airflow Variable `s3_bucket`
- SNS topic:  set via Airflow Variable `sns_topic`
""",
) as dag:

    # ── TASK 1: Check S3 for input data ───────────────────────────────────────
    if HAS_AWS:
        check_s3_data = S3ListOperator(
            task_id="check_s3_input_data",
            bucket="{{ var.value.s3_bucket }}",
            prefix="raw/",
            aws_conn_id="aws_default",
        )
    else:
        check_s3_data = BashOperator(
            task_id="check_s3_input_data",
            bash_command=(
                "aws s3 ls s3://{{ var.value.get('s3_bucket','ridesharing-pipeline-h20250060') }}/raw/ "
                "--recursive --human-readable | tail -5"
            ),
        )

    # ── TASK 2: Run Glue batch processor ─────────────────────────────────────
    if HAS_AWS:
        run_glue_job = GlueJobOperator(
            task_id="run_glue_batch_processor",
            job_name="ridesharing-batch-processor",
            script_location=(
                "s3://{{ var.value.get('s3_bucket','ridesharing-pipeline-h20250060') }}"
                "/scripts/glue_batch_job.py"
            ),
            aws_conn_id="aws_default",
            iam_role_name="AWSGlueServiceRole",
        )
    else:
        run_glue_job = BashOperator(
            task_id="run_glue_batch_processor",
            bash_command=(
                "aws glue start-job-run --job-name ridesharing-batch-processor "
                "--query 'JobRunId' --output text"
            ),
        )

    # ── TASK 3: Run Glue crawler ──────────────────────────────────────────────
    run_glue_crawler = BashOperator(
        task_id="run_glue_crawler",
        bash_command=(
            "aws glue start-crawler --name ridesharing-parquet-crawler && "
            "echo 'Crawler started — waiting for READY...' && "
            "for i in $(seq 1 20); do "
            "  S=$(aws glue get-crawler --name ridesharing-parquet-crawler "
            "    --query \"Crawler.State\" --output text); "
            "  echo \"  state=$S\"; "
            "  [ \"$S\" = \"READY\" ] && exit 0; "
            "  sleep 15; "
            "done; "
            "echo 'Crawler timed out' && exit 1"
        ),
    )

    # ── TASK 4: Run Athena summary queries ────────────────────────────────────
    run_athena_summary = BashOperator(
        task_id="run_athena_summary_queries",
        bash_command=(
            "aws athena start-query-execution "
            "  --query-string \"SELECT city_id, COUNT(*) as trips, "
            "    ROUND(AVG(demand_ratio),3) as avg_demand "
            "    FROM ridesharing_pipeline.zone_demand_summary "
            "    GROUP BY city_id ORDER BY trips DESC\" "
            "  --query-execution-context Database=ridesharing_pipeline "
            "  --result-configuration OutputLocation="
            "s3://{{ var.value.get('s3_bucket','ridesharing-pipeline-h20250060') }}/athena-results/ "
            "  --work-group ridesharing-analytics "
            "  --query 'QueryExecutionId' --output text"
        ),
    )

    # ── TASK 5: Notify success via SNS ────────────────────────────────────────
    notify_success = BashOperator(
        task_id="notify_success",
        bash_command=(
            "aws sns publish "
            "  --topic-arn {{ var.value.get('sns_topic','') }} "
            "  --message 'Ridesharing batch pipeline complete: {{ ds }}' "
            "  --subject 'Pipeline OK' 2>/dev/null || "
            "echo 'SNS not configured — skipping notification'"
        ),
    )

    # ── DEPENDENCIES ──────────────────────────────────────────────────────────
    check_s3_data >> run_glue_job >> run_glue_crawler >> run_athena_summary >> notify_success
