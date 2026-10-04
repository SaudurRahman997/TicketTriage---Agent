"""Application-owned scope gate for the support-ticket triage agent.

This is an intent/domain check, not a list of prohibited question phrases. It
only forwards requests that combine a ticket reference or support domain with
an operational ticket intent. Short replies are accepted when they answer an
immediately preceding in-scope clarification question.
"""
import re
from typing import Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


OUT_OF_SCOPE_MESSAGE = (
    "I'm TicketTriage Sentinel, a support-ticket triage agent. I can look up a "
    "ticket, classify its category or priority, draft an unsent reply, search "
    "support policies, or escalate it to a team. Please tell me which ticket "
    "and what you'd like done."
)
_BOOKING_REQUEST = re.compile(
    r"\b(?:book|reserve|purchase|buy|schedule)\w*\b.*\b(?:ticket|flight|seat|event|concert|"
    r"travel|reservation|booking)\b|\b(?:ticket|flight|seat|event|concert|travel|reservation)\b.*"
    r"\b(?:book|reserve|purchase|buy|schedule)\w*\b",
    re.IGNORECASE,
)
_GENERAL_INFORMATION = re.compile(
    r"\b(?:tell\s+me|explain|describe|biograph\w*|histor\w*|geograph\w*|"
    r"definition|what\s+is|who\s+is|how\s+does|information\s+about)\b",
    re.IGNORECASE,
)

_TICKET_ID = re.compile(r"\b(?:T-\d{3,}|A\d{3,})\b", re.IGNORECASE)
_DOMAIN = re.compile(
    r"\b(?:support|ticket|tickets|case|cases|customer|billing|technical|"
    r"account security|logistics|product|queue|help ?desk)\b",
    re.IGNORECASE,
)
_ACTION = re.compile(
    r"\b(?:triag\w*|classif\w*|categor\w*|prioriti[sz]\w*|label\w*|"
    r"escalat\w*|rout\w*|assign\w*|draft\w*|reply|respond\w*|"
    r"look\s+up|lookup|read|inspect\w*|review\w*|search\w*|find|check|"
    r"what|which|who|when|where|"
    r"clos\w*|resolv\w*|refund\w*|delet\w*|cancel\w*|reset\w*|"
    r"summari[sz]\w*|status|details|help)\b",
    re.IGNORECASE,
)


def _has_operational_scope(text: str) -> bool:
    text = text or ""
    if _TICKET_ID.search(text):
        return True
    return bool(_DOMAIN.search(text) and _ACTION.search(text))


def _is_clarification_reply(text: str, history: Sequence[BaseMessage]) -> bool:
    """Allow concise answers to an active ticket question, not topic changes."""
    if len(history) < 2:
        return False
    previous_user, previous_assistant = history[-2:]
    if not isinstance(previous_user, HumanMessage) or not isinstance(previous_assistant, AIMessage):
        return False
    question = str(previous_assistant.content).strip()
    if "?" not in question or not _has_operational_scope(str(previous_user.content)):
        return False
    words = (text or "").split()
    if not words or len(words) > 5:
        return False
    # Don't let a new informational question masquerade as a short answer.
    if re.match(r"^(?:tell|explain|describe|what|why|when|where|who|how)\b", text.strip(), re.IGNORECASE):
        return False
    return True


def is_in_ticket_scope(text: str, history: Sequence[BaseMessage] = ()) -> bool:
    """Return whether the request belongs to ticket operations."""
    return _has_operational_scope(text) or _is_clarification_reply(text, history)


def out_of_scope_message(text: str) -> str:
    """Give a concise redirect suited to the broad kind of unrelated request."""
    if _BOOKING_REQUEST.search(text or ""):
        return (
            "I work with existing sandbox support tickets, not travel or event bookings. "
            "If you meant a support case, share its ticket ID and what you need done."
        )
    if _GENERAL_INFORMATION.search(text or ""):
        return (
            "That sounds like a general-information question, outside my ticket-triage role. "
            "I can look up a support ticket, classify it, draft an unsent reply, or escalate it. "
            "Which ticket do you need help with?"
        )
    return OUT_OF_SCOPE_MESSAGE
