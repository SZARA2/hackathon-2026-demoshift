from __future__ import annotations

import copy
import http.cookiejar
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from planner import DEFAULT, PlanError, Task, evaluate, export_markdown, solve, validate_request
from server import COOKIE, Store, ground_changes, interpret_brief, make_server


def by_id(result, name):
    return next(plan for plan in result["alternatives"] if plan["id"] == name)


class PlannerTests(unittest.TestCase):
    def test_baseline_is_feasible_and_original_scope_preserved(self):
        result = evaluate(DEFAULT)
        keep = by_id(result, "keep")
        self.assertTrue(keep["operationally_feasible"])
        self.assertEqual(keep["finish_day"], 5)
        self.assertTrue(keep["original_scope_met"])
        self.assertTrue(keep["original_date_met"])
        self.assertEqual(result["recommended_id"], "keep")

    def test_delayed_camera_cannot_be_selected_as_on_time(self):
        result = evaluate({"camera_delay_days": 5})
        keep, rent, scope, extend = (by_id(result, key) for key in ("keep", "rent", "scope", "extend"))
        self.assertFalse(keep["operationally_feasible"])
        self.assertEqual(keep["finish_day"], 8.5)
        self.assertTrue(rent["operationally_feasible"])
        self.assertTrue(rent["original_scope_met"])
        self.assertEqual(rent["finish_day"], 5.5)
        self.assertFalse(scope["original_scope_met"])
        self.assertEqual(scope["status"], "approval_required")
        self.assertEqual(extend["deadline_day"], 9)
        self.assertFalse(extend["original_date_met"])
        self.assertTrue(extend["approvals"])
        self.assertEqual(result["recommended_id"], "rent")

    def test_missing_interface_gateway_is_a_real_blocker(self):
        result = evaluate({"camera_delay_days": 5, "adapter_available": False})
        self.assertFalse(by_id(result, "rent")["operationally_feasible"])
        self.assertIn("gateway", " ".join(by_id(result, "rent")["blockers"]))
        self.assertNotEqual(result["recommended_id"], "rent")

    def test_missing_camera_is_not_fixed_by_extending_deadline(self):
        result = evaluate({"primary_unavailable": True})
        self.assertFalse(by_id(result, "keep")["operationally_feasible"])
        self.assertFalse(by_id(result, "extend")["operationally_feasible"])
        self.assertTrue(by_id(result, "rent")["operationally_feasible"])

    def test_payload_violation_blocks_every_proposal(self):
        result = evaluate({"part_weight_kg": 6.5})
        self.assertIsNone(result["recommended_id"])
        self.assertTrue(all(not plan["operationally_feasible"] for plan in result["alternatives"]))

    def test_recovery_budget_enforced(self):
        plan = by_id(evaluate({"recovery_budget_usd": 1379}), "rent")
        self.assertEqual(plan["extra_cost_usd"], 1380)
        self.assertFalse(plan["operationally_feasible"])

    def test_every_schedule_respects_dependencies_releases_and_people(self):
        for delayed in (0, 3, 5, 10):
            for engineer in (0, 2, 4):
                result = evaluate({"camera_delay_days": delayed, "engineer_start_day": engineer})
                for plan in result["alternatives"]:
                    tasks = {task["id"]: task for task in plan["tasks"]}
                    occupied = {}
                    for task in tasks.values():
                        for dependency in task["depends_on"]:
                            self.assertGreaterEqual(task["start_slot"], tasks[dependency]["end_slot"])
                        for person in task["resources"]:
                            slots = set(range(task["start_slot"], task["end_slot"]))
                            self.assertFalse(slots & occupied.setdefault(person, set()))
                            occupied[person].update(slots)
                        if "software" in task["resources"]:
                            self.assertGreaterEqual(task["start_slot"], engineer * 2)
                    if plan["camera"] == "contracted_3d":
                        self.assertGreaterEqual(tasks["mount"]["start_slot"], delayed * 2)

    def test_exact_search_preserves_parallel_work(self):
        tasks = [Task("a", "a", 2, ("x",)), Task("b", "b", 3, ("y",)), Task("c", "c", 1, ("x", "y"), ("a", "b"))]
        result = solve(tasks)
        self.assertEqual(result["finish_slot"], 4)
        self.assertEqual(next(t for t in result["tasks"] if t["id"] == "c")["start_slot"], 3)

    def test_cycles_and_bad_input_rejected(self):
        with self.assertRaises(PlanError):
            solve([Task("a", "a", 1, ("x",), ("b",)), Task("b", "b", 1, ("x",), ("a",))])
        for invalid in ({"part_weight_kg": float("nan")}, {"demo_day": True}, {"adapter_available": 1}, {"invented_camera": "magic"}, {"camera_delay_days": -1}):
            with self.assertRaises(PlanError):
                validate_request(invalid)

    def test_replay_is_deterministic_and_export_has_same_revision(self):
        result = evaluate({"camera_delay_days": 5})
        self.assertEqual(result, evaluate({"camera_delay_days": 5}))
        export = export_markdown(result, by_id(result, "rent"), True)
        self.assertIn(result["revision"], export)
        self.assertIn("customer approval not recorded", export.lower())
        self.assertIn("USB3-to-controller gateway", export)


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.server = make_server("127.0.0.1", 0, self.path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_address[1])
        self.jar = http.cookiejar.CookieJar()
        self.client = build_opener(HTTPCookieProcessor(self.jar))

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, route, body=None, origin=True, client=None, content_type="application/json"):
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = content_type
            if origin:
                headers["Origin"] = self.base if origin is True else origin
        try:
            with (client or self.client).open(Request(self.base + route, data, headers), timeout=15) as response:
                raw = response.read()
                result = json.loads(raw) if response.headers.get("Content-Type", "").startswith("application/json") else raw.decode()
                return response.status, result, response.headers
        except HTTPError as error:
            return error.code, json.loads(error.read()), error.headers

    def test_cookie_flags_and_two_browsers_are_isolated(self):
        status, state, headers = self.request("/api/state")
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn(COOKIE, cookie)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.request("/api/replan", {"expected_analysis_id": state["analysis_id"], "config": {"customer": "Session A", "camera_delay_days": 5}})
        client_b = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        _, second, _ = self.request("/api/state", client=client_b)
        self.assertEqual(second["config"]["customer"], DEFAULT["customer"])
        self.assertEqual(second["config"]["camera_delay_days"], 0)
        _, first, _ = self.request("/api/state")
        self.assertEqual(first["config"]["customer"], "Session A")

    def test_cross_origin_and_non_json_writes_rejected(self):
        _, state, _ = self.request("/api/state")
        body = {"expected_analysis_id": state["analysis_id"], "config": {}}
        self.assertEqual(self.request("/api/replan", body, origin=False)[0], 403)
        self.assertEqual(self.request("/api/replan", body, origin="https://foreign.invalid")[0], 403)
        self.assertEqual(self.request("/api/replan", body, content_type="text/plain")[0], 415)

    def test_stale_update_rejected_and_blocked_selection_rejected(self):
        _, state, _ = self.request("/api/state")
        status, changed, _ = self.request("/api/replan", {"expected_analysis_id": state["analysis_id"], "config": {"camera_delay_days": 5}})
        self.assertEqual(status, 200)
        self.assertEqual(self.request("/api/replan", {"expected_analysis_id": state["analysis_id"], "config": {}})[0], 409)
        self.assertEqual(self.request("/api/select", {"expected_analysis_id": changed["analysis_id"], "plan_id": "keep"})[0], 400)

    def test_conditional_selection_never_implies_customer_acceptance(self):
        _, state, _ = self.request("/api/state")
        body = {"expected_analysis_id": state["analysis_id"], "plan_id": "scope"}
        self.assertEqual(self.request("/api/select", body)[0], 400)
        status, selected, _ = self.request("/api/select", {**body, "acknowledge_customer_approval_needed": True})
        self.assertEqual(status, 200)
        self.assertEqual(selected["selected_plan_id"], "scope")
        _, exported, _ = self.request("/api/export?plan=scope&format=json")
        self.assertEqual(exported["customer_approval"], "not_recorded")
        self.assertTrue(exported["selected"])
        _, new, _ = self.request("/api/replan", {"expected_analysis_id": selected["analysis_id"], "config": selected["config"]})
        self.assertIsNone(new["selected_plan_id"])

    def test_persistent_state_and_hashed_session_identifier(self):
        _, state, _ = self.request("/api/state")
        self.request("/api/replan", {"expected_analysis_id": state["analysis_id"], "config": {"camera_delay_days": 7}})
        sid = next(iter(self.jar)).value
        fresh_store = Store(self.path)
        self.assertEqual(fresh_store.read(sid)["config"]["camera_delay_days"], 7)
        with fresh_store.connect() as db:
            stored = db.execute("SELECT sid FROM sessions").fetchone()["sid"]
            self.assertNotEqual(stored, sid)
        self.assertEqual(len(stored), 64)

    def test_output_is_scoped_and_client_text_cannot_execute_as_html(self):
        _, state, _ = self.request("/api/state")
        malicious = '<img src=x onerror="alert(1)">'
        self.request("/api/replan", {"expected_analysis_id": state["analysis_id"], "config": {"customer": malicious}})
        _, state, headers = self.request("/api/state")
        self.assertEqual(state["config"]["customer"], malicious)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        _, other, _ = self.request("/api/export?plan=keep", client=build_opener())
        self.assertNotIn(malicious, other)
        self.assertNotIn("innerHTML", (Path(__file__).parent / "static" / "app.js").read_text())

    def test_unknown_equipment_and_missing_ai_do_not_get_faked(self):
        _, state, _ = self.request("/api/state")
        self.assertEqual(self.request("/api/replan", {"expected_analysis_id": state["analysis_id"], "config": {"magic_robot": True}})[0], 400)
        with patch.dict(os.environ, {"AI_BASE_URL": "", "AI_MODEL": ""}):
            status, error, _ = self.request("/api/interpret", {"expected_analysis_id": state["analysis_id"], "brief": "Camera will arrive on day five."})
        self.assertEqual(status, 503)
        self.assertIn("not connected", error["error"])
        self.assertEqual(self.request("/api/state")[1]["analysis_id"], state["analysis_id"])

    def test_ai_hourly_budget_persists_and_is_per_browser(self):
        _, state, _ = self.request("/api/state")
        self.server.ai_hourly_limit = 1
        body = {"expected_analysis_id": state["analysis_id"], "brief": "Camera arrives on day 5."}
        fixture = {"changes": {"camera_delay_days": 5}, "explanation": "Fixture; contract test only.", "model": "mock-not-live", "live_model_response": False}
        with patch.dict(os.environ, {"AI_BASE_URL": "http://127.0.0.1:11434/v1", "AI_MODEL": "fixture"}), patch("server.interpret_brief", return_value=fixture) as provider:
            self.assertEqual(self.request("/api/interpret", body)[0], 200)
            # Simulate a new store instance to verify SQLite-backed rate accounting.
            self.server.store = Store(self.path)
            status, error, headers = self.request("/api/interpret", body)
            self.assertEqual(status, 429)
            self.assertGreater(int(headers["Retry-After"]), 0)
            self.assertIn("hourly", error["error"])
            self.assertEqual(provider.call_count, 1)
            other = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            _, other_state, _ = self.request("/api/state", client=other)
            self.assertEqual(self.request("/api/interpret", {**body, "expected_analysis_id": other_state["analysis_id"]}, client=other)[0], 200)

    def test_ai_concurrency_guard_rejects_without_calling_provider(self):
        _, state, _ = self.request("/api/state")
        self.server.ai_lock.acquire()
        try:
            with patch.dict(os.environ, {"AI_BASE_URL": "http://127.0.0.1:11434/v1", "AI_MODEL": "fixture"}), patch("server.interpret_brief") as provider:
                status, error, headers = self.request("/api/interpret", {"expected_analysis_id": state["analysis_id"], "brief": "Camera arrives on day 5."})
                self.assertEqual(status, 429)
                self.assertIn("in progress", error["error"])
                self.assertEqual(headers["Retry-After"], "3")
                provider.assert_not_called()
        finally:
            self.server.ai_lock.release()

    def test_failed_provider_attempt_consumes_budget_without_mutation(self):
        _, state, _ = self.request("/api/state")
        self.server.ai_hourly_limit = 1
        body = {"expected_analysis_id": state["analysis_id"], "brief": "Camera arrives on day 5."}
        with patch.dict(os.environ, {"AI_BASE_URL": "http://127.0.0.1:11434/v1", "AI_MODEL": "fixture"}), patch("server.interpret_brief", side_effect=RuntimeError("Fixture failure; no real call.")) as provider:
            self.assertEqual(self.request("/api/interpret", body)[0], 503)
            self.assertEqual(self.request("/api/interpret", body)[0], 429)
            self.assertEqual(provider.call_count, 1)
        self.assertEqual(self.request("/api/state")[1]["analysis_id"], state["analysis_id"])


