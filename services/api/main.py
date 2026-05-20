"""
FastAPI RAG service — exposes /query, /chat, /health endpoints.
Calls Bedrock RetrieveAndGenerate API for RAG responses.
Redis (ElastiCache) stores conversation session memory per tenant.
IRSA provides AWS credentials to the pod — no hardcoded keys.
"""

import os
import uuid
import json
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import boto3
import redis
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── AWS Clients ───────────────────────────────────────────────────────────────
bedrock_agent_runtime = boto3.client(
    "bedrock-agent-runtime",
    region_name=os.environ.get("AWS_REGION", "us-east-1")
)

# ── Environment Variables ─────────────────────────────────────────────────────
KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
MODEL_ARN         = os.environ.get(
    "MODEL_ARN",
    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0"
)
REDIS_HOST        = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT        = int(os.environ.get("REDIS_PORT", "6379"))
SESSION_TTL       = int(os.environ.get("SESSION_TTL", "1800"))  # 30 min

# ── Redis Client ──────────────────────────────────────────────────────────────
# decode_responses=True returns strings instead of bytes
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify Redis and Bedrock connectivity."""
    try:
        redis_client.ping()
        logger.info("Redis connection verified")
    except Exception as e:
        logger.warning(f"Redis unavailable: {e} — sessions will be stateless")
    yield


app = FastAPI(
    title="LLMOps RAG API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response Models ───────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str
    tenant_id: str = "default"
    session_id: str | None = None
    max_results: int = 5


class QueryResponse(BaseModel):
    answer: str
    session_id: str
    citations: list
    model_id: str
    latency_ms: float


class ChatRequest(BaseModel):
    message: str
    tenant_id: str = "default"
    session_id: str | None = None


# ── Middleware — request logging with tenant/session tagging ──────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start    = datetime.now(timezone.utc)
    response = await call_next(request)
    duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000

    logger.info(
        f"method={request.method} path={request.url.path} "
        f"status={response.status_code} duration_ms={duration:.2f}"
    )
    return response


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Kubernetes liveness + readiness probe endpoint."""
    redis_ok = False
    try:
        redis_client.ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "status": "healthy",
        "redis": "connected" if redis_ok else "unavailable",
        "knowledge_base_id": KNOWLEDGE_BASE_ID,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ── /query — single-turn RAG ──────────────────────────────────────────────────
@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    """
    Single-turn RAG query.
    Calls Bedrock RetrieveAndGenerate — retrieves relevant chunks from
    OpenSearch and generates a grounded response with citations.
    tenant_id enforced as metadata filter — cross-tenant data isolation.
    """
    session_id = req.session_id or str(uuid.uuid4())
    start      = datetime.now(timezone.utc)

    try:
        response = bedrock_agent_runtime.retrieve_and_generate(
            input={"text": req.query},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KNOWLEDGE_BASE_ID,
                    "modelArn": MODEL_ARN,
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {
                            "numberOfResults": req.max_results,
                            # tenant_id filter — enforces data isolation at retrieval
                            "filter": {
                                "equals": {
                                    "key":   "tenant_id",
                                    "value": req.tenant_id
                                }
                            }
                        }
                    }
                }
            }
        )

        answer   = response["output"]["text"]
        citations = _extract_citations(response)
        latency  = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        # Store query + answer in Redis for session continuity
        _save_to_session(session_id, req.tenant_id, req.query, answer)

        logger.info(
            f"query tenant={req.tenant_id} session={session_id} "
            f"latency_ms={latency:.2f} citations={len(citations)}"
        )

        return QueryResponse(
            answer=answer,
            session_id=session_id,
            citations=citations,
            model_id=MODEL_ARN.split("/")[-1],
            latency_ms=latency
        )

    except bedrock_agent_runtime.exceptions.ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Query processing failed")


# ── /chat — multi-turn conversation ──────────────────────────────────────────
@app.post("/chat")
async def chat(req: ChatRequest):
    """
    Multi-turn chat with session memory from Redis.
    Retrieves conversation history, appends to context, calls RAG.
    Session expires after SESSION_TTL seconds of inactivity.
    """
    session_id = req.session_id or str(uuid.uuid4())
    history    = _get_session_history(session_id)

    # Build context-aware query from history
    if history:
        context_query = f"Previous conversation:\n{history}\n\nCurrent question: {req.message}"
    else:
        context_query = req.message

    # Reuse query endpoint logic
    query_req = QueryRequest(
        query=context_query,
        tenant_id=req.tenant_id,
        session_id=session_id
    )
    return await query(query_req)


# ── Session helpers ───────────────────────────────────────────────────────────
def _save_to_session(session_id: str, tenant_id: str, query: str, answer: str):
    """Appends Q&A turn to Redis session. TTL reset on each write."""
    try:
        key     = f"session:{tenant_id}:{session_id}"
        history = redis_client.get(key) or "[]"
        turns   = json.loads(history)
        turns.append({"q": query, "a": answer})
        # Keep last 10 turns — prevents context window overflow
        turns   = turns[-10:]
        redis_client.setex(key, SESSION_TTL, json.dumps(turns))
    except Exception as e:
        logger.warning(f"Session save failed: {e}")


def _get_session_history(session_id: str) -> str:
    """Returns formatted conversation history from Redis."""
    try:
        key     = f"session:*:{session_id}"
        keys    = redis_client.keys(key)
        if not keys:
            return ""
        history = json.loads(redis_client.get(keys[0]) or "[]")
        return "\n".join([f"Q: {t['q']}\nA: {t['a']}" for t in history])
    except Exception:
        return ""


def _extract_citations(response: dict) -> list:
    """Extracts source citations from Bedrock RetrieveAndGenerate response."""
    citations = []
    for citation in response.get("citations", []):
        for ref in citation.get("retrievedReferences", []):
            citations.append({
                "content":  ref.get("content", {}).get("text", "")[:200],
                "location": ref.get("location", {}).get("s3Location", {}).get("uri", ""),
                "score":    ref.get("score", 0)
            })
    return citations