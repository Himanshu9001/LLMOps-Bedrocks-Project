"""
Prompt Manager — handles versioned prompt retrieval, A/B routing,
and promotion workflow between environments.
Prompts stored in Bedrock Prompt Management, registry in DynamoDB.
"""

import os
import random
import logging
from datetime import datetime, timezone
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

# ── Clients ───────────────────────────────────────────────────────────────────
bedrock_agent = boto3.client("bedrock-agent", region_name=os.environ.get("AWS_REGION", "us-east-1"))
dynamodb      = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))

PROMPT_TABLE  = os.environ.get("PROMPT_TABLE", "llmops-bedrock-dev-prompt-registry")
AB_TEST_RATIO = float(os.environ.get("AB_TEST_RATIO", "0.1"))  # 10% to new version

prompt_table  = dynamodb.Table(PROMPT_TABLE)


class PromptManager:
    """
    Manages versioned prompts with A/B testing and environment promotion.
    
    Usage:
        manager = PromptManager()
        prompt  = manager.get_prompt("rag-system-prompt", env="dev")
        text    = prompt["text"]
    """

    def get_prompt(self, prompt_id: str, env: str = "dev") -> dict:
        """
        Gets active prompt for given ID and environment.
        If A/B test is configured, routes 10% traffic to candidate version.
        Falls back to hardcoded default if DynamoDB/Bedrock unavailable.
        """
        try:
            # Get active prompt version from registry
            active   = self._get_active_version(prompt_id, env)
            candidate = self._get_candidate_version(prompt_id, env)

            # A/B routing — 10% to candidate if one exists
            if candidate and random.random() < AB_TEST_RATIO:
                selected = candidate
                logger.info(f"A/B test: routing to candidate v{candidate['version']}")
            else:
                selected = active
                logger.info(f"Routing to active v{selected['version']}")

            # Fetch actual prompt text from Bedrock
            prompt_text = self._fetch_from_bedrock(
                selected["bedrock_prompt_id"],
                selected["version"]
            )

            return {
                "text":       prompt_text,
                "version":    selected["version"],
                "prompt_id":  prompt_id,
                "env":        env,
                "ab_variant": "candidate" if selected == candidate else "active"
            }

        except Exception as e:
            logger.warning(f"Prompt fetch failed, using default: {e}")
            return self._default_prompt()

    def promote_prompt(self, prompt_id: str, version: str,
                       from_env: str, to_env: str,
                       eval_score: float, threshold: float = 0.75) -> dict:
        """
        Promotes a prompt version to the next environment.
        Blocked if eval_score is below threshold — CI gate enforcement.
        
        Promotion path: dev → staging → prod
        """
        if eval_score < threshold:
            return {
                "success": False,
                "reason":  f"Eval score {eval_score} below threshold {threshold}",
                "action":  "promotion_blocked"
            }

        # Write promoted version to target environment
        prompt_table.put_item(Item={
            "prompt_id":         prompt_id,
            "version":           version,
            "bedrock_prompt_id": self._get_bedrock_id(prompt_id, version, from_env),
            "environment":       to_env,
            "evaluation_score":  str(eval_score),
            "status":            "active",
            "promoted_at":       datetime.now(timezone.utc).isoformat(),
            "promoted_from":     from_env,
            "promoted_by":       "ci-pipeline"
        })

        logger.info(f"Promoted {prompt_id} v{version} from {from_env} to {to_env}")
        return {
            "success":  True,
            "prompt_id": prompt_id,
            "version":  version,
            "from_env": from_env,
            "to_env":   to_env,
            "eval_score": eval_score
        }

    def update_eval_score(self, prompt_id: str, version: str,
                          env: str, score: float) -> None:
        """Updates evaluation score for a prompt version — called by eval pipeline."""
        prompt_table.update_item(
            Key={"prompt_id": prompt_id, "version": version},
            UpdateExpression="SET evaluation_score = :score, evaluated_at = :ts",
            ExpressionAttributeValues={
                ":score": str(score),
                ":ts":    datetime.now(timezone.utc).isoformat()
            }
        )
        logger.info(f"Updated eval score for {prompt_id} v{version}: {score}")

    def _get_active_version(self, prompt_id: str, env: str) -> dict:
        """Queries DynamoDB for active prompt version in given environment."""
        response = prompt_table.query(
            IndexName="environment-index",
            KeyConditionExpression=Key("environment").eq(env),
            FilterExpression=boto3.dynamodb.conditions.Attr("prompt_id").eq(prompt_id)
                           & boto3.dynamodb.conditions.Attr("status").eq("active")
        )
        items = response.get("Items", [])
        if not items:
            raise ValueError(f"No active prompt found for {prompt_id} in {env}")
        # Return highest version number
        return max(items, key=lambda x: int(x["version"]))

    def _get_candidate_version(self, prompt_id: str, env: str) -> Optional[dict]:
        """Returns candidate version for A/B testing if one exists."""
        try:
            response = prompt_table.query(
                IndexName="environment-index",
                KeyConditionExpression=Key("environment").eq(env),
                FilterExpression=boto3.dynamodb.conditions.Attr("prompt_id").eq(prompt_id)
                               & boto3.dynamodb.conditions.Attr("status").eq("candidate")
            )
            items = response.get("Items", [])
            return items[0] if items else None
        except Exception:
            return None

    def _fetch_from_bedrock(self, bedrock_prompt_id: str, version: str) -> str:
        """Fetches prompt text from Bedrock Prompt Management."""
        response = bedrock_agent.get_prompt(
            promptIdentifier=bedrock_prompt_id,
            promptVersion=version
        )
        variants = response.get("variants", [])
        if not variants:
            raise ValueError("No variants in Bedrock prompt")
        return variants[0]["templateConfiguration"]["text"]["text"]

    def _get_bedrock_id(self, prompt_id: str, version: str, env: str) -> str:
        """Looks up Bedrock prompt ID from registry."""
        response = prompt_table.get_item(
            Key={"prompt_id": prompt_id, "version": version}
        )
        return response.get("Item", {}).get("bedrock_prompt_id", "")

    def _default_prompt(self) -> dict:
        """Fallback prompt when Bedrock/DynamoDB unavailable."""
        return {
            "text": (
                "You are an intelligent document assistant. "
                "Answer questions based strictly on the provided context. "
                "If the context is insufficient, say so clearly. "
                "Context: {{context}}\nQuestion: {{question}}"
            ),
            "version":    "default",
            "prompt_id":  "fallback",
            "env":        "unknown",
            "ab_variant": "default"
        }