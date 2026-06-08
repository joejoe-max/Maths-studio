from __future__ import annotations

import re
from typing import Any

import sympy as sp
from sympy.parsing.sympy_parser import (
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from .math_normalizer import (
    extract_equations,
    extract_units,
    extract_unknowns,
    normalize_equation_text,
    normalize_math_text,
    split_knowns_unknowns,
)
from .solver_utils import polish_display_math
from .models import (
    CanonicalProblem,
    DomainScore,
    EquationSpec,
    MethodOption,
    ProblemSpec,
    ProblemStructure,
    StructuredError,
    SubProblemSpec,
)

_TRANSFORMS = standard_transformations + (implicit_multiplication_application,)
_FUNCTION_NAMES = {"sin", "cos", "tan", "log", "ln", "exp", "sqrt", "pi", "E"}
_SUPPORTED_DOMAINS = {"structural", "algebra", "calculus", "ode", "thermo", "circuits", "mechanics", "fluids", "physics", "controls", "statistics", "matrix", "data_viz"}
_ENGINEERING_DOMAINS = {"structural", "mechanics", "fluids", "thermo", "circuits", "physics", "controls"}

METHOD_CATALOG: dict[str, list[MethodOption]] = {
    "algebra": [
        MethodOption(id="isolation", label="Isolation", description="Rearrange a single equation symbolically."),
        MethodOption(id="quadratic_formula", label="Quadratic Formula", description="Solve degree-2 polynomial equations."),
        MethodOption(id="factorization", label="Factorization", description="Factor polynomial equations when possible."),
        MethodOption(id="substitution", label="Substitution", description="Eliminate variables by substitution in systems."),
        MethodOption(id="elimination", label="Elimination", description="Combine equations to remove unknowns."),
        MethodOption(id="matrix", label="Matrix Method", description="Solve linear systems using matrix form."),
    ],
    "matrix": [
        MethodOption(id="row_reduction", label="Row Reduction", description="Gaussian elimination / RREF."),
        MethodOption(id="eigen", label="Eigen Analysis", description="Characteristic equation and eigenspaces."),
        MethodOption(id="inverse", label="Matrix Inverse", description="Inverse by row operations or adjugate."),
    ],
    "calculus": [
        MethodOption(id="differentiation", label="Differentiation", description="Symbolic derivative from expression structure."),
        MethodOption(id="integration", label="Integration", description="Symbolic antiderivative or definite integral."),
        MethodOption(id="series", label="Series Expansion", description="Taylor or Maclaurin expansion."),
        MethodOption(id="laplace", label="Laplace Transform", description="Transform time-domain expression."),
    ],
    "ode": [
        MethodOption(id="characteristic", label="Characteristic Equation", description="Linear constant-coefficient ODE method."),
        MethodOption(id="laplace", label="Laplace Method", description="Solve ODE using transforms and conditions."),
        MethodOption(id="dsolve", label="Symbolic ODE Solve", description="Use symbolic differential equation solving."),
    ],
    "structural": [
        MethodOption(id="equilibrium", label="Equilibrium", description="Use force and moment balance."),
        MethodOption(id="moment_area", label="Moment-Area", description="Use curvature/area relations for deflection."),
        MethodOption(id="energy", label="Energy Method", description="Use strain energy / virtual work when applicable."),
        MethodOption(id="shell_stability", label="Shell Stability", description="Use classical cylindrical-shell buckling relations and imperfection sensitivity checks."),
        MethodOption(id="member_stability", label="Member Stability", description="Use Euler column buckling, torsion, or thin pressure-vessel stress relations."),
    ],
    "mechanics": [
        MethodOption(id="newton", label="Newtonian Mechanics", description="Use kinematics and force balance."),
        MethodOption(id="energy", label="Energy Method", description="Use conservation of energy when applicable."),
    ],
    "circuits": [
        MethodOption(id="ohms_law", label="Ohm's Law", description="Use V = IR for direct circuit quantities."),
        MethodOption(id="nodal", label="Nodal Analysis", description="Use Kirchhoff current law."),
        MethodOption(id="mesh", label="Mesh Analysis", description="Use Kirchhoff voltage law."),
        MethodOption(id="phasor", label="Phasor Analysis", description="Use complex impedance for AC circuits."),
    ],
    "thermo": [
        MethodOption(id="ideal_gas", label="Ideal Gas Law", description="Use PV = nRT."),
        MethodOption(id="energy_balance", label="Energy Balance", description="Apply first-law energy accounting."),
        MethodOption(id="heat_transfer", label="Heat Transfer", description="Use conduction/convection/radiation relations."),
    ],
    "fluids": [MethodOption(id="continuity", label="Continuity", description="Apply conservation of mass."), MethodOption(id="bernoulli", label="Bernoulli", description="Apply energy balance along streamlines.")],
    "physics": [MethodOption(id="symbolic_physics", label="Symbolic Physics", description="Apply the governing physical relation.")],
    "controls": [MethodOption(id="transfer_function", label="Transfer Function", description="Analyze dynamic system response.")],
    "statistics": [MethodOption(id="descriptive", label="Descriptive Statistics", description="Compute statistics from provided data."), MethodOption(id="regression", label="Regression", description="Fit a least-squares model.")],
    "data_viz": [MethodOption(id="plot", label="Plot", description="Render the requested function or dataset.")],
}


def build_problem_spec(raw_input: str, routing: dict[str, Any]) -> ProblemSpec:
    sub_specs: list[SubProblemSpec] = []
    sub_problems = routing.get("sub_problems") or [{"id": "p1", "input_summary": raw_input, "parameters": {}}]
    if len(sub_problems) == 1 and not sub_problems[0].get("isolated_input"):
        sub_problems = _decompose_mixed_input(raw_input, sub_problems[0])

    for index, sub in enumerate(sub_problems, start=1):
        params = dict(sub.get("parameters") or {})
        input_summary = str(sub.get("input_summary") or "")
        raw_query = input_summary if sub.get("isolated_input") else _select_canonical_source(raw_input, input_summary, params)
        normalized_text = normalize_math_text(raw_query)
        canonical = build_canonical_problem(raw_query, params, sub)
        domain = canonical.domain
        equations = canonical.equations
        unknowns = canonical.variables
        knowns, unknowns = split_knowns_unknowns(canonical.parameters, unknowns)
        canonical.variables = unknowns

        spec = SubProblemSpec(
            id=str(sub.get("id") or f"p{index}"),
            domain=domain,
            problem_type=canonical.problem_type,
            raw_query=raw_query,
            normalized_text=normalized_text,
            canonical=canonical,
            input_summary=raw_query,
            parameters=canonical.parameters,
            knowns=knowns,
            unknowns=unknowns,
            constraints=canonical.constraints,
            equations=equations,
            units=canonical.units,
            requested_method=sub.get("requested_method") or params.get("method"),
        )
        spec.feasible_methods = determine_methods(spec)
        spec.selected_method = _auto_select_method(spec)
        sub_specs.append(spec)

    return ProblemSpec(raw_input=raw_input, sub_problems=sub_specs)


def _decompose_mixed_input(raw_input: str, base_sub: dict[str, Any]) -> list[dict[str, Any]]:
    """Split multi-domain prompts into independently classified sub-problems.

    This is deliberately concept-based: it only splits when sentence/connector
    chunks produce different canonical domains. Same-domain engineering parts
    remain merged, so a beam problem asking reactions + moment + stress stays
    one structural problem.
    """
    chunks = _split_candidate_tasks(raw_input)
    if len(chunks) <= 1:
        return [base_sub]

    if _has_shell_buckling_context(raw_input):
        return [base_sub]

    analyzed: list[tuple[str, CanonicalProblem]] = []
    for chunk in chunks:
        canonical = build_canonical_problem(chunk, {}, {"domain": "unknown", "problem_type": "general"})
        if canonical.domain != "unknown":
            analyzed.append((chunk, canonical))

    if len(analyzed) <= 1:
        return [base_sub]

    full_canonical = build_canonical_problem(raw_input, {}, {"domain": "unknown", "problem_type": "general"})
    if _should_keep_engineering_context_merged(raw_input, analyzed, full_canonical):
        return [base_sub]

    return [
        {
            "id": f"p{index}",
            "domain": canonical.domain,
            "problem_type": canonical.problem_type,
            "input_summary": chunk,
            "parameters": canonical.parameters,
            "confidence": canonical.domain_confidence[0].confidence if canonical.domain_confidence else 0.0,
            "isolated_input": True,
        }
        for index, (chunk, canonical) in enumerate(analyzed, start=1)
    ]


def _should_keep_engineering_context_merged(raw_input: str, analyzed: list[tuple[str, CanonicalProblem]], full_canonical: CanonicalProblem) -> bool:
    if _should_keep_structural_property_followups_merged(raw_input, analyzed, full_canonical):
        return True
    if full_canonical.domain not in _ENGINEERING_DOMAINS:
        return False

    known_domains = {canonical.domain for _, canonical in analyzed if canonical.domain != "unknown"}
    if not known_domains or full_canonical.domain not in known_domains:
        return False
    if known_domains - {full_canonical.domain}:
        return False

    setup_count = sum(_has_standalone_engineering_setup(canonical) for _, canonical in analyzed)
    has_part_sequence = bool(re.search(r"\bpart\s*\d+\b", raw_input or "", re.I))
    has_contextual_followup = any(_is_engineering_context_continuation(chunk) for chunk, _ in analyzed[1:])
    return setup_count <= 1 and (has_part_sequence or has_contextual_followup)


def _should_keep_structural_property_followups_merged(raw_input: str, analyzed: list[tuple[str, CanonicalProblem]], full_canonical: CanonicalProblem) -> bool:
    if full_canonical.domain != "structural" or not _has_structural_beam_concepts((raw_input or "").lower()):
        return False
    known_domains = {canonical.domain for _, canonical in analyzed if canonical.domain != "unknown"}
    if not known_domains or known_domains - {"structural", "circuits"}:
        return False
    for chunk, canonical in analyzed:
        if canonical.domain != "circuits":
            continue
        params = canonical.parameters or {}
        circuit_keys = {key for key in params if key not in {"canonical_problem_type", "_units"}}
        if circuit_keys - {"E", "I", "G"}:
            return False
        if not re.search(r"\b(?:E|I|G)\s*=", chunk):
            return False
    return True


def _has_standalone_engineering_setup(canonical: CanonicalProblem) -> bool:
    params = canonical.parameters or {}
    domain = canonical.domain
    if domain == "structural":
        return _has_any(params, ("L", "l", "span", "length")) and _has_any(params, ("P", "w", "point_load", "distributed_load", "udl", "dead_load", "live_load"))
    if domain == "circuits":
        return _has_any(params, ("V", "I", "R", "resistors", "voltage", "current", "resistance"))
    if domain == "fluids":
        return _has_any(params, ("Q", "A1", "A2", "v1", "v2", "u", "v", "d_pipe"))
    if domain == "mechanics":
        return _has_any(params, ("u", "v", "a", "t", "s", "theta", "m"))
    if domain == "thermo":
        return _has_any(params, ("P", "V", "T", "n", "mass", "pressure", "temperature_c"))
    numeric_values = [value for key, value in params.items() if key != "canonical_problem_type" and isinstance(value, (int, float))]
    return len(numeric_values) >= 2


def _is_engineering_context_continuation(chunk: str) -> bool:
    text = (chunk or "").strip().lower()
    return bool(
        re.match(r"^(?:the|this|same)\s+(?:beam|member|pipe|fluid|gas|circuit|system|shell|cylinder)\b", text)
        or re.match(r"^part\s*\d+\b", text)
        or re.match(r"^take\b", text)
        or re.search(r"\b(reactions?|supports?|bending\s+moment|bending\s+stress|maximum\s+stress|where\s+it\s+occurs|imperfections?|post[-\s]?buckling|arc[-\s]?length|limit\s+point)\b", text)
    )


def _split_candidate_tasks(raw_input: str) -> list[str]:
    text = str(raw_input or "").strip()
    if not text:
        return []

    protected = re.sub(r"\[(.*?)\]", lambda m: m.group(0).replace(",", "§COMMA§"), text)
    protected = re.sub(r"(?<=\d)\.(?=\d)", "§DOT§", protected)
    pieces = re.split(
        r"(?:\n+|;|\.\s+|\b(?:also|then|next|and then)\b)",
        protected,
        flags=re.I,
    )
    chunks = []
    for piece in pieces:
        chunk = piece.replace("§COMMA§", ",").replace("§DOT§", ".").strip(" .;\n\t")
        if len(chunk) >= 8:
            chunks.append(chunk)
    chunks = _merge_dependent_followups(chunks)
    return chunks


def _merge_dependent_followups(chunks: list[str]) -> list[str]:
    merged: list[str] = []
    for chunk in chunks:
        if merged and _is_dependent_followup(chunk):
            merged[-1] = f"{merged[-1]}. {chunk}"
        else:
            merged.append(chunk)
    return merged


def _is_dependent_followup(chunk: str) -> bool:
    text = (chunk or "").strip().lower()
    if not re.match(r"^(?:and\s+)?(?:find|calculate|determine|compute|what\s+is)\b", text):
        return False
    has_standalone_data = bool(re.search(r"=|\[[^\]]+\]|\b\d+(?:\.\d+)?\s*(?:v|a|ohm|n|kn|m/s|kg|kpa|hz|m\^2)\b", text))
    has_new_domain_subject = bool(re.search(r"\b(matrix|beam|circuit|data|mean|regression|snell|pipe|gas|projectile)\b", text))
    return not (has_standalone_data or has_new_domain_subject)


def build_canonical_problem(raw_query: str, params: dict[str, Any] | None = None, sub: dict[str, Any] | None = None) -> CanonicalProblem:
    params = {**_extract_parameters_from_text(raw_query), **dict(params or {})}
    sub = dict(sub or {})
    normalized_text = normalize_math_text(raw_query)
    equation_strings = extract_equations(raw_query, params)
    equations = [_analyze_equation(eq) for eq in equation_strings]
    unknowns = extract_unknowns(normalized_text, params, [eq.normalized for eq in equations])
    units = extract_units(raw_query, params)
    structure = _build_structure(equations, unknowns, units, normalized_text)
    domain_scores = _score_domains(canonical_text=normalized_text, params=params, equations=equations, units=units, structure=structure, hinted_domain=str(sub.get("domain") or ""))
    domain = domain_scores[0].domain if domain_scores and domain_scores[0].confidence >= 0.35 else "unknown"
    problem_type = _infer_problem_type(domain, equations, structure, normalized_text, params, str(sub.get("problem_type") or ""))
    params = _canonicalize_params(params, equations, domain, problem_type, normalized_text, units)

    return CanonicalProblem(
        domain=domain,
        equations=equations,
        variables=unknowns,
        constraints=list(sub.get("constraints") or []),
        units=units,
        problem_type=problem_type,
        structure_properties=structure,
        domain_confidence=domain_scores,
        parameters=params,
    )


def _select_canonical_source(raw_input: str, input_summary: str, params: dict[str, Any]) -> str:
    raw = str(raw_input or "").strip()
    summary = str(input_summary or "").strip()
    if raw and summary and summary != raw:
        return f"{raw}\n{summary}"
    return raw or summary


def _has_math_signal(text: str) -> bool:
    return bool(re.search(r"=|\d\s*[A-Za-z]|[+\-*/^]|\b[a-zA-Z]\s*\(", text or ""))


def determine_methods(spec: SubProblemSpec) -> list[MethodOption]:
    structure = spec.canonical.structure_properties
    methods: list[MethodOption] = []

    if spec.domain == "algebra":
        if structure.equation_count <= 1:
            degree = structure.max_degree or 1
            if degree == 2:
                methods = [_method("quadratic_formula", spec.domain), _method("factorization", spec.domain)]
            else:
                methods = [_method("isolation", spec.domain)]
        elif structure.is_linear:
            methods = [_method("elimination", spec.domain), _method("substitution", spec.domain), _method("matrix", spec.domain)]
        else:
            methods = [_method("substitution", spec.domain)]
    elif spec.domain == "calculus":
        pt = spec.problem_type
        selected = "integration" if "integral" in pt else "differentiation" if "derivative" in pt else "series" if "series" in pt else "laplace" if "laplace" in pt else None
        methods = [_method(selected, spec.domain)] if selected else [_method("differentiation", spec.domain), _method("integration", spec.domain)]
    elif spec.domain == "ode":
        methods = [_method("characteristic", spec.domain), _method("laplace", spec.domain), _method("dsolve", spec.domain)]
    elif spec.domain == "structural":
        methods = [_method("equilibrium", spec.domain)]
        if any(key in spec.problem_type for key in ("beam", "deflection")):
            methods.append(_method("moment_area", spec.domain))
            methods.append(_method("energy", spec.domain))
    elif spec.domain in METHOD_CATALOG:
        methods = [item.model_copy() for item in METHOD_CATALOG[spec.domain]]

    for index, method in enumerate(methods):
        method.feasible = True
        method.recommended = index == 0
    return methods


def ensure_requested_method(spec: SubProblemSpec, requested_method: str | None) -> StructuredError | None:
    if not requested_method:
        return None
    allowed = {method.id for method in spec.feasible_methods if method.feasible}
    if requested_method in allowed:
        spec.selected_method = requested_method
        return None
    return StructuredError(
        message="The selected method is not valid for this problem structure.",
        suggestion="Choose one of the feasible methods returned by the backend.",
        stage="method_selection",
        retryable=True,
        retry_available=True,
        valid_methods=spec.feasible_methods,
        problem_id=spec.id,
    )


def normalize_solver_event(event: dict[str, Any], spec: SubProblemSpec) -> dict[str, Any]:
    chunk = dict(event or {})
    chunk["problem_id"] = spec.id
    if chunk.get("type") == "error":
        return structured_error(str(chunk.get("message") or chunk.get("reason") or "The solver could not complete this problem."), problem_id=spec.id, stage=str(chunk.get("stage") or "solving"))
    if chunk.get("type") == "step":
        content = chunk.get("content", "")
        if content:
            chunk["content"] = polish_display_math(normalize_math_text(content))
    if chunk.get("type") == "final":
        answer_text = str(chunk.get("answer") or "").strip()
        if re.match(r"^(error|.*solver error|.*engine error)\b", answer_text, re.I):
            return structured_error(answer_text, problem_id=spec.id, stage="solving")
        chunk["answer"] = polish_display_math(answer_text)
        chunk.setdefault("summary", [])
    return chunk


def structured_error(message: str, problem_id: str | None = None, stage: str = "solving", suggestion: str | None = None, retryable: bool = True) -> dict[str, Any]:
    return StructuredError(
        message=_humanize_error(message),
        suggestion=suggestion or "Check the problem statement, include required values and units, then retry.",
        stage=stage,
        retryable=retryable,
        retry_available=retryable,
        problem_id=problem_id,
    ).model_dump()


def solver_domain_for(spec: SubProblemSpec) -> str:
    if spec.domain == "ode" and spec.problem_type == "vibration":
        return "mechanics"
    if spec.domain == "ode":
        return "calculus"
    return spec.domain


def _analyze_equation(equation: str) -> EquationSpec:
    normalized = normalize_equation_text(equation)
    expression = normalized.replace("=", "-(", 1) + ")" if "=" in normalized else normalized
    variables = sorted(set(re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)\b", normalized)) - _FUNCTION_NAMES)
    degree = None
    is_linear = None
    try:
        local_dict = {name: sp.Symbol(name) for name in variables}
        if "=" in normalized:
            lhs, rhs = normalized.split("=", 1)
            expr = parse_expr(lhs, local_dict=local_dict, transformations=_TRANSFORMS) - parse_expr(rhs, local_dict=local_dict, transformations=_TRANSFORMS)
        else:
            expr = parse_expr(normalized, local_dict=local_dict, transformations=_TRANSFORMS)
        if variables:
            symbols = [local_dict[name] for name in variables]
            poly = sp.Poly(sp.expand(expr), *symbols)
            degree = int(poly.total_degree())
            is_linear = degree <= 1
    except Exception:
        pass
    order = _differential_order(normalized)
    return EquationSpec(raw=equation, normalized=normalized, order=order, is_linear=is_linear, degree=degree)


def _build_structure(equations: list[EquationSpec], unknowns: list[str], units: dict[str, str], text: str) -> ProblemStructure:
    degrees = [eq.degree for eq in equations if eq.degree is not None]
    orders = [eq.order for eq in equations]
    linear_values = [eq.is_linear for eq in equations if eq.is_linear is not None]
    return ProblemStructure(
        equation_count=len(equations),
        unknown_count=len(unknowns),
        is_system=len(equations) > 1,
        is_linear=all(linear_values) if linear_values else None,
        max_degree=max(degrees) if degrees else None,
        differential_order=max(orders) if orders else 0,
        has_units=bool(units),
        has_boundary_conditions=bool(re.search(r"\b(at|when)\s+[A-Za-z]\s*=|\by\(0\)|\binitial\b|\bboundary\b", text, re.I)),
    )


def _score_domains(canonical_text: str, params: dict[str, Any], equations: list[EquationSpec], units: dict[str, str], structure: ProblemStructure, hinted_domain: str = "") -> list[DomainScore]:
    scores = {domain: 0.0 for domain in _SUPPORTED_DOMAINS}
    evidence = {domain: [] for domain in _SUPPORTED_DOMAINS}

    if equations:
        algebra_score = 0.75 if not structure.has_units else 0.40
        if _has_non_algebra_intent(canonical_text):
            algebra_score *= 0.25
        scores["algebra"] += algebra_score
        evidence["algebra"].append("equation structure")
    if structure.is_system and structure.is_linear:
        scores["algebra"] += 0.25
        scores["matrix"] += 0.10
        evidence["algebra"].append("linear system structure")
        evidence["matrix"].append("linear system structure")
    if structure.differential_order > 0:
        scores["algebra"] *= 0.2
        scores["ode"] += 1.00
        scores["calculus"] += 0.25
        evidence["ode"].append("differential equation structure")
    if params.get("expression") and not equations:
        scores["calculus"] += 0.22
        evidence["calculus"].append("symbolic expression")
    lowered_text = canonical_text.lower()
    circuit_context = _has_circuit_context(lowered_text, params, units)
    shell_context = _has_shell_buckling_context(lowered_text)
    if shell_context:
        scores["structural"] += 1.25
        scores["algebra"] *= 0.15
        evidence["structural"].append("cylindrical-shell buckling/stability concepts")
    advanced_structural_context = _advanced_structural_problem_type(lowered_text)
    if advanced_structural_context:
        scores["structural"] += 1.10
        scores["algebra"] *= 0.20
        scores["circuits"] *= 0.25
        scores["mechanics"] *= 0.60
        evidence["structural"].append(f"advanced structural {advanced_structural_context.replace('_', ' ')} concepts")
    if re.search(r"\b(differentiat\w*|derivative|integrat\w*|integral|antiderivative|limit|taylor|maclaurin)\b", lowered_text):
        scores["calculus"] += 0.85
        evidence["calculus"].append("calculus operation intent")
    elif re.search(r"\bseries\b", lowered_text) and not circuit_context:
        scores["calculus"] += 0.85
        evidence["calculus"].append("calculus series intent")
    if re.search(r"(?:\bd\s*[A-Za-z]\s*/\s*d[A-Za-z]\b|\b[A-Za-z]'\s*=|\bdifferential\s+equation\b)", lowered_text):
        scores["ode"] += 0.95
        evidence["ode"].append("differential relation structure")
    if re.search(r"\b(ideal\s+gas|constant\s+pressure|closed\s+system|heated|heat\s+added|work\s+done|temperature|volume\s+doubles|steam|turbine|enthalpy|mass\s+flow)\b", lowered_text):
        scores["thermo"] += 0.70
        evidence["thermo"].append("thermodynamic process structure")
    if circuit_context:
        scores["circuits"] += 0.65
        evidence["circuits"].append("circuit structure")
    if re.search(r"\b(series|parallel)\b", lowered_text) and circuit_context:
        scores["circuits"] += 0.45
        evidence["circuits"].append("resistor network topology")
    if re.search(r"\b(ode|differential\s+equation|mass\s*[- ]spring|damper|y''|x'')\b", lowered_text):
        scores["ode"] += 0.70
        evidence["ode"].append("ODE language/structure")
    if re.search(r"\b(mass[-\s]*spring[-\s]*damper|spring[-\s]*mass[-\s]*damper|damping\s+ratio|natural\s+frequency)\b", lowered_text):
        scores["mechanics"] += 0.80
        scores["ode"] *= 0.45
        evidence["mechanics"].append("vibration system quantities")
    if re.search(r"\b(projectile|launch|trajectory|time\s+of\s+flight|kinematics|suvat|velocity|acceleration|friction|work\s+energy|centripetal)\b", lowered_text):
        scores["mechanics"] += 0.62
        evidence["mechanics"].append("mechanics motion/force structure")
    if re.search(r"\b(ball|object|car|particle)\b", lowered_text) and re.search(r"\b(thrown|falls?|lands?|height|speed|m/s|accelerates?)\b", lowered_text):
        scores["mechanics"] += 0.62
        evidence["mechanics"].append("physical motion word problem")
    if re.search(r"\b(bernoulli|continuity|pipe\s+flow|reynolds|fluid|flow\s+rate|head\s+loss|darcy|friction\s+factor|pressure\s+drop|pump|hydraulic)\b", lowered_text):
        scores["fluids"] += 0.62
        evidence["fluids"].append("fluid mechanics structure")
    if re.search(r"\b(water|fluid|pipe|inlet|outlet|narrows?|discharge)\b", lowered_text) and re.search(r"\b(flow|velocity|continuity|pipe|area)\b", lowered_text):
        scores["fluids"] += 0.78
        evidence["fluids"].append("continuity flow concepts")
    if re.search(r"\b(transfer\s+function|bode|control\s+system|step\s+response|stability|poles?|zeros?)\b", lowered_text):
        scores["controls"] += 0.62
        evidence["controls"].append("control-system structure")
    if re.search(r"\b(mean|median|standard\s+deviation|variance|regression|correlation|hypothesis|t-test|statistics|data\s*:)\b", lowered_text):
        scores["statistics"] += 0.58
        evidence["statistics"].append("statistical-analysis structure")
    if re.search(r"\b(matrix|determinant|eigenvalues?|eigenvectors?|inverse|row\s+reduc|rref)\b", lowered_text) or (params.get("matrix") is not None and not re.search(r"\b(data|mean|median|standard\s+deviation|regression|correlation)\b", lowered_text)):
        scores["matrix"] += 0.82
        evidence["matrix"].append("matrix object/operation")
    if re.search(r"\b(snell|refraction|refracted|optic|light\s+passes|wave|wavelength|doppler)\b", lowered_text):
        scores["physics"] += 0.72
        evidence["physics"].append("physics optics/wave concepts")
    if re.search(r"\b(plot|graph|chart|visuali[sz]e|draw)\b", lowered_text) and (params.get("expression") or re.search(r"\b(sin|cos|tan|log|exp|sqrt|x\^?\d*)\b", lowered_text)):
        scores["data_viz"] += 0.58
        evidence["data_viz"].append("plotting request structure")
    if re.search(r"\b(plot|graph|chart|visuali[sz]e|draw)\b", lowered_text):
        scores["data_viz"] += 0.45
        evidence["data_viz"].append("visualization intent")
    if _has_unit_family(units, ("n", "kn", "mpa", "gpa", "m^4", "nm")) and _has_any(params, ("L", "l", "span", "length", "P", "w", "E", "I", "dead_load", "live_load")):
        scores["structural"] += 0.62
        evidence["structural"].append("load/span/material quantities")
    if _has_any(params, ("L", "l", "span", "length")) and _has_any(params, ("P", "w", "point_load", "distributed_load", "udl")):
        scores["structural"] += 0.55
        evidence["structural"].append("beam length and load quantities")
    if re.search(r"\b(second\s+moment\s+of\s+area|bending\s+stress|bending\s+moment|support\s+reactions?|rectangular\s+cross-section)\b", lowered_text):
        scores["structural"] += 0.55
        evidence["structural"].append("structural response or section property concepts")
    if _has_any(params, ("V", "I", "R", "voltage", "current", "resistance", "C")) and _has_unit_family(units, ("v", "a", "ohm", "f")):
        scores["circuits"] += 0.60
        evidence["circuits"].append("electrical quantities and units")
    if re.search(r"\b(resistance|current|voltage|ohm|amps?|amperes?|volts?)\b", lowered_text) and _has_unit_family(units, ("v", "a", "ohm")):
        scores["circuits"] += 0.70
        evidence["circuits"].append("electrical word problem with units")
    if _has_any(params, ("P", "V", "T", "n", "Q", "m", "c", "p", "v", "t", "mass", "pressure", "temperature_c", "R_specific", "Cp", "volume_ratio")) and _has_unit_family(units, ("k", "j", "kj", "pa", "kpa", "mol", "kg")):
        scores["thermo"] += 0.45
        evidence["thermo"].append("thermodynamic quantities and units")
    if _has_any(params, ("mass", "pressure", "temperature_c", "R_specific", "Cp", "volume_ratio")):
        scores["thermo"] += 0.35
        evidence["thermo"].append("canonical gas-process quantities")
    if _has_any(params, ("dead_load", "live_load", "gamma_dead", "gamma_live", "bar_count", "bar_diameter", "fck", "fy", "b", "d")):
        scores["structural"] += 0.45
        evidence["structural"].append("reinforced-concrete beam design quantities")
    if _has_structural_beam_concepts(lowered_text):
        scores["structural"] += 0.72
        evidence["structural"].append("beam/support/load/response concepts")
    if hinted_domain in _SUPPORTED_DOMAINS and hinted_domain != "unknown":
        hint_bonus = 0.08 if scores.get(hinted_domain, 0.0) > 0 else 0.0
        if hint_bonus:
            scores[hinted_domain] += hint_bonus
            evidence[hinted_domain].append("parser semantic hint")

    total = max(sum(max(v, 0.0) for v in scores.values()), 1.0)
    ranked = [DomainScore(domain=domain, confidence=round(min(score / total, 1.0), 3), evidence=evidence[domain]) for domain, score in scores.items() if score > 0]
    ranked.sort(key=lambda item: item.confidence, reverse=True)
    return ranked or [DomainScore(domain="unknown", confidence=0.0, evidence=[])]


def _has_non_algebra_intent(text: str) -> bool:
    return bool(re.search(
        r"\b(plot|graph|chart|differentiat\w*|derivative|integrat\w*|integral|matrix|determinant|eigen|inverse|transfer\s+function|bode|regression|snell|wave|continuity|bernoulli|buckl\w*|shell|cylinder|cylindrical|donnell|imperfection|post[-\s]?buckling|arc[-\s]?length|column|euler|torsion|shaft|pressure\s+vessel|hoop\s+stress)\b",
        (text or "").lower(),
    ))


def _infer_problem_type(domain: str, equations: list[EquationSpec], structure: ProblemStructure, text: str, params: dict[str, Any], hinted: str) -> str:
    hinted = (hinted or "").lower()
    if domain == "ode" or structure.differential_order > 0:
        return "ode"
    if domain == "algebra":
        if structure.is_system:
            return "linear_system" if structure.is_linear else "nonlinear_system"
        if structure.max_degree == 2:
            return "quadratic_equation"
        return "single_equation"
    if domain == "calculus":
        lowered = text.lower()
        if "∫" in text or re.search(r"\bintegr", lowered):
            return "integral"
        if re.search(r"\bd/d|\bderivative|\bdifferentiat", lowered):
            return "derivative"
        if re.search(r"\blaplace\b", lowered):
            return "laplace_transform"
        if re.search(r"\bseries\b|\btaylor\b|\bmaclaurin\b", lowered):
            return "series"
        return "calculus_expression"
    if domain == "structural":
        if _has_shell_buckling_context(text):
            return "shell_buckling"
        advanced_type = _advanced_structural_problem_type(text)
        if advanced_type:
            return advanced_type
        if _has_any(params, ("dead_load", "live_load", "bar_count", "bar_diameter")):
            return "rc_beam_design"
        return "beam_analysis"
    if domain == "mechanics":
        lowered = text.lower()
        if re.search(r"\b(projectile|launch|trajectory|time\s+of\s+flight|range)\b", lowered):
            return "projectile_motion"
        if re.search(r"\b(vibration|oscillation|spring|shm)\b", lowered):
            return "vibration"
        if re.search(r"\b(friction|normal\s+force)\b", lowered):
            return "friction"
        if re.search(r"\b(work|energy|kinetic|potential)\b", lowered):
            return "work_energy"
        return "kinematics"
    if domain == "fluids":
        lowered = text.lower()
        has_continuity_quantities = _has_any(params, ("A1", "A2", "a1", "a2", "area1", "area2", "v1", "v2"))
        if re.search(r"\b(head\s+loss|darcy|friction\s+factor|pressure\s+drop|major\s+loss)\b", lowered):
            return "head_loss"
        if "bernoulli" in lowered:
            return "bernoulli_equation"
        if "continuity" in lowered or (has_continuity_quantities and re.search(r"\b(area|velocity|flow|inlet|outlet)\b", lowered)):
            return "continuity"
        if "reynolds" in lowered or "pipe" in lowered:
            return "pipe_flow"
        return "continuity"
    if domain == "controls":
        lowered = text.lower()
        if "bode" in lowered or "frequency" in lowered:
            return "bode_plot"
        if "step" in lowered and "response" in lowered:
            return "step_response"
        return "transfer_function"
    if domain == "statistics":
        lowered = text.lower()
        if re.search(r"\b(regression|correlation|linear\s+fit)\b", lowered):
            return "linear_regression"
        if re.search(r"\b(hypothesis|t-test|ttest)\b", lowered):
            return "hypothesis_test"
        return "descriptive_statistics"
    if domain == "matrix":
        lowered = text.lower()
        if "determinant" in lowered or re.search(r"\bdet\b", lowered):
            return "determinant"
        if "eigen" in lowered:
            return "eigenvalue_analysis"
        if "inverse" in lowered or "invert" in lowered:
            return "matrix_inverse"
        if re.search(r"\b(row\s+reduc|rref|echelon)\b", lowered):
            return "row_reduction"
        return "matrix_operations"
    if domain == "data_viz":
        return "function_plot"
    if domain == "circuits":
        lowered = text.lower()
        if re.search(r"\b(rc\s+circuit|rc\s+transient|capacitor|time\s+constant)\b", lowered) or _has_any(params, ("C", "capacitance", "capacitor")):
            return "rc_circuit"
        if re.search(r"\b(rl\s+circuit|rl\s+transient|inductor|inductance)\b", lowered) or _has_any(params, ("L_ind", "inductance", "inductor")):
            return "rl_circuit"
        if re.search(r"\b(series|parallel|network)\b", lowered) and _has_any(params, ("resistors", "R", "resistance")):
            return "circuit_analysis"
        return "ohms_law" if _has_any(params, ("V", "I", "R", "v", "i", "r", "voltage", "current", "resistance")) else "circuit_analysis"
    if domain == "thermo":
        if re.search(r"\b(turbine|enthalpy|h1|h2|mass\s+flow)\b", text.lower()):
            return "turbine_power"
        if _has_any(params, ("mass", "pressure", "temperature_c", "R_specific", "Cp", "volume_ratio")):
            return "constant_pressure_gas_process"
        return "ideal_gas" if _has_any(params, ("P", "V", "T", "n", "p", "v", "t")) else "thermodynamics"
    return hinted if hinted and hinted != "general" else "general"


def _has_structural_beam_concepts(text: str) -> bool:
    has_member = bool(re.search(r"\b(beams?|members?|girders?|spans?)\b", text))
    has_support = bool(re.search(r"\b(simply\s+supported|cantilever|fixed\s+end|supports?|reaction|roller|pin)\b", text))
    has_load = bool(re.search(r"\b(load|point\s+load|uniform(?:ly)?\s+distributed|udl|kn\s*/\s*m|kn\s+per\s+m|kilonewtons?\s+per\s+met(?:re|er))\b", text))
    has_response = bool(re.search(r"\b(bending\s+moment|shear\s+force|deflection|bending\s+stress|second\s+moment|moment\s+of\s+inertia|cross[-\s]?section)\b", text))
    return has_member and ((has_support and has_load) or has_response)


def _has_shell_buckling_context(text: str) -> bool:
    lowered = (text or "").lower()
    has_shell_subject = bool(re.search(r"\b(cylindrical\s+shell|thin[-\s]?walled\s+cylind(?:er|rical)|shell|cylinder)\b", lowered))
    has_stability_intent = bool(re.search(r"\b(buckl\w*|critical\s+load|donnell|imperfection|post[-\s]?buckling|arc[-\s]?length|limit\s+point|end[-\s]?shortening)\b", lowered))
    return has_shell_subject and has_stability_intent


def _advanced_structural_problem_type(text: str) -> str:
    lowered = (text or "").lower()
    if re.search(r"\b(euler\s+)?(?:column|strut)\b", lowered) and re.search(r"\b(buckl\w*|critical\s+load|p\s*cr|pcr|end\s+conditions?|pinned|fixed|free)\b", lowered):
        return "euler_column_buckling"
    if re.search(r"\b(torsion|angle\s+of\s+twist|twist|torque|shaft)\b", lowered) and re.search(r"\b(shear\s+stress|polar|diameter|solid\s+circular|hollow\s+circular|g\s*=|shear\s+modulus)\b", lowered):
        return "shaft_torsion"
    if re.search(r"\b(pressure\s+vessel|thin[-\s]?walled\s+(?:cylinder|vessel)|hoop\s+stress|longitudinal\s+stress)\b", lowered) and re.search(r"\b(pressure|internal\s+pressure|radius|thickness|wall)\b", lowered):
        return "thin_pressure_vessel"
    return ""


def _canonicalize_params(params: dict[str, Any], equations: list[EquationSpec], domain: str, problem_type: str, text: str, units: dict[str, str] | None = None) -> dict[str, Any]:
    result = dict(params)
    units = dict(units or {})
    if units:
        result.setdefault("_units", units)
    if equations and "equations" not in result:
        result["equations"] = [eq.normalized for eq in equations]
    if domain == "calculus":
        _extract_calculus_limits(result, text)
    if domain in {"calculus", "ode"} and not result.get("expression") and equations:
        result["expression"] = equations[0].normalized
    if domain == "calculus" and not result.get("expression"):
        inferred = _infer_expression_from_text(text)
        if inferred:
            result["expression"] = inferred
    if domain == "ode":
        result.setdefault("calculus_mode", "ode")
    if domain == "data_viz" and not result.get("expression"):
        inferred = _infer_expression_from_text(text)
        if inferred:
            result["expression"] = inferred
    if domain == "fluids":
        if "d_pipe" in result and "D" not in result:
            result["D"] = result["d_pipe"]
        if "A1" in result:
            result.setdefault("a1", result["A1"])
            result.setdefault("area1", result["A1"])
        if "A2" in result:
            result.setdefault("a2", result["A2"])
            result.setdefault("area2", result["A2"])
        if "v1" in result:
            result.setdefault("u", result["v1"])
        if "v2" in result:
            result.setdefault("v", result["v2"])
    if domain == "circuits":
        _scale_circuit_quantity(result, units, ("R", "r", "resistance"), "resistance")
        _scale_circuit_quantity(result, units, ("C", "c", "capacitance"), "capacitance")
        _scale_circuit_quantity(result, units, ("L", "l", "inductance"), "inductance")
        _scale_circuit_quantity(result, units, ("V", "v", "voltage"), "voltage")
    if domain == "thermo" and problem_type == "constant_pressure_gas_process":
        if "temperature_c" in result and "T1" not in result:
            result["T1"] = float(result["temperature_c"]) + 273.15
        if "pressure" in result and "P" not in result:
            result["P"] = float(result["pressure"])
        if "mass" in result and "m" not in result:
            result["m"] = result["mass"]
    if domain == "structural":
        if problem_type == "shell_buckling" or _has_shell_buckling_context(text):
            _canonicalize_shell_buckling_params(result, units, text)
        _canonicalize_beam_params(result, text)
    result.setdefault("canonical_problem_type", problem_type)
    return result


def _canonicalize_beam_params(params: dict[str, Any], text: str) -> None:
    if "h" in params and "d" not in params:
        params["d"] = params["h"]
    if params.get("I") in (None, "") and params.get("b") not in (None, "") and params.get("d") not in (None, ""):
        try:
            b_mm = float(params["b"])
            d_mm = float(params["d"])
            params["I"] = b_mm * d_mm**3 / 12.0 / 1e12
            params["I_source"] = "rectangle_bd3_over_12"
        except (TypeError, ValueError):
            pass
    lowered = text.lower()
    if "simply supported" in lowered:
        params.setdefault("support", "simply_supported")
    elif "cantilever" in lowered:
        params.setdefault("support", "cantilever")


def _canonicalize_shell_buckling_params(params: dict[str, Any], units: dict[str, str], text: str) -> None:
    if "t" in params and "t_shell" not in params:
        params["t_shell"] = params["t"]
    for key in ("R", "L", "t_shell", "delta"):
        if key not in params:
            continue
        unit = units.get(key) or (units.get("t") if key == "t_shell" else "")
        if unit:
            _scale_shell_param_in_place(params, key, unit)
    if "E" in params and units.get("E"):
        _scale_shell_param_in_place(params, "E", units["E"])

    source = str(text or "")
    label_patterns = (("R", r"radius|r"), ("L", r"length|l"), ("t_shell", r"thickness|wall\s+thickness|t"), ("E", r"young[’'`s]*\s+modulus|elastic\s+modulus|modulus|e"))
    for key, label in label_patterns:
        if key not in params:
            continue
        unit_match = re.search(rf"\b(?:{label})\b[^\d=]{{0,32}}(?:=|is|of)?\s*[-+]?\d*\.?\d+(?:e[-+]?\d+)?\s*(?:\\?,?\s*)?(?:\\text\s*\{{\s*)?([A-Za-zµμ]+)", source, re.I)
        if unit_match:
            _scale_shell_param_in_place(params, key, unit_match.group(1))

    if "delta" not in params and params.get("delta_over_t") not in (None, "") and params.get("t_shell") not in (None, ""):
        try:
            params["delta"] = float(params["delta_over_t"]) * float(params["t_shell"])
        except (TypeError, ValueError):
            pass
    params.pop("equations", None)
    params.pop("variable_meanings", None)


def _scale_shell_param_in_place(params: dict[str, Any], key: str, unit: str) -> None:
    try:
        value = float(params[key])
        normalized = (unit or "").lower().replace("μ", "u").replace("µ", "u").strip("{} ")
        if key == "E" and normalized in {"gpa", "mpa", "kpa"} and abs(value) >= 1e6:
            return
        if key != "E" and normalized in {"mm", "millimetre", "millimeter", "millimetres", "millimeters"} and abs(value) < 1.0:
            return
        if key != "E" and normalized in {"cm", "centimetre", "centimeter", "centimetres", "centimeters"} and abs(value) < 1.0:
            return
        params[key] = _scale_shell_quantity(key, value, unit)
    except (TypeError, ValueError):
        return



def _scale_circuit_quantity(params: dict[str, Any], units: dict[str, str], aliases: tuple[str, ...], quantity_type: str) -> None:
    key = next((name for name in aliases if name in params and params.get(name) not in (None, "", "?")), None)
    if not key:
        return
    unit = next((units.get(name) for name in aliases if units.get(name)), "")
    scale = _circuit_unit_scale(str(unit), quantity_type)
    if scale == 1.0:
        return
    try:
        params[key] = float(params[key]) * scale
    except (TypeError, ValueError):
        return


def _extract_calculus_limits(params: dict[str, Any], text: str) -> None:
    if params.get("lower_limit") is not None and params.get("upper_limit") is not None:
        return
    match = re.search(r"\bfrom\s+([-+]?\d*\.?\d+|pi|π)\s*\*?\s*(?:to|t\s*\*\s*o)\s+([-+]?\d*\.?\d+|pi|π)\b", text or "", re.I)
    if not match:
        return
    params.setdefault("lower_limit", _normalize_limit_token(match.group(1)))
    params.setdefault("upper_limit", _normalize_limit_token(match.group(2)))


def _normalize_limit_token(value: str) -> str:
    token = str(value or "").strip().lower().replace("π", "pi")
    return "pi" if token == "pi" else token


def _circuit_unit_scale(unit: str, quantity_type: str) -> float:
    normalized = unit.strip().lower().replace("ω", "ohm").replace("Ω", "ohm").replace("µ", "u")
    normalized = normalized.replace(" ", "")
    if quantity_type == "resistance":
        if normalized in {"kohm", "kiloohm", "kiloohms", "kω"}:
            return 1e3
        if normalized in {"mohm", "megaohm", "megaohms", "mω"}:
            return 1e6
    if quantity_type == "capacitance":
        if normalized in {"mf", "millifarad", "millifarads"}:
            return 1e-3
        if normalized in {"uf", "microfarad", "microfarads"}:
            return 1e-6
        if normalized in {"nf", "nanofarad", "nanofarads"}:
            return 1e-9
        if normalized in {"pf", "picofarad", "picofarads"}:
            return 1e-12
    if quantity_type == "inductance":
        if normalized in {"mh", "millihenry", "millihenries"}:
            return 1e-3
        if normalized in {"uh", "microhenry", "microhenries"}:
            return 1e-6
    if quantity_type == "voltage":
        if normalized in {"kv", "kilovolt", "kilovolts"}:
            return 1e3
        if normalized in {"mv", "millivolt", "millivolts"}:
            return 1e-3
    return 1.0


def _infer_expression_from_text(text: str) -> str:
    lowered = (text or "").lower()
    named = [
        (r"\bsin(e)?\b", "sin(x)"),
        (r"\bcos(ine)?\b", "cos(x)"),
        (r"\btan(gent)?\b", "tan(x)"),
        (r"\bexp(onential)?\b", "exp(x)"),
        (r"\blog(arithm)?\b|\bln\b", "log(x)"),
        (r"\bsqrt|square\s+root\b", "sqrt(x)"),
        (r"\bx\s*(?:\^|\*\*)\s*2\b|x\s+squared", "x**2"),
        (r"\bx\s*(?:\^|\*\*)\s*3\b|x\s+cubed", "x**3"),
    ]
    explicit = re.search(r"(?:y|f\s*\(\s*x\s*\)|s\s*\(\s*t\s*\))\s*=\s*([^,.;]+)", text or "", re.I)
    if explicit:
        return _strip_expression_range_words(normalize_math_text(explicit.group(1)))
    operation = re.search(r"\b(?:differentiate|integrate|plot|graph)\s+(.+?)(?:\s+(?:with\s+respect\s+to|from|over)\b|[.;]|$)", text or "", re.I)
    if operation:
        candidate = operation.group(1).strip()
        if re.search(r"[A-Za-z]\s*(?:\^|\*\*)|\b(?:sin|cos|tan|log|sqrt|exp)\b|[+*/]", candidate, re.I):
            return _strip_expression_range_words(normalize_math_text(candidate))
    for pattern, expression in named:
        if re.search(pattern, lowered):
            return expression
    return ""


def _strip_expression_range_words(expression: str) -> str:
    value = str(expression or "")
    value = re.sub(r"\s*\*?\s*with\s+respect\s+to\s+[A-Za-z].*$", "", value, flags=re.I)
    value = re.sub(r"\s*\*?\s*(?:from|over)\s+[-+]?\d*\.?\d+.*$", "", value, flags=re.I)
    value = re.sub(r"\s*\*?\s*to\s+[-+]?\d*\.?\d+.*$", "", value, flags=re.I)
    return value.strip(" ,")



def _singular_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z]", "", name or "").lower()
    if cleaned.endswith("ies") and len(cleaned) > 3:
        return cleaned[:-3] + "y"
    if cleaned.endswith("s") and len(cleaned) > 1:
        return cleaned[:-1]
    return cleaned


def _symbol_for_name(name: str, used: set[str]) -> str:
    for char in _singular_name(name):
        if char.isalpha() and char not in used:
            used.add(char)
            return char
    fallback = f"v{len(used) + 1}"
    used.add(fallback)
    return fallback


def _extract_linear_cost_equations(raw_text: str) -> tuple[list[str], dict[str, str]]:
    source = raw_text or ""
    pattern = re.compile(
        r"(?:(\d+)\s+)?([A-Za-z][A-Za-z-]*)\s+(?:and|&)\s+(?:(\d+)\s+)?([A-Za-z][A-Za-z-]*)\s+"
        r"(?:cost|costs|total|is|=)\s*(?:₦|N|\$|USD|NGN)?\s*([\d,]+(?:\.\d+)?)",
        re.I,
    )
    matches = pattern.findall(source)
    if len(matches) < 2:
        sentence_pattern = re.compile(
            r"([^.;]*?)(?:cost|costs|total|is|=)\s*(?:₦|N|\$|USD|NGN)?\s*([\d,]+(?:\.\d+)?)",
            re.I,
        )
        count_word = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an)"
        parsed_rows: list[tuple[dict[str, int], str]] = []
        for lhs_text, total in sentence_pattern.findall(source):
            counts: dict[str, int] = {}
            for count_raw, item in re.findall(rf"\b({count_word})\s+([A-Za-z][A-Za-z-]*)\b", lhs_text, re.I):
                item_name = _singular_name(item)
                if item_name in {"and", "cost", "total"}:
                    continue
                counts[item_name] = counts.get(item_name, 0) + _count_word_to_int(count_raw)
            if counts:
                parsed_rows.append((counts, total.replace(",", "")))
        item_names: list[str] = []
        for counts, _ in parsed_rows:
            for item_name in counts:
                if item_name not in item_names:
                    item_names.append(item_name)
        if len(parsed_rows) >= 2 and len(item_names) >= 2:
            used_symbols: set[str] = set()
            symbol_map = {name: _symbol_for_name(name, used_symbols) for name in item_names}
            equations = []
            for counts, total in parsed_rows[: len(item_names)]:
                terms = [f"{counts.get(name, 0)}*{symbol_map[name]}" for name in item_names if counts.get(name, 0)]
                equations.append(f"{' + '.join(terms)} = {total}")
            meanings = {symbol: name for name, symbol in symbol_map.items()}
            return equations, meanings
    if len(matches) < 2:
        return [], {}

    names: list[str] = []
    for _, first_name, _, second_name, _ in matches:
        for item in (_singular_name(first_name), _singular_name(second_name)):
            if item and item not in names:
                names.append(item)
    if len(names) < 2:
        return [], {}

    used_symbols: set[str] = set()
    symbol_map = {name: _symbol_for_name(name, used_symbols) for name in names}
    equations: list[str] = []
    for first_count, first_name, second_count, second_name, total in matches:
        first_count = first_count or "1"
        second_count = second_count or "1"
        left = f"{first_count}*{symbol_map[_singular_name(first_name)]} + {second_count}*{symbol_map[_singular_name(second_name)]}"
        right = total.replace(",", "")
        equations.append(f"{left} = {right}")
    meanings = {symbol: name for name, symbol in symbol_map.items()}
    return equations, meanings


