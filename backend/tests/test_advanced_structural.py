import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.engine.problem_pipeline import build_problem_spec, solver_domain_for
from capabilities.advanced_structural_engine import solve_advanced_structural


def parse(prompt: str):
    routing = {"sub_problems": [{"id": "p1", "domain": "unknown", "problem_type": "general", "input_summary": prompt, "parameters": {}, "confidence": 0.0}]}
    return build_problem_spec(prompt, routing).sub_problems[0]


async def solve(spec, prompt: str):
    events = []
    async for event in solve_advanced_structural({"parameters": spec.parameters, "problem_type": spec.problem_type, "domain": spec.domain, "raw_query": prompt}):
        events.append(event)
    return events


def summary_value(events, label: str):
    final = [event for event in events if event.get("type") == "final"][-1]
    return {item["label"]: item for item in final["summary"]}[label]["decimal"]


class AdvancedStructuralRegressionTests(unittest.TestCase):
    def test_euler_column_buckling_routes_and_solves(self):
        prompt = "A steel pinned-pinned column has length L=3 m, E=200 GPa, I=8e-6 m^4. Calculate Euler critical buckling load."
        spec = parse(prompt)
        self.assertEqual(spec.domain, "structural")
        self.assertEqual(spec.problem_type, "euler_column_buckling")
        self.assertAlmostEqual(spec.parameters["E"], 200e9)
        self.assertAlmostEqual(spec.parameters["K"], 1.0)
        events = asyncio.run(solve(spec, prompt))
        self.assertAlmostEqual(summary_value(events, "P_cr"), 1.754596338e6, delta=1.0)

    def test_solid_shaft_torsion_routes_and_solves(self):
        prompt = "A solid circular steel shaft has diameter d=50 mm, length L=1.2 m, shear modulus G=80 GPa, torque T=2 kN m. Find maximum shear stress and angle of twist."
        spec = parse(prompt)
        self.assertEqual(spec.problem_type, "shaft_torsion")
        self.assertAlmostEqual(spec.parameters["d"], 0.05)
        self.assertAlmostEqual(spec.parameters["T"], 2000.0)
        events = asyncio.run(solve(spec, prompt))
        self.assertAlmostEqual(summary_value(events, "tau_max"), 8.148733086e7, delta=10.0)
        self.assertAlmostEqual(summary_value(events, "theta"), 0.0488923985, delta=1e-8)

    def test_thin_pressure_vessel_routes_and_solves(self):
        prompt = "A thin-walled pressure vessel cylinder has radius R=0.5 m, wall thickness t=5 mm, internal pressure p=2 MPa. Find hoop stress and longitudinal stress."
        spec = parse(prompt)
        self.assertEqual(spec.problem_type, "thin_pressure_vessel")
        self.assertAlmostEqual(spec.parameters["p"], 2e6)
        self.assertNotIn("T", spec.parameters)
        events = asyncio.run(solve(spec, prompt))
        self.assertAlmostEqual(summary_value(events, "sigma_hoop"), 200e6, delta=1.0)
        self.assertAlmostEqual(summary_value(events, "sigma_longitudinal"), 100e6, delta=1.0)

    def test_beam_material_properties_do_not_split_to_circuit(self):
        prompt = "A simply supported beam L=8 m carries a UDL w=5 kN/m and a point load P=20 kN at midspan. Find reactions, max moment and deflection if E=200 GPa, I=4e-5 m^4."
        routing = {"sub_problems": [{"id": "p1", "domain": "unknown", "problem_type": "general", "input_summary": prompt, "parameters": {}, "confidence": 0.0}]}
        specs = build_problem_spec(prompt, routing).sub_problems
        self.assertEqual(len(specs), 1)
        spec = specs[0]
        self.assertEqual(spec.domain, "structural")
        self.assertEqual(spec.problem_type, "beam_analysis")
        self.assertAlmostEqual(spec.parameters["L"], 8.0)
        self.assertAlmostEqual(spec.parameters["E"], 200e9)
        self.assertAlmostEqual(spec.parameters["I"], 4e-5)

    def test_head_loss_turbine_and_vibration_route_to_existing_engines(self):
        cases = [
            ("Water flows through a 100 mm diameter pipe, length 50 m, velocity 2 m/s, Darcy friction factor f=0.02. Compute Darcy-Weisbach head loss and pressure drop.", "fluids", "head_loss", {"D": 0.1, "L": 50.0, "v": 2.0, "f": 0.02}),
            ("Steam enters a turbine at h1=3200 kJ/kg and exits at h2=2400 kJ/kg with mass flow 5 kg/s. Find turbine power output.", "thermo", "turbine_power", {"h1": 3200.0, "h2": 2400.0, "m_dot": 5.0}),
            ("A mass-spring-damper system has m=10 kg, c=40 N s/m, k=1000 N/m. Find natural frequency, damping ratio and classify damping.", "mechanics", "vibration", {"m": 10.0, "c": 40.0, "k": 1000.0}),
        ]
        for prompt, expected_solver, expected_type, expected_params in cases:
            spec = parse(prompt)
            self.assertEqual(solver_domain_for(spec), expected_solver)
            self.assertEqual(spec.problem_type, expected_type)
            for key, expected in expected_params.items():
                self.assertAlmostEqual(float(spec.parameters[key]), expected)


if __name__ == "__main__":
    unittest.main()
