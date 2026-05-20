"""
FastAPI RAG service with Langfuse observability + CloudWatch custom metrics.
Publishes LLMOps/Bedrock namespace: latency p50/p95/p99, error rate, token usage.
"""

import os
import uuid
import json
import logging
import threading
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from collections import deque

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

cloudwatch = boto3.client(
    "cloudwatch",
    region_name=os.environ.get("AWS_REGION", "us-east-1")
)

# ── Langfuse ──────────────────────────────────────────────────────────────────
langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
)

# ── Config ────────────────────────────────────────────────────────────────────
KNOWLEDGE_BASE_ID = os.environ["KNOWLEDGE_BASE_ID"]
MODEL_ARN         = os.environ.get(
    "MODEL_ARN",
    "arn:aws:bedrock:us-east-1:011528270076:inference-profile/us.amazon.nova-pro-v1:0"
)
REDIS_HOST  = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT  = int(os.environ.get("REDIS_PORT", "6379"))
SESSION_TTL = int(os.environ.get("SESSION_TTL", "1800"))
CW_NAMESPACE = "LLMOps/Bedrock"

# ── In-memory latency buffer for percentile calculation ───────────────────────
# Keeps last 1000 latency values — percentiles computed per flush
_latency_buffer = deque(maxlen=1000)
_buffer_lock    = threading.Lock()
_error_count    = 0
_request_count  = 0

