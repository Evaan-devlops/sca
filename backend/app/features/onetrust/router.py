import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.features.onetrust.auth import login_onetrust
from app.features.onetrust.filter_code import filter_code_flow
from app.features.onetrust.mapper import DEFAULT_EXPERIENCE_KIT, get_experience_kit_for_url
from app.features.onetrust.schemas import (
    AddAppRequest,
    AddAppResponse,
    FilterCodeRequest,
    FilterCodeResponse,
    LoginResponse,
    MapperDefaultResponse,
    MapperResolveRequest,
    MapperResolveResponse,
)
from app.features.onetrust.websites import add_app_flow

logger = logging.getLogger(__name__)
router = APIRouter()


async def _ndjson_stream(
    api_name: str,
    input_url: str,
    flow_fn: Callable[[Callable[[dict], Awaitable[None]]], Awaitable[dict]],
) -> AsyncGenerator[str, None]:
    """Async generator that runs a flow function and yields NDJSON lines."""
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def emit(event: dict) -> None:
        await queue.put(event)

    yield json.dumps({"event": "started", "api": api_name, "input_url": input_url}) + "\n"

    async def run_flow() -> None:
        try:
            result = await flow_fn(emit)
            await queue.put({
                "event": "finished",
                "status": result.get("status", ""),
                "result": result,
            })
        except Exception as exc:  # noqa: BLE001
            logger.exception("[%s] unhandled error in streaming flow: %s", api_name, exc)
            await queue.put({"event": "error", "message": str(exc)})
        finally:
            await queue.put(None)  # sentinel

    task = asyncio.create_task(run_flow())

    while True:
        item = await queue.get()
        if item is None:
            break
        yield json.dumps(item) + "\n"

    await task  # ensure task is fully awaited


@router.post("/auth/login", response_model=LoginResponse)
async def auth_login() -> LoginResponse:
    result = await login_onetrust()
    return LoginResponse(**result)


@router.post("/add_app", response_model=AddAppResponse)
async def add_app(request: AddAppRequest) -> AddAppResponse:
    result = await add_app_flow(url=request.url)
    return AddAppResponse(**result)


@router.post("/add_app/stream")
async def add_app_stream(request: AddAppRequest) -> StreamingResponse:
    """Stream step-by-step NDJSON events for /add_app workflow."""
    captured_url = request.url

    async def generate() -> AsyncGenerator[str, None]:
        async for line in _ndjson_stream(
            "add_app",
            captured_url,
            lambda emit_fn: add_app_flow(captured_url, emit=emit_fn),
        ):
            yield line

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.post("/filter_code", response_model=FilterCodeResponse)
async def filter_code(request: FilterCodeRequest) -> FilterCodeResponse:
    result = await filter_code_flow(url=request.url)
    return FilterCodeResponse(**result)


@router.post("/filter_code/stream")
async def filter_code_stream(request: FilterCodeRequest) -> StreamingResponse:
    """Stream step-by-step NDJSON events for /filter_code workflow."""
    captured_url = request.url

    async def generate() -> AsyncGenerator[str, None]:
        async for line in _ndjson_stream(
            "filter_code",
            captured_url,
            lambda emit_fn: filter_code_flow(captured_url, emit=emit_fn),
        ):
            yield line

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.get("/mapper/default", response_model=MapperDefaultResponse)
async def mapper_default() -> MapperDefaultResponse:
    return MapperDefaultResponse(
        default_experience_kit=DEFAULT_EXPERIENCE_KIT,
        mode="default_for_all_urls",
    )


@router.post("/mapper/resolve", response_model=MapperResolveResponse)
async def mapper_resolve(request: MapperResolveRequest) -> MapperResolveResponse:
    return MapperResolveResponse(
        url=request.url,
        experience_kit=get_experience_kit_for_url(request.url),
        mode="default_for_all_urls",
    )
