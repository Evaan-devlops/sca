import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Raise from services to return a structured HTTP error. E.g.: raise AppError(404, "msg")"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Flatten Pydantic 422 errors into one readable string instead of a nested array."""
    messages = []
    for error in exc.errors():
        loc = " → ".join(str(p) for p in error["loc"] if p != "body")
        msg = error["msg"]
        messages.append(f"{loc}: {msg}" if loc else msg)
    return JSONResponse(status_code=422, content={"detail": " | ".join(messages)})


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    from app.core.config import settings

    detail = (
        f"{type(exc).__name__}: {exc}"
        if settings.debug
        else "An unexpected error occurred."
    )
    return JSONResponse(status_code=500, content={"detail": detail})