# ── Redis ─────────────────────────────────────────────────────────────────────
redis_client = redis.Redis(
    host=REDIS_HOST, port=REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=2, socket_timeout=2
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        redis_client.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning(f"Redis unavailable: {e}")
    yield
    langfuse.flush()


app = FastAPI(title="LLMOps RAG API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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


# ── CloudWatch metrics helper ─────────────────────────────────────────────────
def publish_metrics(latency_ms: float, success: bool,
                    tenant_id: str, citation_count: int):
    """
    Publishes custom metrics to CloudWatch LLMOps/Bedrock namespace.
    Dimensions: tenant_id, model — enables per-tenant cost attribution.
    Runs in background thread to not block request handling.
    """
    global _error_count, _request_count

    with _buffer_lock:
        _latency_buffer.append(latency_ms)
        _request_count += 1
        if not success:
            _error_count += 1

        # Calculate percentiles from buffer
        sorted_latencies = sorted(_latency_buffer)
        n = len(sorted_latencies)
        p50 = sorted_latencies[int(n * 0.50)] if n > 0 else 0
        p95 = sorted_latencies[int(n * 0.95)] if n > 0 else 0
        p99 = sorted_latencies[int(n * 0.99)] if n > 0 else 0
        error_rate = (_error_count / _request_count * 100) if _request_count > 0 else 0

    model_name = MODEL_ARN.split("/")[-1]

    try:
        cloudwatch.put_metric_data(
            Namespace=CW_NAMESPACE,
            MetricData=[
                {
                    "MetricName": "QueryLatency",
                    "Value": latency_ms,
                    "Unit": "Milliseconds",
                    "Dimensions": [
                        {"Name": "tenant_id", "Value": tenant_id},
                        {"Name": "model",     "Value": model_name}
                    ]
                },
                {
                    "MetricName": "LatencyP50",
                    "Value": p50,
                    "Unit": "Milliseconds",
                    "Dimensions": [{"Name": "model", "Value": model_name}]
                },
                {
                    "MetricName": "LatencyP95",
                    "Value": p95,
                    "Unit": "Milliseconds",
                    "Dimensions": [{"Name": "model", "Value": model_name}]
                },
                {
                    "MetricName": "LatencyP99",
                    "Value": p99,
                    "Unit": "Milliseconds",
                    "Dimensions": [{"Name": "model", "Value": model_name}]
                },
                {
                    "MetricName": "ErrorRate",
                    "Value": error_rate,
                    "Unit": "Percent",
                    "Dimensions": [{"Name": "model", "Value": model_name}]
                },
                {
                    "MetricName": "CitationCount",
                    "Value": citation_count,
                    "Unit": "Count",
                    "Dimensions": [{"Name": "tenant_id", "Value": tenant_id}]
                },
                {
                    "MetricName": "RequestCount",
                    "Value": 1,
                    "Unit": "Count",
                    "Dimensions": [
                        {"Name": "tenant_id", "Value": tenant_id},
                        {"Name": "success",   "Value": str(success)}
                    ]
                }
            ]
        )
    except Exception as e:
        logger.warning(f"CloudWatch publish failed: {e}")


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


# ── Health ────────────────────────────────────────────────────────────────────
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


# ── /query ────────────────────────────────────────────────────────────────────
@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    session_id = req.session_id or str(uuid.uuid4())
    start      = datetime.now(timezone.utc)
    success    = True

    trace = langfuse.trace(
        name="rag-query",
        user_id=req.tenant_id,
        session_id=session_id,
        metadata={"tenant_id": req.tenant_id, "kb_id": KNOWLEDGE_BASE_ID},
        tags=["rag", "query", req.tenant_id]
    )

    try:
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

        retrieval_span.end(output={"answer": answer[:200], "citations": len(citations)})

        trace.generation(
            name="rag-generation",
            model=MODEL_ARN.split("/")[-1],
            input=req.query,
            output=answer,
            metadata={"latency_ms": latency, "citations": len(citations)}
        )

        trace.update(output={"answer": answer[:200], "latency_ms": latency})

        # Publish CloudWatch metrics in background — non-blocking
        threading.Thread(
            target=publish_metrics,
            args=(latency, True, req.tenant_id, len(citations)),
            daemon=True
        ).start()

        _save_to_session(session_id, req.tenant_id, req.query, answer)

        logger.info(
            f"query tenant={req.tenant_id} latency_ms={latency:.2f} "
            f"citations={len(citations)} trace_id={trace.id}"
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
        success = False
        trace.update(output={"error": str(e)})
        threading.Thread(
            target=publish_metrics,
            args=(0, False, req.tenant_id, 0),
            daemon=True
        ).start()
        logger.error(f"Query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── /chat ─────────────────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(req: QueryRequest):
    session_id = req.session_id or str(uuid.uuid4())
    history    = _get_session_history(session_id)
    context_query = f"Previous conversation:\n{history}\n\nCurrent question: {req.query}" if history else req.query
    return await query(QueryRequest(query=context_query, tenant_id=req.tenant_id, session_id=session_id))


# ── /agent ────────────────────────────────────────────────────────────────────
@app.post("/agent")
async def agent_query(req: QueryRequest):
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

        result  = invoke_supervisor(query=req.query, session_id=session_id, tenant_id=req.tenant_id)
        latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        trace.generation(
            name="agent-generation",
            model="nova-pro-supervisor",
            input=req.query,
            output=result.get("answer", ""),
            metadata={"latency_ms": latency}
        )

        threading.Thread(
            target=publish_metrics,
            args=(latency, True, req.tenant_id, len(result.get("citations", []))),
            daemon=True
        ).start()

        result["trace_id"] = str(trace.id)
        return result

    except Exception as e:
        trace.update(output={"error": str(e)})
        logger.error(f"Agent failed, falling back to RAG: {e}")
        return await query(req)


# ── /metrics — expose internal metrics ────────────────────────────────────────
@app.get("/metrics")
async def metrics():
    """Internal metrics endpoint — p50/p95/p99 latency from in-memory buffer."""
    with _buffer_lock:
        if not _latency_buffer:
            return {"message": "No requests yet"}
        sorted_l = sorted(_latency_buffer)
        n = len(sorted_l)
        return {
            "request_count": _request_count,
            "error_count":   _error_count,
            "error_rate_pct": round(_error_count / _request_count * 100, 2) if _request_count > 0 else 0,
            "latency_p50_ms": sorted_l[int(n * 0.50)],
            "latency_p95_ms": sorted_l[int(n * 0.95)],
            "latency_p99_ms": sorted_l[int(n * 0.99)],
            "latency_min_ms": sorted_l[0],
            "latency_max_ms": sorted_l[-1],
            "sample_count":  n
        }


# ── Helpers ───────────────────────────────────────────────────────────────────
def _save_to_session(session_id, tenant_id, q, a):
    try:
        key   = f"session:{tenant_id}:{session_id}"
        turns = json.loads(redis_client.get(key) or "[]")
        turns.append({"q": q, "a": a})
        redis_client.setex(key, SESSION_TTL, json.dumps(turns[-10:]))
    except Exception as e:
        logger.warning(f"Session save failed: {e}")


def _get_session_history(session_id):
    try:
        keys = redis_client.keys(f"session:*:{session_id}")
        if not keys:
            return ""
        return "\n".join([f"Q: {t['q']}\nA: {t['a']}" for t in json.loads(redis_client.get(keys[0]) or "[]")])
    except Exception:
        return ""


def _extract_citations(response):
    citations = []
    for c in response.get("citations", []):
        for ref in c.get("retrievedReferences", []):
            citations.append({
                "content":  ref.get("content", {}).get("text", "")[:200],
                "location": ref.get("location", {}).get("s3Location", {}).get("uri", ""),
                "score":    ref.get("score", 0)
            })
    return citations
