"""
Prompt templates — defines all prompt IDs and their default configurations.
Single source of truth for prompt names used across the platform.
"""

# Prompt IDs — used as keys in DynamoDB registry and Bedrock Prompt Management
PROMPTS = {
    "rag_system":      "rag-system-prompt",
    "summarization":   "summarization-prompt",
    "sql_generation":  "sql-generation-prompt",
    "eval_judge":      "eval-judge-prompt",
}

# Minimum eval score required for environment promotion
PROMOTION_THRESHOLDS = {
    "dev_to_staging": 0.70,
    "staging_to_prod": 0.85,
}

# A/B test traffic split — percentage routed to candidate version
AB_TEST_RATIO = 0.10