def _count_word_to_int(value: str) -> int:
    lowered = (value or "").lower()
    if lowered in {"a", "an"}:
        return 1
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    if lowered in words:
        return words[lowered]
    try:
        return int(float(lowered))
    except ValueError:
        return 1

def _method(method_id: str | None, domain: str) -> MethodOption:
    for method in METHOD_CATALOG.get(domain, []):
        if method.id == method_id:
            return method.model_copy()
    return MethodOption(id=method_id or "symbolic", label=(method_id or "symbolic").replace("_", " ").title())


def _auto_select_method(spec: SubProblemSpec) -> str | None:
    if len(spec.feasible_methods) == 1:
        return spec.feasible_methods[0].id
    for method in spec.feasible_methods:
        if method.recommended:
            return method.id
    return None


def _differential_order(text: str) -> int:
    if re.search(r"d\s*\*\*?\s*\d+|d\^\d+|y''|[A-Za-z]\s*''", text):
        return 2
    if re.search(r"d\s*/\s*d|dy\s*/\s*dx|[A-Za-z]\s*'|Derivative\(", text):
        return 1
    return 0


def _has_any(params: dict[str, Any], names: tuple[str, ...]) -> bool:
    return any(name in params and params.get(name) not in (None, "", "?") for name in names)


def _has_unit_family(units: dict[str, str], unit_tokens: tuple[str, ...]) -> bool:
    unit_values = [str(unit).lower().replace("ω", "ohm") for unit in units.values()]
    normalized_units: set[str] = set()
    for unit in unit_values:
        normalized_units.add(unit)
        normalized_units.update(part for part in re.split(r"[^a-z0-9^]+", unit) if part)
    return any(token.lower().replace("ω", "ohm") in normalized_units for token in unit_tokens)


