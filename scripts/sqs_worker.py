"""Run one durable SQS worker: python scripts/sqs_worker.py"""

from __future__ import annotations

import logging
import os
import time

import boto3

from core.execution.sqs_taskqueue import decode_task

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("sqs-worker")


def main() -> None:
    queue_url = os.environ["TASK_QUEUE_URL"]
    client = boto3.client("sqs", region_name=os.getenv("AWS_REGION"))
    wait = int(os.getenv("TASK_QUEUE_LONG_POLL_SECONDS", "20"))
    visibility = int(os.getenv("TASK_QUEUE_VISIBILITY_TIMEOUT", "900"))
    logger.info("SQS worker listening on configured queue")
    while True:
        response = client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=wait,
            VisibilityTimeout=visibility,
            AttributeNames=["ApproximateReceiveCount"],
        )
        messages = response.get("Messages", [])
        if not messages:
            continue
        message = messages[0]
        try:
            func, args, kwargs = decode_task(message["Body"])
            logger.info("running %s", getattr(func, "__name__", func))
            func(*args, **kwargs)
        except Exception:
            logger.exception("task failed; leaving message for retry/dead-letter queue")
            time.sleep(1)
            continue
        client.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])


if __name__ == "__main__":
    main()
