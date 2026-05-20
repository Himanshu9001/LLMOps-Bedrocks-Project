"""
Fine-tuning dataset preparation pipeline.
Sources: golden eval dataset + human-reviewed examples from feedback loop.
Output: JSONL in Bedrock fine-tuning format uploaded to S3.
Triggered automatically when eval score drops below threshold for 3 days.
"""

import os
import json
import boto3
import logging
from datetime import datetime, timezone
from decimal import Decimal

logger    = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

s3        = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb  = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))

EVAL_BUCKET   = os.environ.get("EVAL_BUCKET", "llmops-bedrock-dev-eval-datasets")
EVAL_TABLE    = os.environ.get("EVAL_TABLE", "llmops-bedrock-dev-eval-results")
MIN_SCORE     = float(os.environ.get("MIN_QUALITY_SCORE", "0.75"))


def prepare_finetuning_dataset(output_key: str = None) -> str:
    """
    Builds JSONL fine-tuning dataset from:
    1. Golden eval dataset (high-quality Q&A pairs)
    2. High-scoring eval results (actual good responses from live system)

    Bedrock fine-tuning format:
    {"prompt": "...", "completion": "..."}
    """
    examples = []

    # Source 1: golden dataset
    golden = _load_golden_dataset()
    for item in golden:
        examples.append({
            "prompt":     f"Question: {item['question']}\nAnswer:",
            "completion": item["expected_answer"]
        })

    # Source 2: high-scoring live responses from eval results
    live_examples = _load_high_quality_responses()
    examples.extend(live_examples)

    logger.info(f"Prepared {len(examples)} fine-tuning examples "
                f"({len(golden)} golden + {len(live_examples)} live)")

    # Write JSONL
    timestamp  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_key = output_key or f"finetuning/dataset_{timestamp}.jsonl"
    jsonl      = "\n".join(json.dumps(ex) for ex in examples)

    s3.put_object(
        Bucket=EVAL_BUCKET,
        Key=output_key,
        Body=jsonl.encode("utf-8"),
        ContentType="application/jsonl"
    )

    logger.info(f"Dataset uploaded: s3://{EVAL_BUCKET}/{output_key}")
    return f"s3://{EVAL_BUCKET}/{output_key}"


def should_trigger_finetune() -> dict:
    """
    Checks last 3 eval runs — triggers fine-tuning if score dropped
    below threshold for 3 consecutive days.
    This is the data flywheel trigger condition.
    """
    table    = dynamodb.Table(EVAL_TABLE)
    response = table.scan(
        FilterExpression="attribute_exists(avg_score)",
        Limit=10
    )

    items = sorted(
        response.get("Items", []),
        key=lambda x: x.get("timestamp", ""),
        reverse=True
    )[:3]

    if len(items) < 3:
        return {"trigger": False, "reason": "Insufficient eval history (need 3 runs)"}

    scores        = [float(item.get("avg_score", 1.0)) for item in items]
    all_below     = all(s < MIN_SCORE for s in scores)
    avg           = sum(scores) / len(scores)

    logger.info(f"Last 3 eval scores: {scores} — avg: {avg:.3f} — threshold: {MIN_SCORE}")

    if all_below:
        return {
            "trigger":  True,
            "reason":   f"Score below {MIN_SCORE} for 3 consecutive runs",
            "scores":   scores,
            "avg_score": avg
        }

    return {
        "trigger":  False,
        "reason":   f"Scores {scores} not all below threshold {MIN_SCORE}",
        "avg_score": avg
    }


def _load_golden_dataset() -> list:
    """Loads golden Q&A pairs from S3."""
    try:
        obj     = s3.get_object(Bucket=EVAL_BUCKET, Key="golden/rag_golden_dataset.jsonl")
        content = obj["Body"].read().decode("utf-8")
        return [json.loads(line) for line in content.strip().split("\n") if line]
    except Exception as e:
        logger.warning(f"Golden dataset load failed: {e}")
        return []


def _load_high_quality_responses() -> list:
    """
    Loads high-scoring responses from S3 eval results.
    Only includes examples where overall_score >= MIN_SCORE.
    These are proven good responses from the live system.
    """
    examples = []
    try:
        paginator = s3.get_paginator("list_objects_v2")
        pages     = paginator.paginate(Bucket=EVAL_BUCKET, Prefix="results/")

        for page in pages:
            for obj in page.get("Contents", [])[:5]:  # Last 5 eval runs
                try:
                    data    = json.loads(s3.get_object(
                        Bucket=EVAL_BUCKET, Key=obj["Key"]
                    )["Body"].read())

                    for result in data.get("results", []):
                        if result.get("overall_score", 0) >= MIN_SCORE:
                            examples.append({
                                "prompt":     f"Question: {result['question']}\nAnswer:",
                                "completion": result["actual"]
                            })
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"Live results load failed: {e}")

    return examples


if __name__ == "__main__":
    check = should_trigger_finetune()
    print(json.dumps(check, indent=2))

    if check["trigger"]:
        dataset_uri = prepare_finetuning_dataset()
        print(f"Dataset ready: {dataset_uri}")
    else:
        print("Fine-tuning not triggered")