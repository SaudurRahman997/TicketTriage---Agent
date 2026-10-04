"""Bounded agent loop. The model proposes; THIS module validates, executes and decides when to stop."""
import json
import re
import secrets
import time
from typing import Optional
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import ValidationError

from .arena import FaultInjector, ToolTimeout, log_event
from .config import PRICES, Settings
from .llm import BudgetError, LLMError
from .models import AgentDecision, ArenaResponse
from .prompts import SYSTEM_PROMPT, build_turn_prompt
from .scope import is_in_ticket_scope, out_of_scope_message
from .tools import REGISTRY, RESTRICTED_ACTIONS, ToolBox, ToolFailure, describe_tools, norm_id

TERMINAL = {"needs_clarification": "clarification_requested", "completed": "goal_completed",
            "blocked": "blocked_by_policy", "approval_required": "approval_required", "failed": "model_reported_failure"}


class ContractError(Exception):
    pass


class RunState:
    def __init__(self, goal: str):
        self.goal, self.steps, self.repairs, self.tool_failures = goal, 0, 0, 0
        self.seen: set[str] = set()
        self.done: list[str] = []
        self.observations: list[str] = []
        self.feedback: list[str] = []
        self.calls: list[dict] = []
        self.errors: list = []
        self.events: list[dict] = []
        self.last_call: Optional[str] = None
        self.tokens_in: Optional[int] = 0
        self.tokens_out: Optional[int] = 0

    def event(self, kind: str, **kv) -> None:
        self.events.append({"step": self.steps, "type": kind, **kv})

    def add_usage(self, tin, tout) -> None:
        self.tokens_in = None if (tin is None or self.tokens_in is None) else self.tokens_in + tin
        self.tokens_out = None if (tout is None or self.tokens_out is None) else self.tokens_out + tout


def parse_decision(text: str) -> AgentDecision:
    """Layer 1+2: extract JSON, then schema-validate."""
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    i = s.find("{")
    if i < 0:
        raise ContractError("no JSON object found in output")
    try:
        obj, _ = json.JSONDecoder().raw_decode(s[i:])
    except json.JSONDecodeError as e:
        raise ContractError(f"invalid JSON ({e.msg})")
    try:
        return AgentDecision.model_validate(obj)
    except ValidationError as e:
        raise ContractError("schema: " + "; ".join(f"{'.'.join(map(str, x['loc'])) or 'root'}: {x['msg']}" for x in e.errors()[:4]))


def enforce_autonomy(d: AgentDecision) -> AgentDecision:
    """System-owned boundary: restricted actions are never executed, whatever the model says."""
    if d.action and d.action.strip().lower() in RESTRICTED_ACTIONS:
        return AgentDecision(status="approval_required", user_message=(
            f"'{d.action}' is a consequential action I am not permitted to perform automatically. "
            "It needs human approval. I can instead save a draft reply or escalate the ticket to the right team."))
    return d


