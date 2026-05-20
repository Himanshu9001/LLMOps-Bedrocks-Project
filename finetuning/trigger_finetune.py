"""
Bedrock fine-tuning job trigger.
Creates a custom model fine-tuning job on Amazon Titan or Llama.
Called by Step Functions or manually when dataset is ready.
Fine-tuned model goes through same eval → CI gate → promotion pipeline.
"""

import os
import json
import boto3
import logging
from datetime import datetime, timezone

logger  = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

bedrock = boto3.client("bedrock", region_name=os.environ.get("AWS_REGION", "us-east-1"))
s3      = boto3.client("s3",     region_name=os.environ.get("AWS_REGION", "us-east-1"))

EVAL_BUCKET     = os.environ.get("EVAL_BUCKET", "llmops-bedrock-dev-eval-datasets")
OUTPUT_BUCKET   = os.environ.get("EVAL_BUCKET", "llmops-bedrock-dev-eval-datasets")
FINETUNE_ROLE   = os.environ.get("FINETUNE_ROLE_ARN", "")

# Bedrock supports fine-tuning on: amazon.titan-text-express-v1, meta.llama2-13b, cohere.command
BASE_MODEL_ID   = "amazon.titan-text-express-v1"


def start_finetuning_job(dataset_s3_uri: str, job_name: str = None) -> dict:
    """
    Starts a Bedrock model customization (fine-tuning) job.
    Job runs asynchronously — poll status via get_model_customization_job.
    Fine-tuned model registered in Bedrock model registry on completion.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    job_name  = job_name or f"llmops-finetune-{timestamp}"

    output_uri = f"s3://{OUTPUT_BUCKET}/finetuning/output/{job_name}/"

    logger.info(f"Starting fine-tuning job: {job_name}")
    logger.info(f"Base model: {BASE_MODEL_ID}")
    logger.info(f"Dataset: {dataset_s3_uri}")

    try:
        response = bedrock.create_model_customization_job(
            jobName=job_name,
            customModelName=f"llmops-custom-{timestamp}",
            roleArn=FINETUNE_ROLE,
            baseModelIdentifier=BASE_MODEL_ID,
            customizationType="FINE_TUNING",
            trainingDataConfig={"s3Uri": dataset_s3_uri},
            outputDataConfig={"s3Uri": output_uri},
            hyperParameters={
                "epochCount":        "3",
                "batchSize":         "8",
                "learningRate":      "0.00005",
                "learningRateWarmupSteps": "100"
            }
        )

        job_arn = response["jobArn"]
        logger.info(f"Fine-tuning job started: {job_arn}")

        return {
            "job_name":   job_name,
            "job_arn":    job_arn,
            "base_model": BASE_MODEL_ID,
            "dataset":    dataset_s3_uri,
            "output":     output_uri,
            "status":     "STARTED"
        }

    except Exception as e:
        logger.error(f"Fine-tuning job failed to start: {e}")
        raise


def check_job_status(job_name: str) -> dict:
    """Polls fine-tuning job status — used by Step Functions wait loop."""
    response = bedrock.get_model_customization_job(jobIdentifier=job_name)
    return {
        "job_name": job_name,
        "status":   response["status"],
        "model_id": response.get("outputModelArn", "")
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        dataset_uri = sys.argv[1]
        result      = start_finetuning_job(dataset_uri)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python trigger_finetune.py s3://bucket/path/dataset.jsonl")