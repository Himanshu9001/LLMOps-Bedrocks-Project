"""
Supervisor agent — invokes Bedrock Agent and handles EventStream response.
Routes queries to the supervisor agent which internally uses KB retrieval.
"""

import os
import uuid
import logging
import boto3

logger = logging.getLogger(__name__)

AGENT_ID       = os.environ.get("AGENT_ID", "4AP3RGIQHK")
AGENT_ALIAS_ID = os.environ.get("AGENT_ALIAS_ID", "33GXHZXGLY")
AWS_REGION     = os.environ.get("AWS_REGION", "us-east-1")

client = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)


def invoke_supervisor(query: str, session_id: str = None, tenant_id: str = "default") -> dict:
    """
    Invokes the Bedrock supervisor agent.
    Handles EventStream response — iterates chunks to assemble full response.
    session_id enables multi-turn memory within Bedrock AgentCore.
    """
    session_id = session_id or str(uuid.uuid4())

    try:
        response = client.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=query,
            # Pass tenant_id as session attribute for agent context
            sessionState={
                "sessionAttributes": {
                    "tenant_id": tenant_id
                }
            }
        )

        # Collect full response from EventStream
        full_response = ""
        citations     = []

        for event in response["completion"]:
            if "chunk" in event:
                chunk = event["chunk"]
                full_response += chunk["bytes"].decode("utf-8")

                # Extract citations from chunk attribution
                if "attribution" in chunk:
                    for ref in chunk["attribution"].get("citations", []):
                        for retrieved in ref.get("retrievedReferences", []):
                            citations.append({
                                "content":  retrieved.get("content", {}).get("text", "")[:200],
                                "location": retrieved.get("location", {}).get("s3Location", {}).get("uri", "")
                            })

        logger.info(f"Agent response: session={session_id} tenant={tenant_id} citations={len(citations)}")

        return {
            "answer":     full_response,
            "session_id": session_id,
            "citations":  citations,
            "agent_id":   AGENT_ID,
            "source":     "bedrock-agent"
        }

    except Exception as e:
        logger.error(f"Agent invocation failed: {e}", exc_info=True)
        raise