def semantic_validate(d: AgentDecision, state: RunState) -> list[str]:
    """Layer 3: do the values make sense together and in the current state?"""
    if d.status != "continue":
        return [] if (d.user_message or "").strip() else [f"status '{d.status}' requires a non-empty user_message"]
    if not d.action:
        return ["status 'continue' requires an action"]
    if d.action not in REGISTRY:
        return [f"unknown action '{d.action}'; valid actions: {', '.join(REGISTRY)}"]
    model, _, needs_read = REGISTRY[d.action]
    try:
        args = model.model_validate(d.arguments)
    except ValidationError as e:
        return [f"bad arguments for {d.action}: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:4])]
    tid = getattr(args, "ticket_id", None)
    if needs_read and norm_id(tid) not in state.seen:
        return [f"{d.action} not permitted yet: call get_ticket for '{tid}' first"]
    return []


def _history_messages(history: list[BaseMessage]) -> list[tuple[str, str]]:
    return [("assistant" if isinstance(m, AIMessage) else "user", str(m.content)) for m in history]


def _cost(model_name: str, tin, tout):
    price = PRICES.get(model_name)
    if price is None or tin is None or tout is None:
        return None
    return round((tin * price[0] + tout * price[1]) / 1_000_000, 6)


def run_agent(*, task: str, external_context, max_steps: int, fault: str, history: list[BaseMessage],
              llm, settings: Settings, request_id: Optional[str] = None, model_label: str = "",
              data_path=None) -> ArenaResponse:
    t0 = time.monotonic()
    deadline = t0 + settings.run_timeout_seconds
    max_steps = max(1, min(max_steps, settings.hard_max_steps))
    state = RunState(task)
    inj = FaultInjector(fault)
    tools = ToolBox(data_path, inj)
    nonce = secrets.token_hex(6)

    def finish(status, stop_reason, message="") -> ArenaResponse:
        tin, tout = state.tokens_in, state.tokens_out
        if state.steps == 0:
            tin = tout = None
        r = ArenaResponse(
            request_id=request_id, status=status, final_response=message, steps=state.steps, stop_reason=stop_reason,
            tool_calls=state.calls, errors=state.errors, events=state.events,
            metrics={"model": model_label or None, "latency_ms": int((time.monotonic() - t0) * 1000),
                     "input_tokens": tin, "output_tokens": tout,
                     "estimated_cost_usd": _cost(model_label.split(":", 1)[-1], tin, tout),
                     "max_steps": max_steps, "repair_attempts": state.repairs, "injected_fault": fault if inj.fired else None})
        log_event(request_id=request_id, status=status, stop_reason=stop_reason, steps=state.steps, tools=[c["name"] for c in state.calls])
        return r

    if not task.strip():
        return finish("needs_clarification", "empty_task", "What would you like me to do? Please describe the ticket task (e.g. which ticket to triage).")
    if len(task) > settings.max_task_chars:
        state.errors.append("task_too_large")
        return finish("budget_exceeded", "input_too_large", "The request is too large for one bounded run. Please split it into smaller tasks.")

    # Enforce the narrow operational scope before any model call or tool action.
    # External context is deliberately excluded: notes cannot redefine the user's goal.
    if not is_in_ticket_scope(task, history):
        return finish("needs_clarification", "out_of_scope", out_of_scope_message(task))

    # For a ticket operation that needs an identifier, clarify before any tool call.
    import re
    ticket_id_found = bool(re.search(r"\bT-\d+\b", task.upper()))
    ticket_operation = bool(re.search(
        r"\b(?:ticket|tickets|support case|customer issue|triag\w*|classif\w*|"
        r"escalat\w*|draft\w*|clos\w*|delet\w*|refund\w*)\b",
        task,
        re.IGNORECASE,
    ))
    if ticket_operation and not ticket_id_found and not re.search(r"\bA\d{3,}\b", task, re.IGNORECASE):
        return finish("needs_clarification", "clarification_requested", "Which ticket id should I act on?")

    ext_text = "\n".join(f"[{i.source}] {i.content}" for i in external_context)[:settings.max_external_chars]
    tool_text = describe_tools()
    hist = _history_messages(history)

    while state.steps < max_steps:
        if time.monotonic() > deadline:
            state.errors.append("run_timeout")
            return finish("budget_exceeded", "run_timeout", "Stopped: the time budget for this run was reached.")
        prompt = build_turn_prompt(goal=task, step=state.steps + 1, max_steps=max_steps, seen=state.seen, done=state.done,
                                   feedback=state.feedback, tools=tool_text, external=ext_text,
                                   observations="\n".join(state.observations[-6:]), nonce=nonce)
        state.steps += 1
        try:
            res = llm.generate(SYSTEM_PROMPT, hist + [("user", prompt)], settings.max_output_tokens)
        except BudgetError as e:
            state.errors.append(str(e))
            return finish("budget_exceeded", "spend_cap_reached", "The service's model-call budget is exhausted. Please try again later.")
        except LLMError as e:
            state.errors.append(str(e))
            state.event("model_error", detail=str(e))
            return finish("failed", "model_error", "The model provider could not be reached. No action was taken.")
        state.add_usage(res.input_tokens, res.output_tokens)
        text = inj.after_model(res.text)

        # ---- contract gate: parse -> schema -> autonomy -> semantic ----
        problems: list[str] = []
        decision = None
        try:
            decision = enforce_autonomy(parse_decision(text))
            problems = semantic_validate(decision, state)
        except ContractError as e:
            problems = [str(e)]
        state.event("decision", valid=not problems, status=getattr(decision, "status", None),
                    action=getattr(decision, "action", None), problems=problems)
        if problems:
            state.repairs += 1
            state.feedback = problems
            state.errors.append({"type": "contract_violation", "step": state.steps, "problems": problems})
            if state.repairs > settings.max_tool_retries:
                return finish("contract_error", "invalid_model_output_after_repairs",
                              "I could not produce a valid action after several attempts, so I stopped without acting.")
            continue
        state.feedback = []

        if decision.status != "continue":
            return finish(decision.status, TERMINAL[decision.status], decision.user_message or "")

        # ---- loop guard ----
        sig = json.dumps([decision.action, decision.arguments], sort_keys=True)
        if sig == state.last_call:
            state.errors.append("repeated_identical_action")
            return finish("budget_exceeded", "loop_detected", "Stopped: the same action was repeated without progress.")
        state.last_call = sig

        # ---- act with bounded tool retries ----
        attempts, ok, result, err = 0, False, None, None
        while attempts <= settings.max_tool_retries and time.monotonic() < deadline:
            attempts += 1
            try:
                result, ok = tools.run(decision.action, decision.arguments), True
                break
            except (ToolTimeout, ToolFailure) as e:
                err = f"{type(e).__name__}: {e}"
                state.event("tool_error", tool=decision.action, attempt=attempts, detail=err)
        call = {"step": state.steps, "name": decision.action, "arguments": decision.arguments, "ok": ok, "attempts": attempts}
        state.calls.append(call)          # always logged, including the call that ends the run
        if ok:
            call["result"] = result
            if decision.action == "get_ticket" and result.get("ok"):
                state.seen.add(norm_id(decision.arguments.get("ticket_id")))
            if decision.action in ("classify_ticket", "draft_reply", "escalate_ticket") and result.get("ok"):
                state.done.append(f"{decision.action}({decision.arguments.get('ticket_id')})")
            state.observations.append(f"step {state.steps} {decision.action} -> " + json.dumps(result)[:1500])
            state.tool_failures = 0
        else:
            call["error"] = err
            state.tool_failures += 1
            state.errors.append({"type": "tool_failure", "tool": decision.action, "detail": err})
            state.observations.append(f"step {state.steps} {decision.action} FAILED after {attempts} attempts: {err}. Choose a different action or stop.")
            if state.tool_failures >= 2:
                return finish("tool_error", "tool_failed_after_retries", f"A tool failed repeatedly ({decision.action}); I stopped without completing the task.")

    summary = f"Stopped: step budget of {max_steps} reached before the goal was completed. Done so far: {', '.join(state.done) or 'nothing consequential'}."
    state.errors.append("max_steps_reached")
    return finish("budget_exceeded", "max_steps_reached", summary)
