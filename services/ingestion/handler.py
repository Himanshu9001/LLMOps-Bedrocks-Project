"""
Lambda ingestion handler — triggered by S3 PutObject events on the raw bucket.
Flow: S3 upload → Lambda → PyMuPDF parse → metadata → DynamoDB → Bedrock KB sync
"""

import json
import os
import uuid
import boto3
import logging
from datetime import datetime, timezone
from urllib.parse import unquote_plus

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Clients ───────────────────────────────────────────────────────────────────
s3_client         = boto3.client("s3")
dynamodb          = boto3.resource("dynamodb")
bedrock_agent     = boto3.client("bedrock-agent", region_name=os.environ["AWS_REGION"])

# ── Environment variables (injected by Lambda Terraform config) ───────────────
KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
DATA_SOURCE_ID    = os.environ["DATA_SOURCE_ID"]
METADATA_TABLE    = os.environ["METADATA_TABLE"]
PROCESSED_BUCKET  = os.environ["PROCESSED_BUCKET"]

metadata_table = dynamodb.Table(METADATA_TABLE)


def lambda_handler(event, context):
    """
    Entry point — processes each S3 record from the event.
    S3 can batch multiple records in one event under high load.
    """
    results = []

    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key    = unquote_plus(record["s3"]["object"]["key"])

        logger.info(f"Processing: s3://{bucket}/{key}")

        try:
            result = process_document(bucket, key)
            results.append({"key": key, "status": "success", "chunks": result["chunk_count"]})
        except Exception as e:
            logger.error(f"Failed to process {key}: {str(e)}", exc_info=True)
            results.append({"key": key, "status": "failed", "error": str(e)})

    # Trigger Bedrock KB sync after all documents processed
    # Single sync job per Lambda invocation — not per document
    try:
        trigger_kb_sync()
    except Exception as e:
        logger.error(f"KB sync trigger failed: {str(e)}", exc_info=True)

    logger.info(f"Processed {len(results)} documents: {results}")
    return {"statusCode": 200, "body": json.dumps(results)}


def process_document(bucket: str, key: str) -> dict:
    """
    Downloads document from S3, extracts metadata, writes to DynamoDB.
    Actual chunking/embedding is handled by Bedrock KB sync — not here.
    Lambda's job: metadata enrichment + audit trail only.
    """
    # Extract tenant_id and document type from S3 key convention
    # Expected key format: {tenant_id}/{doc_type}/{filename}
    # e.g. tenant_acme/10-k/apple_2024_10k.pdf
    parts     = key.split("/")
    tenant_id = parts[0] if len(parts) >= 3 else "default"
    doc_type  = parts[1] if len(parts) >= 3 else "unknown"
    filename  = parts[-1]

    # Download file to /tmp — Lambda has 512MB ephemeral storage
    local_path = f"/tmp/{uuid.uuid4()}_{filename}"
    s3_client.download_file(bucket, key, local_path)

    # Extract metadata based on file type
    if filename.lower().endswith(".pdf"):
        metadata = extract_pdf_metadata(local_path, filename)
    else:
        metadata = extract_text_metadata(local_path, filename)

    # Build chunk metadata record for DynamoDB
    doc_id    = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    item = {
        "tenant_id":          tenant_id,
        "chunk_id":           doc_id,
        "document_type":      doc_type,
        "filename":           filename,
        "s3_key":             key,
        "s3_bucket":          bucket,
        "ingestion_timestamp": timestamp,
        "page_count":         metadata.get("page_count", 0),
        "word_count":         metadata.get("word_count", 0),
        "parse_status":       metadata.get("status", "success"),
        "knowledge_base_id":  KNOWLEDGE_BASE_ID,
    }

    # Write metadata to DynamoDB
    metadata_table.put_item(Item=item)
    logger.info(f"Metadata written to DynamoDB: {doc_id}")

    # Copy to processed bucket for audit trail
    processed_key = f"processed/{tenant_id}/{doc_type}/{filename}"
    s3_client.copy_object(
        CopySource={"Bucket": bucket, "Key": key},
        Bucket=PROCESSED_BUCKET,
        Key=processed_key
    )

    return {"doc_id": doc_id, "chunk_count": metadata.get("page_count", 1)}


def extract_pdf_metadata(local_path: str, filename: str) -> dict:
    """
    Extracts page count and word count from PDF using PyMuPDF (fitz).
    PyMuPDF handles encrypted PDFs, scanned docs, and complex layouts
    better than pdfplumber for metadata extraction.
    Falls back gracefully if parsing fails — never blocks ingestion.
    """
    try:
        import fitz  # PyMuPDF

        doc        = fitz.open(local_path)
        page_count = len(doc)
        word_count = 0

        for page in doc:
            # Extract text and count words per page
            text        = page.get_text()
            word_count += len(text.split())

        doc.close()

        # Flag low-quality extractions — likely scanned PDFs
        parse_status = "success" if word_count > 100 else "low_quality"

        logger.info(f"{filename}: {page_count} pages, {word_count} words, status={parse_status}")

        return {
            "page_count":   page_count,
            "word_count":   word_count,
            "status":       parse_status
        }

    except Exception as e:
        logger.warning(f"PDF parse failed for {filename}: {e}")
        return {"page_count": 0, "word_count": 0, "status": "parse_failed"}


def extract_text_metadata(local_path: str, filename: str) -> dict:
    """
    Extracts word count from plain text files (.txt, .md, .json).
    """
    try:
        with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
            content    = f.read()
            word_count = len(content.split())

        return {"page_count": 1, "word_count": word_count, "status": "success"}

    except Exception as e:
        logger.warning(f"Text parse failed for {filename}: {e}")
        return {"page_count": 1, "word_count": 0, "status": "parse_failed"}


def trigger_kb_sync() -> None:
    """
    Triggers Bedrock Knowledge Base ingestion job.
    This is what actually chunks, embeds, and indexes documents into OpenSearch.
    Lambda only handles metadata — Bedrock handles the heavy lifting.
    clientToken ensures idempotency — same token = same job, no duplicates.
    """
    client_token = str(uuid.uuid4())

    response = bedrock_agent.start_ingestion_job(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        dataSourceId=DATA_SOURCE_ID,
        clientToken=client_token,
        description=f"Auto-sync triggered by Lambda at {datetime.now(timezone.utc).isoformat()}"
    )

    job_id = response["ingestionJob"]["ingestionJobId"]
    status = response["ingestionJob"]["status"]

    logger.info(f"KB sync job started: {job_id}, status: {status}")