# TicketTriage Sentinel — Agent Arena (Assignment 1)

A bounded single-agent service for **Support-Ticket Triage** (domain #11). The agent reads sandbox tickets,
classifies category/priority, consults policy snippets, drafts replies and escalates to internal queues.
Everything runs on mock data in `data/sample_data.json`; nothing is ever sent, refunded or deleted.

## 1. Problem and completion condition
Given a triage request (+ optional untrusted notes), the run is **completed** when every ticket the user named has been
read and the requested labels/drafts/escalations were saved in the sandbox, and the final message reports only what
tool observations confirm. Otherwise it ends in a typed stop (`needs_clarification`, `blocked`, `approval_required`,
`tool_error`, `contract_error`, `budget_exceeded`, `failed`).

## 2. Agent Design Canvas
| # | Element | This agent |
|---|---|---|
| 1 | Operational goal | Triage named support tickets inside a sandbox queue and report results. |
| 2 | Completion condition | Requested ticket(s) read, requested sandbox writes confirmed by tool results, summary grounded in observations. |
| 3 | System boundary | FastAPI service + sandbox `ToolBox` over JSON data. No network tools, no real email/refund/delete. |
| 4 | Observations | User goal, bounded chat history, optional external notes (untrusted), tool results (untrusted data), run state. |
| 5 | Actions / tools | `list_open_tickets`, `get_ticket`, `search_kb`, `classify_ticket`, `draft_reply`, `escalate_ticket`. |
| 6 | State | `RunState`: goal, step, repair count, tool-failure count, tickets read, actions done, observations, events, tokens. |
| 7 | Autonomy boundary | Auto: read, search, classify, draft (unsent), escalate to sandbox queue. Never: send email, refund, delete/close tickets, reset passwords, change accounts → `approval_required`. |
| 8 | Primary risks | Ambiguous ids, prompt injection in ticket bodies/notes, malformed model JSON, tool timeouts, runaway loops, cost. |
| 9 | Evaluation criteria | Arena categories A–F (`evaluation/public_cases.json`), offline scripted tests, model comparison table. |

## 3. Architecture
```
client ──► FastAPI (api.py) ──► rate limit / semaphore / daily call cap
                                   │
                                   ▼
        ┌────────────────────── agent.py loop (max_steps, timeout) ───────────────────────┐
        │ build prompt (prompts.py) ─► LLM (llm.py) ─► [fault: invalid_agent_decision]     │
        │      ▲                                         │                                  │
        │      │                          parse JSON → Pydantic schema → autonomy gate →    │
        │      │                          semantic validation ──invalid──► repair (≤2) /    │
        │ observation ◄── ToolBox ◄─ retries (≤2) ◄─ [fault: tool_timeout /                 │
        │ (fenced data)   (tools.py)     │            malformed_tool_output]                │
        └────────── terminal status: completed | needs_clarification | blocked | … ─────────┘
```
```
app/  main.py api.py agent.py models.py prompts.py memory.py tools.py arena.py llm.py config.py static/{index.html,app.js,style.css}
data/sample_data.json   evaluation/{public_cases.json,run_public_tests.py,model_comparison.py}
tests/test_agent.py     arena_manifest.json  render.yaml  Dockerfile  run.py  requirements.txt  .env.example
```
The system, not the model, owns validation, limits and stopping. `llm.py` is a thin httpx client (Anthropic, Gemini).

## 4. Prompt & context design
Layers are kept separate: **SYSTEM** (static role, contract, trust rules, autonomy) · **history** (real prior turns as
role messages, from `memory.py`) · **USER goal + RUN STATE + tools** (trusted, rendered per step from `prompts.TURN_TEMPLATE`) ·
**external context** and **tool observations** (each inside `<…boundary="random-nonce">` fences and labelled data).
External `trust` labels are ignored: all external text is untrusted. There is no keyword filter for injection;
protection is the instruction hierarchy plus the system-enforced autonomy gate (a model that "obeys" an injected
refund request still cannot execute it).

## 5. Memory policy
`SessionStore`: LangChain `HumanMessage/AIMessage`, last **6 turns**, **24,000-char** ceiling (oldest pairs dropped),
**100 sessions** (LRU). In-memory, **one worker**: history is lost on restart/sleep; browser reload starts a new session;
**New chat** calls `/chat/reset`. `/arena/run` is stateless (`request_id` is correlation only).

## 6. Structured output, validation, recovery
`AgentDecision {status, action, arguments, user_message}` (Pydantic; `status ∈ continue|needs_clarification|completed|blocked|approval_required|failed`).
1. **Parse** (JSON extraction) → 2. **Schema** (types/enums) → 3. **Autonomy gate** (restricted actions → `approval_required`) →
4. **Semantic**: known action, per-tool argument models (enums, lengths), `get_ticket` before classify/draft/escalate, non-`continue` statuses need `user_message`.
Failure → feedback is added to the next prompt, up to **2 repairs** (each costs a step) → `contract_error`.

## 7. Stopping conditions and limits
| Limit | Value (env) | Stop |
|---|---|---|
| Steps (incl. repairs) | request `max_steps`, capped by `HARD_MAX_STEPS=12` | `budget_exceeded / max_steps_reached` |
| Wall clock | `RUN_TIMEOUT_SECONDS=40` | `budget_exceeded / run_timeout` |
| Tool retries / repairs | `MAX_TOOL_RETRIES=2` | `tool_error` (2 consecutive failed tools) / `contract_error` |
| Repeated identical call | — | `budget_exceeded / loop_detected` |
| Input size | 6000 chars task | `budget_exceeded / input_too_large` |
| Output tokens / call | `MAX_OUTPUT_TOKENS=512` | — |
| History | 6 turns / 24k chars | — |
| Service spend | `MAX_DAILY_MODEL_CALLS`, per-IP rate limit, `MAX_CONCURRENT_RUNS` | `budget_exceeded / spend_cap_reached`, HTTP 429 |
Token usage and `estimated_cost_usd` are reported when the provider returns usage, else `null` (never a fake zero).
Prices in `config.PRICES` are estimates — verify before quoting.

## 8. Fault injection
`arena_config.fault` (string or `{"type": …}`) fires **once, at the first matching operation**: `tool_timeout` (first tool call raises, retried),
`malformed_tool_output` (first tool returns garbage, rejected by the output contract, retried), `invalid_agent_decision` (first model output replaced by an invalid decision, repaired).

## 9. Expected model comparison (hypotheses, not measured results)

The following is an expectation-based comparison of two configured candidates. It is **not experimental evidence**: no pass rate, latency, token-use, or per-case cost is predicted here. The assignment's model-selection experiment still requires running the same representative cases on both models and recording the observed results.

| model | expected strengths | expected trade-offs | context window | published standard API price (USD / 1M tokens) | measurement status |
|---|---|---|---|---|---|
| `gemini:gemini-3.1-flash-lite` | Designed for low-latency, high-volume and lightweight agent tasks; likely the faster option for short ticket requests. | Higher published input/output token rates than GPT-4o mini; actual task reliability and latency must be measured on this agent. | 1M input / 64K output tokens | $0.25 input / $1.50 output | Expected only; not measured |
| `openai:gpt-4o-mini` | Focused small model; lower published token rates and ample context for this bounded workflow. | May have higher latency than Flash-Lite; task success and structured-decision reliability must be measured. | 128K tokens | $0.15 input / $0.60 output | Expected only; not measured |

The agent retains at most **24,000 characters** of chat history and requests at most **512 output tokens per model call**, so either model's published context window is larger than this application's configured history limit. Based on published standard rates, GPT-4o mini is expected to cost less per token, while Gemini Flash-Lite is expected to favor response speed. These are hypotheses, not observed per-run costs or latency. Actual cost comparison also needs complete provider token-usage data. See the providers' [Gemini 3.1 Flash-Lite model details and pricing](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite) and [GPT-4o mini model details](https://developers.openai.com/api/docs/models/gpt-4o-mini).

To perform the required experiment with the same public cases, run `python evaluation/model_comparison.py --models gemini:gemini-3.1-flash-lite,openai:gpt-4o-mini` after configuring both API keys. The script writes `evaluation/model_comparison.md`. Replace this expected comparison with measured results and add a rationale based on observed reliability, latency, context needs, and cost before submission.

## 10. Run locally
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env        # then set MODEL_PROVIDER, MODEL_NAME and ONE API key
.\.venv\Scripts\python.exe run.py  # http://127.0.0.1:8000  (docs at /docs)
```
Tests (free, scripted model): `python -m unittest discover -s tests -v`
Public cases (costs money): `python evaluation/run_public_tests.py --url http://127.0.0.1:8000`

## 11. Deploy (Render)
Private GitHub repo → Render Web Service (Python). Build `pip install -r requirements.txt`; start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`; health check `/health`. Add `ANTHROPIC_API_KEY` or
`GEMINI_API_KEY` as secret env vars, plus `MODEL_PROVIDER` / `MODEL_NAME`. Verify the UI, `/health`, `/arena/manifest` and a POST to `/arena/run` via `/docs`.

## 12. Limitations
Free instances sleep (cold start of ~1 min) and restart, which wipes chat history. Single worker only. Tickets are mock
data and per-run sandbox writes are discarded after each run. Rate limits/caps are per process. Semantic checks cover
structure and state, not whether a classification is *correct*; quality depends on the model chosen.
