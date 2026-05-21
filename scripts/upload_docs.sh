#!/bin/bash
# Upload documents to S3 with required metadata sidecar files.
# Usage: ./scripts/upload_docs.sh <file_path> <tenant_id> <doc_type>
# Example: ./scripts/upload_docs.sh docs/manual.pdf tenant_acme general

set -e

FILE_PATH=$1
TENANT_ID=${2:-"tenant_test"}
DOC_TYPE=${3:-"general"}
BUCKET="llmops-bedrock-dev-raw"
REGION="us-east-1"

if [ -z "$FILE_PATH" ]; then
  echo "Usage: $0 <file_path> [tenant_id] [doc_type]"
  exit 1
fi

FILENAME=$(basename "$FILE_PATH")
S3_KEY="${TENANT_ID}/${DOC_TYPE}/${FILENAME}"
METADATA_FILE="/tmp/${FILENAME}.metadata.json"

# Create metadata sidecar
cat > "$METADATA_FILE" << METADATA
{
  "metadataAttributes": {
    "tenant_id": "${TENANT_ID}",
    "document_type": "${DOC_TYPE}",
    "source_file": "${FILENAME}",
    "uploaded_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  }
}
METADATA

echo "Uploading document: s3://${BUCKET}/${S3_KEY}"
aws s3 cp "$FILE_PATH" "s3://${BUCKET}/${S3_KEY}" --region "$REGION"

echo "Uploading metadata: s3://${BUCKET}/${S3_KEY}.metadata.json"
aws s3 cp "$METADATA_FILE" "s3://${BUCKET}/${S3_KEY}.metadata.json" --region "$REGION"

echo "Triggering KB sync..."
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id 0OW8LBTZU5 \
  --data-source-id $(aws bedrock-agent list-data-sources \
    --knowledge-base-id 0OW8LBTZU5 \
    --query "dataSourceSummaries[0].dataSourceId" \
    --output text --region "$REGION") \
  --region "$REGION"

echo "Done. Document will be indexed in ~60 seconds."
rm -f "$METADATA_FILE"
