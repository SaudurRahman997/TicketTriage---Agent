"""Sandbox tools for the ticket-triage agent. Nothing here touches real systems."""
import copy
import json
from typing import Any, Callable, Literal, Optional
from pydantic import BaseModel, Field
from .config import BASE_DIR

CATEGORIES = Literal["billing", "technical", "account", "shipping", "feature_request", "other"]
PRIORITIES = Literal["low", "medium", "high", "urgent"]
TEAMS = Literal["billing_team", "tech_support", "account_security", "logistics", "product"]

# Consequential actions the agent must never execute itself (autonomy boundary).
RESTRICTED_ACTIONS = {"send_email", "issue_refund", "refund", "delete_ticket", "close_ticket",
                      "reset_password", "modify_account", "delete_account"}


class ToolFailure(Exception):
    """Tool raised, or returned output violating the tool-output contract."""


class NoArgs(BaseModel):
    pass


class GetTicketArgs(BaseModel):
    ticket_id: str = Field(min_length=1, max_length=40)


class SearchKbArgs(BaseModel):
    query: str = Field(min_length=2, max_length=200)


class ClassifyArgs(BaseModel):
    ticket_id: str
    category: CATEGORIES
    priority: PRIORITIES


class DraftArgs(BaseModel):
    ticket_id: str
    body: str = Field(min_length=10, max_length=1200)


class EscalateArgs(BaseModel):
    ticket_id: str
    team: TEAMS
    reason: str = Field(min_length=5, max_length=300)


# name -> (args model, description, needs the ticket to have been read first)
REGISTRY: dict[str, tuple[type[BaseModel], str, bool]] = {
    "list_open_tickets": (NoArgs, "List ids+subjects of open tickets in the sandbox queue.", False),
    "get_ticket": (GetTicketArgs, "Read one ticket (subject, body, status).", False),
    "search_kb": (SearchKbArgs, "Search internal policy/knowledge-base snippets by keywords.", False),
    "classify_ticket": (ClassifyArgs, "Save category + priority labels on a ticket (sandbox write).", True),
    "draft_reply": (DraftArgs, "Save a DRAFT reply for human review. Never sent to the customer.", True),
    "escalate_ticket": (EscalateArgs, "Route ticket to an internal team queue (sandbox write).", True),
}


def describe_tools() -> str:
    lines = []
    for name, (model, desc, _) in REGISTRY.items():
        fields = ", ".join(f"{k}: {json.dumps(v.get('enum') or v.get('type'))}" for k, v in model.model_json_schema().get("properties", {}).items())
        lines.append(f"- {name}({fields}) -- {desc}")
    return "\n".join(lines)


def norm_id(x: Any) -> str:
    return str(x).strip().upper()


class ToolBox:
    """Per-run sandbox state. Fault injection happens at this boundary."""

    def __init__(self, data_path=None, injector=None):
        data = json.loads((data_path or BASE_DIR / "data" / "sample_data.json").read_text(encoding="utf-8"))
        self.tickets = {norm_id(t["id"]): copy.deepcopy(t) for t in data["tickets"]}
        self.kb = data["kb"]
        self.labels: dict[str, dict] = {}
        self.drafts: dict[str, str] = {}
        self.escalations: list[dict] = []
        self.injector = injector
        self._impl: dict[str, Callable[..., dict]] = {
            "list_open_tickets": self._list, "get_ticket": self._get, "search_kb": self._kb,
            "classify_ticket": self._classify, "draft_reply": self._draft, "escalate_ticket": self._escalate}

    # --- implementations: domain problems return {"ok": False}; only infrastructure faults raise ---
    def _list(self) -> dict:
        return {"ok": True, "tickets": [{"id": t["id"], "subject": t["subject"]} for t in self.tickets.values() if t["status"] == "open"]}

    def _get(self, ticket_id: str) -> dict:
        t = self.tickets.get(norm_id(ticket_id))
        return {"ok": True, "ticket": t} if t else {"ok": False, "error": f"ticket '{ticket_id}' not found"}

    def _kb(self, query: str) -> dict:
        words = {w for w in query.lower().split() if len(w) > 2}
        scored = sorted(((sum(w in (a["title"] + " " + a["text"]).lower() for w in words), a) for a in self.kb), key=lambda x: -x[0])
        return {"ok": True, "matches": [a for s, a in scored[:2] if s > 0]}

    def _need(self, ticket_id: str):
        return None if norm_id(ticket_id) in self.tickets else {"ok": False, "error": f"ticket '{ticket_id}' not found"}

    def _classify(self, ticket_id, category, priority) -> dict:
        err = self._need(ticket_id)
        if err:
            return err
        self.labels[norm_id(ticket_id)] = {"category": category, "priority": priority}
        return {"ok": True, "saved": self.labels[norm_id(ticket_id)]}

    def _draft(self, ticket_id, body) -> dict:
        err = self._need(ticket_id)
        if err:
            return err
        self.drafts[norm_id(ticket_id)] = body
        return {"ok": True, "status": "draft_saved_not_sent"}

    def _escalate(self, ticket_id, team, reason) -> dict:
        err = self._need(ticket_id)
        if err:
            return err
        self.escalations.append({"ticket_id": norm_id(ticket_id), "team": team, "reason": reason})
        return {"ok": True, "status": "queued", "team": team}

    def run(self, name: str, args: dict) -> dict:
        if self.injector:
            self.injector.before_tool()
        try:
            result = self._impl[name](**args)
        except ToolFailure:
            raise
        except Exception as e:  # any tool exception becomes a typed ToolFailure
            raise ToolFailure(f"{name} raised {type(e).__name__}") from None
        if self.injector:
            result = self.injector.after_tool(result)
        if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
            raise ToolFailure(f"{name} returned malformed output")
        return result
