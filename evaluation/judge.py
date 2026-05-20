"""
LLM-as-Judge evaluator using Amazon Nova Pro.
Nova Pro content format: array of strings, not typed objects.
"""

import os
import json
import logging
import boto3

logger      = logging.getLogger(__name__)
bedrock     = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "us-east-1"))
JUDGE_MODEL = "us.amazon.nova-pro-v1:0"

JUDGE_PROMPT = """You are an expert evaluator for RAG systems.

Question: {question}
Expected Answer: {expected_answer}
Actual Answer: {actual_answer}
Retrieved Context: {context}

Score each metric 0.0-1.0:
- FAITHFULNESS: No hallucinations, stays true to context
- RELEVANCE: Addresses the question
- COMPLETENESS: Covers key points from expected answer
- CONCISENESS: Appropriately concise

Respond ONLY with valid JSON, no other text:
{{"faithfulness": 0.0, "relevance": 0.0, "completeness": 0.0, "conciseness": 0.0, "overall": 0.0, "reasoning": "brief explanation"}}"""


def evaluate_response(question: str, expected_answer: str,
                      actual_answer: str, context: str = "") -> dict:
    """Calls Nova Pro judge to score a RAG response."""
    prompt = JUDGE_PROMPT.format(
        question=question,
        expected_answer=expected_answer,
        actual_answer=actual_answer,
        context=context[:500] if context else "No context retrieved"
    )

    try:
        response = bedrock.invoke_model(
            modelId=JUDGE_MODEL,
            body=json.dumps({
                "messages": [{
                    "role": "user",
                    "content": [{"text": prompt}]  # Nova Pro: no "type" key
                }],
                "inferenceConfig": {"maxTokens": 512, "temperature": 0.0}
            }),
            contentType="application/json",
            accept="application/json"
        )

        body   = json.loads(response["body"].read())
        text   = body["output"]["message"]["content"][0]["text"]

        start  = text.find("{")
        end    = text.rfind("}") + 1
        scores = json.loads(text[start:end])

        scores["overall"] = (
            scores.get("faithfulness", 0) * 0.35 +
            scores.get("relevance", 0)    * 0.35 +
            scores.get("completeness", 0) * 0.20 +
            scores.get("conciseness", 0)  * 0.10
        )

        return scores

    except Exception as e:
        logger.error(f"Judge evaluation failed: {e}")
        return {
            "faithfulness": 0.0, "relevance": 0.0,
            "completeness": 0.0, "conciseness": 0.0,
            "overall": 0.0, "reasoning": f"Evaluation failed: {str(e)}"
        }
