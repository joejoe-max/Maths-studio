import asyncio
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.engine.problem_pipeline import build_problem_spec
from capabilities.shell_engine import solve_shell_buckling


ORIGINAL_PROMPT = r'''A thin-walled cylindrical shell has the following properties: - Radius $R = 1.0 \, \text{m}$ - Thickness $t = 2 \, \text{mm}$ - Length $L = 2.0 \, \text{m}$ - Young’s modulus $E = 210 \, \text{GPa}$ - Poisson’s ratio $\nu = 0.3$ The cylinder is simply supported at both ends and subjected to a uniform axial compressive load $P$. *Part 1:* Calculate the classical linear buckling load $P_{cr}$ using Donnell’s shell theory for axisymmetric buckling. Explain why this value is likely unconservative for a real structure. *Part 2:* The shell has an initial geometric imperfection in the form $w_0 = \delta \cos\left(\frac{\pi x}{L}\right)\cos(n\theta)$, with $\delta = 0.5t$ and $n = 8$. Discuss qualitatively how this imperfection affects the load-displacement path compared to the perfect shell. Sketch the expected load vs. end-shortening curves for both cases. *Part 3:* Explain why an arc-length method is required to trace the post-buckling equilibrium path past the limit point, and what phenomenon occurs at that point.'''


def parse(prompt: str):
    routing = {"sub_problems": [{"id": "p1", "domain": "unknown", "problem_type": "general", "input_summary": prompt, "parameters": {}, "confidence": 0.0}]}
    return build_problem_spec(prompt, routing).sub_problems


async def solve(spec, prompt: str):
    events = []
    async for event in solve_shell_buckling({"parameters": spec.parameters, "raw_query": prompt, "domain": spec.domain, "problem_type": spec.problem_type}):
        events.append(event)
    return events


class ShellBucklingRegressionTests(unittest.TestCase):
    def test_original_multi_part_prompt_stays_merged_and_solves(self):
        specs = parse(ORIGINAL_PROMPT)
        self.assertEqual(len(specs), 1)
        spec = specs[0]
        self.assertEqual(spec.domain, "structural")
        self.assertEqual(spec.problem_type, "shell_buckling")
        self.assertAlmostEqual(spec.parameters["R"], 1.0)
        self.assertAlmostEqual(spec.parameters["t_shell"], 0.002)
        self.assertAlmostEqual(spec.parameters["E"], 210e9)
        self.assertAlmostEqual(spec.parameters["delta"], 0.001)

        events = asyncio.run(solve(spec, ORIGINAL_PROMPT))
        final = [event for event in events if event.get("type") == "final"][-1]
        summary = {item["label"]: item for item in final["summary"]}
        self.assertAlmostEqual(summary["P_cr"]["decimal"], 3.194315662e6, delta=1.0)
        self.assertIn("unconservative", final["answer"].lower())
        self.assertTrue(any(event.get("type") == "diagram" and event.get("diagram_type") == "load_end_shortening" for event in events))

    def test_plain_assignment_units_are_scaled_once(self):
        prompt = "Find Donnell buckling for a cylindrical shell R=0.75 m, t=1.5 mm, L=1.8 m, E=70 GPa, nu=0.33, delta=0.2t."
        spec = parse(prompt)[0]
        self.assertEqual(spec.problem_type, "shell_buckling")
        self.assertAlmostEqual(spec.parameters["E"], 70e9)
        self.assertAlmostEqual(spec.parameters["t_shell"], 0.0015)
        events = asyncio.run(solve(spec, prompt))
        final = [event for event in events if event.get("type") == "final"][-1]
        p_cr = {item["label"]: item for item in final["summary"]}["P_cr"]["decimal"]
        self.assertAlmostEqual(p_cr, 6.052524795e5, delta=1.0)

    def test_missing_required_property_reports_clean_error(self):
        prompt = "Thin shell buckling: R=1 m, t=2 mm, L=2 m. Compute Pcr."
        spec = parse(prompt)[0]
        events = asyncio.run(solve(spec, prompt))
        errors = [event for event in events if event.get("type") == "error"]
        self.assertTrue(errors)
        self.assertIn("Young", errors[-1]["message"])


if __name__ == "__main__":
    unittest.main()
