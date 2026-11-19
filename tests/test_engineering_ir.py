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

    def test_does_not_invent_units(self):
        model = build_engineering_model("The load is 12.", {"domain": "structural"}, {"P": 12}, {})
        self.assertIsNone(model["quantities"][0]["unit"])
        self.assertEqual(model["quantities"][0]["dimension"], None)

    def test_flags_non_positive_geometry(self):
        model = build_engineering_model("A beam has zero span.", {"domain": "structural"}, {"L": 0}, {})
        self.assertEqual(model["validation"]["status"], "invalid")
        self.assertTrue(model["validation"]["errors"])

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
