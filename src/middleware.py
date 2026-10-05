import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.requests import Request

from src.config import settings

logger = logging.getLogger("bookly.access")


def register_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_request(request: Request, call_next):
        started_at = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started_at
        client = request.client
        client_address = f"{client.host}:{client.port}" if client else "unknown"
        logger.info(
            "%s - %s %s - %s - %.4fs",
            client_address,
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    configured_host = settings.DOMAIN.split(":", maxsplit=1)[0]
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
