import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import (
    AppError,
    app_error_handler,
    global_exception_handler,
    validation_error_handler,
)
from app.features.onetrust.browser import browser_manager
from app.features.onetrust.router import router as onetrust_router
from app.features.intercom.router import router as intercom_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("OneTrust Automation API starting (debug=%s).", settings.debug)
    yield
    await browser_manager.close()


app = FastAPI(
    title="OneTrust Automation API",
    description="Automates authorized OneTrust sandbox workflows via Playwright",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, global_exception_handler)

app.include_router(onetrust_router)
app.include_router(intercom_router)


class HealthResponse(BaseModel):
    status: str
    browser_ready: bool


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", browser_ready=browser_manager.is_ready)
