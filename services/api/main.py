"""
FastAPI RAG service with Langfuse observability.
Every LLM call traced: tokens, latency, cost, model, tenant.
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
from langfuse import Langfuse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── AWS Clients ───────────────────────────────────────────────────────────────
bedrock_agent_runtime = boto3.client(
    "bedrock-agent-runtime",
    region_name=os.environ.get("AWS_REGION", "us-east-1")
)

# ── Langfuse Client ───────────────────────────────────────────────────────────
# Traces every LLM call with prompt, response, tokens, latency, cost
langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
)

# ── Environment Variables ─────────────────────────────────────────────────────
KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
MODEL_ARN         = os.environ.get(
    "MODEL_ARN",
    "arn:aws:bedrock:us-east-1:011528270076:inference-profile/us.amazon.nova-pro-v1:0"
)
REDIS_HOST  = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT  = int(os.environ.get("REDIS_PORT", "6379"))
SESSION_TTL = int(os.environ.get("SESSION_TTL", "1800"))

# ── Redis Client ──────────────────────────────────────────────────────────────
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        redis_client.ping()
        logger.info("Redis connection verified")
    except Exception as e:
        logger.warning(f"Redis unavailable: {e}")
    yield
    # Flush Langfuse traces on shutdown
    langfuse.flush()


app = FastAPI(title="LLMOps RAG API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────────────────────
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
    trace_id: str | None = None


# ── Middleware ────────────────────────────────────────────────────────────────
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
    redis_ok = False
    try:
        redis_client.ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "status":            "healthy",
        "redis":             "connected" if redis_ok else "unavailable",
        "knowledge_base_id": KNOWLEDGE_BASE_ID,
        "timestamp":         datetime.now(timezone.utc).isoformat()
    }


# ── /query — single-turn RAG with Langfuse tracing ───────────────────────────
@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    """
    Single-turn RAG query with full Langfuse observability.
    Every call traced: input, output, latency, model, tenant_id.
    """
    session_id = req.session_id or str(uuid.uuid4())
    start      = datetime.now(timezone.utc)

    # Create Langfuse trace — root span for this request
    trace = langfuse.trace(
        name="rag-query",
        user_id=req.tenant_id,
        session_id=session_id,
        metadata={
            "tenant_id": req.tenant_id,
            "kb_id":     KNOWLEDGE_BASE_ID,
            "model":     MODEL_ARN.split("/")[-1]
        },
        tags=["rag", "query", req.tenant_id]
    )

    try:
        # Span: Bedrock RetrieveAndGenerate call
        retrieval_span = trace.span(
            name="bedrock-retrieve-and-generate",
            input={"query": req.query, "tenant_id": req.tenant_id}
        )

        response = bedrock_agent_runtime.retrieve_and_generate(
            input={"text": req.query},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KNOWLEDGE_BASE_ID,
                    "modelArn":        MODEL_ARN,
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {
                            "numberOfResults": req.max_results,
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

        answer    = response["output"]["text"]
        citations = _extract_citations(response)
        latency   = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        # End retrieval span with output
        retrieval_span.end(
            output={
                "answer":         answer[:200],
                "citation_count": len(citations),
                "latency_ms":     latency
            }
        )

        # Log generation as Langfuse generation event — captures token usage
        trace.generation(
            name="rag-generation",
            model=MODEL_ARN.split("/")[-1],
            input=req.query,
            output=answer,
            metadata={
                "citations":  len(citations),
                "latency_ms": latency,
                "tenant_id":  req.tenant_id
            }
        )

        # Update trace with final output
        trace.update(
            output={"answer": answer[:200], "latency_ms": latency},
            metadata={"citation_count": len(citations)}
        )

        # Save to Redis session
        _save_to_session(session_id, req.tenant_id, req.query, answer)

        logger.info(
            f"query tenant={req.tenant_id} session={session_id} "
            f"latency_ms={latency:.2f} citations={len(citations)} "
            f"trace_id={trace.id}"
        )

        return QueryResponse(
            answer=answer,
            session_id=session_id,
            citations=citations,
            model_id=MODEL_ARN.split("/")[-1],
            latency_ms=latency,
            trace_id=str(trace.id)
        )

    except Exception as e:
        trace.update(
            output={"error": str(e)},
            metadata={"status": "failed"}
        )
        logger.error(f"Query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── /chat — multi-turn ────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(req: QueryRequest):
    session_id = req.session_id or str(uuid.uuid4())
    history    = _get_session_history(session_id)

    if history:
        context_query = f"Previous conversation:\n{history}\n\nCurrent question: {req.query}"
    else:
        context_query = req.query

    return await query(QueryRequest(
        query=context_query,
        tenant_id=req.tenant_id,
        session_id=session_id
    ))


# ── /agent — Bedrock supervisor agent ────────────────────────────────────────
@app.post("/agent")
async def agent_query(req: QueryRequest):
    """Multi-agent RAG endpoint with Langfuse tracing."""
    session_id = req.session_id or str(uuid.uuid4())
    start      = datetime.now(timezone.utc)

    trace = langfuse.trace(
        name="agent-query",
        user_id=req.tenant_id,
        session_id=session_id,
        tags=["agent", req.tenant_id]
    )

    try:
        import sys
        sys.path.insert(0, "/app")
        from agents.supervisor import invoke_supervisor

        result  = invoke_supervisor(
            query=req.query,
            session_id=session_id,
            tenant_id=req.tenant_id
        )
        latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        trace.generation(
            name="agent-generation",
            model="nova-pro-supervisor",
            input=req.query,
            output=result.get("answer", ""),
            metadata={"latency_ms": latency, "trace_id": str(trace.id)}
        )

        result["trace_id"] = str(trace.id)
        return result

    except Exception as e:
        trace.update(output={"error": str(e)})
        logger.error(f"Agent query failed, falling back to RAG: {e}")
        return await query(req)


# ── Session helpers ───────────────────────────────────────────────────────────
def _save_to_session(session_id: str, tenant_id: str, query: str, answer: str):
    try:
        key     = f"session:{tenant_id}:{session_id}"
        history = redis_client.get(key) or "[]"
        turns   = json.loads(history)
        turns.append({"q": query, "a": answer})
        turns   = turns[-10:]
        redis_client.setex(key, SESSION_TTL, json.dumps(turns))
    except Exception as e:
        logger.warning(f"Session save failed: {e}")


def _get_session_history(session_id: str) -> str:
    try:
        keys    = redis_client.keys(f"session:*:{session_id}")
        if not keys:
            return ""
        history = json.loads(redis_client.get(keys[0]) or "[]")
        return "\n".join([f"Q: {t['q']}\nA: {t['a']}" for t in history])
    except Exception:
        return ""


def _extract_citations(response: dict) -> list:
    citations = []
    for citation in response.get("citations", []):
        for ref in citation.get("retrievedReferences", []):
            citations.append({
                "content":  ref.get("content", {}).get("text", "")[:200],
                "location": ref.get("location", {}).get("s3Location", {}).get("uri", ""),
                "score":    ref.get("score", 0)
            })
    return citations
