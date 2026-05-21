# ADR-001: Single AWS Account vs Multi-Account Architecture

**Status:** Decided  
**Date:** 2026-05-21  
**Author:** Himanshu Singh

## Context

Enterprise LLMOps platforms typically use AWS Organizations with separate accounts per environment (dev/staging/prod) for blast radius isolation. This project needed to decide between:

- **Option A:** Single AWS account with resource naming prefixes
- **Option B:** Multi-account via AWS Organizations (3 accounts minimum)

## Decision

**Chosen: Option A — Single AWS Account**

## Rationale

### Why single account for this project

- Portfolio project — no real customer data, no compliance requirements
- Multi-account setup adds 2-3 hours of AWS Organizations configuration with minimal learning value
- Resource naming prefixes (llmops-bedrock-dev-*) provide logical isolation
- Separate Terraform state keys per environment provide state isolation
- Cost: single account avoids per-account baseline charges

### Why multi-account in production

- **Blast radius:** a misconfigured IAM policy in dev cannot affect prod resources
- **Billing:** per-account cost attribution without tagging complexity
- **Security:** prod account has stricter SCPs (Service Control Policies)
- **Compliance:** SOC2/HIPAA/PCI often require environment separation

## Production Migration Path

When this platform moves to production:

    AWS Organizations
    +-- Root
        +-- Management Account (billing only)
        +-- dev/     Account ID: xxxx  (this project's current account)
        +-- staging/ Account ID: yyyy
        +-- prod/    Account ID: zzzz  (restricted SCPs, no console access)

Cross-account deployment via:
- GitHub Actions OIDC role in each account
- Terraform workspaces per environment
- Separate state buckets per account

## Consequences

- **Accepted risk:** dev IAM misconfiguration could theoretically affect prod if sharing account
- **Mitigation:** strict resource tagging, separate state keys, naming conventions
- **Future work:** migrate to multi-account when platform moves to production
