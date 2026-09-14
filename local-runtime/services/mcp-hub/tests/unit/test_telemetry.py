"""Unit tests for Hub telemetry helpers (Spec 028)."""
from __future__ import annotations

import unittest

from mcp_hub.domain.telemetry import subject_hash, telemetry_event


class TestTelemetry(unittest.TestCase):
    def test_subject_hash_stable_and_truncated(self) -> None:
        h = subject_hash("user-sub-1")
        self.assertEqual(h, subject_hash("user-sub-1"))
        self.assertEqual(len(h), 16)
        self.assertNotIn("user-sub-1", h)

    def test_subject_hash_empty(self) -> None:
        self.assertEqual(subject_hash(""), "")
        self.assertEqual(subject_hash(None), "")

    def test_telemetry_event_shape(self) -> None:
        ev = telemetry_event(
            event_type="tools_call",
            mcp_client_slug="cursor",
            subject="alice",
            groups=["g-devs"],
            tool_name="agent__demo",
            phase="denied",
            error_code="agents_disabled",
            duration_ms=12,
            meta={"wait_mode": "accepted"},
        )
        self.assertEqual(ev["event_type"], "tools_call")
        self.assertEqual(ev["mcp_client_slug"], "cursor")
        self.assertEqual(ev["subject_hash"], subject_hash("alice"))
        self.assertNotIn("subject", ev)
        self.assertEqual(ev["idp_groups"], ["g-devs"])
        self.assertEqual(ev["phase"], "denied")
        self.assertEqual(ev["meta"]["wait_mode"], "accepted")
        self.assertTrue(ev["request_id"])


if __name__ == "__main__":
    unittest.main()
