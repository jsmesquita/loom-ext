"""In-memory session cancel + approval-gate registry."""
from __future__ import annotations

import threading
from typing import Any


class MemorySessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancel: dict[str, threading.Event] = {}
        self._approvals: dict[str, dict[str, Any]] = {}

    def begin(self, session_id: str) -> threading.Event:
        with self._lock:
            event = threading.Event()
            self._cancel[session_id] = event
            return event

    def cancel(self, session_id: str) -> bool:
        with self._lock:
            event = self._cancel.get(session_id)
            if event is None:
                return False
            event.set()
            return True

    def end(self, session_id: str) -> None:
        with self._lock:
            self._cancel.pop(session_id, None)
            self._approvals.pop(session_id, None)

    def active_count(self) -> int:
        with self._lock:
            return len(self._cancel)

    def arm_approval(self, session_id: str) -> None:
        """Prepare a gate the invoke loop will wait on (one pending per session)."""
        with self._lock:
            self._approvals[session_id] = {
                "event": threading.Event(),
                "decision": None,
            }

    def resolve_approval(self, session_id: str, decision: str) -> bool:
        with self._lock:
            entry = self._approvals.get(session_id)
            if entry is None:
                return False
            entry["decision"] = decision
            entry["event"].set()
            return True

    def wait_approval(self, session_id: str, timeout_s: float) -> str:
        with self._lock:
            entry = self._approvals.get(session_id)
        if entry is None:
            return "timeout"
        ok = entry["event"].wait(timeout=max(1.0, float(timeout_s)))
        with self._lock:
            decision = entry.get("decision") or ("timeout" if not ok else "denied")
            self._approvals.pop(session_id, None)
        return str(decision)
