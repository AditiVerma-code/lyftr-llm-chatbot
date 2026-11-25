import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import (
    init_db,
    check_db_health,
    add_message,
    session_exists,
    get_session_messages,
)
from app.gateway import (
    execute_chat_completion,
    AllProvidersUnavailableException,
    cache_enabled_status,
)
from app.models import (
    HealthResponse,
    ChatRequest,
    ChatResponse,
    SessionHistoryResponse,
    SessionMessage,
    MessageMetadata,
)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite schema on startup
    logger.info("Initializing database schema...")
    init_db()
    logger.info(f"Database initialized at: {settings.DATABASE_URL}")
    logger.info(f"Key pool configured with {len(settings.key_pool)} keys.")
    yield


app = FastAPI(
    title="Lyftr AI - Resilient LLM Chatbot Gateway",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,  # Spec: exposes exactly these three endpoints
    redoc_url=None,
    openapi_url=None,
)

# Configure CORS
origins = settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from fastapi.encoders import jsonable_encoder

# Standardize all error responses to strictly JSON with a 'detail' field
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(exc.errors())},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(AllProvidersUnavailableException)
async def all_providers_unavailable_handler(request: Request, exc: AllProvidersUnavailableException):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "all providers unavailable"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "internal server error"},
    )


# 1. GET /health
@app.get("/health", response_model=HealthResponse)
async def health():
    """
    Returns 200 once the app is running, the database is reachable and the key pool is loaded.
    { "status": "ok", "keys_configured": 2, "cache_enabled": true }
    """
    db_ok = check_db_health()
    if not db_ok:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="database unreachable",
        )

    keys_count = len(settings.key_pool)
    if keys_count < 1:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="no keys configured in pool",
        )

    return HealthResponse(
        status="ok",
        keys_configured=keys_count,
        cache_enabled=cache_enabled_status,
    )


# 2. POST /chat
@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure"),
):
    """
    Processes chat requests with multi-turn memory, response caching, and key pool failover.
    Supports X-Simulate-Failure header for testing failovers on demand.
    """
    # 1. Retrieve session history from SQLite (oldest first, without system prompt)
    history_messages = get_session_messages(request.session_id)

    # 2. Build full message payload for LLM (system prompt + history + new user message)
    system_prompt = request.system_prompt or settings.DEFAULT_SYSTEM_PROMPT
    llm_messages = [{"role": "system", "content": system_prompt}]
    for msg in history_messages:
        llm_messages.append({"role": msg["role"], "content": msg["content"]})
    llm_messages.append({"role": "user", "content": request.message})

    # 3. Call LiteLLM gateway (with automatic failover, caching, and failure simulation)
    # Notice: If this raises AllProvidersUnavailableException, nothing is written to DB.
    reply_text, metadata = execute_chat_completion(
        messages=llm_messages,
        model=settings.DEFAULT_MODEL,
        simulate_failure_header=x_simulate_failure,
    )

    # 4. Save to SQLite ONLY upon successful completion
    add_message(
        session_id=request.session_id,
        role="user",
        content=request.message,
    )
    add_message(
        session_id=request.session_id,
        role="assistant",
        content=reply_text,
        metadata=metadata.model_dump(),
    )

    return ChatResponse(
        session_id=request.session_id,
        reply=reply_text,
        metadata=metadata,
    )


# 3. GET /sessions/{session_id}/messages
@app.get("/sessions/{session_id}/messages", response_model=SessionHistoryResponse)
async def get_messages(session_id: str):
    """
    Returns the stored history of one session from SQLite, oldest first, without the system prompt.
    Returns 404 {"detail": "session not found"} if the session is unknown.
    """
    if not session_exists(session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="session not found",
        )

    raw_messages = get_session_messages(session_id)
    formatted = []
    for m in raw_messages:
        meta = None
        if "metadata" in m and m["metadata"]:
            meta = MessageMetadata(**m["metadata"])
        formatted.append(
            SessionMessage(
                role=m["role"],
                content=m["content"],
                metadata=meta,
            )
        )

    return SessionHistoryResponse(
        session_id=session_id,
        messages=formatted,
    )
