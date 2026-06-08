from .models import CanonicalProblem, DomainScore, MethodOption, ProblemSpec, ProblemStructure, StructuredError, SubProblemSpec
from .interaction import (
    build_method_selection_event,
    build_missing_parameters_event,
    determine_missing_fields,
    should_prompt_for_method,
)
from .problem_pipeline import (
    METHOD_CATALOG,
    build_canonical_problem,
    build_problem_spec,
    determine_methods,
    ensure_requested_method,
    normalize_solver_event,
    solver_domain_for,
    structured_error,
)

__all__ = [
    "CanonicalProblem",
    "DomainScore",
    "MethodOption",
    "ProblemSpec",
    "ProblemStructure",
    "StructuredError",
    "SubProblemSpec",
    "build_method_selection_event",
    "build_missing_parameters_event",
    "determine_missing_fields",
    "should_prompt_for_method",
    "METHOD_CATALOG",
    "build_canonical_problem",
    "build_problem_spec",
    "determine_methods",
    "ensure_requested_method",
    "normalize_solver_event",
    "solver_domain_for",
    "structured_error",
]
