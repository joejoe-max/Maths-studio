"""API startup and HTTP smoke tests for the FastAPI application."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BACKEND = str(Path(__file__).resolve().parents[1] / "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

os.environ.setdefault("MAX_CONCURRENT_SOLVES", "6")

from fastapi.testclient import TestClient
from main import app, MAX_CONCURRENT_SOLVES, _normalize_routing_shape


class ApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get("status"), "ok")

    def test_analyze_endpoint_returns_canonical_result(self):
        response = self.client.post("/api/compute/analyze", json={"input": "Solve 2x + 4 = 10"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("domain"))
        self.assertTrue(payload.get("problem_structure"))

    def test_concurrent_solve_default_is_bounded(self):
        self.assertEqual(MAX_CONCURRENT_SOLVES, 6)


    def test_legacy_root_model_is_attached_only_to_single_subproblem(self):
        model = {"entities": [{"id": "beam_1", "type": "beam"}]}
        single = _normalize_routing_shape({
            "sub_problems": [{"id": "p1", "domain": "structural"}],
            "engineering_model": model,
        }, "unknown")
        self.assertEqual(single["sub_problems"][0]["engineering_model"], model)

        multiple = _normalize_routing_shape({
            "sub_problems": [
                {"id": "p1", "domain": "structural"},
                {"id": "p2", "domain": "structural"},
            ],
            "engineering_model": model,
        }, "unknown")
        self.assertNotIn("engineering_model", multiple["sub_problems"][0])
        self.assertNotIn("engineering_model", multiple["sub_problems"][1])

if __name__ == "__main__":
    unittest.main()
