#!/usr/bin/env python3
"""
Bedrock Prompt Management — Setup Script
Creates initial prompt versions in Bedrock Prompt Management.
Run once during environment setup.

Current prompts (as of 2026-05-21):
  - ID: 19CBGRODIV (v1 — active)
  - ID: 39LLRCT5E7 (v2 — candidate, A/B testing)

Usage:
  python3 scripts/setup_prompts.py --env dev
"""

import boto3
import json
import argparse

bedrock_agent = boto3.client("bedrock-agent", region_name="us-east-1")

RAG_SYSTEM_PROMPT_V1 = """You are an expert knowledge assistant for enterprise document Q&A.

Your role:
- Answer questions accurately based ONLY on the provided context
- Always cite your sources when referencing specific information
- If the answer is not in the context, clearly say so — do not hallucinate
- Keep answers concise and professional
- For multi-part questions, address each part systematically

Context will be provided automatically from the knowledge base.
Tenant: {tenant_id}"""

RAG_SYSTEM_PROMPT_V2 = """You are an expert enterprise knowledge assistant with deep analytical capabilities.

Core principles:
- Ground every response in the retrieved context — never speculate beyond it
- Provide structured, well-organized answers with clear sections when appropriate
- Always cite specific sources using [Source: filename] notation
- Acknowledge knowledge gaps honestly rather than guessing
- Optimize for accuracy over comprehensiveness

When context is insufficient: state exactly what information is missing
Tenant context: {tenant_id}
Response language: Professional, precise, actionable"""


def create_prompt(name: str, content: str, description: str) -> dict:
    response = bedrock_agent.create_prompt(
        name=name,
        description=description,
        variants=[{
            "name": "default",
            "modelId": "us.amazon.nova-pro-v1:0",
            "templateType": "TEXT",
            "templateConfiguration": {
                "text": {
                    "text": content,
                    "inputVariables": [{"name": "tenant_id"}]
                }
            }
        }]
    )
    print(f"Created prompt: {response['id']} — {name}")
    return response


def create_prompt_version(prompt_id: str, description: str) -> dict:
    response = bedrock_agent.create_prompt_version(
        promptIdentifier=prompt_id,
        description=description
    )
    print(f"Created version {response['version']} for prompt {prompt_id}")
    return response


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="dev", choices=["dev", "staging", "prod"])
    args = parser.parse_args()

    print(f"Setting up Bedrock prompts for environment: {args.env}")

    # Create v1 prompt
    v1 = create_prompt(
        name=f"rag-system-prompt-{args.env}-v1",
        content=RAG_SYSTEM_PROMPT_V1,
        description="RAG system prompt v1 — baseline"
    )
    create_prompt_version(v1["id"], "v1 — production baseline")

    # Create v2 prompt (candidate for A/B testing)
    v2 = create_prompt(
        name=f"rag-system-prompt-{args.env}-v2",
        content=RAG_SYSTEM_PROMPT_V2,
        description="RAG system prompt v2 — enhanced with structured output"
    )
    create_prompt_version(v2["id"], "v2 — candidate for A/B testing")

    print("\nPrompt IDs to add to DynamoDB prompt registry:")
    print(json.dumps({
        "v1_prompt_id": v1["id"],
        "v2_prompt_id": v2["id"],
        "env": args.env
    }, indent=2))
