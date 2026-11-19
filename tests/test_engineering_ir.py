import unittest

from backend.engine.engineering_ir import build_engineering_model


class EngineeringIRTests(unittest.TestCase):
    def test_preserves_source_and_structures_quantities(self):
        model = build_engineering_model(
            "A beam spans six metres.",
            {
                "domain": "structural",
                "problem_type": "beam_analysis",
                "engineering_model": {
                    "entities": [{"id": "beam_1", "type": "beam"}],
                    "quantities": [{
                        "name": "L", "unit": "m", "dimension": "length",
                        "object": "beam_1", "source_text": "spans six metres",
                    }],
                    "relationships": [{"type": "has_span", "source": "beam_1", "target": "beam_1"}],
                },
            },
            {"L": 6.0},
            {"L": "m"},
        )
        self.assertEqual(model["quantities"][0]["value"], 6.0)
        self.assertEqual(model["quantities"][0]["dimension"], "length")
        self.assertEqual(model["quantities"][0]["source_text"], "spans six metres")

    def test_preserves_quantities_without_legacy_solver_parameter(self):
        model = build_engineering_model(
            "A steel beam has a specified Poisson ratio.",
            {
                "domain": "structural",
                "engineering_model": {
                    "entities": [{"id": "beam_1", "type": "beam"}],
                    "quantities": [{
                        "name": "poisson_ratio", "value": 0.3,
                        "dimension": "dimensionless", "role": "known",
                        "object": "beam_1", "source_text": "Poisson ratio is 0.3",
                    }],
                },
            },
            {"L": 6},
            {"L": "m"},
        )
        names = {quantity["name"] for quantity in model["quantities"]}
        self.assertIn("poisson_ratio", names)
        self.assertIn("L", names)
        ratio = next(q for q in model["quantities"] if q["name"] == "poisson_ratio")
        self.assertEqual(ratio["value"], 0.3)
        self.assertIsNone(ratio["solver_value"])

    def test_does_not_invent_units(self):
        model = build_engineering_model("The load is 12.", {"domain": "structural"}, {"P": 12}, {})
        self.assertIsNone(model["quantities"][0]["unit"])
        self.assertEqual(model["quantities"][0]["dimension"], None)

    def test_flags_non_positive_geometry(self):
        model = build_engineering_model("A beam has zero span.", {"domain": "structural"}, {"L": 0}, {})
        self.assertEqual(model["validation"]["status"], "invalid")
        self.assertTrue(model["validation"]["errors"])

    def test_flags_unit_dimension_conflicts(self):
        model = build_engineering_model(
            "A beam length is 6 metres.",
            {
                "domain": "structural",
                "engineering_model": {
                    "quantities": [{
                        "name": "L", "unit": "m", "dimension": "force"
                    }]
                },
            },
            {"L": 6},
            {},
        )
        self.assertEqual(model["validation"]["status"], "invalid")
        self.assertIn("represents", model["validation"]["errors"][0])

    def test_rejects_non_finite_values(self):
        model = build_engineering_model(
            "A beam span is not finite.",
            {"domain": "structural"},
            {"L": float("inf")},
            {},
        )
        self.assertEqual(model["validation"]["status"], "invalid")
        self.assertIn("finite", model["validation"]["errors"][0])

    def test_flags_relationships_to_missing_entities(self):
        model = build_engineering_model(
            "A beam is connected to a support.",
            {
                "domain": "structural",
                "engineering_model": {
                    "entities": [{"id": "beam_1", "type": "beam"}],
                    "relationships": [{
                        "type": "supported_by", "source": "beam_1", "target": "support_1"
                    }],
                },
            },
            {},
            {},
        )
        self.assertEqual(model["validation"]["status"], "invalid")
        self.assertIn("support_1", model["validation"]["errors"][0])

    def test_keeps_ambiguity_and_missing_information_visible(self):
        model = build_engineering_model(
            "A beam is loaded.",
            {
                "domain": "structural",
                "missing_information": ["support condition"],
                "ambiguities": ["load may be total force or intensity"],
            },
            {},
            {},
        )
        self.assertEqual(model["validation"]["status"], "needs_review")
        self.assertTrue(model["missing_information"])
        self.assertTrue(model["ambiguities"])

    def test_flags_dimensionally_inconsistent_relation(self):
        model = build_engineering_model(
            "A physical relation is stated.",
            {
                "domain": "mechanics",
                "engineering_model": {
                    "entities": [{"id": "body", "type": "body"}],
                    "relationships": [{
                        "type": "equals", "source": "body", "target": "body",
                        "lhs_dimension": "force", "rhs_dimension": "length",
                    }],
                },
            },
            {},
            {},
        )
        self.assertEqual(model["validation"]["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
