"""Routes, model selection, session handoff, rate/concurrency/spend controls."""
import asyncio
import json
import time
import uuid
from collections import defaultdict, deque
from datetime import date
from fastapi import APIRouter, HTTPException, Request

from .agent import run_agent
from .arena import bound_response, run_with_timeout
from .config import BASE_DIR, default_model_id, model_options, settings
from .llm import BudgetError, LLMError, build_client
from .memory import SessionStore
from .models import ArenaRequest, ArenaResponse, ChatRequest, ChatResponse, ResetRequest

router = APIRouter()
sessions = SessionStore(settings.history_turns, settings.history_chars, settings.max_sessions)
_slots = asyncio.Semaphore(settings.max_concurrent_runs)
_hits: dict[str, deque] = defaultdict(deque)
_daily = {"day": date.today(), "calls": 0}
client_factory = build_client      # tests replace this with a scripted client


class CappedClient:
    """Wraps a provider client with a global daily model-call cap (spend control)."""

    def __init__(self, inner):
        self.inner = inner

    def generate(self, system, messages, max_tokens):
        if _daily["day"] != date.today():
            _daily.update(day=date.today(), calls=0)
        if _daily["calls"] >= settings.max_daily_model_calls:
            raise BudgetError("daily model-call cap reached")
        _daily["calls"] += 1
        return self.inner.generate(system, messages, max_tokens)


def _rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    q, now = _hits[ip], time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.rate_limit_per_minute:
        raise HTTPException(429, "rate limit exceeded; try again in a minute")
    q.append(now)


def _resolve_model(model_id):
    mid = model_id or default_model_id()
    if model_id and model_id not in {o["id"] for o in model_options()}:
        raise HTTPException(400, f"unknown model '{model_id}'; choose one of {[o['id'] for o in model_options()]}")
    return mid


def _execute(req_task, ext, max_steps, fault, history, mid, request_id) -> ArenaResponse:
    try:
        if not mid:
            raise LLMError("no model is configured on this deployment")
        provider, name = mid.split(":", 1)
        llm = CappedClient(client_factory(provider, name))
    except LLMError as e:
        return ArenaResponse(request_id=request_id, status="failed", stop_reason="model_not_configured",
                             final_response="No model is configured on the server, so no agent run was performed.", errors=[str(e)])
    return run_agent(task=req_task, external_context=ext, max_steps=max_steps, fault=fault, history=history,
                     llm=llm, settings=settings, request_id=request_id, model_label=mid)


@router.get("/health")
def health():
    return {"status": "ok", "model_configured": default_model_id() is not None}


@router.get("/arena/manifest")
def manifest():
    return json.loads((BASE_DIR / "arena_manifest.json").read_text(encoding="utf-8"))


@router.get("/models")
def models():
    return {"default": default_model_id(), "models": model_options()}


@router.post("/arena/run", response_model=ArenaResponse)
async def arena_run(body: ArenaRequest, request: Request):
    _rate_limit(request)
    rid = body.request_id or str(uuid.uuid4())
    cfg = body.arena_config
    async with _slots:       # independent runs: no session history is passed
        resp = await run_with_timeout(
            lambda: _execute(body.task, body.external_context, cfg.max_steps, cfg.fault.type, [], default_model_id(), rid),
            settings.run_timeout_seconds, rid)
    return bound_response(resp, settings.max_response_bytes)


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    _rate_limit(request)
    mid = _resolve_model(body.model)
    sid = body.session_id or str(uuid.uuid4())
    history = sessions.get(sid)
    async with _slots:
        resp = await run_with_timeout(
            lambda: _execute(body.message, body.external_context, settings.max_steps, "none", history, mid, None),
            settings.run_timeout_seconds)
    if resp.final_response and resp.stop_reason not in ("model_not_configured", "run_timeout"):
        sessions.add_turn(sid, body.message, resp.final_response)
    resp = bound_response(resp, settings.max_response_bytes)
    return ChatResponse(**resp.model_dump(), session_id=sid, model=mid)


@router.post("/chat/reset")
def reset(body: ResetRequest):
    sessions.reset(body.session_id)
    return {"status": "reset", "session_id": body.session_id}
