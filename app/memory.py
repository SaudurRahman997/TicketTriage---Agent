"""Conversation memory: LangChain messages, bounded, in-memory, one worker. Lost on restart."""
import threading
from collections import OrderedDict
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


class SessionStore:
    def __init__(self, max_turns: int = 6, max_chars: int = 24000, max_sessions: int = 100):
        self.max_turns, self.max_chars, self.max_sessions = max_turns, max_chars, max_sessions
        self._s: "OrderedDict[str, list[BaseMessage]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, sid: str) -> list[BaseMessage]:
        with self._lock:
            return list(self._s.get(sid, []))

    def add_turn(self, sid: str, human: str, ai: str) -> None:
        with self._lock:
            msgs = self._s.pop(sid, [])
            msgs += [HumanMessage(content=human), AIMessage(content=ai)]
            msgs = msgs[-self.max_turns * 2:]
            while len(msgs) > 2 and sum(len(str(m.content)) for m in msgs) > self.max_chars:
                msgs = msgs[2:]
            self._s[sid] = msgs
            while len(self._s) > self.max_sessions:      # evict least-recently-used session
                self._s.popitem(last=False)

    def reset(self, sid: str) -> None:
        with self._lock:
            self._s.pop(sid, None)
