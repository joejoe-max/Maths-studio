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
from main import app, MAX_CONCURRENT_SOLVES


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


if __name__ == "__main__":
    unittest.main()
