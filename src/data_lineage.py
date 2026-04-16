#!/usr/bin/env python3
"""
data_lineage.py — Data lineage tracker (OBS1)

Records which pipeline stage processed each event batch,
writes lineage records to DynamoDB table 'ridesharing-lineage'
and logs to stdout for Prometheus scraping.

Lineage record schema:
    batch_id       — UUID per Spark micro-batch
    stage          — ingestion | streaming | batch_glue | athena
    input_source   — e.g. kafka://gps-normal
    output_sink    — e.g. dynamodb://surge-pricing | s3://bucket/path
    record_count   — events in this batch
    started_at     — ISO-8601
    completed_at   — ISO-8601
    duration_ms    — processing duration
    schema_version — 1 or 2
    status         — success | failed | partial

Usage (from Spark job):
    from src.data_lineage import LineageTracker
    tracker = LineageTracker(stage="streaming")
    bid = tracker.start_batch(source="kafka://gps-normal", count=1000)
    # ... do work ...
    tracker.end_batch(bid, sink="dynamodb://surge-pricing", status="success")
"""

import os
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
LINEAGE_TABLE  = os.environ.get("LINEAGE_TABLE",  "ridesharing-lineage")
AWS_REGION     = os.environ.get("AWS_REGION",     "ap-south-1")
ENABLE_DYNAMO  = os.environ.get("LINEAGE_DYNAMO", "true").lower() == "true"


class LineageTracker:
    """Lightweight lineage tracker for ridesharing pipeline stages."""

    def __init__(self, stage: str):
        self.stage = stage
        self._open: dict = {}
        self._dynamo = None
        if ENABLE_DYNAMO:
            self._init_dynamo()

    def _init_dynamo(self):
        try:
            import boto3
            self._dynamo = boto3.resource("dynamodb", region_name=AWS_REGION)
            self._table  = self._dynamo.Table(LINEAGE_TABLE)
        except Exception as e:
            logger.warning(f"[lineage] DynamoDB init failed: {e} — logging only")
            self._dynamo = None

    # ── PUBLIC ────────────────────────────────────────────────────────────────
    def start_batch(
        self,
        source: str,
        count: int,
        schema_version: int = 2,
    ) -> str:
        """Register batch start. Returns batch_id."""
        batch_id = str(uuid.uuid4())
        self._open[batch_id] = {
            "batch_id":       batch_id,
            "stage":          self.stage,
            "input_source":   source,
            "record_count":   count,
            "started_at":     datetime.now(tz=timezone.utc).isoformat(),
            "schema_version": schema_version,
            "_t0":            time.time(),
        }
        logger.info(
            f"[lineage] START  stage={self.stage} batch={batch_id[:8]} "
            f"source={source} count={count}"
        )
        return batch_id

    def end_batch(
        self,
        batch_id: str,
        sink: str,
        status: str = "success",
        error: Optional[str] = None,
    ) -> None:
        """Record batch completion and write to DynamoDB."""
        if batch_id not in self._open:
            logger.warning(f"[lineage] Unknown batch_id {batch_id[:8]}")
            return

        record = self._open.pop(batch_id)
        now    = datetime.now(tz=timezone.utc).isoformat()
        dur_ms = int((time.time() - record.pop("_t0")) * 1000)

        record.update({
            "output_sink":   sink,
            "completed_at":  now,
            "duration_ms":   dur_ms,
            "status":        status,
        })
        if error:
            record["error"] = error[:500]

        logger.info(
            f"[lineage] END    stage={self.stage} batch={batch_id[:8]} "
            f"sink={sink} status={status} dur={dur_ms}ms"
        )

        # Write to DynamoDB (best-effort — never block pipeline)
        if self._dynamo:
            try:
                self._table.put_item(Item=record)
            except Exception as e:
                logger.warning(f"[lineage] DynamoDB write failed: {e}")

    def record_schema_upgrade(
        self,
        batch_id: str,
        from_version: int,
        to_version: int,
        upgraded_count: int,
    ) -> None:
        """Log schema upgrade event for a batch."""
        logger.info(
            f"[lineage] SCHEMA batch={batch_id[:8]} "
            f"v{from_version}→v{to_version} upgraded={upgraded_count}"
        )

    # ── PROMETHEUS METRICS ────────────────────────────────────────────────────
    def prometheus_metrics(self) -> str:
        open_count = len(self._open)
        return (
            "# HELP lineage_open_batches Currently in-flight batches\n"
            "# TYPE lineage_open_batches gauge\n"
            f"lineage_open_batches{{stage=\"{self.stage}\"}} {open_count}\n"
        )


# ── STANDALONE TEST ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    t = LineageTracker(stage="streaming")
    bid = t.start_batch(source="kafka://gps-normal", count=500)
    time.sleep(0.1)
    t.end_batch(bid, sink="dynamodb://surge-pricing", status="success")
    print(t.prometheus_metrics())
    print("data_lineage: OK")
