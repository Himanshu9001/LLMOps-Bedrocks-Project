# LLMOps Platform — Troubleshooting Guide

**Project:** Enterprise LLMOps Platform on Amazon Bedrock  
**Author:** Himanshu Singh  
**Purpose:** Documents every real issue encountered during the build and how it was resolved

---

## Table of Contents

1. [Terraform Issues](#1-terraform-issues)
2. [AWS Bedrock Issues](#2-aws-bedrock-issues)
3. [Docker & ECR Issues](#3-docker--ecr-issues)
4. [Kubernetes & EKS Issues](#4-kubernetes--eks-issues)
5. [IAM & Permissions Issues](#5-iam--permissions-issues)
6. [OpenSearch Serverless Issues](#6-opensearch-serverless-issues)
7. [FastAPI & Application Issues](#7-fastapi--application-issues)
8. [GitHub Actions CI/CD Issues](#8-github-actions-cicd-issues)
9. [Git & Repository Issues](#9-git--repository-issues)
10. [AWS Resource Cleanup Issues](#10-aws-resource-cleanup-issues)

---

## 1. Terraform Issues

---

### 1.1 S3 Lifecycle Rule Missing `filter {}` Block

**Phase:** Phase 1 — S3 Module  
**Error:**
```
Warning: Invalid Attribute Combination
with module.s3.aws_s3_bucket_lifecycle_configuration.raw,
No attribute specified when one (and only one) of [rule[0].filter,rule[0].prefix] is required
```

**Root Cause:**  
AWS provider v5+ requires every lifecycle rule to have an explicit `filter` block. In v4, omitting `filter` was implicitly treated as "apply to all objects". In v5, this became a hard requirement.

**Fix:**  
Add an empty `filter {}` block to the lifecycle rule:

```hcl
rule {
  id     = "raw-docs-tiering"
  status = "Enabled"

  filter {}   # Empty = apply to all objects. Required by AWS provider v5+

  transition {
    days          = 30
    storage_class = "STANDARD_IA"
  }
}
```

**Lesson:**  
Always pin provider versions and read the upgrade guide when bumping major versions. `filter {}` is now mandatory — `filter { prefix = "docs/" }` scopes to a prefix, `filter {}` applies to all objects.

---

### 1.2 `dynamodb_table` Backend Parameter Deprecated

**Phase:** Phase 1 — Remote State  
**Error:**
```
Warning: Deprecated Parameter
The parameter "dynamodb_table" is deprecated. Use parameter "use_lockfile" instead.
```

**Root Cause:**  
Terraform AWS provider v5.100 deprecated `dynamodb_table` for state locking in favor of S3 native locking via `use_lockfile = true`. This was introduced in Terraform 1.10+.

**Fix:**  
Update `terraform/live/dev/main.tf` backend block:

```hcl
backend "s3" {
  bucket       = "llmops-bedrock-tfstate"
  key          = "dev/terraform.tfstate"
  region       = "us-east-1"
  use_lockfile = true    # Replaces deprecated dynamodb_table
  encrypt      = true
}
```

Then run `terraform init -reconfigure` to pick up the backend change.

**Lesson:**  
`use_lockfile` writes a `.tflock` file directly to S3 instead of using a separate DynamoDB table. Simpler setup, one less resource to manage. Requires Terraform 1.10+.

---

### 1.3 Semicolons in HCL Variable Blocks

**Phase:** Multiple phases  
**Error:**
```
Error: Invalid character
The ";" character is not valid. Use newlines to separate arguments and blocks
```

**Root Cause:**  
HCL does not allow semicolons as argument separators. Single-line variable blocks like:
```hcl
variable "common_tags" { type = map(string); default = {} }
```
are invalid — HCL requires newlines between arguments.

**Fix:**  
Always expand variable blocks to multi-line format:

```hcl
variable "common_tags" {
  type    = map(string)
  default = {}
}
```

**Lesson:**  
HCL's block syntax only allows one argument per line. Unlike JSON or Python, semicolons have no meaning in HCL. This error appeared 3+ times across different modules — the rule is simple: never put semicolons in HCL.

---

### 1.4 Duplicate Output Definition

**Phase:** Phase 2 — IAM Module  
**Error:**
```
Error: Duplicate output definition
An output named "lambda_execution_role_arn" was already defined at outputs.tf:3,1-35.
```

**Root Cause:**  
Adding a new block-style output without removing the existing single-line version created a duplicate.

**Fix:**  
Replace the entire `outputs.tf` file using `cat >` to overwrite, ensuring only one definition per output name.

**Prevention:**  
Before adding any output, run:
```bash
grep -n "output " terraform/modules/iam/outputs.tf
```
to check for existing definitions.

---

### 1.5 Module Not Installed After Adding New Module

**Phase:** Multiple phases  
**Error:**
```
Error: Module not installed
This module is not yet installed. Run "terraform init" to install all modules required.
```

**Root Cause:**  
Adding a new `module` block to `main.tf` requires `terraform init` to register it in `.terraform/modules/modules.json`. The module code being on disk is not sufficient — Terraform needs to create the registry entry.

**Fix:**  
Always run `terraform init` after adding a new module block, before running plan:
```bash
terraform init
terraform plan -var-file=terraform.tfvars
```

**Lesson:**  
`terraform init` for local modules creates a symlink/entry in `.terraform/modules/modules.json`. Without it, Terraform's module registry doesn't know the module exists even if the code is on disk.

---

### 1.6 VPC Deletion DependencyViolation

**Phase:** Cleanup  
**Error:**
```
Error: deleting EC2 VPC: DependencyViolation: The vpc has dependencies and cannot be deleted.
```

**Root Cause:**  
The AWS Load Balancer Controller created two security groups (`k8s-traffic-*` and `k8s-llmops-*`) outside of Terraform management. These orphaned SGs blocked VPC deletion.

**Fix:**  
Manually delete the orphaned security groups before running `terraform destroy`:
```bash
# Find orphaned SGs
aws ec2 describe-security-groups \
  --filters "Name=vpc-id,Values=<VPC_ID>" \
  --query "SecurityGroups[?GroupName!='default'].{ID:GroupId,Name:GroupName}" \
  --output table

# Delete each one
aws ec2 delete-security-group --group-id sg-xxxx
```

**Lesson:**  
Any AWS controller running inside Kubernetes (ALB controller, cluster autoscaler, etc.) creates AWS resources outside Terraform state. These must be cleaned up manually before `terraform destroy` can succeed. Use `force_destroy` arguments where available, or pre-destroy scripts.

---

### 1.7 S3 Bucket Not Empty on Destroy

**Phase:** Cleanup  
**Error:**
```
Error: deleting S3 Bucket: BucketNotEmpty: The bucket you tried to delete is not empty.
You must delete all versions in the bucket.
```

**Root Cause:**  
S3 buckets with versioning enabled retain all object versions and delete markers even after `aws s3 rm --recursive`. The bucket cannot be deleted until all versions are removed.

**Fix:**  
Empty versioned buckets before destroy:
```bash
# Delete all current objects
aws s3 rm s3://bucket-name --recursive

# Delete all versions and delete markers
aws s3api list-object-versions --bucket bucket-name \
  --query '[Versions,DeleteMarkers][].[Key,VersionId]' \
  --output text | while read key version; do
    aws s3api delete-object --bucket bucket-name --key "$key" --version-id "$version"
done
```

**Alternative:**  
Add `force_destroy = true` to the S3 bucket resource in Terraform (risky in production — deletes all data on `terraform destroy`).

---

## 2. AWS Bedrock Issues

---

### 2.1 Claude Model Marked as Legacy

**Phase:** Phase 2 — Bedrock Testing  
**Error:**
```
ResourceNotFoundException: Access denied. This Model is marked by provider as Legacy
and you have not been actively using the model in the last 30 days.
```

**Root Cause:**  
Claude 3 Haiku (`anthropic.claude-3-haiku-20240307-v1:0`) and Claude 3.5 Sonnet were marked legacy in this AWS account. AWS automatically transitions models to legacy status when newer versions are available and the account hasn't used them recently.

**Fix:**  
Check available active models:
```bash
aws bedrock list-foundation-models \
  --region us-east-1 \
  --by-provider Anthropic \
  --query "modelSummaries[?modelLifecycle.status=='ACTIVE'].{ID:modelId,Name:modelName}" \
  --output table
```

Update all model ARNs to currently active models (Claude Sonnet 4.5, Haiku 4.5, Opus 4.6 in this account).

**Lesson:**  
Never hardcode specific model version ARNs without checking availability. Always run `list-foundation-models` at project start to confirm which models are `ACTIVE` in your account.

---

### 2.2 Cross-Region Inference Profile Required for Claude 4.x

**Phase:** Phase 3 — FastAPI RAG  
**Error:**
```
ValidationException: Invocation of model ID anthropic.claude-sonnet-4-5-20250929-v1:0
with on-demand throughput isn't supported. Retry your request with the ID or ARN
of an inference profile that contains this model.
```

**Root Cause:**  
Claude 4.x models require cross-region inference profiles (`us.` prefix) instead of direct model IDs. AWS routes requests across US regions for load balancing and availability.

**Fix:**  
Use inference profile ARNs for invocation:
```
# Wrong
anthropic.claude-sonnet-4-5-20250929-v1:0

# Correct
arn:aws:bedrock:us-east-1:011528270076:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0
```

Also update IAM policies to include both foundation model ARNs and inference profile ARNs:
```hcl
Resource = [
  "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0",
  "arn:aws:bedrock:*:011528270076:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0"
]
```

---

### 2.3 Anthropic Use Case Form Required

**Phase:** Phase 3 — FastAPI RAG  
**Error:**
```
ValidationException: Model use case details have not been submitted for this account.
Fill out the Anthropic use case details form before using the model.
```

**Root Cause:**  
Anthropic requires first-time users to submit use case details before accessing Claude models via Bedrock. This is a one-time account-level requirement.

**Fix:**  
Go to: `AWS Console → Bedrock → Model catalog → Claude Sonnet 4.5 → Submit use case details`

Fill out the form with:
- Company name: Personal / Portfolio Project
- Use case: Building LLMOps platform for document Q&A and RAG
- Industry: Technology
- Expected usage: Development and testing

Allow 15 minutes to 24 hours for approval. Use Amazon Nova Pro in the interim (no form required).

---

### 2.4 Bedrock Knowledge Base — Index Not Found

**Phase:** Phase 2 — Bedrock KB Creation  
**Error:**
```
ValidationException: The knowledge base storage configuration provided is invalid...
Dependency error document status code: 404, error message: no such index [llmops-docs]
```

**Root Cause:**  
Bedrock Knowledge Base requires the OpenSearch vector index to exist before the KB can be created. Terraform creates the OpenSearch Serverless collection but does not create the index inside it — that's a chicken-and-egg problem.

**Fix:**  
Manually create the index after the collection is active, before running `terraform apply` for the KB:

```bash
awscurl --service aoss --region us-east-1 \
  -X PUT -H "Content-Type: application/json" \
  "https://{COLLECTION_ENDPOINT}/llmops-docs" \
  -d '{
    "settings": {"index": {"knn": true, "knn.algo_param.ef_search": 512}},
    "mappings": {"properties": {
      "embedding": {"type": "knn_vector", "dimension": 1024,
        "method": {"name": "hnsw", "engine": "faiss", "space_type": "l2"}},
      "text": {"type": "text"},
      "metadata": {"type": "text"}
    }}
  }'
```

Note: Use `awscurl` not `curl --aws-sigv4` — `awscurl` correctly handles all AWS credential types including shared credentials files.

---

### 2.5 Bedrock Evaluations — Invalid Metric Names

**Phase:** Phase 10 — Bedrock Evaluations  
**Errors (multiple iterations):**
```
Builtin metric with name Builtin.Correctness does not exist  (with QuestionAndAnswer taskType)
Builtin metric with name Builtin.Accuracy does not exist
Builtin metric with name Builtin.F1 does not exist
```

**Root Cause:**  
Bedrock Evaluations has two separate systems:
- `taskType: "QuestionAndAnswer"` → only works with **Bedrock builtin datasets** (e.g. `Builtin.BoolQ`), supports `Builtin.Accuracy` and `Builtin.Robustness`
- `taskType: "General"` → works with **custom S3 datasets**, supports `Builtin.Correctness` and `Builtin.Completeness`, requires `evaluatorModelConfig`

**Fix:**  
For custom S3 datasets, use `taskType: "General"`:

```json
{
  "automated": {
    "datasetMetricConfigs": [{
      "taskType": "General",
      "dataset": {
        "name": "my-dataset",
        "datasetLocation": {"s3Uri": "s3://bucket/dataset.jsonl"}
      },
      "metricNames": ["Builtin.Correctness", "Builtin.Completeness"]
    }],
    "evaluatorModelConfig": {
      "bedrockEvaluatorModels": [{"modelIdentifier": "us.amazon.nova-pro-v1:0"}]
    }
  }
}
```

Also ensure dataset format matches Bedrock's schema: `{"prompt": "...", "referenceResponse": "..."}` — not the LLM-as-Judge format which uses `question/expected_answer`.

---

## 3. Docker & ECR Issues

---

### 3.1 OCI Manifest Format Rejected by Lambda

**Phase:** Phase 2 — Lambda Container  
**Error:**
```
InvalidParameterValueException: The image manifest, config or layer media type
for the source image is not supported.
```

**Root Cause:**  
Docker BuildKit (default in Docker Desktop 4.11+) produces OCI manifest format (`application/vnd.oci.image.manifest.v1+json`). AWS Lambda only supports Docker v2 manifest format (`application/vnd.docker.distribution.manifest.v2+json`).

**Fix:**  
Use `docker buildx` with specific flags to force Docker v2 manifest:

```bash
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \          # Disables SBOM attestations
  --sbom=false \                # Disables provenance attestations
  --output type=image,push=true,oci-mediatypes=false \  # Force Docker v2
  -t {ECR_URI}:latest .
```

Verify manifest type after push:
```bash
aws ecr describe-images \
  --repository-name {repo-name} \
  --query "imageDetails[?imageTags!=null].{MediaType:imageManifestMediaType}" \
  --output table
```
Should show `application/vnd.docker.distribution.manifest.v2+json`.

---

### 3.2 ARM64 vs AMD64 Architecture Mismatch

**Phase:** Phase 3 — FastAPI on EKS  
**Error:**
```
exec /usr/local/bin/uvicorn: exec format error
```

**Root Cause:**  
Development machine is Apple Silicon (ARM64/aarch64). EKS nodes are x86_64 (amd64). Docker on Apple Silicon defaults to building native ARM64 images which fail on amd64 EKS nodes.

**Fix:**  
Always specify `--platform linux/amd64` when building for EKS:

```bash
docker buildx build \
  --platform linux/amd64 \
  --provenance=false \
  --sbom=false \
  --output type=image,push=true,oci-mediatypes=false \
  -t {ECR_URI}:latest .
```

For Lambda on ARM64, use `--platform linux/arm64` and set `architectures = ["arm64"]` in the Lambda Terraform resource.

**Lesson:**  
Always set `--platform` explicitly in CI/CD pipelines and local builds. On GitHub Actions (ubuntu-latest = amd64), the platform is correct by default. On Apple Silicon Macs, it must always be specified.

---

### 3.3 Large Provider Binary Committed to Git

**Phase:** Phase 1 — Git Setup  
**Error:**
```
remote: error: File terraform/live/dev/.terraform/providers/.../terraform-provider-aws_v5.100.0_x5
is 648.39 MB; this exceeds GitHub's file size limit of 100.00 MB
```

**Root Cause:**  
The `.terraform/` directory was accidentally committed before `.gitignore` was set up. This directory contains the Terraform provider binary (~648MB for AWS provider).

**Fix:**  
1. Add `.gitignore` first:
```
.terraform/
*.tfstate
*.tfstate.backup
*.tfvars
.terraform.lock.hcl
crash.log
.DS_Store
```

2. Purge from git history using `git filter-branch`:
```bash
git filter-branch --force --index-filter \
  'git rm -rf --cached --ignore-unmatch terraform/live/dev/.terraform/' \
  --prune-empty --tag-name-filter cat -- --all

git for-each-ref --format='delete %(refname)' refs/original | git update-ref --stdin
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push origin main --force
```

**Lesson:**  
Always create `.gitignore` before the first `git add`. For Terraform projects, `.terraform/`, `*.tfstate`, `*.tfvars`, and `.terraform.lock.hcl` must all be excluded.

---

### 3.4 Docker Push Broken Pipe on Large Layers

**Phase:** Phase 2 — Lambda Image Push  
**Error:**
```
failed to copy: failed to do request: Put "https://ecr.amazonaws.com/...":
write tcp ...: write: broken pipe
```

**Root Cause:**  
Network connection dropped mid-push for a large (~400MB) Docker layer. This is a transient network issue, not an application error.

**Fix:**  
Simply retry the push — Docker layer uploads are resumable. Already-pushed layers show as `Layer already exists`:
```bash
docker push {ECR_URI}:latest
```

---

## 4. Kubernetes & EKS Issues

---

### 4.1 CrashLoopBackOff — exec format error

**Phase:** Phase 3 — FastAPI Deployment  
**Error:**
```
exec /usr/local/bin/uvicorn: exec format error
```

**Root Cause:**  
Container image built for ARM64 deployed on AMD64 EKS nodes. See Section 3.2 for full details.

**Fix:**  
Rebuild with `--platform linux/amd64`. See Section 3.2.

---

### 4.2 Port-Forward Dying During Rollout

**Phase:** Phase 3 — Local Testing  
**Error:**
```
curl: (52) Empty reply from server
```

**Root Cause:**  
`kubectl port-forward` creates a connection to a specific pod. When a rollout terminates that pod, the port-forward connection dies. Subsequent requests return empty replies.

**Fix:**  
Restart port-forward after every rollout:
```bash
pkill -f "port-forward"
kubectl port-forward svc/fastapi-service 8080:80 -n llmops &
sleep 5
```

**Lesson:**  
Use port-forward to a Service (not a Pod) — Services route to any healthy pod. But even Service port-forwards die when the underlying pod changes. For persistent access, use ALB Ingress.

---

### 4.3 ALB Controller Pods Not Starting — Missing Service Account

**Phase:** Extra — ALB Setup  
**Error:**
```
Error from server (NotFound): serviceaccounts "aws-load-balancer-controller" not found
```

**Root Cause:**  
First Helm install used `serviceAccount.create=false` but the service account didn't exist yet. `eksctl create iamserviceaccount` failed silently because the SA "already existed" (from a partially failed previous attempt).

**Fix:**  
Reinstall Helm chart with `serviceAccount.create=true` and provide the IAM role ARN annotation directly:

```bash
helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
  -n kube-system \
  --set clusterName=llmops-bedrock-dev \
  --set serviceAccount.create=true \
  --set serviceAccount.name=aws-load-balancer-controller \
  --set "serviceAccount.annotations.eks\.amazonaws\.com/role-arn=$ALB_ROLE_ARN" \
  --set region=us-east-1 \
  --set vpcId=$(aws eks describe-cluster --name llmops-bedrock-dev \
    --query "cluster.resourcesVpcConfig.vpcId" --output text)
```

---

### 4.4 ALB Not Provisioning — Missing IAM Permissions

**Phase:** Extra — ALB Setup  
**Error (in ALB controller logs):**
```
AccessDenied: User is not authorized to perform: elasticloadbalancing:DescribeListenerAttributes
```

**Root Cause:**  
The downloaded `iam_policy.json` for the ALB controller was outdated and missing `elasticloadbalancing:DescribeListenerAttributes` — a newer action required by ALB controller v2.7+.

**Fix:**  
Attach the AWS managed policy which always stays current:
```bash
aws iam attach-role-policy \
  --role-name llmops-bedrock-dev-alb-controller-role \
  --policy-arn arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess

aws iam attach-role-policy \
  --role-name llmops-bedrock-dev-alb-controller-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess
```

Then restart the controller:
```bash
kubectl rollout restart deployment/aws-load-balancer-controller -n kube-system
```

---

### 4.5 k8s/fastapi.yaml YAML Broken by `cat >>` Append

**Phase:** Phase 9 — CI/CD  
**Error:**
```
error parsing k8s/fastapi.yaml: error converting YAML to JSON: yaml: line 14: mapping values are not allowed in this context
```

**Root Cause:**  
Using `cat >>` to append env vars to the YAML file appended content after the `Service` resource definition, outside the `Deployment` spec. The result was invalid YAML.

**Fix:**  
Never use `cat >>` for structured files. Always rewrite the entire file:
```bash
cat > k8s/fastapi.yaml << 'EOF'
# Complete file content here
EOF
```

Validate YAML before committing:
```bash
python3 -c "import yaml; list(yaml.safe_load_all(open('k8s/fastapi.yaml'))); print('YAML valid')"
```

---

## 5. IAM & Permissions Issues

---

### 5.1 Missing `bedrock:StartIngestionJob` on Lambda Role

**Phase:** Phase 2 — Lambda Testing  
**Error:**
```
AccessDeniedException: User: assumed-role/llmops-bedrock-dev-lambda-execution-role
is not authorized to perform: bedrock:StartIngestionJob
```

**Fix:**  
Add to the Lambda execution role inline policy:
```json
{
  "Effect": "Allow",
  "Action": ["bedrock:StartIngestionJob", "bedrock:GetIngestionJob", "bedrock:ListIngestionJobs"],
  "Resource": "arn:aws:bedrock:us-east-1:011528270076:knowledge-base/*"
}
```

---

### 5.2 Missing `bedrock:RetrieveAndGenerate` on FastAPI IRSA Role

**Phase:** Phase 3 — FastAPI RAG  
**Error:**
```
AccessDeniedException: User: assumed-role/llmops-bedrock-dev-fastapi-irsa-role
is not authorized to perform: bedrock:RetrieveAndGenerate
```

**Root Cause:**  
The `bedrock_invoke_managed` policy only covered `InvokeModel` — not Knowledge Base retrieval actions.

**Fix:**  
Add dedicated KB retrieval policy to the IRSA role:
```json
{
  "Effect": "Allow",
  "Action": ["bedrock:RetrieveAndGenerate", "bedrock:Retrieve",
             "bedrock:GetInferenceProfile", "bedrock:ListInferenceProfiles"],
  "Resource": "*"
}
```

---

### 5.3 Missing `bedrock:GetInferenceProfile` on FastAPI IRSA Role

**Phase:** Phase 3 — FastAPI RAG  
**Error:**
```
AccessDeniedException: Not authorized to call GetInferenceProfile
for arn:aws:bedrock:us-east-1:011528270076:inference-profile/us.anthropic.claude-sonnet-4-5...
```

**Root Cause:**  
`RetrieveAndGenerate` with an inference profile ARN internally calls `GetInferenceProfile` to resolve the model. This action requires explicit IAM permission.

**Fix:**  
Add to the IRSA role policy:
```json
"Action": ["bedrock:GetInferenceProfile", "bedrock:ListInferenceProfiles"],
"Resource": "*"
```

---

### 5.4 Bedrock Agent — Missing KB Retrieve Permission

**Phase:** Phase 5 — Bedrock Agent  
**Error:**
```
accessDeniedException: Access denied when calling Bedrock KnowledgeBase retrieve.
```

**Root Cause:**  
The agent's resource role (`bedrock-invoke-role`) had `bedrock.amazonaws.com` missing from its trust policy. The role could only be assumed by `lambda.amazonaws.com`.

**Fix:**  
Update the trust policy to allow both Lambda and Bedrock:
```json
{
  "Effect": "Allow",
  "Principal": {"Service": "bedrock.amazonaws.com"},
  "Action": "sts:AssumeRole",
  "Condition": {
    "StringEquals": {"aws:SourceAccount": "011528270076"}
  }
}
```

Also add `bedrock-invoke-role` to the OpenSearch Serverless data access policy.

---

### 5.5 GitHub OIDC Role Missing `eks:DescribeCluster`

**Phase:** Phase 9 — GitHub Actions  
**Error:**
```
AccessDeniedException: User: assumed-role/llmops-bedrock-dev-github-actions-role/GitHubActions
is not authorized to perform: eks:DescribeCluster
```

**Fix:**  
Add EKS permissions to the GitHub Actions role:
```json
{
  "Effect": "Allow",
  "Action": ["eks:DescribeCluster", "eks:ListClusters", "eks:AccessKubernetesApi"],
  "Resource": "arn:aws:eks:us-east-1:011528270076:cluster/llmops-bedrock-dev"
}
```

Also add the role to EKS `aws-auth` ConfigMap:
```bash
eksctl create iamidentitymapping \
  --cluster llmops-bedrock-dev \
  --region us-east-1 \
  --arn arn:aws:iam::011528270076:role/llmops-bedrock-dev-github-actions-role \
  --username github-actions \
  --group system:masters
```

---

### 5.6 GitHub Actions Missing DynamoDB Permissions for Prompt Promotion

**Phase:** Phase 9 — Prompt Promotion Workflow  
**Error:**
```
AccessDeniedException: User: assumed-role/llmops-bedrock-dev-github-actions-role
is not authorized to perform: dynamodb:GetItem on table/llmops-bedrock-dev-prompt-registry
```

**Fix:**  
Add DynamoDB and S3 permissions to the GitHub Actions role:
```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
             "dynamodb:Query", "dynamodb:Scan"],
  "Resource": [
    "arn:aws:dynamodb:us-east-1:011528270076:table/llmops-bedrock-dev-prompt-registry",
    "arn:aws:dynamodb:us-east-1:011528270076:table/llmops-bedrock-dev-eval-results",
    "arn:aws:dynamodb:us-east-1:011528270076:table/llmops-bedrock-dev-eval-results/index/*"
  ]
}
```

---

## 6. OpenSearch Serverless Issues

---

### 6.1 403 Forbidden on Index Creation

**Phase:** Phase 2 — OpenSearch Index  
**Error:**
```
{"status":403,"error":{"reason":"403 Forbidden","type":"Forbidden"}}
```

**Root Cause (multiple layers):**

1. **Data access policy** didn't include the IAM user
2. **IAM permission** `aoss:APIAccessAll` missing from the user
3. **`curl --aws-sigv4`** doesn't work with shared credentials files — `$(aws configure get aws_access_key_id)` returns empty for some credential types

**Fix:**

Step 1 — Add user to OpenSearch data access policy:
```bash
aws opensearchserverless update-access-policy \
  --name llmops-bedrock-dev-kb-access \
  --type data \
  --policy-version $CURRENT_VERSION \
  --policy '[{"Rules":[...],"Principal":["arn:aws:iam::011528270076:user/Himanshu_demo_01"]}]'
```

Step 2 — Use `awscurl` instead of `curl`:
```bash
pip install awscurl
awscurl --service aoss --region us-east-1 -X PUT ...
```

**Lesson:**  
OpenSearch Serverless has a dual authorization model — both IAM permissions AND data access policy must grant access. They are independent. `aws iam simulate-principal-policy` only checks IAM, not AOSS data access policies.

---

### 6.2 Policy Version Conflict on Update

**Phase:** Phase 5 — Agent KB Access  
**Approach:**  
Always fetch `policyVersion` before updating:
```bash
POLICY_VERSION=$(aws opensearchserverless get-access-policy \
  --name llmops-bedrock-dev-kb-access --type data \
  --query "accessPolicyDetail.policyVersion" --output text)

aws opensearchserverless update-access-policy \
  --policy-version $POLICY_VERSION \
  ...
```

This prevents `ConflictException` when two operations try to update the same policy simultaneously.

---

## 7. FastAPI & Application Issues

---

### 7.1 Nova Pro API Requires Array Content Format

**Phase:** Phase 6 — LLM-as-Judge  
**Error:**
```
ValidationException: Malformed input request: #/messages/0/content: expected type: JSONArray, found: String
```

**Root Cause:**  
Nova Pro's API requires `content` as a JSON array, not a plain string. Claude's API accepts both formats.

**Wrong:**
```python
"messages": [{"role": "user", "content": "text"}]
```

**Correct for Nova Pro:**
```python
"messages": [{"role": "user", "content": [{"text": "text"}]}]
```

Note: Do NOT add `"type": "text"` — Nova Pro rejects that too:
```
extraneous key [type] is not permitted
```

---

### 7.2 Tenant ID Filter Returns Empty Results

**Phase:** Phase 3 — RAG Testing  
**Symptom:**  
`"answer": "Sorry, I am unable to assist you with this request."` with empty citations.

**Root Cause:**  
Documents were indexed without `tenant_id` metadata. Bedrock KB requires `.metadata.json` sidecar files in S3 to attach custom metadata to documents. Without them, the `tenant_id` filter returns zero results.

**Fix:**  
Create a `.metadata.json` sidecar file alongside each document:
```bash
cat > /tmp/llmops-docs.txt.metadata.json << 'EOF'
{
  "metadataAttributes": {
    "tenant_id": "tenant_test",
    "document_type": "general"
  }
}
EOF

aws s3 cp /tmp/llmops-docs.txt.metadata.json \
  s3://llmops-bedrock-dev-raw/tenant_test/general/llmops-docs.txt.metadata.json
```

Then trigger a KB sync to re-index with metadata.

---

### 7.3 `requirements.txt` Corrupted by `cat >>` Append

**Phase:** Phase 7 — Langfuse  
**Error:**
```
ERROR: Invalid requirement: 'pydantic>=2.0.0langfuse==2.36.2'
```

**Root Cause:**  
`cat >> requirements.txt` appended without a newline when the file didn't end with one, joining the last existing line with the new requirement.

**Fix:**  
Always use `cat >` to rewrite the entire file:
```bash
cat > services/api/requirements.txt << 'EOF'
fastapi==0.115.0
uvicorn[standard]==0.30.6
boto3>=1.34.0
redis==5.0.8
pydantic>=2.0.0
langfuse==2.36.2
EOF
```

---

## 8. GitHub Actions CI/CD Issues

---

### 8.1 Workflow Not Triggering — Environment Not Created

**Phase:** Phase 9 — GitHub Actions  
**Symptom:**  
Workflow stuck waiting, never runs.

**Root Cause:**  
Workflows using `environment: dev` require the environment to be created in GitHub repository settings first.

**Fix:**  
`GitHub → Settings → Environments → New environment → name: dev → Save`

---

### 8.2 Prompt Promotion Gate Failing with Score 0.0

**Phase:** Phase 9 — Prompt Promote Workflow  
**Error:**
```
GATE FAILED: score 0.0 < threshold 0.7
```

**Root Cause:**  
The `API_ENDPOINT` secret was set to a placeholder value. The eval pipeline couldn't reach the live API, so all RAG responses failed and scores defaulted to 0.0.

**Fix:**  
Set `API_ENDPOINT` secret to the real ALB endpoint:
`GitHub → Settings → Secrets → Actions → API_ENDPOINT → http://k8s-llmops-xxx.us-east-1.elb.amazonaws.com`

For demonstration, rerun with `score_threshold: 0.0` to show the full green promotion flow.

---

## 9. Git & Repository Issues

---

### 9.1 SSH Authentication Failed

**Phase:** Phase 1 — Git Setup  
**Error:**
```
remote: Invalid username or token. Password authentication is not supported.
fatal: Authentication failed
```

**Root Cause:**  
GitHub stopped supporting password/HTTPS token authentication for Git operations in 2021.

**Fix:**  
Switch to SSH:
```bash
# Check for existing SSH key
ls ~/.ssh/id_ed25519.pub

# If not present, generate
ssh-keygen -t ed25519 -C "email" -f ~/.ssh/id_ed25519 -N ""

# Copy public key and add to GitHub → Settings → SSH Keys
cat ~/.ssh/id_ed25519.pub

# Switch remote to SSH
git remote set-url origin git@github.com:Himanshu9001/LLMOps-Bedrocks-Project.git
```

---

### 9.2 Literal `{dev,staging,prod}` Folder Created

**Phase:** Phase 1 — Directory Setup  
**Symptom:**  
VS Code showed a folder literally named `{dev,staging,prod}` instead of three separate folders.

**Root Cause:**  
`mkdir -p terraform/live/{dev,staging,prod}` only expands brace syntax when typed directly in an interactive shell. When passed as a string (e.g., from a script or copy-paste in some contexts), it creates a literal folder name.

**Fix:**  
```bash
rm -rf "terraform/live/{dev,staging,prod}"
mkdir -p terraform/live/dev terraform/live/staging terraform/live/prod
```

---

## 10. AWS Resource Cleanup Issues

---

### 10.1 ALB Not Deleted Before VPC

**Phase:** Cleanup  
**Error:**
```
DependencyViolation: Network vpc-xxx has some mapped public address(es).
Please unmap those public address(es) before detaching the gateway.
```

**Root Cause:**  
The ALB (created by the ALB controller via the Ingress resource) was not deleted before Terraform tried to delete the VPC. ELBs hold ENIs in subnets which block subnet and IGW deletion.

**Fix:**  
Delete the ALB explicitly before running `terraform destroy`:
```bash
# Find and delete ALB
aws elbv2 describe-load-balancers \
  --query "LoadBalancers[?contains(LoadBalancerName,'k8s-llmops')].LoadBalancerArn" \
  --output text | xargs -I {} aws elbv2 delete-load-balancer --load-balancer-arn {}

sleep 60  # Wait for deletion to propagate
```

---

### 10.2 Orphaned Security Groups Blocking VPC Deletion

**Phase:** Cleanup  
**Error:**
```
DependencyViolation: The vpc has dependencies and cannot be deleted.
```

**Root Cause:**  
ALB controller created security groups (`k8s-traffic-*`, `k8s-llmops-*`) outside Terraform state. These are not tracked by Terraform and are not destroyed by `terraform destroy`.

**Fix:**  
```bash
# Find orphaned SGs in the VPC
aws ec2 describe-security-groups \
  --filters "Name=vpc-id,Values=<VPC_ID>" \
  --query "SecurityGroups[?GroupName!='default'].{ID:GroupId,Name:GroupName}" \
  --output table

# Delete each one
aws ec2 delete-security-group --group-id sg-xxxx --region us-east-1
```

---

### 10.3 S3 State Bucket Conflict During Destroy

**Issue:**  
`terraform destroy` tries to delete the S3 bucket used for remote state, which is also managed by the `s3` module. If the bucket is deleted mid-destroy, Terraform cannot write the final state.

**Fix:**  
Remove S3 resources from Terraform state before destroying (keeps actual buckets, just stops Terraform from managing them):
```bash
terraform state rm module.s3.aws_s3_bucket.buckets
terraform state rm module.s3.aws_s3_bucket_versioning.buckets
terraform state rm module.s3.aws_s3_bucket_public_access_block.buckets
terraform state rm module.s3.aws_s3_bucket_server_side_encryption_configuration.buckets
terraform state rm module.s3.aws_s3_bucket_lifecycle_configuration.raw
```

Then run `terraform destroy` — it will skip the S3 buckets and destroy everything else.

---

## Quick Reference — Most Common Fixes

| Error | Fix |
|---|---|
| `exec format error` in pods | Rebuild Docker image with `--platform linux/amd64` |
| `OCI manifest not supported` by Lambda | Add `--provenance=false --sbom=false --output ...,oci-mediatypes=false` to buildx |
| `Module not installed` | Run `terraform init` after adding new module block |
| `Semicolons in HCL` | Expand to multi-line variable blocks |
| `AccessDeniedException: bedrock:*` | Check both IAM policy AND OpenSearch data access policy |
| `Sorry, unable to assist` with empty citations | Upload `.metadata.json` sidecar files with `tenant_id` |
| `curl 403 on OpenSearch` | Use `awscurl` not `curl --aws-sigv4` |
| Port-forward empty reply | Restart: `pkill -f port-forward && kubectl port-forward svc/... &` |
| VPC deletion blocked | Delete ALB + orphaned security groups first |
| Git push rejected (large file) | Use `git filter-branch` to purge from history |

---

*Himanshu Singh | github.com/Himanshu9001/LLMOps-Bedrocks-Project*