"""Observe SDK tools/call before validation; never alter a business outcome."""

import asyncio
import json
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4
import anyio
from MCP_server.identity import request_identity
from MCP_server.services.usage_service import insert_event

logger = logging.getLogger(__name__)
LOG_TIMEOUT_SECONDS = 1.1


def result_error(result):
    data = result.model_dump(by_alias=True) if hasattr(result, "model_dump") else result
    if not isinstance(data, dict) or not data.get(
        "isError", data.get("is_error", False)
    ):
        return False, None
    payload = data.get("structuredContent", data.get("structured_content"))
    if payload is None:
        for block in data.get("content", []):
            try:
                payload = json.loads(block.get("text", ""))
            except (ValueError, TypeError):
                continue
            if isinstance(payload, dict):
                break
    code = payload.get("code") if isinstance(payload, dict) else None
    return True, code if isinstance(code, (int, str)) else None


def usage_middleware(collection_provider):
    async def observe(ctx, call_next):
        if ctx.method != "tools/call":
            return await call_next(ctx)
        params = ctx.params if isinstance(ctx.params, Mapping) else {}
        name = params.get("name")
        event = {
            "_id": str(uuid4()),
            "tool_name": name[:200] if isinstance(name, str) else "<invalid>",
            **request_identity(ctx.request),
            "started_at": datetime.now(timezone.utc),
            "outcome": "error",
            "error_code": None,
        }
        started = perf_counter()
        try:
            result = await call_next(ctx)
            failed, code = result_error(result)
            event.update(outcome="error" if failed else "success", error_code=code)
            return result
        except asyncio.CancelledError:
            event["outcome"] = "cancelled"
            raise
        except Exception as error:
            code = getattr(getattr(error, "error", None), "code", None)
            event["error_code"] = code if isinstance(code, (str, int)) else None
            raise
        finally:
            event.update(
                completed_at=datetime.now(timezone.utc),
                duration_ms=round((perf_counter() - started) * 1000, 3),
            )
            try:
                # Shield cancellation long enough to make one bounded insert.
                # PyMongo's own timeout also bounds the worker thread's lifetime.
                with anyio.CancelScope(shield=True):
                    await asyncio.wait_for(
                        asyncio.to_thread(insert_event, collection_provider(), event),
                        timeout=LOG_TIMEOUT_SECONDS,
                    )
            except Exception:
                logger.warning(
                    "Tool usage event could not be stored; tool outcome preserved."
                )

    return observe
