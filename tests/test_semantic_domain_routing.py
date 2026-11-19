import unittest

from backend.engine.problem_pipeline import build_canonical_problem


class SemanticDomainRoutingTests(unittest.TestCase):
    def test_structured_physical_meaning_can_route_unusual_wording(self):
        spec = build_canonical_problem(
            "The member extends across six metres and carries an evenly spread action.",
            {
                "domain": "structural",
                "confidence": 0.91,
                "engineering_model": {
                    "entities": [{"id": "member_1", "type": "beam"}],
                    "quantities": [
                        {"name": "L", "value": 6, "unit": "m", "dimension": "length"},
                        {"name": "w", "value": 10, "unit": "kN/m", "dimension": "force_per_length"},
                    ],
                    "relationships": [{"type": "carries_load", "source": "member_1", "target": "member_1"}],
                },
            },
            {},
        )
        self.assertEqual(spec.domain, "structural")
        self.assertGreaterEqual(spec.domain_confidence[0].confidence, 0.9)
        self.assertIn("structured semantic engineering model", " ".join(spec.domain_confidence[0].evidence))

    def test_structured_semantics_preserve_solver_problem_type(self):
        spec = build_canonical_problem(
            "The member is six metres long and has a defined end restraint.",
            {
                "domain": "structural",
                "problem_type": "euler_column_buckling",
                "confidence": 0.9,
                "engineering_model": {
                    "entities": [{"id": "column_1", "type": "column"}],
                    "quantities": [{"name": "L", "value": 6, "unit": "m", "dimension": "length"}],
                    "relationships": [{"type": "restrained_by", "source": "column_1", "target": "support_1"}],
                },
            },
            {},
        )
        self.assertEqual(spec.domain, "structural")
        self.assertEqual(spec.problem_type, "euler_column_buckling")

    def test_domain_hint_without_structured_model_is_not_overtrusted(self):
        spec = build_canonical_problem(
            "Differentiate x squared.",
            {},
            {"domain": "structural", "confidence": 0.99},
        )
        self.assertEqual(spec.domain, "calculus")


if __name__ == "__main__":
    unittest.main()
