import asyncio
import unittest

from backend.capabilities.advanced_structural_engine import solve_advanced_structural
from backend.capabilities.beam_engine import solve_beam
from backend.engine.engineering_adapters import prepare_engineering_solver_input


def beam_payload(boundary_conditions=None, parameters=None, quantities=None):
    return {
        "domain": "structural",
        "problem_type": "beam_analysis",
        "raw_query": "A beam carries a load.",
        "parameters": parameters if parameters is not None else {"L": 6.0, "P": 10_000.0, "a": 3.0, "E": 200e9, "I": 8e-5},
        "engineering_model": {
            "entities": [{"id": "beam_1", "type": "beam"}],
            "quantities": quantities or [],
            "boundary_conditions": boundary_conditions or [],
            "relationships": [],
        },
    }


class EngineeringAdapterTests(unittest.TestCase):
    def test_explicit_pin_roller_support_is_adapted(self):
        data = beam_payload(
            boundary_conditions=[
                {"object": "beam_1", "location": "left", "condition": "pinned support"},
                {"object": "beam_1", "location": "right", "condition": "roller support"},
            ]
        )
        prepared, error = prepare_engineering_solver_input(data)
        self.assertIsNone(error)
        self.assertIn("simply supported", prepared["raw_query"])
        self.assertTrue(prepared["parameters_in_si"])

    def test_missing_supports_block_solver(self):
        prepared, error = prepare_engineering_solver_input(beam_payload())
        self.assertIsNotNone(error)
        self.assertIn("support conditions", error.lower())

    def test_fixed_free_supports_are_adapted_as_cantilever(self):
        data = beam_payload(
            boundary_conditions=[
                {"location": "left", "condition": "fixed"},
                {"location": "right", "condition": "free"},
            ]
        )
        prepared, error = prepare_engineering_solver_input(data)
        self.assertIsNone(error)
        self.assertIn("cantilever", prepared["raw_query"])

    def test_missing_material_or_section_stiffness_blocks_deflection_solver(self):
        params = {"L": 6.0, "P": 10_000.0, "a": 3.0}
        data = beam_payload(
            boundary_conditions=[{"condition": "simply supported"}],
            parameters=params,
        )
        _, error = prepare_engineering_solver_input(data)
        self.assertIsNotNone(error)
        self.assertIn("Young's modulus", error)

    def test_point_load_position_is_not_assumed(self):
        params = {"L": 6.0, "P": 10_000.0, "E": 200e9, "I": 8e-5}
        data = beam_payload(
            boundary_conditions=[{"condition": "simply supported"}],
            parameters=params,
        )
        _, error = prepare_engineering_solver_input(data)
        self.assertIsNotNone(error)
        self.assertIn("point-load position", error)

    def test_semantic_quantities_fill_legacy_solver_fields(self):
        data = beam_payload(
            boundary_conditions=[{"condition": "simply supported"}],
            parameters={},
            quantities=[
                {"name": "L", "value": 6, "solver_value": 6, "unit": "m"},
                {"name": "P", "value": 10, "solver_value": 10_000, "unit": "kN"},
                {"name": "a", "value": 3, "solver_value": 3, "unit": "m"},
                {"name": "E", "value": 200, "solver_value": 200e9, "unit": "GPa"},
                {"name": "I", "value": 8e-5, "solver_value": 8e-5, "unit": "m^4"},
            ],
        )
        prepared, error = prepare_engineering_solver_input(data)
        self.assertIsNone(error)
        self.assertEqual(prepared["parameters"]["L"], 6)
        self.assertEqual(prepared["parameters"]["P"], 10_000)
        self.assertEqual(prepared["parameters"]["E"], 200e9)

    def test_recognized_semantic_units_are_converted_to_si(self):
        data = beam_payload(
            boundary_conditions=[{"condition": "simply supported"}],
            parameters={},
            quantities=[
                {"name": "L", "value": 6000, "unit": "mm"},
                {"name": "P", "value": 10, "unit": "kN"},
                {"name": "a", "value": 3000, "unit": "mm"},
                {"name": "E", "value": 200, "unit": "GPa"},
                {"name": "I", "value": 8e-5, "unit": "m^4"},
            ],
        )
        prepared, error = prepare_engineering_solver_input(data)
        self.assertIsNone(error)
        self.assertAlmostEqual(prepared["parameters"]["L"], 6.0)
        self.assertAlmostEqual(prepared["parameters"]["P"], 10_000.0)
        self.assertAlmostEqual(prepared["parameters"]["a"], 3.0)
        self.assertAlmostEqual(prepared["parameters"]["E"], 200e9)

    def test_unknown_semantic_units_are_not_guessed(self):
        data = beam_payload(
            boundary_conditions=[{"condition": "simply supported"}],
            parameters={},
            quantities=[
                {"name": "L", "value": 6, "unit": "furlong"},
                {"name": "P", "value": 10, "unit": "mystery-force"},
                {"name": "E", "value": 200, "unit": "GPa"},
                {"name": "I", "value": 8e-5, "unit": "m^4"},
            ],
        )
        _, error = prepare_engineering_solver_input(data)
        self.assertIsNotNone(error)
        self.assertIn("span", error.lower())

    def test_shaft_torsion_adapter_requires_section_and_converts_units(self):
        data = {
            "domain": "structural",
            "problem_type": "shaft_torsion",
            "parameters": {},
            "engineering_model": {
                "entities": [{"id": "shaft_1", "type": "solid circular shaft"}],
                "quantities": [
                    {"name": "T", "value": 2, "unit": "kN*m"},
                    {"name": "L", "value": 1200, "unit": "mm"},
                    {"name": "G", "value": 80, "unit": "GPa"},
                    {"name": "d", "value": 50, "unit": "mm"},
                ],
            },
        }
        prepared, error = prepare_engineering_solver_input(data)
        self.assertIsNone(error)
        self.assertAlmostEqual(prepared["parameters"]["T"], 2000)
        self.assertAlmostEqual(prepared["parameters"]["L"], 1.2)
        self.assertAlmostEqual(prepared["parameters"]["G"], 80e9)
        self.assertAlmostEqual(prepared["parameters"]["d"], 0.05)
        self.assertEqual(prepared["parameters"]["d_inner"], 0.0)

    def test_hollow_shaft_requires_inner_diameter(self):
        data = {
            "domain": "structural",
            "problem_type": "shaft_torsion",
            "parameters": {"T": 2000, "L": 1.2, "G": 80e9, "d": 0.05},
            "engineering_model": {"entities": [{"type": "hollow circular shaft"}]},
        }
        _, error = prepare_engineering_solver_input(data)
        self.assertIsNotNone(error)
        self.assertIn("inner diameter", error)

    def test_pressure_vessel_requires_cylindrical_closed_end_geometry(self):
        data = {
            "domain": "structural",
            "problem_type": "thin_pressure_vessel",
            "parameters": {"p": 2e6, "R": 0.5, "t_wall": 0.005},
            "engineering_model": {
                "entities": [{"type": "cylindrical pressure vessel"}],
                "boundary_conditions": [{"condition": "closed ends"}],
            },
        }
        prepared, error = prepare_engineering_solver_input(data)
        self.assertIsNone(error)
        self.assertTrue(prepared["parameters_in_si"])

    def test_pressure_vessel_rejects_thick_wall_geometry(self):
        data = {
            "domain": "structural",
            "problem_type": "thin_pressure_vessel",
            "parameters": {"p": 2e6, "R": 0.05, "t_wall": 0.01},
            "engineering_model": {
                "entities": [{"type": "cylindrical pressure vessel"}],
                "boundary_conditions": [{"condition": "closed ends"}],
            },
        }
        _, error = prepare_engineering_solver_input(data)
        self.assertIsNotNone(error)
        self.assertIn("thin-wall", error.lower())

    def test_adapted_beam_input_reaches_deterministic_beam_solver(self):
        data = beam_payload(
            boundary_conditions=[{"condition": "simply supported"}],
            parameters={"L": 6.0, "P": 10_000.0, "a": 3.0, "E": 200e9, "I": 8e-5},
        )
        prepared, error = prepare_engineering_solver_input(data)
        self.assertIsNone(error)

        async def run():
            return [event async for event in solve_beam(prepared)]

        events = asyncio.run(run())
        final = next(event for event in events if event.get("type") == "final")
        summary = {item["label"]: float(item["value"]) for item in final["summary"]}
        self.assertAlmostEqual(summary["R_A"], 5_000.0, delta=0.1)
        self.assertAlmostEqual(summary["R_B"], 5_000.0, delta=0.1)
        self.assertAlmostEqual(summary["M_max"], 15_000.0, delta=0.1)

    def test_equivalent_support_representations_produce_same_beam_result(self):
        base_parameters = {"L": 6.0, "P": 10_000.0, "a": 3.0, "E": 200e9, "I": 8e-5}
        representations = [
            {
                "boundary_conditions": [
                    {"location": "left", "condition": "pinned"},
                    {"location": "right", "condition": "roller"},
                ],
                "entities": [{"id": "beam_1", "type": "beam"}],
            },
            {
                "entities": [
                    {"id": "beam_1", "type": "beam"},
                    {"id": "support_a", "type": "pin support"},
                    {"id": "support_b", "type": "roller support"},
                ],
                "relationships": [
                    {"type": "supported_by", "source": "beam_1", "target": "support_a"},
                    {"type": "supported_by", "source": "beam_1", "target": "support_b"},
                ],
            },
        ]
        results = []
        for model in representations:
            prepared, error = prepare_engineering_solver_input({
                "domain": "structural",
                "problem_type": "beam_analysis",
                "raw_query": "A beam carries a central point load.",
                "parameters": dict(base_parameters),
                "engineering_model": model,
            })
            self.assertIsNone(error)

            async def run():
                return [event async for event in solve_beam(prepared)]

            events = asyncio.run(run())
            final = next(event for event in events if event.get("type") == "final")
            summary = {item["label"]: float(item["value"]) for item in final["summary"]}
            results.append((summary["R_A"], summary["R_B"], summary["M_max"]))

        for actual, expected in zip(results[1], results[0]):
            self.assertAlmostEqual(actual, expected, delta=0.1)

    def test_adapted_column_input_reaches_euler_solver(self):
        data = {
            "domain": "structural",
            "problem_type": "euler_column_buckling",
            "parameters": {"L": 3, "E": 200e9, "I": 8e-6},
            "engineering_model": {
                "boundary_conditions": [
                    {"location": "top", "condition": "pinned"},
                    {"location": "bottom", "condition": "pinned"},
                ],
                "quantities": [],
            },
        }
        prepared, error = prepare_engineering_solver_input(data)
        self.assertIsNone(error)

        async def run():
            return [event async for event in solve_advanced_structural(prepared)]

        events = asyncio.run(run())
        final = next(event for event in events if event.get("type") == "final")
        pcr = float(next(item["value"] for item in final["summary"] if item["label"] == "P_cr"))
        self.assertAlmostEqual(pcr, 1.754596338e6, delta=5.0)

    def test_adapted_shaft_input_reaches_torsion_solver(self):
        data = {
            "domain": "structural",
            "problem_type": "shaft_torsion",
            "parameters": {},
            "engineering_model": {
                "entities": [{"id": "shaft_1", "type": "solid circular shaft"}],
                "quantities": [
                    {"name": "T", "value": 2, "unit": "kN*m"},
                    {"name": "L", "value": 1200, "unit": "mm"},
                    {"name": "G", "value": 80, "unit": "GPa"},
                    {"name": "d", "value": 50, "unit": "mm"},
                ],
            },
        }
        prepared, error = prepare_engineering_solver_input(data)
        self.assertIsNone(error)

        async def run():
            return [event async for event in solve_advanced_structural(prepared)]

        events = asyncio.run(run())
        final = next(event for event in events if event.get("type") == "final")
        summary = {item["label"]: float(item["value"]) for item in final["summary"]}
        self.assertAlmostEqual(summary["tau_max"], 8.148733086e7, delta=100.0)

    def test_adapted_pressure_vessel_input_reaches_membrane_solver(self):
        data = {
            "domain": "structural",
            "problem_type": "thin_pressure_vessel",
            "parameters": {"p": 2e6, "R": 0.5, "t_wall": 0.005},
            "engineering_model": {
                "entities": [{"type": "cylindrical pressure vessel"}],
                "boundary_conditions": [{"condition": "closed ends"}],
            },
        }
        prepared, error = prepare_engineering_solver_input(data)
        self.assertIsNone(error)

        async def run():
            return [event async for event in solve_advanced_structural(prepared)]

        events = asyncio.run(run())
        final = next(event for event in events if event.get("type") == "final")
        summary = {item["label"]: float(item["value"]) for item in final["summary"]}
        self.assertAlmostEqual(summary["sigma_hoop"], 200e6, delta=1.0)
        self.assertAlmostEqual(summary["sigma_longitudinal"], 100e6, delta=1.0)

    def test_column_effective_length_requires_explicit_restraints_or_factor(self):
        data = {
            "domain": "structural",
            "problem_type": "euler_column_buckling",
            "parameters": {"L": 3, "E": 200e9, "I": 8e-6},
            "engineering_model": {"boundary_conditions": [], "quantities": []},
        }
        _, error = prepare_engineering_solver_input(data)
        self.assertIsNotNone(error)
        self.assertIn("factor K", error)

    def test_column_factor_can_follow_explicit_pinned_pinned_conditions(self):
        data = {
            "domain": "structural",
            "problem_type": "euler_column_buckling",
            "parameters": {"L": 3, "E": 200e9, "I": 8e-6},
            "engineering_model": {
                "boundary_conditions": [
                    {"location": "top", "condition": "pinned"},
                    {"location": "bottom", "condition": "pinned"},
                ],
                "quantities": [],
            },
        }
        prepared, error = prepare_engineering_solver_input(data)
        self.assertIsNone(error)
        self.assertEqual(prepared["parameters"]["K"], 1.0)


    def test_negated_beam_support_does_not_authorize_solver(self):
        data = beam_payload(
            boundary_conditions=[{"condition": "not simply supported; one end is fixed"}],
        )
        _, error = prepare_engineering_solver_input(data)
        self.assertIsNotNone(error)
        self.assertIn("support conditions", error.lower())

    def test_negated_column_restraint_does_not_derive_effective_length_factor(self):
        data = {
            "domain": "structural",
            "problem_type": "euler_column_buckling",
            "parameters": {"L": 3, "E": 200e9, "I": 8e-6},
            "engineering_model": {
                "boundary_conditions": [
                    {"location": "top", "condition": "not pinned"},
                    {"location": "bottom", "condition": "pinned"},
                ],
            },
        }
        _, error = prepare_engineering_solver_input(data)
        self.assertIsNotNone(error)
        self.assertIn("effective length factor", error.lower())

    def test_negated_closed_end_condition_is_rejected(self):
        data = {
            "domain": "structural",
            "problem_type": "thin_pressure_vessel",
            "parameters": {"p": 2e6, "R": 0.5, "t_wall": 0.005},
            "engineering_model": {
                "entities": [{"type": "cylindrical pressure vessel"}],
                "boundary_conditions": [{"condition": "ends are not closed"}],
            },
        }
        _, error = prepare_engineering_solver_input(data)
        self.assertIsNotNone(error)
        self.assertIn("closed ends", error.lower())

    def test_negated_solid_section_is_not_treated_as_solid_shaft(self):
        data = {
            "domain": "structural",
            "problem_type": "shaft_torsion",
            "parameters": {"T": 2000, "L": 1.2, "G": 80e9, "d": 0.05},
            "engineering_model": {
                "entities": [{"type": "not a solid circular shaft"}],
            },
        }
        _, error = prepare_engineering_solver_input(data)
        self.assertIsNotNone(error)
        self.assertIn("solid or hollow", error.lower())

if __name__ == "__main__":
    unittest.main()
