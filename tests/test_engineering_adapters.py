import unittest

from backend.engine.engineering_adapters import prepare_engineering_solver_input


def beam_payload(boundary_conditions=None, parameters=None, quantities=None):
    return {
        "domain": "structural",
        "problem_type": "beam_analysis",
        "raw_query": "A beam carries a load.",
        "parameters": parameters or {"L": 6.0, "P": 10_000.0, "a": 3.0, "E": 200e9, "I": 8e-5},
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


if __name__ == "__main__":
    unittest.main()
