"""Public contracts: Arena request/response, model decision schema, chat models."""
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator

FAULT_TYPES = ("none", "tool_timeout", "malformed_tool_output", "invalid_agent_decision")
DecisionStatus = Literal["continue", "needs_clarification", "completed", "blocked", "approval_required", "failed"]
RunStatus = Literal["completed", "needs_clarification", "blocked", "approval_required",
                    "tool_error", "contract_error", "budget_exceeded", "failed"]


class AgentDecision(BaseModel):
    """The ONLY thing the model may emit. Validated before anything executes."""
    status: DecisionStatus
    action: Optional[str] = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    user_message: Optional[str] = None


class ExternalItem(BaseModel):
    source: str = "note"
    content: str = ""
    trust: str = "untrusted"   # informational only: the agent ALWAYS treats external text as untrusted data


class Fault(BaseModel):
    type: Literal["none", "tool_timeout", "malformed_tool_output", "invalid_agent_decision"] = "none"


class ArenaConfig(BaseModel):
    max_steps: int = Field(6, ge=1)
    fault: Fault = Field(default_factory=Fault)

    @field_validator("fault", mode="before")
    @classmethod
    def _fault_str(cls, v):
        return {"type": v} if isinstance(v, str) else v


class ArenaRequest(BaseModel):
    request_id: Optional[str] = None   # correlation only, never a memory key
    task: str = ""
    external_context: list[ExternalItem] = Field(default_factory=list)
    arena_config: ArenaConfig = Field(default_factory=ArenaConfig)


class ArenaResponse(BaseModel):
    request_id: Optional[str] = None
    status: RunStatus
    final_response: str = ""
    steps: int = 0
    stop_reason: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[Any] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(min_length=1, max_length=4000)
    model: Optional[str] = None
    external_context: list[ExternalItem] = Field(default_factory=list)


class ChatResponse(ArenaResponse):
    session_id: str = ""
    model: Optional[str] = None


class ResetRequest(BaseModel):
    session_id: str
