import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.requests import Request

from src.config import settings
from src.observability import log_json, normalize_request_id, request_id_context

logger = logging.getLogger("bookly.access")


def register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_request(request: Request, call_next):
        started_at = time.perf_counter()
        request_id = normalize_request_id(request.headers.get("X-Request-ID"))
        context_token = request_id_context.set(request_id)
        client_ip = request.client.host if request.client else "unknown"
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            log_json(
                logger,
                logging.INFO,
                "http.request.completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
                client_ip=client_ip,
            )
            return response
        except Exception:
            log_json(
                logger,
                logging.ERROR,
                "http.request.failed",
                exc_info=True,
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=round((time.perf_counter() - started_at) * 1000, 3),
                client_ip=client_ip,
            )
            raise
        finally:
            request_id_context.reset(context_token)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    configured_host = settings.PUBLIC_BASE_URL.host
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[
            "testserver",
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            configured_host,
            "bookly-api-dc03.onrender.com",
        ],
    )