def _has_circuit_context(text: str, params: dict[str, Any], units: dict[str, str]) -> bool:
    return (
        bool(re.search(r"\b(rc\s+circuit|rl\s+circuit|resistors?|capacitors?|inductors?|voltage|current|ohms?|amps?|amperes?|volts?|battery|circuit)\b", text))
        or _has_any(params, ("resistors", "V", "I", "R", "voltage", "current", "resistance", "C", "capacitance", "L_ind", "inductance"))
        or _has_unit_family(units, ("v", "a", "ohm", "f"))
    )


def _extract_parameters_from_text(text: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if not text:
        return params
    raw_text = _replace_number_words(str(text))
    lowered = raw_text.lower()
    normalized = normalize_math_text(text)
    target_variable = _extract_target_variable(raw_text)
    if target_variable:
        params["target_variable"] = target_variable
    assignment = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)", re.I)
    for match in assignment.finditer(normalized):
        name, value = match.groups()
        segment_start = max(normalized.rfind(delimiter, 0, match.start()) for delimiter in (";", ",", "\n")) + 1
        lhs_prefix = normalized[segment_start:match.start()]
        if re.search(r"[+\-*/^]|\b[A-Za-z][A-Za-z0-9_]*\b", lhs_prefix.strip()):
            continue
        try:
            params[name] = float(value) if any(ch in value.lower() for ch in (".", "e")) else int(value)
        except ValueError:
            params[name] = value
    for name, value in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*([-+]?\d*\.?\d+[eE][-+]?\d+)\b", raw_text):
        params[name] = float(value)
    quantity_patterns = {
        "L": r"\b(?:span|length)\s*(?:of|is|=)?\s*([-+]?\d*\.?\d+)",
        "w": r"\b(?:udl|uniformly\s+distributed\s+load|distributed\s+load|load\s+intensity)\s*(?:of|is|=)?\s*([-+]?\d*\.?\d+)",
        "P": r"\b(?:point\s+load|force)\s*(?:of|is|=)?\s*([-+]?\d*\.?\d+)",
        "theta": r"\b(?:angle|theta)\s*(?:of|is|=|at)?\s*([-+]?\d*\.?\d+)",
        "u": r"\b(?:initial\s+velocity|launch\s+speed|speed|velocity)\s*(?:of|is|=|at)?\s*([-+]?\d*\.?\d+)",
        "v": r"\b(?:final\s+velocity|outlet\s+velocity|exit\s+velocity)\s*(?:of|is|=)?\s*([-+]?\d*\.?\d+)",
        "a": r"\b(?:acceleration)\s*(?:of|is|=)?\s*([-+]?\d*\.?\d+)",
        "t": r"\b(?:time)\s*(?:of|is|=)?\s*([-+]?\d*\.?\d+)",
        "s": r"\b(?:displacement|distance)\s*(?:of|is|=)?\s*([-+]?\d*\.?\d+)",
        "m": r"\b(?:mass)\s*(?:of|is|=)?\s*([-+]?\d*\.?\d+)",
        "Q": r"\b(?:flow\s+rate|discharge)\s*(?:of|is|=)?\s*([-+]?\d*\.?\d+)",
        "d_pipe": r"\b(?:pipe\s+diameter|diameter)\s*(?:of|is|=)?\s*([-+]?\d*\.?\d+)",
    }
    for name, pattern in quantity_patterns.items():
        if name in params:
            continue
        match = re.search(pattern, normalized, re.I) or re.search(pattern, raw_text, re.I)
        if match:
            value = match.group(1)
            params[name] = float(value) if "." in value else int(value)

    _extract_beam_quantities(raw_text, params)
    _extract_shell_buckling_quantities(raw_text, params)
    _extract_advanced_structural_quantities(raw_text, params)
    _extract_general_engineering_quantities(raw_text, params)

    semantic_patterns = {
        "L": r"\b(?:spans?|span\s*=|length\s+of)\s+([-+]?\d*\.?\d+)",
        "dead_load": r"\bdead\s+load\s+(?:of|=|is)?\s*([-+]?\d*\.?\d+)",
        "live_load": r"\blive\s+load\s+(?:of|=|is)?\s*([-+]?\d*\.?\d+)",
        "gamma_dead": r"\b(?:load\s+factor|factor)\s+of\s+([-+]?\d*\.?\d+)\s+for\s+dead",
        "gamma_live": r"\b([-+]?\d*\.?\d+)\s+for\s+live",
        "d": r"\beffective\s+depth\s+d\s*=\s*([-+]?\d*\.?\d+)",
        "fy": r"\b(?:fy|steel\s+yield\s+strength)\s*=*\s*([-+]?\d*\.?\d+)",
        "mass": r"\bcontains\s+([-+]?\d*\.?\d+)\s*kg",
        "pressure": r"\bat\s+([-+]?\d*\.?\d+)\s*kpa",
        "temperature_c": r"\band\s+([-+]?\d*\.?\d+)\s*°?c",
        "R_specific": r"\bR\s*=\s*([-+]?\d*\.?\d+)\s*kJ/kg",
        "Cp": r"\bCp\s*=\s*([-+]?\d*\.?\d+)",
        "frequency": r"\b(?:frequency|f)\s*(?:of|is|=)?\s*([-+]?\d*\.?\d+)",
    }
    for name, pattern in semantic_patterns.items():
        if name not in params:
            match = re.search(pattern, raw_text, re.I)
            if match:
                value = match.group(1)
                params[name] = float(value) if "." in value else int(value)

    section_match = re.search(r"(\d+)\s*mm\s+wide\s*[×x]\s*(\d+)\s*mm\s+deep", raw_text, re.I)
    if section_match:
        params.setdefault("b", int(section_match.group(1)))
        params.setdefault("h", int(section_match.group(2)))
    concrete_match = re.search(r"\bC\s*(\d+)\b", raw_text, re.I)
    if concrete_match:
        params.setdefault("fck", int(concrete_match.group(1)))
    bars_match = re.search(r"\b(\d+)\s*T\s*(\d+)\b", raw_text, re.I)
    if bars_match:
        params.setdefault("bar_count", int(bars_match.group(1)))
        params.setdefault("bar_diameter", int(bars_match.group(2)))
    if "volume doubles" in lowered or "volume is doubled" in lowered:
        params.setdefault("volume_ratio", 2.0)
    if "simply supported" in lowered:
        params.setdefault("support", "simply_supported")
    if "cantilever" in lowered and "simply supported" not in lowered:
        params.setdefault("support", "cantilever")
    cost_equations, variable_meanings = _extract_linear_cost_equations(raw_text)
    if cost_equations and "equations" not in params:
        params["equations"] = cost_equations
        params["variable_meanings"] = variable_meanings

    matrix_match = re.search(r"(?:matrix|A)", raw_text, re.I)
    bracket_rows = re.findall(r"\[\s*([-+0-9.,\s]+?)\s*\]", raw_text)
    if matrix_match and len(bracket_rows) >= 1 and "matrix" not in params:
        rows = []
        for row_text in bracket_rows:
            values = [float(item) for item in re.findall(r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?", row_text, re.I)]
            if values:
                rows.append(values)
        if rows and len({len(row) for row in rows}) == 1:
            params["matrix"] = rows

    data_match = re.search(r"\b(?:data|values?|numbers?|set|list)\s*[:=]\s*\[?([\d.,\s+-]+)\]?", raw_text, re.I)
    if data_match and "data" not in params:
        values = [float(item) for item in re.findall(r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?", data_match.group(1), re.I)]
        if len(values) >= 2:
            params["data"] = values

    coeff_match = re.search(r"(?:den|denominator)\s*[:=]\s*\[([^\]]+)\]", raw_text, re.I)
    if coeff_match and "den" not in params:
        params["den"] = [float(item) for item in re.findall(r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?", coeff_match.group(1), re.I)]
    coeff_match = re.search(r"(?:num|numerator)\s*[:=]\s*\[([^\]]+)\]", raw_text, re.I)
    if coeff_match and "num" not in params:
        params["num"] = [float(item) for item in re.findall(r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?", coeff_match.group(1), re.I)]

    resistor_match = re.search(r"(?:resistors?|resistance values?)\s*[:=]\s*\[?([\d.,\s+-]+)\]?", raw_text, re.I)
    if resistor_match and "resistors" not in params:
        values = [float(item) for item in re.findall(r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?", resistor_match.group(1), re.I)]
        if values:
            params["resistors"] = values

    _extract_circuit_quantities(raw_text, params)

    if "equations" not in params:
        equations = extract_equations(text, params)
        if equations:
            params["equations"] = equations
    return params


def _extract_circuit_quantities(text: str, params: dict[str, Any]) -> None:
    source = str(text or "")
    if not re.search(r"\b(circuits?|resistors?|resistance|capacitors?|capacitance|inductors?|inductance|voltage|current|ohms?|amps?|amperes?|volts?|battery)\b|Ω", source, re.I):
        return
    if "V" not in params and "voltage" not in params:
        voltage_match = re.search(r"\b([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(?:v|volts?)\b", source, re.I)
        if voltage_match:
            params["V"] = _number_value(voltage_match.group(1))
    if "I" not in params and "current" not in params:
        current_match = re.search(r"\b([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(?:a|amps?|amperes?)\b", source, re.I)
        if current_match:
            params["I"] = _number_value(current_match.group(1))
    if "resistors" not in params:
        resistor_values = [
            _number_value(value)
            for value in re.findall(r"\b([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(?:ohms?|Ω)\b", source, re.I)
        ]
        if len(resistor_values) > 1:
            params["resistors"] = resistor_values
        elif len(resistor_values) == 1 and "R" not in params and "resistance" not in params:
            params["R"] = resistor_values[0]
    lowered = source.lower()
    if "mode" not in params:
        if re.search(r"\bparallel\b", lowered):
            params["mode"] = "parallel"
        elif re.search(r"\bseries\b", lowered):
            params["mode"] = "series"


def _number_value(value: str) -> int | float:
    return float(value) if "." in value or "e" in value.lower() else int(value)


def _extract_target_variable(text: str) -> str | None:
    patterns = [
        r"\bsolve\s+for\s+([A-Za-z])\b",
        r"\bsolve\b.*?\bfor\s+([A-Za-z])\b",
        r"\bmake\s+([A-Za-z])\s+the\s+subject\b",
        r"\bexpress\s+([A-Za-z])\s+in\s+terms\s+of\b",
        r"\bfind\s+([A-Za-z])\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if match:
            return match.group(1).lower()
    return None


def _replace_number_words(text: str) -> str:
    numbers = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
        "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
        "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
        "eighty": 80, "ninety": 90,
    }
    value = text
    for word, number in sorted(numbers.items(), key=lambda item: len(item[0]), reverse=True):
        value = re.sub(rf"\b{word}\b", str(number), value, flags=re.I)
    return value


def _extract_general_engineering_quantities(raw_text: str, params: dict[str, Any]) -> None:
    source = str(raw_text or "")
    lowered = source.lower()

    if "n1" not in params:
        match = re.search(r"\bn1\s*=\s*([-+]?\d*\.?\d+)", source, re.I)
        if match:
            params["n1"] = _coerce_number(match.group(1))
    if "n2" not in params:
        match = re.search(r"\bn2\s*=\s*([-+]?\d*\.?\d+)", source, re.I)
        if match:
            params["n2"] = _coerce_number(match.group(1))
    if "theta1" not in params:
        match = re.search(r"\b(?:theta1|angle|incidence\s+angle)\s*(?:=|of|is)?\s*([-+]?\d*\.?\d+)\s*(?:degrees?|°)?", source, re.I)
        if match:
            params["theta1"] = _coerce_number(match.group(1))

    if "frequency" not in params:
        match = re.search(r"\b(?:frequency|f)\s*(?:=|of|is)?\s*([-+]?\d*\.?\d+)\s*(?:hz|hertz)?", source, re.I)
        if match:
            params["frequency"] = _coerce_number(match.group(1))
    if "wavelength" not in params:
        match = re.search(r"\b(?:wavelength|lambda)\s*(?:=|of|is)?\s*([-+]?\d*\.?\d+)\s*(?:m|met(?:re|er)s?)?", source, re.I)
        if match:
            params["wavelength"] = _coerce_number(match.group(1))

    if "A1" not in params:
        match = re.search(r"\b(?:A1|area\s*1|inlet\s+area|from(?:\s+area)?)\s*(?:=|of|is)?\s*([-+]?\d*\.?\d+)\s*(?:m\^2|m²|square\s+met(?:re|er)s?)", source, re.I)
        if match:
            params["A1"] = _coerce_number(match.group(1))
    if "A2" not in params:
        match = re.search(r"\b(?:A2|area\s*2|outlet\s+area|to(?:\s+area)?)\s*(?:=|of|is)?\s*([-+]?\d*\.?\d+)\s*(?:m\^2|m²|square\s+met(?:re|er)s?)", source, re.I)
        if match:
            params["A2"] = _coerce_number(match.group(1))
    if "v1" not in params:
        match = re.search(r"\b(?:v1|inlet\s+velocity|inlet\s+speed|velocity|speed)\s*(?:=|of|is|at)?\s*([-+]?\d*\.?\d+)\s*m/s", source, re.I)
        if match:
            params["v1"] = _coerce_number(match.group(1))

    _extract_projectile_quantities(source, params)
    _extract_fluid_head_loss_quantities(source, params)
    _extract_vibration_quantities(source, params)
    _extract_turbine_quantities(source, params)
    _extract_thermo_process_quantities(source, params)

    if "x" not in params:
        match = re.search(r"\bx\s*=\s*\[([^\]]+)\]", source, re.I)
        if match:
            params["x"] = [float(item) for item in re.findall(r"[-+]?\d*\.?\d+", match.group(1))]
    if "y" not in params:
        match = re.search(r"\by\s*=\s*\[([^\]]+)\]", source, re.I)
        if match:
            params["y"] = [float(item) for item in re.findall(r"[-+]?\d*\.?\d+", match.group(1))]
    if "data" not in params and re.search(r"\b(mean|median|standard\s+deviation|variance|class\s+scored|scores?)\b", lowered):
        values = [float(item) for item in re.findall(r"[-+]?\d*\.?\d+", source)]
        if len(values) >= 2:
            params["data"] = values


def _extract_projectile_quantities(source: str, params: dict[str, Any]) -> None:
    lowered = source.lower()
    if not re.search(r"\b(projectile|launch(?:ed)?|thrown|trajectory|time\s+of\s+flight|horizontal\s+range)\b", lowered):
        return
    if "u" not in params and "initial_velocity" not in params:
        speed_match = re.search(r"\b(?:at|with|speed\s+of|initial\s+speed\s+of|initial\s+velocity\s+of)?\s*([-+]?\d*\.?\d+)\s*m/s\b", source, re.I)
        if speed_match:
            params["u"] = _coerce_number(speed_match.group(1))
    if "theta" not in params and "angle" not in params:
        angle_match = re.search(r"\b(?:at\s+an\s+angle\s+of|angle\s+of|at)?\s*([-+]?\d*\.?\d+)\s*(?:degrees?|°)\b", source, re.I)
        if angle_match:
            params["theta"] = _coerce_number(angle_match.group(1))


def _extract_thermo_process_quantities(source: str, params: dict[str, Any]) -> None:
    lowered = source.lower()
    if not re.search(r"\b(air|gas|ideal\s+gas|constant\s+pressure|heated|volume\s+doubles?)\b", lowered):
        return
    if "mass" not in params and "m" not in params:
        mass_match = re.search(r"\b([-+]?\d*\.?\d+)\s*kg\s+(?:of\s+)?(?:air|gas|steam|nitrogen|oxygen)\b", source, re.I)
        if mass_match:
            params["mass"] = _coerce_number(mass_match.group(1))
    if "pressure" not in params and "P" not in params:
        pressure_match = re.search(r"\b(?:at\s+)?([-+]?\d*\.?\d+)\s*kpa\b", source, re.I)
        if pressure_match:
            params["pressure"] = _coerce_number(pressure_match.group(1))
    if "temperature_c" not in params:
        temp_match = re.search(r"\b(?:and|at)?\s*([-+]?\d*\.?\d+)\s*(?:°\s*c|deg(?:rees?)?\s*c|celsius)\b", source, re.I)
        if temp_match:
            params["temperature_c"] = _coerce_number(temp_match.group(1))
    if "volume_ratio" not in params:
        if re.search(r"\bvolume\s+(?:doubles|is\s+doubled)\b", lowered):
            params["volume_ratio"] = 2.0
        else:
            ratio_match = re.search(r"\bvolume\s+(?:becomes|is)\s+([-+]?\d*\.?\d+)\s+times\b", source, re.I)
            if ratio_match:
                params["volume_ratio"] = float(ratio_match.group(1))


def _extract_fluid_head_loss_quantities(source: str, params: dict[str, Any]) -> None:
    lowered = source.lower()
    if not re.search(r"\b(head\s+loss|darcy|friction\s+factor|pressure\s+drop|pipe)\b", lowered):
        return
    if "D" not in params and "d" not in params:
        diameter_match = re.search(r"\b(?:pipe\s+)?(?:diameter|d)\s*(?:=|is|of)?\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(mm|cm|m)?\b", source, re.I)
        if not diameter_match:
            diameter_match = re.search(r"\b([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(mm|cm|m)\s+diameter\s+pipe\b", source, re.I)
        if diameter_match:
            value = float(diameter_match.group(1))
            unit = (diameter_match.group(2) or "m").lower()
            if unit == "mm":
                value *= 1e-3
            elif unit == "cm":
                value *= 1e-2
            params["D"] = value
    if "L" not in params and "length" not in params:
        match = re.search(r"\b(?:length|l)\s*(?:=|is|of)?\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*m\b", source, re.I)
        if match:
            params["L"] = float(match.group(1))
    if "v" not in params and "velocity" not in params:
        match = re.search(r"\b(?:velocity|speed|v)\s*(?:=|is|of)?\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*m/s\b", source, re.I)
        if match:
            params["v"] = float(match.group(1))
    if "f" not in params and "friction" not in params:
        match = re.search(r"\b(?:darcy\s+)?friction\s+factor\s*(?:f\s*)?(?:=|is|of)?\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\b", source, re.I)
        if match:
            params["f"] = float(match.group(1))


def _extract_vibration_quantities(source: str, params: dict[str, Any]) -> None:
    lowered = source.lower()
    if not re.search(r"\b(vibration|mass[-\s]*spring|spring[-\s]*mass|damper|damping\s+ratio|natural\s+frequency)\b", lowered):
        return
    patterns = {
        "m": r"\b(?:mass|m)\s*(?:=|is|of)?\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*kg\b",
        "c": r"\b(?:damping\s+coefficient|damper|c)\s*(?:=|is|of)?\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(?:n\s*s/m|n\s*sec/m|ns/m)?\b",
        "k": r"\b(?:spring\s+constant|stiffness|k)\s*(?:=|is|of)?\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(?:n/m)?\b",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, source, re.I)
        if match:
            params[key] = float(match.group(1))
    if "w" in params and params.get("w") == params.get("k"):
        params.pop("w", None)


def _extract_turbine_quantities(source: str, params: dict[str, Any]) -> None:
    lowered = source.lower()
    if not re.search(r"\b(turbine|enthalpy|steam|h1|h2|mass\s+flow)\b", lowered):
        return
    for key in ("h1", "h2"):
        if key not in params:
            match = re.search(rf"\b{key}\s*=\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(kj/kg|j/kg)?\b", source, re.I)
            if match:
                value = float(match.group(1))
                if (match.group(2) or "").lower() == "j/kg":
                    value /= 1000.0
                params[key] = value
    if "m_dot" not in params:
        match = re.search(r"\b(?:mass\s+flow(?:\s+rate)?|m_dot|ṁ)\s*(?:=|is|of)?\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*kg/s\b", source, re.I)
        if match:
            params["m_dot"] = float(match.group(1))


def _extract_beam_quantities(raw_text: str, params: dict[str, Any]) -> None:
    source = str(raw_text or "")
    lowered = source.lower()
    numeric = r"([-+]?\d*\.?\d+)"

    if "L" not in params:
        patterns = [
            rf"\bL\s*=\s*{numeric}\s*(?:m|met(?:re|er)s?)\b",
            rf"\b(?:beam|member|girder)\s+{numeric}\s*(?:m|met(?:re|er)s?)\s+long\b",
            rf"\b{numeric}\s*(?:m|met(?:re|er)s?)\s+(?:long|span|beam|member|girder)\b",
            rf"\b(?:spanning|span\s+of|span\s*=|length\s+of)\s*{numeric}\s*(?:m|met(?:re|er)s?)\b",
        ]
        value = _first_numeric_match(patterns, source)
        if value is not None:
            params["L"] = value

    for key, pattern in {
        "E": rf"\bE\s*=\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(GPa|MPa|Pa)?\b",
        "I": rf"\bI\s*=\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*(m\^4|m4|mm\^4|mm4)?\b",
    }.items():
        match = re.search(pattern, source, re.I)
        if match:
            value = float(match.group(1))
            unit = (match.group(2) or "").lower()
            if key == "E" and unit == "gpa":
                value *= 1e9
            elif key == "E" and unit == "mpa":
                value *= 1e6
            elif key == "I" and unit in {"mm^4", "mm4"}:
                value *= 1e-12
            params[key] = value

    if "w" not in params:
        patterns = [
            rf"\b(?:udl|uniform(?:ly)?\s+distributed\s+load|distributed\s+load|load\s+intensity)\D{{0,24}}{numeric}\s*(?:k?N\s*/\s*m|k?N\s+per\s+m|kilonewtons?\s+per\s+met(?:re|er))",
            rf"\b{numeric}\s*(?:k?N\s*/\s*m|k?N\s+per\s+m|kilonewtons?\s+per\s+met(?:re|er))\b",
        ]
        value = _first_numeric_match(patterns, source)
        if value is not None:
            params["w"] = value

    if "P" not in params:
        patterns = [
            rf"\b(?:point\s+load|concentrated\s+load)\D{{0,18}}{numeric}\s*(?:k?N|kilonewtons?|newtons?)\b",
            rf"\b{numeric}\s*(?:k?N|kilonewtons?|newtons?)\s+(?:point\s+load|concentrated\s+load)\b",
        ]
        value = _first_numeric_match(patterns, source)
        if value is not None:
            params["P"] = value

    if "a" not in params and re.search(r"\b(?:center|centre|midspan|mid-span)\b", lowered):
        if "L" in params:
            try:
                params["a"] = float(params["L"]) / 2.0
            except (TypeError, ValueError):
                pass

    section_patterns = [
        rf"\b(?:rectangular\s+)?cross[-\s]?section\D{{0,40}}{numeric}\s*mm\s+(?:wide|breadth|breadth\s*b)\D{{0,20}}{numeric}\s*mm\s+(?:deep|depth|height)",
        rf"\b{numeric}\s*mm\s+(?:wide|breadth)\s+(?:and|by|x|\*)\s+{numeric}\s*mm\s+(?:deep|depth|high)",
    ]
    if "b" not in params or ("h" not in params and "d" not in params):
        for pattern in section_patterns:
            match = re.search(pattern, source, re.I)
            if match:
                params.setdefault("b", _coerce_number(match.group(1)))
                params.setdefault("h", _coerce_number(match.group(2)))
                params.setdefault("d", _coerce_number(match.group(2)))
                break


def _extract_shell_buckling_quantities(raw_text: str, params: dict[str, Any]) -> None:
    source = str(raw_text or "")
    if not _has_shell_buckling_context(source):
        return

    value = r"([-+]?\d*\.?\d+(?:e[-+]?\d+)?)"
    unit = r"(?:\s*\\?,?\s*(?:\\text\s*\{\s*)?([A-Za-zµμ]+)(?:\s*\})?)?"

    patterns = {
        "R": [rf"\b(?:radius|r)\b(?:\s*\$?\s*r\s*\$?)?\s*(?:=|is|of)?\s*{value}{unit}"],
        "t_shell": [rf"\b(?:thickness|shell\s+thickness|wall\s+thickness|t)\b(?:\s*\$?\s*t\s*\$?)?\s*(?:=|is|of)?\s*{value}{unit}"],
        "L": [rf"\b(?:length|shell\s+length|l)\b(?:\s*\$?\s*l\s*\$?)?\s*(?:=|is|of)?\s*{value}{unit}"],
        "E": [rf"\b(?:young[’'`s]*\s+modulus|elastic\s+modulus|modulus|e)\b(?:\s*\$?\s*e\s*\$?)?\s*(?:=|is|of)?\s*{value}{unit}"],
        "nu": [rf"\b(?:poisson[’'`s]*\s+ratio|nu|ν)\b(?:\s*\$?\s*(?:nu|ν)\s*\$?)?\s*(?:=|is)?\s*{value}"],
        "n": [rf"\bn\s*=\s*{value}\b", rf"\bwave\s*number\s*(?:n\s*)?(?:=|is)?\s*{value}\b"],
    }
    for name, name_patterns in patterns.items():
        for pattern in name_patterns:
            match = re.search(pattern, source, re.I)
            if not match:
                continue
            numeric_value = float(match.group(1))
            unit_text = match.group(2) if len(match.groups()) >= 2 else ""
            params[name] = _scale_shell_quantity(name, numeric_value, unit_text or "")
            break

    if "delta" not in params:
        delta_match = re.search(r"\b(?:delta|δ)\s*=\s*([-+]?\d*\.?\d+)\s*(?:\*?\s*)?(?:t\b|thickness\b)", source, re.I)
        if delta_match:
            try:
                params["delta_over_t"] = float(delta_match.group(1))
            except ValueError:
                pass
        else:
            absolute_delta = re.search(r"\b(?:imperfection\s+amplitude|delta|δ)\s*(?:=|is)?\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*([A-Za-zµμ]+)?", source, re.I)
            if absolute_delta:
                params["delta"] = _scale_shell_quantity("length", float(absolute_delta.group(1)), absolute_delta.group(2) or "")


def _scale_shell_quantity(name: str, value: float, unit: str) -> float:
    normalized = (unit or "").lower().replace("μ", "u").replace("µ", "u")
    normalized = normalized.strip("{} ")
    if name == "E":
        if normalized in {"gpa"}:
            return value * 1e9
        if normalized in {"mpa"}:
            return value * 1e6
        if normalized in {"kpa"}:
            return value * 1e3
        return value
    if normalized in {"mm", "millimetre", "millimeter", "millimetres", "millimeters"}:
        return value * 1e-3
    if normalized in {"cm", "centimetre", "centimeter", "centimetres", "centimeters"}:
        return value * 1e-2
    if normalized in {"um", "micrometre", "micrometer", "micrometres", "micrometers"}:
        return value * 1e-6
    return value


def _extract_advanced_structural_quantities(raw_text: str, params: dict[str, Any]) -> None:
    source = str(raw_text or "")
    problem_type = _advanced_structural_problem_type(source)
    if not problem_type:
        return

    value = r"([-+]?\d*\.?\d+(?:e[-+]?\d+)?)"
    unit = r"(?:\s*([A-Za-zµμ/^0-9·.]+))?"

    quantity_patterns = {
        "L": [rf"\b(?:length|column\s+length|shaft\s+length|l)\b(?:\s*l)?\s*(?:=|is|of)?\s*{value}{unit}"],
        "E": [rf"\b(?:young[’'`s]*\s+modulus|elastic\s+modulus|modulus|e)\b(?:\s*e)?\s*(?:=|is|of)?\s*{value}{unit}"],
        "G": [rf"\b(?:shear\s+modulus|modulus\s+of\s+rigidity|g)\b(?:\s*g)?\s*(?:=|is|of)?\s*{value}{unit}"],
        "I": [rf"\b(?:second\s+moment\s+of\s+area|moment\s+of\s+inertia|i)\b(?:\s*i)?\s*(?:=|is|of)?\s*{value}{unit}"],
        "T": [rf"\b(?:torque|twisting\s+moment|t)\b(?:\s*t)?\s*(?:=|is|of)?\s*{value}\s*(kN\s*m|kN\s*·\s*m|N\s*m|N\s*·\s*m|Nm|kNm)?"],
        "d": [rf"\b(?:diameter|shaft\s+diameter|d)\b(?:\s*d)?\s*(?:=|is|of)?\s*{value}{unit}"],
        "R": [rf"\b(?:radius|r)\b(?:\s*r)?\s*(?:=|is|of)?\s*{value}{unit}"],
        "t_wall": [rf"\b(?:wall\s+thickness|thickness|t)\b(?:\s*t)?\s*(?:=|is|of)?\s*{value}{unit}"],
        "p": [rf"\b(?:internal\s+pressure|pressure|p)\b(?:\s*p)?\s*(?:=|is|of)?\s*{value}{unit}"],
        "K": [rf"\b(?:effective\s+length\s+factor|k)\b\s*(?:=|is)?\s*{value}\b"],
    }
    for key, patterns in quantity_patterns.items():
        for pattern in patterns:
            match = re.search(pattern, source, re.I)
            if not match:
                continue
            numeric = float(match.group(1))
            unit_text = match.group(2) if len(match.groups()) >= 2 and match.group(2) else ""
            params[key] = _scale_advanced_structural_quantity(key, numeric, unit_text)
            break

    lowered = source.lower()
    if problem_type == "euler_column_buckling" and "K" not in params:
        if re.search(r"\bpinned[-\s]?pinned|pin[-\s]?ended|simply\s+supported\s+column\b", lowered):
            params["K"] = 1.0
        elif re.search(r"\bfixed[-\s]?fixed|built[-\s]?in\s+both\b", lowered):
            params["K"] = 0.5
        elif re.search(r"\bfixed[-\s]?pinned|pinned[-\s]?fixed\b", lowered):
            params["K"] = 0.699
        elif re.search(r"\bfixed[-\s]?free|cantilever\s+column\b", lowered):
            params["K"] = 2.0

    if problem_type == "shaft_torsion":
        if re.search(r"\bhollow\b", lowered):
            params.setdefault("section", "hollow_circular")
            inner = re.search(r"\b(?:inner\s+diameter|inside\s+diameter|d_i|di)\b\s*(?:=|is|of)?\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)\s*([A-Za-zµμ]+)?", source, re.I)
            if inner:
                params["d_inner"] = _scale_advanced_structural_quantity("d", float(inner.group(1)), inner.group(2) or "")
        else:
            params.setdefault("section", "solid_circular")
        params.pop("t_wall", None)
    elif problem_type == "thin_pressure_vessel":
        params.pop("T", None)


def _scale_advanced_structural_quantity(name: str, value: float, unit: str) -> float:
    normalized = (unit or "").lower().replace("μ", "u").replace("µ", "u").replace("·", "*").replace(" ", "").strip(".,;:")
    if name in {"E", "G"}:
        if normalized == "gpa":
            return value * 1e9
        if normalized == "mpa":
            return value * 1e6
        if normalized == "kpa":
            return value * 1e3
    if name == "p":
        if normalized == "mpa":
            return value * 1e6
        if normalized == "kpa":
            return value * 1e3
        if normalized == "bar":
            return value * 1e5
    if name == "T":
        if normalized in {"knm", "kn*m"}:
            return value * 1e3
    if name in {"L", "d", "R", "t_wall", "d_inner"}:
        if normalized in {"mm", "millimetre", "millimeter", "millimetres", "millimeters"}:
            return value * 1e-3
        if normalized in {"cm", "centimetre", "centimeter", "centimetres", "centimeters"}:
            return value * 1e-2
    return value


def _first_numeric_match(patterns: list[str], source: str) -> float | int | None:
    for pattern in patterns:
        match = re.search(pattern, source, re.I)
        if match:
            return _coerce_number(match.group(1))
    return None


def _coerce_number(value: str) -> float | int:
    return float(value) if "." in str(value) else int(value)


def _humanize_error(message: str) -> str:
    text = str(message or "The computation could not be completed.").strip()
    text = re.sub(r"Traceback \(most recent call last\):.*", "The computation could not be completed.", text, flags=re.S)
    text = re.sub(r"File \"[^\"]+\", line \d+[^\n]*", "", text)
    text = re.sub(r"[A-Za-z_]*Error:\s*", "", text)
    return text[:280] + ("…" if len(text) > 280 else "")
