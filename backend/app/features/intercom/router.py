import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.features.intercom.intercom import process_ticket_flow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intercom")


async def _ndjson_stream(
    api_name: str,
    ticket: str,
    flow_fn: Callable[[Callable[[dict], Awaitable[None]]], Awaitable[dict]],
) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def emit(event: dict) -> None:
        await queue.put(event)

    yield json.dumps({"event": "started", "api": api_name, "ticket": ticket}) + "\n"

    async def run_flow() -> None:
        try:
            result = await flow_fn(emit)
            await queue.put({"event": "finished", "status": result.get("status", ""), "result": result})
        except Exception as exc:  # noqa: BLE001
            logger.exception("%s unhandled error: %s", api_name, exc)
            await queue.put({"event": "error", "message": str(exc)})
        finally:
            await queue.put(None)

    task = asyncio.create_task(run_flow())

    while True:
        item = await queue.get()
        if item is None:
            break
        yield json.dumps(item) + "\n"

    await task


@router.post("/process_ticket")
async def process_ticket(request: dict) -> dict:
    ticket = request.get("ticket")
    if not ticket:
        return {"status": "error", "message": "ticket is required"}
    result = await process_ticket_flow(str(ticket))
    return result


@router.post("/process_ticket/stream")
async def process_ticket_stream(request: dict):
    ticket = request.get("ticket")
    if not ticket:
        async def gen_err() -> AsyncGenerator[str, None]:
            yield json.dumps({"event": "error", "message": "ticket missing"}) + "\n"

        return StreamingResponse(gen_err(), media_type="application/x-ndjson")

    async def generate() -> AsyncGenerator[str, None]:
        async for line in _ndjson_stream("intercom_process_ticket", str(ticket), lambda emit_fn: process_ticket_flow(str(ticket), emit=emit_fn)):
            yield line

    return StreamingResponse(generate(), media_type="application/x-ndjson")
