import json
import logging
import re
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

request_id_context: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)
SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def normalize_request_id(candidate: str | None) -> str:
    if candidate and SAFE_REQUEST_ID.fullmatch(candidate):
        return candidate
    return str(uuid.uuid4())


def log_json(
    logger: logging.Logger,
    level: int,
    event: str,
    *,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    request_id = request_id_context.get()
    if request_id is not None:
        payload["request_id"] = request_id
    logger.log(
        level,
        json.dumps(payload, separators=(",", ":"), default=str),
        exc_info=exc_info,
    )
