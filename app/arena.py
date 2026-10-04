"""Arena helpers: fault injection at model/tool boundary, timeout wrapper, response bound, safe logging."""
import asyncio
import json
import logging
import re
from .models import ArenaResponse

logger = logging.getLogger("arena")
_SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|AIza[0-9A-Za-z_\-]{20,}|(?i:api[_-]?key)\s*[=:]\s*\S+)")


def redact(text) -> str:
    return _SECRET.sub("[REDACTED]", str(text))


def log_event(**kv) -> None:
    logger.info(redact(json.dumps(kv, default=str)))


class ToolTimeout(Exception):
    pass


class FaultInjector:
    """Fires the configured fault ONCE, on the first matching operation of the run."""

    def __init__(self, kind: str = "none"):
        self.kind, self.fired = kind, False

    def _fire(self, kind: str) -> bool:
        if self.kind == kind and not self.fired:
            self.fired = True
            return True
        return False

    def before_tool(self) -> None:
        if self._fire("tool_timeout"):
            raise ToolTimeout("injected tool timeout")

    def after_tool(self, result):
        return "<<corrupted tool payload>>" if self._fire("malformed_tool_output") else result

    def after_model(self, text: str) -> str:
        if self._fire("invalid_agent_decision"):
            return '{"status": "teleport", "action": 42, "arguments": "nope"}'
        return text


def bound_response(resp: ArenaResponse, max_bytes: int) -> ArenaResponse:
    size = lambda: len(resp.model_dump_json().encode())
    if size() <= max_bytes:
        return resp
    resp.events = resp.events[:20]
    if size() > max_bytes:
        resp.tool_calls = [{**c, "result": str(c.get("result", ""))[:200]} for c in resp.tool_calls]
    if size() > max_bytes:
        resp.final_response = resp.final_response[:2000] + " ...[truncated]"
    resp.errors.append("response_truncated_to_fit_limit")
    return resp


async def run_with_timeout(fn, timeout: float, request_id=None) -> ArenaResponse:
    try:
        return await asyncio.wait_for(asyncio.to_thread(fn), timeout + 5)
    except asyncio.TimeoutError:
        return ArenaResponse(request_id=request_id, status="budget_exceeded", stop_reason="run_timeout",
                             final_response="The run exceeded its time limit and was stopped.",
                             errors=["run_timeout"])
