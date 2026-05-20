"""
Main evaluation pipeline — runs golden dataset against live RAG endpoint,
scores each response with LLM judge, writes results to DynamoDB.
Triggered by: prompt version promotion, nightly cron, model swap.
"""

import os
import json
import uuid
import logging
import requests
import boto3
from datetime import datetime, timezone
from decimal import Decimal

from judge import evaluate_response

logger      = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

dynamodb    = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
s3_client   = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))

EVAL_TABLE      = os.environ.get("EVAL_TABLE", "llmops-bedrock-dev-eval-results")
EVAL_BUCKET     = os.environ.get("EVAL_BUCKET", "llmops-bedrock-dev-eval-datasets")
API_ENDPOINT    = os.environ.get("API_ENDPOINT", "http://localhost:8080")
PROMPT_VERSION  = os.environ.get("PROMPT_VERSION", "1")
PASS_THRESHOLD  = float(os.environ.get("PASS_THRESHOLD", "0.70"))

eval_table  = dynamodb.Table(EVAL_TABLE)


def run_evaluation(dataset_key: str = "golden/rag_golden_dataset.jsonl") -> dict:
    """
    Runs full evaluation pipeline against golden dataset.
    Returns summary with pass/fail determination for CI gate.
    """
    eval_run_id = str(uuid.uuid4())
    logger.info(f"Starting eval run: {eval_run_id}")

    # Load golden dataset from S3
    dataset = _load_dataset(dataset_key)
    logger.info(f"Loaded {len(dataset)} golden Q&A pairs")

    results     = []
    total_score = 0.0

    for i, item in enumerate(dataset):
        logger.info(f"Evaluating {i+1}/{len(dataset)}: {item['question'][:50]}...")

        # Call live RAG API
        actual_answer, context = _call_rag_api(
            item["question"],
            item.get("tenant_id", "default")
        )

        # Score with LLM judge
        scores = evaluate_response(
            question=item["question"],
            expected_answer=item["expected_answer"],
            actual_answer=actual_answer,
            context=context
        )

        result = {
            "question":        item["question"],
            "expected":        item["expected_answer"],
            "actual":          actual_answer,
            "category":        item.get("category", "general"),
            "scores":          scores,
            "overall_score":   scores["overall"]
        }

        results.append(result)
        total_score += scores["overall"]

        logger.info(f"Score: {scores['overall']:.3f} — {scores.get('reasoning', '')[:80]}")

    avg_score  = total_score / len(results) if results else 0.0
    passed     = avg_score >= PASS_THRESHOLD

    summary = {
        "eval_run_id":    eval_run_id,
        "prompt_version": PROMPT_VERSION,
        "total_samples":  len(results),
        "avg_score":      round(avg_score, 4),
        "passed":         passed,
        "threshold":      PASS_THRESHOLD,
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "per_category":   _aggregate_by_category(results)
    }

    # Write results to DynamoDB
    _write_results(eval_run_id, summary, results)

    logger.info(f"Eval complete: score={avg_score:.3f} passed={passed}")
    return summary


def _load_dataset(key: str) -> list:
    """Loads JSONL golden dataset from S3."""
    obj      = s3_client.get_object(Bucket=EVAL_BUCKET, Key=key)
    content  = obj["Body"].read().decode("utf-8")
    return [json.loads(line) for line in content.strip().split("\n") if line]


def _call_rag_api(question: str, tenant_id: str) -> tuple:
    """Calls live RAG API endpoint, returns (answer, context_str)."""
    try:
        response = requests.post(
            f"{API_ENDPOINT}/query",
            json={"query": question, "tenant_id": tenant_id},
            timeout=30
        )
        data    = response.json()
        answer  = data.get("answer", "")
        context = " ".join([c.get("content", "") for c in data.get("citations", [])])
        return answer, context
    except Exception as e:
        logger.error(f"RAG API call failed: {e}")
        return "API call failed", ""


def _aggregate_by_category(results: list) -> dict:
    """Groups scores by question category for drill-down analysis."""
    categories = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r["overall_score"])

    return {
        cat: round(sum(scores)/len(scores), 4)
        for cat, scores in categories.items()
    }


def _write_results(eval_run_id: str, summary: dict, results: list):
    """Writes eval summary to DynamoDB and detailed results to S3."""
    # DynamoDB — summary record for CI gate queries
    eval_table.put_item(Item={
        "eval_run_id":    eval_run_id,
        "prompt_version": summary["prompt_version"],
        "avg_score":      Decimal(str(summary["avg_score"])),
        "passed":         summary["passed"],
        "total_samples":  summary["total_samples"],
        "timestamp":      summary["timestamp"],
        "per_category":   json.dumps(summary["per_category"])
    })

    # S3 — full detailed results for analysis
    s3_client.put_object(
        Bucket=EVAL_BUCKET,
        Key=f"results/{eval_run_id}.json",
        Body=json.dumps({"summary": summary, "results": results}, indent=2)
    )

    logger.info(f"Results written: DynamoDB + s3://eval-datasets/results/{eval_run_id}.json")


if __name__ == "__main__":
    summary = run_evaluation()
    print(json.dumps(summary, indent=2))