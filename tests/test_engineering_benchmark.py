import unittest

from tests.engineering_benchmark import evaluate_case, run_benchmark


def _routing(case, *, wrong=False):
    gold = case["gold"]
    quantities = [
        {"name": name, "value": item["value"], "unit": item["unit"]}
        for name, item in gold.get("quantities", {}).items()
    ]
    model = {
        "entities": [{"id": f"e{i}", "type": value} for i, value in enumerate(gold.get("entity_types", []))],
        "quantities": quantities,
        "relationships": [{"type": value} for value in gold.get("relationship_types", [])],
        "boundary_conditions": [{"condition": value} for value in gold.get("boundary_terms", [])],
        "requested_outputs": gold.get("requested_outputs", []),
        "missing_information": gold.get("required_blocker_terms", []),
        "ambiguities": [],
        "blocking_issues": gold.get("required_blocker_terms", []),
    }
    return {"sub_problems": [{
        "domain": gold["domain"],
        "problem_type": "wrong_type" if wrong else gold["problem_type"],
        "input_summary": case["prompt"],
        "parameters": {},
        "engineering_model": model,
    }]}


class EngineeringBenchmarkHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        from pathlib import Path
        cls.cases = json.loads((Path(__file__).parent / "engineering_benchmark_cases.json").read_text())

    def test_gold_shaped_outputs_pass_through_production_pipeline(self):
        case = self.cases[0]
        result = evaluate_case(case, _routing(case))
        self.assertTrue(result["passed"], result["errors"])

    def test_wrong_problem_type_fails(self):
        case = self.cases[0]
        result = evaluate_case(case, _routing(case, wrong=True))
        self.assertFalse(result["passed"])
        self.assertFalse(result["metrics"]["problem_type"])

    def test_missing_required_ambiguity_fails(self):
        case = next(item for item in self.cases if item["id"] == "beam_missing_support")
        routing = _routing(case)
        routing["sub_problems"][0]["engineering_model"]["blocking_issues"] = []
        routing["sub_problems"][0]["engineering_model"]["missing_information"] = []
        result = evaluate_case(case, routing)
        self.assertFalse(result["metrics"]["blockers"])

    def test_missing_prediction_fails_and_is_counted(self):
        report = run_benchmark(self.cases[:2], {})
        self.assertEqual(report["failed"], 2)
        self.assertEqual(report["pass_rate"], 0.0)

    def test_unexpected_quantity_is_reported_as_possible_hallucination(self):
        case = self.cases[0]
        routing = _routing(case)
        routing["sub_problems"][0]["engineering_model"]["quantities"].append(
            {"name": "I", "value": 123, "unit": "m^4"}
        )
        result = evaluate_case(case, routing)
        self.assertFalse(result["metrics"]["no_invented_quantities"])


    def test_underspecified_beam_cannot_gain_invented_supports(self):
        case = next(item for item in self.cases if item["id"] == "beam_missing_support")
        routing = _routing(case)
        routing["sub_problems"][0]["engineering_model"]["boundary_conditions"] = [
            {"condition": "simply supported with pin and roller"}
        ]
        result = evaluate_case(case, routing)
        self.assertFalse(result["metrics"]["boundary_conditions"])
        self.assertTrue(any("invented or contradicted" in error for error in result["errors"]))

    def test_equivalence_signature_normalizes_units(self):
        from tests.engineering_benchmark import run_benchmark

        case_a = dict(self.cases[0])
        case_b = dict(case_a)
        case_b["id"] = "beam_unit_variant"
        case_a["equivalence_group"] = "same_beam"
        case_b["equivalence_group"] = "same_beam"
        routing_a = _routing(case_a)
        routing_b = _routing(case_b)
        model_b = routing_b["sub_problems"][0]["engineering_model"]
        for quantity in model_b["quantities"]:
            if quantity["name"] == "L":
                quantity["value"] = 6000
                quantity["unit"] = "mm"
        report = run_benchmark([case_a, case_b], {
            case_a["id"]: routing_a,
            case_b["id"]: routing_b,
        })
        self.assertEqual(report["equivalence_failures"], [])

if __name__ == "__main__":
    unittest.main()