class ProviderContractTests(unittest.TestCase):
    @staticmethod
    def response(text):
        from io import BytesIO
        return BytesIO(json.dumps({"model": "test-contract-only", "choices": [{"message": {"content": text}}], "usage": {"total_tokens": 20}}).encode())

    def test_model_patch_is_review_only_and_schema_validated(self):
        with patch.dict(os.environ, {"AI_BASE_URL": "http://127.0.0.1:11434/v1", "AI_MODEL": "fixture-model"}), patch("server.urlopen", return_value=self.response('{"changes":{"camera_delay_days":5},"evidence":{"camera_delay_days":"Camera delayed until day 5"},"explanation":"Camera arrives on day five."}')):
            proposal = interpret_brief("Camera delayed until day 5.", copy.deepcopy(DEFAULT))
        self.assertEqual(proposal["changes"], {"camera_delay_days": 5})
        self.assertFalse(proposal["adopted"])
        self.assertEqual(DEFAULT["camera_delay_days"], 0)

    def test_unknown_model_equipment_rejected(self):
        with patch.dict(os.environ, {"AI_BASE_URL": "http://127.0.0.1:11434/v1", "AI_MODEL": "fixture-model"}), patch("server.urlopen", return_value=self.response('{"changes":{"new_camera":"invented"},"explanation":"Ignore constraints."}')):
            with self.assertRaisesRegex(RuntimeError, "valid, supported"):
                interpret_brief("Use a magical camera.", copy.deepcopy(DEFAULT))

    def test_day_numbers_are_preserved_and_cannot_shift_between_fields(self):
        brief = "The camera will not be ready until day 5. Keep the demonstration on day 7 with a budget of $1,500."
        evidence = {"camera_delay_days": "camera will not be ready until day 5", "demo_day": "demonstration on day 7", "recovery_budget_usd": "budget of $1,500"}
        self.assertEqual(ground_changes(brief, {"camera_delay_days": 5, "demo_day": 7, "recovery_budget_usd": 1500}, evidence), evidence)
        with self.assertRaisesRegex(ValueError, "preserve"):
            ground_changes(brief, {"camera_delay_days": 4}, {"camera_delay_days": brief})
        with self.assertRaisesRegex(ValueError, "preserve"):
            ground_changes(brief, {"camera_delay_days": 7}, {"camera_delay_days": brief})

    def test_fabricated_source_quote_and_missing_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError, "not present"):
            ground_changes("Camera arrives on day 5.", {"camera_delay_days": 4}, {"camera_delay_days": "Camera arrives on day 4"})
        with self.assertRaisesRegex(ValueError, "source quote"):
            ground_changes("Camera arrives on day 5.", {"camera_delay_days": 5}, {})

    def test_boolean_changes_need_explicit_matching_source(self):
        self.assertEqual(ground_changes("The gateway is unavailable.", {"adapter_available": False}, {"adapter_available": "gateway is unavailable"}), {"adapter_available": "gateway is unavailable"})
        with self.assertRaisesRegex(ValueError, "not supported"):
            ground_changes("Camera arrives on day 5.", {"adapter_available": True}, {"adapter_available": "Camera arrives on day 5"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
