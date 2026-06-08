import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.engine.problem_pipeline import build_problem_spec
from capabilities.symbolic_engine import solve_algebra


def parse(prompt: str):
    routing = {"sub_problems": [{"id": "p1", "domain": "unknown", "problem_type": "general", "input_summary": prompt, "parameters": {}, "confidence": 0.0}]}
    return build_problem_spec(prompt, routing).sub_problems


async def solve_events(equations, target_variable=None):
    events = []
    async for event in solve_algebra({"parameters": {"equations": equations, "target_variable": target_variable}, "problem_type": "linear_system" if len(equations) > 1 else "single_equation", "domain": "algebra"}):
        events.append(event)
    return events


def final_answer(events):
    return [event for event in events if event.get("type") == "final"][-1]["answer"]


class PipelineHardeningTests(unittest.TestCase):
    def test_mixed_domain_prompt_splits_into_independent_problems(self):
        prompt = (
            "A simply supported beam spans 6 m carrying 15 kN/m. Find maximum bending moment. "
            "Solve 4x - 2y = 0 for y. "
            "Steam enters a turbine at h1=3200 kJ/kg and exits at h2=2400 kJ/kg with mass flow 5 kg/s. Find turbine power output."
        )
        specs = parse(prompt)
        self.assertGreaterEqual(len(specs), 3)
        self.assertIn("structural", [spec.domain for spec in specs])
        self.assertIn("algebra", [spec.domain for spec in specs])
        self.assertIn("thermo", [spec.domain for spec in specs])

    def test_same_domain_independent_problems_do_not_auto_merge(self):
        prompt = "Solve x + 3 = 7. Solve y - 2 = 5."
        specs = parse(prompt)
        self.assertEqual(len(specs), 2)
        self.assertTrue(all(spec.domain == "algebra" for spec in specs))

    def test_uppercase_linear_equation_is_normalized(self):
        events = asyncio.run(solve_events(["4X - 2x = 9"]))
        answer = final_answer(events)
        self.assertIn("x", answer.lower())
        self.assertFalse(any(event.get("type") == "error" for event in events))

    def test_solve_for_target_variable_symbolically(self):
        events = asyncio.run(solve_events(["4x - 2y = 0"], target_variable="y"))
        answer = final_answer(events).replace(" ", "")
        self.assertIn("y=2x", answer)

    def test_identity_system_returns_complete_symbolic_result(self):
        events = asyncio.run(solve_events(["x + 3 = y", "y - 3 = x"]))
        answer = final_answer(events).lower()
        self.assertTrue("x" in answer or "y" in answer)
        self.assertFalse(any(event.get("type") == "error" for event in events))


if __name__ == "__main__":
    unittest.main()
