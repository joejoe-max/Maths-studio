# Engineering Understanding Benchmark v1

This benchmark measures whether the semantic router extracts physical meaning from varied engineering language. It is deliberately separate from numerical solver accuracy.

## Run it

1. Send each case's `prompt` through the same Gemini semantic-routing call used by Maths Studio.
2. Save one JSON object per line in a predictions file:

```json
{"id":"beam_textbook","routing":{"sub_problems":[{"domain":"structural","problem_type":"beam_analysis","parameters":{},"engineering_model":{}}]}}
```

3. Run:

```bash
python -m tests.engineering_benchmark --predictions /path/to/predictions.jsonl --output benchmark-report.json
```

Exit code 0 means all supplied cases passed; exit code 1 means at least one case failed. Missing predictions fail rather than silently disappearing.

## What is checked

- Domain and solver problem type.
- Physical entity types.
- Named quantities, numeric values and source units.
- Physical relationships and support/boundary evidence.
- Requested outputs.
- Required missing-information/ambiguity flags.
- Unexpected quantities (a basic hallucination signal).
- Equivalent-prompt consistency: cases in the same equivalence group must yield the same core physical signature.

The evaluator runs outputs through `build_problem_spec`, the app's routing-to-`SubProblemSpec` path, before inspecting its engineering IR. It therefore tests the actual extraction handoff and IR construction, not just a standalone comparison of JSON dictionaries.

## Important limitation

This is an evaluation harness, not proof that the LLM understands all natural language. CI can test the evaluator and its failure detection without an API key; a real understanding score requires fresh router outputs from the configured model. The gold set is an initial, reviewable sample, not a cap on language coverage. Add new cases when failures reveal a new physical distinction or ambiguity.
