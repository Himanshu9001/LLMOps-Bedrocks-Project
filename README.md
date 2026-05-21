# Enterprise LLMOps Platform on Amazon Bedrock

**Author:** Himanshu Singh (Heman) | Cloud DevOps & AI Engineer  
**GitHub:** [Himanshu9001/LLMOps-Bedrocks-Project](https://github.com/Himanshu9001/LLMOps-Bedrocks-Project)  
**Stack:** AWS · Bedrock · EKS · Terraform · FastAPI · Langfuse · GitHub Actions  
**Status:** Production-grade — 10 phases complete + Redis, ALB, ArgoCD, Load Testing

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Full Technology Stack](#3-full-technology-stack)
4. [Repository Structure](#4-repository-structure)
5. [Phase Breakdown](#5-phase-breakdown)
6. [Infrastructure (Terraform)](#6-infrastructure-terraform)
7. [Services](#7-services)
8. [Kubernetes Manifests](#8-kubernetes-manifests)
9. [CI/CD Workflows](#9-cicd-workflows)
10. [Observability](#10-observability)
11. [Security](#11-security)
12. [Evaluation Pipeline](#12-evaluation-pipeline)
13. [Load Testing](#13-load-testing)
14. [Known Limitations & Future Work](#14-known-limitations--future-work)
15. [Cost Estimate](#15-cost-estimate)
16. [Quick Start — Rebuild from Scratch](#16-quick-start--rebuild-from-scratch)

---

## 1. Project Overview

This project is a production-grade Enterprise LLMOps Platform built on Amazon Bedrock. It mirrors what real companies like CBRE, Stripe, and Harman International run in production — covering every LLMOps pillar: RAG, agents, evaluation, observability, cost control, CI/CD, and fine-tuning.

The platform implements **Intelligent Document Processing** and a **Multi-Agent Knowledge Assistant** that ingests enterprise documents, exposes a multi-agent RAG API, continuously evaluates quality, manages costs, and self-improves via a data flywheel.

### Use Case

- Ingest enterprise documents (PDF, TXT) from S3 automatically
- Chunk and embed documents using Bedrock Knowledge Base + Titan Embeddings v2
- Answer questions via RAG using Claude / Nova Pro with citation tracking
- Multi-agent orchestration using Bedrock supervisor agent
- Continuous quality evaluation with LLM-as-Judge and CI promotion gates
- Full observability: Langfuse traces + CloudWatch p50/p95/p99 metrics
- Prompt versioning with A/B routing and eval-gated promotion
- Automated fine-tuning trigger via data flywheel

### Key Metrics

| Metric | Value |
|---|---|
| RAG Eval Score (LLM-as-Judge) | **0.767 / 1.0 — PASSING** (threshold 0.70) |
| API Latency (p50) | 2845ms |
| API Latency (p95) | 5258ms |
| Load Test Error Rate | 4.83% at 5 concurrent users |
| Prompt Injection Defense | 400ms intercept, HTTP 400 status |
| CI/CD | GitHub Actions OIDC — zero static credentials |
| Infrastructure | 44 AWS resources via Terraform IaC |
| Phases Completed | 10 phases + Redis, ALB, ArgoCD, Load Testing |

---

## 2. Architecture

### High-Level Flow

```
Documents (PDF/TXT)
      |
      v
S3 Raw Bucket ──► Lambda Ingestion ──► Bedrock Knowledge Base
                  (PyMuPDF parse)        (OpenSearch Serverless)
                  (DynamoDB metadata)    (Titan Embeddings v2)
                                                |
                                                v
User Query ──► FastAPI (EKS) ──► Bedrock RetrieveAndGenerate
              (Guardrails)        (Claude Sonnet 4.5 / Nova Pro)
              (IRSA auth)                  |
              (Redis sessions)             v
                                    RAG Response
                                    + Citations
                                    + Trace ID (Langfuse)
                                    + CloudWatch Metrics
```

### Multi-Agent Architecture

- **Supervisor Agent** — routes queries, decomposes multi-step tasks
- **Document Agent** — RAG over Bedrock Knowledge Base (tenant-scoped)
- **Summarization Agent** — long-document distillation (placeholder)
- **SQL Agent** — natural language to SQL (placeholder for Phase 5+)

### AWS Account Details

| Resource | Value |
|---|---|
| AWS Account ID | 011528270076 |
| Primary Region | us-east-1 |
| EKS Cluster | llmops-bedrock-dev |
| VPC | vpc-010d981123f5e621c (10.0.0.0/16) |
| Knowledge Base ID | 0OW8LBTZU5 |
| Bedrock Agent ID | 4AP3RGIQHK |
| Guardrail ID | l85cdv5umyr3 |
| Public ALB | k8s-llmops-fastapii-7cc3c8b514-1333502527.us-east-1.elb.amazonaws.com |

---

## 3. Full Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| LLM Gateway | Amazon Bedrock | Claude Sonnet 4.5, Nova Pro, Haiku 4.5 via cross-region inference profiles |
| RAG | Bedrock Knowledge Base + OpenSearch Serverless | Vector store with Titan Embeddings v2, 1024 dimensions, HNSW/faiss |
| Agents | Bedrock Agents + AgentCore | Supervisor agent with KB retrieval, session memory |
| Prompt Mgmt | Bedrock Prompt Management + DynamoDB | Versioned prompts, A/B routing (10%), eval-gated promotion |
| Evaluation | LLM-as-Judge (Nova Pro) + Bedrock Evaluations | Golden dataset, faithfulness/relevance/completeness scoring |
| Observability | Langfuse Cloud + CloudWatch + /metrics endpoint | Per-request traces, p50/p95/p99 latency, error rate, citation count |
| CI/CD | GitHub Actions (OIDC) + ArgoCD | Zero static credentials, GitOps for K8s manifests |
| IaC | Terraform (modular, 5 modules) | Remote state S3 + S3 native locking (use_lockfile) |
| API Layer | FastAPI on EKS + ALB | 2 replicas, HPA, IRSA, Redis sessions, public ALB endpoint |
| Security | Bedrock Guardrails + Prompt Injection Defense | Content filtering, PII redaction, pattern-based + semantic injection check |
| Session Memory | Redis 7 on EKS | 30-min TTL, 10-turn history, keyed by tenant_id + session_id |
| Cost Control | Bedrock Intelligent Prompt Routing | Auto-route simple queries to Haiku, complex to Sonnet |
| Load Testing | k6 | 5 concurrent users, p95 5.15s, 4.83% error rate |
| Fine-tuning | Step Functions + Bedrock Custom Model | Data flywheel trigger, JSONL dataset prep, eval-gated promotion |
| Storage | S3 + DynamoDB + ElastiCache Redis | Raw docs, processed, eval datasets, prompt versions, metadata |

---

## 4. Repository Structure

```
LLMOps-Bedrocks-Project/
├── terraform/
│   ├── modules/
│   │   ├── vpc/               # VPC, subnets, NAT GW, VPC endpoints
│   │   ├── s3/                # S3 buckets (raw, processed, eval, prompts, tfstate)
│   │   ├── dynamodb/          # prompt-registry, document-metadata, eval-results, tfstate-lock
│   │   ├── iam/               # 4 roles: github-actions, bedrock-invoke, lambda-execution, fastapi-irsa
│   │   ├── eks/               # EKS cluster, node groups (system + application), OIDC
│   │   ├── bedrock/           # Knowledge Base, OpenSearch Serverless, data source
│   │   └── lambda_ingestion/  # ECR repo, Lambda function, S3 trigger, CloudWatch alarm
│   └── live/
│       └── dev/               # main.tf, variables.tf, outputs.tf, terraform.tfvars
├── services/
│   ├── api/                   # FastAPI RAG service (main.py, Dockerfile, requirements.txt)
│   ├── ingestion/             # Lambda handler (handler.py, Dockerfile, requirements.txt)
│   ├── agents/                # Bedrock agent wrappers (supervisor.py)
│   └── prompt_management/     # PromptManager class, prompt registry
├── k8s/
│   ├── namespace.yaml
│   ├── serviceaccount.yaml    # IRSA annotation
│   ├── fastapi.yaml           # Deployment + Service
│   ├── redis.yaml             # Redis Deployment + Service
│   ├── hpa.yaml               # HorizontalPodAutoscaler
│   ├── ingress.yaml           # ALB Ingress
│   └── argocd-app.yaml        # ArgoCD Application
├── evaluation/
│   ├── evaluator.py           # Main eval pipeline
│   ├── judge.py               # LLM-as-Judge (Nova Pro)
│   └── golden_dataset.py
├── finetuning/
│   ├── prepare_dataset.py     # JSONL dataset preparation
│   └── trigger_finetune.py    # Bedrock custom model job trigger
├── load-testing/
│   └── k6_test.js             # k6 load test script
├── .github/workflows/
│   ├── infra-deploy.yml       # Terraform plan/apply
│   ├── api-deploy.yml         # ECR build + EKS rollout
│   ├── prompt-promote.yml     # Eval gate + DynamoDB promotion
│   └── finetune-trigger.yml   # Nightly eval check + fine-tune trigger
├── docs/adr/
│   └── ADR-001-single-vs-multi-account.md
└── scripts/
    └── bootstrap.sh           # S3 state bucket + DynamoDB lock table
```

---

## 5. Phase Breakdown

| Phase | Name | Key Deliverables | Status |
|---|---|---|---|
| 1 | Foundation & Infrastructure | Terraform IaC, VPC, S3, DynamoDB, IAM (4 roles), EKS cluster (v1.31), OIDC | ✅ Complete |
| 2 | Document Ingestion Pipeline | Lambda + S3 trigger, PyMuPDF parsing, Bedrock KB, OpenSearch Serverless, DynamoDB metadata | ✅ Complete |
| 3 | RAG API Layer | FastAPI on EKS, IRSA, /query /chat /agent endpoints, Redis sessions, citations | ✅ Complete |
| 4 | Prompt Management | Bedrock Prompt Management, DynamoDB registry, A/B routing (10%), eval-gated promotion | ✅ Complete |
| 5 | Multi-Agent Orchestration | Bedrock supervisor agent, KB association, alias, EventStream handling | ✅ Complete |
| 6 | Evaluation Pipeline | Golden dataset, LLM-as-Judge, 0.767 score, CI gate blocking promotion < 0.70 | ✅ Complete |
| 7 | Observability & Cost Control | Langfuse Cloud traces, CloudWatch LLMOps/Bedrock namespace, p50/p95/p99 metrics | ✅ Complete |
| 8 | Guardrails & Security | Bedrock Guardrails (l85cdv5umyr3), prompt injection defense (2-layer), PII redaction | ✅ Complete |
| 9 | CI/CD & GitOps | GitHub Actions OIDC (3 workflows), ArgoCD GitOps, zero static credentials | ✅ Complete |
| 10 | Fine-Tuning & Continuous Training | Dataset prep, Bedrock eval job, data flywheel trigger, Step Functions orchestration | ✅ Complete |
| Extra | Redis + ALB + Load Testing | Redis session memory, public ALB endpoint, k6 load test (p95 5.15s, 4.83% error) | ✅ Complete |

---

## 6. Infrastructure (Terraform)

### Remote State

| Setting | Value |
|---|---|
| State Bucket | llmops-bedrock-tfstate |
| State Key | dev/terraform.tfstate |
| Locking | `use_lockfile = true` (S3 native, Terraform 1.10+) |
| Encryption | AES256 |
| Provider | hashicorp/aws ~> 5.0 (v5.100.0) |

### VPC Module

- CIDR: `10.0.0.0/16`
- Public subnets: `subnet-0739828468eb7d645`, `subnet-0839af0b8a17b2510` (us-east-1a/1b)
- Private subnets: `subnet-0057f54d45dc9b3b2`, `subnet-0776bbc556c30ff0d` (us-east-1a/1b)
- Single NAT Gateway (cost-optimized for dev)
- VPC Endpoints: `bedrock-runtime` (Interface), `bedrock-agent-runtime` (Interface), `S3` (Gateway), `DynamoDB` (Gateway)
- All Bedrock traffic stays private — never leaves AWS network

### S3 Module

| Bucket | Purpose | Features |
|---|---|---|
| llmops-bedrock-dev-raw | Raw ingested documents | Versioning, SSE-AES256, lifecycle tiering (IA@30d, Glacier@90d) |
| llmops-bedrock-dev-processed | Post-processed documents | Versioning, SSE-AES256 |
| llmops-bedrock-dev-eval-datasets | Golden datasets + eval results | Versioning, SSE-AES256 |
| llmops-bedrock-dev-prompt-versions | Prompt artifact storage | Versioning, SSE-AES256 |
| llmops-bedrock-dev-tfstate | Terraform remote state | Versioning, SSE-AES256, public access blocked |

### DynamoDB Module

| Table | PK | SK | Purpose |
|---|---|---|---|
| llmops-bedrock-dev-prompt-registry | prompt_id | version | Prompt versions with eval scores and environment |
| llmops-bedrock-dev-document-metadata | tenant_id | chunk_id | Per-chunk metadata for ingested documents |
| llmops-bedrock-dev-eval-results | eval_run_id | prompt_version | Evaluation run results for CI gate queries |
| llmops-bedrock-dev-tfstate-lock | LockID | - | Terraform state locking |

### IAM Module — 4 Roles

| Role | Trust Principal | Key Permissions |
|---|---|---|
| llmops-bedrock-dev-github-actions-role | GitHub OIDC (token.actions.githubusercontent.com) | S3 state, ECR push, EKS describe, DynamoDB prompt-registry, S3 eval |
| llmops-bedrock-dev-bedrock-invoke-role | lambda.amazonaws.com + bedrock.amazonaws.com | bedrock:InvokeModel, Retrieve, RetrieveAndGenerate, InvokeAgent, StartIngestionJob |
| llmops-bedrock-dev-lambda-execution-role | lambda.amazonaws.com | S3 raw/processed, DynamoDB document-metadata, CloudWatch logs, VPC networking |
| llmops-bedrock-dev-fastapi-irsa-role | EKS OIDC (system:serviceaccount:llmops:fastapi-sa) | bedrock:RetrieveAndGenerate, Retrieve, GetInferenceProfile, InvokeModel, CloudWatch |

### EKS Module

- Cluster: `llmops-bedrock-dev` (Kubernetes v1.31.14)
- OIDC Provider: `arn:aws:iam::011528270076:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/B39E862F43D5BECE1549B9C3EF658320`
- System node group: 2x t3.medium (min 2, max 4) — tainted `NO_SCHEDULE`
- Application node group: 2x t3.large (min 1, max 6)
- Control plane logging: api, audit, authenticator, controllerManager, scheduler

---

## 7. Services

### FastAPI RAG Service (`services/api/`)

Production FastAPI service running on EKS with full observability and security.

#### Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness + readiness probe. Returns Redis status, KB ID, timestamp |
| `/query` | POST | Single-turn RAG query. Bedrock RetrieveAndGenerate with tenant_id filter, Langfuse trace, CloudWatch metrics |
| `/chat` | POST | Multi-turn conversation. Redis session history appended to context |
| `/agent` | POST | Bedrock supervisor agent invocation. Falls back to /query on failure |
| `/metrics` | GET | Internal metrics: p50/p95/p99 latency, error rate, request count from in-memory buffer |

#### Security Layers on `/query`

- **Layer 1 — Pattern matching (~0ms):** 12 known injection patterns checked via Python string matching before any API call. Returns HTTP 400 immediately on match.
- **Layer 2 — Bedrock Guardrail (~400ms):** `apply_guardrail()` API call for semantic injection check, PII redaction (EMAIL/PHONE/NAME anonymized; SSN/credit card blocked), topic denial.
- **Layer 3 — Tenant isolation:** `tenant_id` metadata filter on every `RetrieveAndGenerate` call — cross-tenant data leakage impossible at API layer.

#### Observability

- Every request traced in Langfuse Cloud: prompt, response, latency, model, tenant_id, `trace_id` returned in API response
- CloudWatch namespace `LLMOps/Bedrock`: QueryLatency, LatencyP50/P95/P99, ErrorRate, CitationCount, RequestCount — all with tenant_id and model dimensions
- Background thread publishes metrics — zero latency impact on request handling

### Lambda Ingestion Service (`services/ingestion/`)

Container-based Lambda function triggered by S3 `ObjectCreated` events on the raw bucket.

#### Flow

1. S3 upload triggers Lambda via S3 bucket notification
2. Document downloaded to `/tmp` (512MB ephemeral storage)
3. PyMuPDF parses PDF: page count, word count, parse quality check
4. Metadata written to DynamoDB `document-metadata` table: `tenant_id`, `chunk_id`, `document_type`, `source`, `page_count`, `word_count`
5. Document copied to `processed/` bucket for audit trail
6. Bedrock KB sync job triggered via `start_ingestion_job` API

**Architecture:** arm64, 1GB memory, 5-minute timeout

#### S3 Key Convention

```
{tenant_id}/{document_type}/{filename}
Example: tenant_acme/10-k/apple_2024_10k.pdf
```

### Prompt Management (`services/prompt_management/`)

#### PromptManager Class

- `get_prompt(prompt_id, env)`: retrieves active prompt from DynamoDB registry, fetches text from Bedrock Prompt Management
- **A/B routing:** 10% traffic to candidate version when `status='candidate'` exists for the environment
- `promote_prompt()`: eval score gate check, writes promoted version to target environment in DynamoDB
- **Fallback:** hardcoded default prompt when Bedrock/DynamoDB unavailable

#### Prompt Registry Schema

| Field | Example | Purpose |
|---|---|---|
| prompt_id | rag-system-prompt | Logical prompt name |
| version | 1 | Version number |
| bedrock_prompt_id | 19CBGRODIV | Bedrock Prompt Management ID |
| bedrock_arn | arn:aws:bedrock:...:prompt/19CBGRODIV:1 | Full ARN for invocation |
| environment | dev | dev / staging / prod |
| status | active | active / candidate |
| evaluation_score | 0.767 | Latest eval score (0.0 - 1.0) |

---

## 8. Kubernetes Manifests

| File | Purpose | Key Config |
|---|---|---|
| namespace.yaml | llmops namespace | All workloads isolated in llmops namespace |
| serviceaccount.yaml | IRSA for FastAPI pod | Annotated with fastapi-irsa-role ARN |
| fastapi.yaml | FastAPI Deployment + Service | 2 replicas, arm64, 1GB limit, liveness/readiness probes on /health |
| redis.yaml | Redis 7 Deployment + Service | 1 replica, 256MB limit, ClusterIP service `redis-service` |
| hpa.yaml | HorizontalPodAutoscaler | Min 2 / Max 10 replicas, scale at 70% CPU or 80% memory |
| ingress.yaml | ALB Ingress | internet-facing ALB, target-type ip, healthcheck /health, ingressClassName: alb |
| argocd-app.yaml | ArgoCD Application | Watches k8s/ directory in main branch, automated sync with selfHeal + prune |

### IRSA — How It Works

IRSA (IAM Roles for Service Accounts) allows Kubernetes pods to assume IAM roles without storing AWS credentials anywhere.

1. EKS creates an OIDC provider linked to the cluster
2. IAM role trust policy allows the EKS OIDC provider to assume it for a specific service account
3. Service account annotated with `eks.amazonaws.com/role-arn`
4. Pod mounts a projected service account token — AWS SDK automatically exchanges it for temporary credentials via `STS AssumeRoleWithWebIdentity`
5. No `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` ever appears in the pod

---

## 9. CI/CD Workflows

### Authentication — OIDC (Zero Static Credentials)

All GitHub Actions workflows authenticate to AWS via OIDC — no AWS access keys stored in GitHub Secrets. The GitHub Actions OIDC provider issues a JWT token that is exchanged for temporary AWS credentials via `STS AssumeRoleWithWebIdentity`.

- GitHub OIDC provider registered in AWS IAM
- Trust policy scoped to repo: `repo:Himanshu9001/LLMOps-Bedrocks-Project:*`
- Temporary credentials expire after 1 hour — no rotation needed

### Workflow Summary

| Workflow | Trigger | Steps | Gate |
|---|---|---|---|
| infra-deploy.yml | Push to main (terraform/**) or manual | terraform init → validate → fmt check → plan → apply | Manual approval for prod environment |
| api-deploy.yml | Push to main (services/api/** or k8s/**) or manual | OIDC auth → ECR login → docker buildx (amd64) → Trivy scan → ECR push → kubectl apply → rollout status | Trivy CRITICAL/HIGH scan (non-blocking) |
| prompt-promote.yml | Manual dispatch | OIDC auth → run evaluator.py → extract score → gate check → DynamoDB put_item | Eval score >= score_threshold (default 0.70) |
| finetune-trigger.yml | Nightly 2AM UTC or manual | OIDC auth → check last 3 eval scores → if all below threshold → prepare JSONL dataset → upload to S3 | 3 consecutive runs below MIN_QUALITY_SCORE (default 0.75) |

### ArgoCD GitOps

- ArgoCD installed in kube-system namespace (7 pods)
- Application `llmops-fastapi` watches `k8s/` directory in main branch
- Automated sync: `prune=true` (deletes removed resources), `selfHeal=true` (reverts manual changes)
- UI: `https://localhost:8081` — run `kubectl port-forward svc/argocd-server 8081:443 -n argocd`

---

## 10. Observability

### Langfuse Cloud

- Every `/query`, `/chat`, `/agent` request creates a Langfuse trace
- Trace structure: root span → `bedrock-retrieve-and-generate` span → generation event
- Generation event captures: model ID, input query, output answer, latency, citation count
- `trace_id` returned in every API response — correlate API logs with Langfuse traces
- Dashboard: https://cloud.langfuse.com

### CloudWatch Custom Metrics (`LLMOps/Bedrock` namespace)

| Metric | Dimensions | Unit | Purpose |
|---|---|---|---|
| QueryLatency | tenant_id, model | Milliseconds | Per-request latency for cost attribution per tenant |
| LatencyP50 | model | Milliseconds | 50th percentile from in-memory rolling buffer (last 1000 requests) |
| LatencyP95 | model | Milliseconds | 95th percentile — SLA monitoring |
| LatencyP99 | model | Milliseconds | 99th percentile — outlier detection |
| ErrorRate | model | Percent | Error rate from rolling buffer |
| CitationCount | tenant_id | Count | Average citations per response — retrieval quality signal |
| RequestCount | tenant_id, success | Count | Request volume per tenant with success/failure split |

### Internal `/metrics` Endpoint

FastAPI exposes `GET /metrics` returning real-time percentiles from an in-memory deque (last 1000 requests). Used for local debugging and future Prometheus scraping.

---

## 11. Security

### Bedrock Guardrail (`l85cdv5umyr3`)

| Protection | Config | Action |
|---|---|---|
| SEXUAL content | HIGH input + output strength | Block |
| VIOLENCE content | HIGH input + output strength | Block |
| HATE speech | HIGH input + output strength | Block |
| PROMPT_ATTACK | HIGH input strength, NONE output | Block on input, allow output |
| EMAIL | PII detection | Anonymize → `[EMAIL]` |
| PHONE | PII detection | Anonymize |
| NAME | PII detection | Anonymize |
| US_SOCIAL_SECURITY_NUMBER | PII detection | Block entire request |
| CREDIT_DEBIT_CARD_NUMBER | PII detection | Block entire request |
| Financial advice topic | Deny topic | Block with custom message |
| Prompt injection topic | Deny topic | Block with custom message |

### Two-Layer Prompt Injection Defense

- **Layer 1 — Pattern matching (~0ms):** 12 known patterns checked via Python `str.lower()` before any API call. Returns HTTP 400 immediately on match.
- **Layer 2 — Bedrock Guardrail semantic check (~400ms):** `apply_guardrail()` catches semantic attacks patterns miss. Returns HTTP 400 with guardrail message on intervention.

### Network Security

- All Bedrock API calls go through VPC Interface endpoints — traffic never leaves AWS network
- EKS nodes in private subnets — no direct internet access
- Security group on VPC endpoints: ingress only on port 443 from private subnet CIDRs
- Lambda runs inside VPC — accesses DynamoDB and S3 via VPC endpoints

### IAM Least Privilege

- Bedrock model ARNs scoped to specific model versions — not `bedrock:*` wildcard
- Lambda KB sync permission scoped to specific `knowledge-base/*` ARN
- FastAPI IRSA role scoped to `system:serviceaccount:llmops:fastapi-sa` only
- GitHub Actions role scoped to specific repo via OIDC condition

---

## 12. Evaluation Pipeline

### LLM-as-Judge Evaluator

Custom evaluation pipeline using Nova Pro as judge to score RAG responses on 4 metrics.

| Metric | Weight | Description |
|---|---|---|
| Faithfulness | 35% | Does the answer stay true to retrieved context? No hallucinations? |
| Relevance | 35% | Does the answer address the question asked? |
| Completeness | 20% | Does it cover key points from expected answer? |
| Conciseness | 10% | Appropriately concise without being too brief? |

### Latest Eval Results

| Category | Score | Status |
|---|---|---|
| platform_overview | 0.785 | ✅ PASS |
| multi_tenancy | 0.860 | ✅ PASS |
| technical | 0.725 | ✅ PASS |
| models | 0.740 | ✅ PASS |
| **Overall Average** | **0.767** | **✅ PASS (threshold 0.70)** |

### CI Gate

- Eval pipeline runs in GitHub Actions `prompt-promote.yml` workflow
- Gate: if `avg_score < score_threshold` → exit code 1 → blocks promotion
- Score written to DynamoDB `eval_results` table with `eval_run_id` and `prompt_version`
- Detailed results written to `s3://eval-datasets/results/{eval_run_id}.json`

### Bedrock Evaluations API

- Evaluation job: `arn:aws:bedrock:us-east-1:011528270076:evaluation-job/vllrrwhv8na4`
- taskType: `General` with `Builtin.Correctness` and `Builtin.Completeness` metrics
- Evaluator model: Nova Pro as judge
- Dataset: `s3://llmops-bedrock-dev-eval-datasets/golden/bedrock_eval_dataset.jsonl`
- Results: `s3://llmops-bedrock-dev-eval-datasets/bedrock-eval-results/`

---

## 13. Load Testing

### k6 Results

| Metric | Value |
|---|---|
| Tool | k6 v0.54.0 |
| Target | ALB endpoint (internet-facing) |
| Stages | Ramp 0→3 (30s), hold at 5 (60s), ramp down (30s) |
| Total Requests | 124 |
| Throughput | ~1 req/s (Bedrock on-demand TPM limit) |
| Error Rate | **4.83%** (3 requests hit ALB timeout) |
| Median Latency | 2845ms |
| P90 Latency | 5151ms |
| P95 Latency | 5258ms |
| Max Latency | 6645ms |
| P95 Threshold (15s) | ✅ PASSED |
| Error Rate Threshold (20%) | ✅ PASSED |

### Observations

- Bedrock on-demand throughput limits at ~1 req/s for Nova Pro — expected behavior
- 4.83% errors are ALB 504 timeouts when Bedrock takes >15s — not application errors
- HPA did not trigger at 5 concurrent users — CPU utilization stayed below 70% threshold
- Redis session memory working correctly — health check shows `"redis": "connected"` throughout test

---

## 14. Known Limitations & Future Work

| Item | Description | Priority |
|---|---|---|
| Secrets in k8s YAML | Langfuse keys and Guardrail ID committed in plaintext in `k8s/fastapi.yaml`. Fix: move to Kubernetes Secrets or AWS Secrets Manager + External Secrets Operator | 🔴 HIGH |
| Single AWS Account | No true blast radius isolation. Mitigation: separate state keys, resource naming prefixes. Fix: AWS Organizations 3-account structure | 🟡 MEDIUM |
| No HTTPS on ALB | API exposed over HTTP. Fix: ACM certificate + Route53 domain + ALB HTTPS listener | 🟡 MEDIUM |
| ArgoCD vs kubectl drift | `api-deploy.yml` uses `kubectl set image`; ArgoCD `selfHeal` will revert it. Fix: update image tag in `fastapi.yaml` in CI, commit + push, let ArgoCD sync | 🟡 MEDIUM |
| ALB controller IAM role not in Terraform | `llmops-bedrock-dev-alb-controller-role` created manually. Fix: add to eks module as `aws_iam_role` resource | 🟢 LOW |
| Redis not persistent | In-cluster Redis pod — sessions lost on pod restart. Fix: ElastiCache Redis with Multi-AZ for production | 🟢 LOW |
| No HPA validation under load | HPA configured but never triggered. Fix: run higher concurrency k6 test or use KEDA for Bedrock-specific metrics | 🟢 LOW |
| Bedrock Evaluations dataset format | Custom dataset requires `prompt/referenceResponse` format — different from LLM-as-Judge format | 🟢 LOW |

---

## 15. Cost Estimate

### Monthly Running Cost (When Fully Deployed)

| Resource | Cost/Month | Notes |
|---|---|---|
| EKS Cluster | $72 | $0.10/hr — control plane only |
| 2x t3.medium (system nodes) | $60 | $0.042/hr each |
| 2x t3.large (app nodes) | $120 | $0.083/hr each |
| NAT Gateway | $32 | $0.045/hr + data processing |
| OpenSearch Serverless | $350 | 2 OCU minimum — most expensive resource |
| Bedrock Interface VPC Endpoints | $14 | 2x endpoints at $0.01/hr each |
| Bedrock API Calls | Usage-based | ~$0.003/1K input tokens (Nova Pro) |
| S3 + DynamoDB | <$5 | Minimal data volumes |
| **Total (with OpenSearch)** | **~$653** | Destroy OpenSearch when not actively using |
| **Total (without OpenSearch)** | **~$303** | Keep EKS + NAT GW running between sessions |

### Cost Optimization Strategy

- Destroy OpenSearch Serverless collection between sessions — saves $350/month
- Scale down EKS node groups to 0 when not using — saves $180/month
- Use Bedrock Intelligent Prompt Routing to send simple queries to Haiku (20x cheaper than Sonnet)
- S3 lifecycle tiering: raw docs move to STANDARD_IA at 30 days, GLACIER at 90 days

---

## 16. Quick Start — Rebuild from Scratch

### Prerequisites

- AWS CLI configured with IAM user (programmatic access)
- Terraform >= 1.7.5
- `kubectl` + `eksctl` + `helm` installed
- Docker Desktop running

### Step 1 — Bootstrap State Bucket

```bash
bash scripts/bootstrap.sh
```

### Step 2 — Deploy Infrastructure

```bash
cd terraform/live/dev
terraform init
terraform apply -var-file=terraform.tfvars
```

### Step 3 — Update kubeconfig

```bash
aws eks update-kubeconfig --region us-east-1 --name llmops-bedrock-dev
```

### Step 4 — Create OpenSearch Index

```bash
awscurl --service aoss --region us-east-1 \
  -X PUT -H 'Content-Type: application/json' \
  "https://{OPENSEARCH_ENDPOINT}/llmops-docs" \
  -d '{"settings":{"index":{"knn":true}},"mappings":{"properties":{"embedding":{"type":"knn_vector","dimension":1024},"text":{"type":"text"},"metadata":{"type":"text"}}}}'
```

### Step 5 — Build and Deploy API

```bash
cd services/api
docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
  --output type=image,push=true,oci-mediatypes=false \
  -t {AWS_ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/llmops-bedrock-dev-api:latest .
```

### Step 6 — Deploy to Kubernetes

```bash
kubectl apply -f k8s/
```

### Step 7 — Test

```bash
ALB=$(kubectl get ingress fastapi-ingress -n llmops \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

# Health check
curl http://$ALB/health

# RAG query
curl -X POST http://$ALB/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "what are the key features?", "tenant_id": "tenant_test"}'
```

---

*Himanshu Singh | github.com/Himanshu9001/LLMOps-Bedrocks-Project*