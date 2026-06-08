"""
symbolic_engine.py — Step-by-step algebra with full derivation trace.

Emits derivation_step events showing each mathematical transformation.
All solving is deterministic SymPy — no LLM involved.
"""
from __future__ import annotations

import re
import sympy as sp
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
)
from engine.math_normalizer import normalize_math_text

_TRANSFORMS = standard_transformations + (implicit_multiplication_application,)


def _latex(expr) -> str:
    return sp.latex(expr)


def _parse(s: str, local_dict: dict | None = None) -> sp.Expr:
    s = normalize_math_text(s.strip())
    return parse_expr(s, local_dict=local_dict or {}, transformations=_TRANSFORMS)


def _equation_sides(eq_str: str, sym_dict: dict[str, sp.Symbol]) -> tuple[sp.Expr, sp.Expr]:
    cleaned = _normalize_symbol_case(str(eq_str or ""))
    cleaned = re.sub(r"\bsolve\s+for\s+[a-z]\b.*$", "", cleaned, flags=re.I).strip(" ;,.?")
    if "=" in cleaned:
        lhs_s, rhs_s = cleaned.split("=", 1)
        return _parse(lhs_s.strip(), sym_dict), _parse(rhs_s.strip(), sym_dict)
    return _parse(cleaned, sym_dict), sp.Integer(0)


def _symbols_from_equations(equations: list[str]) -> tuple[list[str], dict[str, sp.Symbol]]:
    names: list[str] = []
    for eq_str in equations:
        cleaned = _normalize_symbol_case(str(eq_str or ""))
        for name in re.findall(r"\b([a-z])\b", cleaned):
            if name not in {"e"} and name not in names:
                names.append(name)
    names.sort()
    return names, {name: sp.Symbol(name) for name in names}


def _summary_item(label: str, value: sp.Expr) -> dict:
    item = {"label": label, "value": str(value)}
    if getattr(value, "is_number", False):
        try:
            item["decimal"] = float(value.evalf())
        except Exception:
            pass
    return item


def _format_assignment(symbol: sp.Symbol, value: sp.Expr) -> str:
    if getattr(value, "is_number", False):
        try:
            decimal = float(value.evalf())
            if sp.simplify(value - decimal) == 0:
                return f"{_latex(symbol)} = {decimal:.6g}"
            return f"{_latex(symbol)} = {_latex(value)} \\approx {decimal:.6g}"
        except Exception:
            pass
    return f"{_latex(symbol)} = {_latex(value)}"


def _step(operation: str, op_label: str, from_latex: str, to_latex: str, note: str = "") -> dict:
    return {
        "type": "derivation_step",
        "operation": operation,
        "operation_label": op_label,
        "from_latex": from_latex,
        "to_latex": to_latex,
        "note": note,
    }


def _eq_state(latex_str: str, label: str = "") -> dict:
    return {"type": "equation_state", "latex": latex_str, "label": label}


def _section(title: str) -> dict:
    return {"type": "section", "title": title}




def can_solve(problem) -> float:
    domain = getattr(problem, "domain", None) if not isinstance(problem, dict) else problem.get("domain")
    problem_type = getattr(problem, "problem_type", None) if not isinstance(problem, dict) else problem.get("problem_type")
    if domain == "algebra":
        return 1.0 if not problem_type or problem_type in {'nonlinear_system', 'single_equation', 'linear_system', 'quadratic_equation'} else 0.75
    return 0.0

async def solve_algebra(data: dict):
    """
    Main algebra solver — routes to specific sub-solvers and streams derivation events.
    """
    params = data.get("parameters", {})
    problem_type = data.get("problem_type", "").lower()
    raw_query = data.get("raw_query", "")

    equations_raw: list[str] = params.get("equations", [])
    expression_raw: str = params.get("expression", "")
    target_variable: str | None = params.get("target_variable")

    if not equations_raw and not expression_raw:
        yield {"type": "error", "message": "No equations or expression found in problem."}
        return

    try:
        if equations_raw:
            if len(equations_raw) == 1:
                async for evt in _solve_single_equation(equations_raw[0], problem_type, target_variable=target_variable):
                    yield evt
            else:
                async for evt in _solve_system(equations_raw):
                    yield evt
        elif expression_raw:
            if any(kw in problem_type for kw in ("quadratic", "polynomial", "roots")):
                async for evt in _solve_polynomial(expression_raw, problem_type):
                    yield evt
            elif "factor" in problem_type or "factor" in raw_query.lower():
                async for evt in _solve_factorisation(expression_raw):
                    yield evt
            elif "simplif" in problem_type or "simplif" in raw_query.lower():
                async for evt in _solve_simplification(expression_raw):
                    yield evt
            else:
                async for evt in _solve_single_equation(expression_raw, problem_type, target_variable=target_variable):
                    yield evt

    except Exception as exc:
        yield {"type": "error", "message": f"Symbolic algebra error: {exc}"}


async def _solve_single_equation(eq_str: str, problem_type: str, target_variable: str | None = None):
    """
    Solve a single equation with step-by-step derivation trace.
    Handles linear, quadratic, and general polynomial equations.
    """
    yield _section("EQUATION ANALYSIS")

    # Detect variables
    eq_str = _normalize_symbol_case(eq_str)
    target_variable = target_variable.lower() if isinstance(target_variable, str) and target_variable else None
    syms, sym_dict = _symbols_from_equations([eq_str])
    if not syms:
        yield {"type": "error", "message": "No variables found in equation."}
        return

    primary = target_variable if target_variable in syms else syms[0]
    x = sym_dict[primary]

    # Parse equation
    lhs, rhs = _equation_sides(eq_str, sym_dict)

    eq = sp.Eq(lhs, rhs)
    yield _eq_state(f"{_latex(lhs)} = {_latex(rhs)}", "Given equation")

    # Collect to one side
    expr = lhs - rhs
    expr_expanded = sp.expand(expr)
    if target_variable and target_variable in syms:
        async for evt in _solve_for_target(eq, expr_expanded, x):
            yield evt
        return
    poly = sp.Poly(expr_expanded, x) if expr_expanded.is_polynomial(x) else None
    degree = poly.degree() if poly else None

    if expr_expanded != expr:
        yield _step(
            "expand",
            "Expand and collect terms",
            f"{_latex(lhs)} = {_latex(rhs)}",
            f"{_latex(expr_expanded)} = 0",
            "Bring all terms to the left-hand side",
        )

    if degree == 1:
        async for evt in _linear_steps(expr_expanded, x, sym_dict):
            yield evt
    elif degree == 2:
        async for evt in _quadratic_steps(expr_expanded, x):
            yield evt
    else:
        async for evt in _general_solve_steps(eq, x):
            yield evt


async def _linear_steps(expr: sp.Expr, x: sp.Symbol, sym_dict: dict):
    """Solve a linear equation showing each algebraic manipulation."""
    yield _section("LINEAR EQUATION — STEP-BY-STEP")

    # Get coefficients: expr = a*x + b  →  x = -b/a
    coeffs = sp.Poly(expr, x).all_coeffs()
    a = sp.simplify(coeffs[0])
    b = sp.simplify(coeffs[1]) if len(coeffs) > 1 else sp.Integer(0)

    current = f"{_latex(expr)} = 0"
    yield _eq_state(current, "Working equation")

    # Step 1: If constant term present, subtract it
    if b != 0:
        b_neg = sp.simplify(-b)
        new_expr = sp.simplify(a * x)
        op_label = f"Add {_latex(b_neg)} to both sides" if b_neg > 0 else f"Subtract {_latex(-b_neg)} from both sides"
        yield _step(
            "isolate_variable_term",
            op_label,
            current,
            f"{_latex(new_expr)} = {_latex(b_neg)}",
            f"Move the constant term to the right side",
        )
        current = f"{_latex(new_expr)} = {_latex(b_neg)}"

    # Step 2: Divide by coefficient
    if a != 1 and a != 0:
        x_val = sp.simplify(-b / a)
        yield _step(
            "divide_coefficient",
            f"Divide both sides by {_latex(a)}",
            current,
            f"{_latex(x)} = {_latex(x_val)}",
            f"Isolate {_latex(x)} by dividing by its coefficient",
        )
    elif a == 0:
        if b == 0:
            yield {"type": "final", "answer": "Identity: true for all values of the variable."}
        else:
            yield {"type": "final", "answer": "No solution: equation is inconsistent."}
        return

    solution = sp.simplify(-b / a)
    value_text = _format_assignment(x, solution)

    yield _eq_state(f"{_latex(x)} = {_latex(solution)}", "Solution")

    # Verification
    verification = sp.simplify(expr.subs(x, solution))
    passed = verification == 0
    yield {
        "type": "verification",
        "passed": passed,
        "checks": [{
            "label": f"Substitution check: substitute {_latex(x)} = {_latex(solution)}",
            "passed": passed,
            "detail": f"LHS − RHS = {_latex(sp.simplify(verification))} {'= 0 ✓' if passed else '≠ 0 ✗'}",
        }],
    }

    yield {
        "type": "final",
        "answer": f"### Solution\n\n$$\n{value_text}\n$$",
        "summary": [_summary_item(str(x), solution)],
    }


async def _solve_for_target(eq: sp.Eq, expr: sp.Expr, target: sp.Symbol):
    """Solve or rearrange a single equation for an explicitly requested variable."""
    yield _section(f"SOLVE FOR {_latex(target)}")
    yield _eq_state(f"{_latex(expr)} = 0", f"Collect terms before isolating {_latex(target)}")

    solutions = sp.solve(eq, target, dict=True)
    if not solutions:
        yield {"type": "error", "message": f"Could not isolate {target} from the equation."}
        return

    value = sp.simplify(solutions[0][target])
    yield _step(
        "isolate_requested_variable",
        f"Isolate {_latex(target)}",
        f"{_latex(expr)} = 0",
        f"{_latex(target)} = {_latex(value)}",
        "Solve symbolically for the requested variable.",
    )
    yield _eq_state(f"{_latex(target)} = {_latex(value)}", "Requested rearrangement")

    verification = sp.simplify(eq.lhs.subs(target, value) - eq.rhs.subs(target, value))
    passed = verification == 0
    yield {
        "type": "verification",
        "passed": passed,
        "checks": [{
            "label": f"Substitution check: substitute {_latex(target)} = {_latex(value)}",
            "passed": passed,
            "detail": f"LHS − RHS = {_latex(verification)} {'= 0 ✓' if passed else '≠ 0 ✗'}",
        }],
    }

    summary = {"label": str(target), "value": str(value)}
    try:
        summary["decimal"] = float(value.evalf())
        if value.is_number and sp.simplify(value - summary["decimal"]) == 0:
            answer_value = f"{summary['decimal']:.6g}"
        else:
            answer_value = _latex(value)
    except Exception:
        answer_value = _latex(value)
    yield {
        "type": "final",
        "answer": f"### Solution\n\n$$\n{_latex(target)} = {answer_value}\n$$",
        "summary": [summary],
    }


def _normalize_symbol_case(text: str) -> str:
    normalized = normalize_math_text(str(text or ""))
    return re.sub(r"\b([A-Z])\b", lambda match: match.group(1).lower(), normalized)


async def _quadratic_steps(expr: sp.Expr, x: sp.Symbol):
    """Solve a quadratic equation showing discriminant and root formula steps."""
    yield _section("QUADRATIC EQUATION — COMPLETE SOLUTION")

    coeffs = sp.Poly(expr, x).all_coeffs()
    a = sp.simplify(coeffs[0])
    b = sp.simplify(coeffs[1]) if len(coeffs) > 1 else sp.Integer(0)
    c = sp.simplify(coeffs[2]) if len(coeffs) > 2 else sp.Integer(0)

    # Show standard form
    yield _eq_state(
        f"{_latex(a)}{_latex(x)}^{{2}} + {_latex(b)}{_latex(x)} + {_latex(c)} = 0",
        f"Standard form: $a={_latex(a)},\\ b={_latex(b)},\\ c={_latex(c)}$",
    )

    # Discriminant
    D = sp.simplify(b**2 - 4*a*c)
    yield _step(
        "compute_discriminant",
        "Compute the discriminant Δ = b² − 4ac",
        f"\\Delta = b^{{2}} - 4ac",
        f"\\Delta = ({_latex(b)})^{{2}} - 4({_latex(a)})({_latex(c)}) = {_latex(D)}",
        "The discriminant determines the nature of the roots",
    )

    if D > 0:
        nature = "Two distinct real roots (Δ > 0)"
    elif D == 0:
        nature = "One repeated real root (Δ = 0)"
    else:
        nature = "Two complex conjugate roots (Δ < 0)"

    yield _eq_state(f"\\Delta = {_latex(D)}", nature)

    # Apply quadratic formula
    yield _step(
        "apply_quadratic_formula",
        "Apply the quadratic formula",
        f"{_latex(x)} = \\frac{{-b \\pm \\sqrt{{\\Delta}}}}{{2a}}",
        f"{_latex(x)} = \\frac{{-({_latex(b)}) \\pm \\sqrt{{{_latex(D)}}}}}{{2({_latex(a)})}}",
        "Substitute the known coefficients",
    )

    roots = sp.solve(expr, x)
    if len(roots) == 0:
        yield {"type": "final", "answer": "No solutions found."}
        return

    root_latex = ",\\quad ".join(
        f"{_latex(x)}_{{{i+1}}} = {_latex(sp.simplify(r))}" for i, r in enumerate(roots)
    )
    yield _eq_state(root_latex, "Roots")

    # Verification for each root
    checks = []
    for i, r in enumerate(roots):
        val = sp.simplify(expr.subs(x, r))
        checks.append({
            "label": f"Verify {_latex(x)} = {_latex(sp.simplify(r))}",
            "passed": sp.simplify(val) == 0,
            "detail": f"f({_latex(sp.simplify(r))}) = {_latex(sp.simplify(val))} {'= 0 ✓' if sp.simplify(val) == 0 else '✗'}",
        })
    yield {"type": "verification", "passed": all(c["passed"] for c in checks), "checks": checks}

    summary_parts = []
    for i, r in enumerate(roots):
        r_simplified = sp.simplify(r)
        try:
            decimal_val = float(r_simplified.evalf())
            summary_parts.append({"label": f"x_{i+1}", "value": str(r_simplified), "decimal": decimal_val})
        except Exception:
            summary_parts.append({"label": f"x_{i+1}", "value": str(r_simplified)})

    roots_str = "\n\n".join(
        f"$$\n{_latex(x)}_{{{i+1}}} = {_latex(sp.simplify(r))}\n$$" for i, r in enumerate(roots)
    )
    yield {
        "type": "final",
        "answer": f"### Quadratic Roots\n\n{roots_str}\n\n**Discriminant:** $\\Delta = {_latex(D)}$ — {nature}",
        "summary": summary_parts,
    }


async def _solve_system(equations: list[str]):
    """Solve a system of equations with Gaussian elimination style derivation."""
    yield _section("SYSTEM OF EQUATIONS")

    n = len(equations)
    yield {"type": "step", "content": f"System of {n} equations detected — applying symbolic elimination."}

    all_vars, sym_dict = _symbols_from_equations(equations)
    if not all_vars:
        yield {"type": "error", "message": "No variables found in the equation system."}
        return

    # Parse equations
    parsed_eqs = []
    eq_latexes = []
    for eq_str in equations:
        lhs, rhs = _equation_sides(eq_str, sym_dict)
        parsed_eqs.append(sp.Eq(lhs, rhs))
        eq_latexes.append(f"{_latex(lhs)} = {_latex(rhs)}")

    # Show the system
    system_latex = "\\begin{cases}\n" + " \\\\\n".join(eq_latexes) + "\n\\end{cases}"
    yield _eq_state(system_latex, f"System of {n} equations in {len(all_vars)} unknowns: {', '.join(all_vars)}")

    symbols_list = [sym_dict[s] for s in all_vars]

    # Solve
    solution = sp.solve(parsed_eqs, symbols_list, dict=True)

    if not solution:
        # Try linsolve for linear systems
        try:
            lhs_exprs = []
            rhs_vals = []
            for eq_str in equations:
                lhs, rhs = _equation_sides(eq_str, sym_dict)
                lhs_exprs.append(lhs)
                rhs_vals.append(rhs)

            lin_sol = list(sp.linsolve(
                [(lhs - rhs) for lhs, rhs in zip(lhs_exprs, rhs_vals)],
                symbols_list,
            ))
            if lin_sol:
                sol_dict = {s: v for s, v in zip(symbols_list, lin_sol[0])}
                solution = [sol_dict]
        except Exception:
            pass

    if not solution:
        yield {"type": "final", "answer": "No solution found. The system may be inconsistent or underdetermined."}
        return

    solutions = solution if isinstance(solution, list) else [solution]

    # Show solution derivation
    yield _section("ELIMINATION & BACK-SUBSTITUTION")

    # Show linear combination steps for 2-variable linear systems only
    if len(all_vars) == 2 and n == 2 and len(solutions) == 1:
        async for evt in _show_2x2_elimination(parsed_eqs, sym_dict, all_vars):
            yield evt

    summary = []
    result_parts = []
    checks = []

    for sol_index, sol in enumerate(solutions, start=1):
        solution_lines = []
        for sym_key, sym_obj in sym_dict.items():
            if sym_obj in sol:
                val = sp.simplify(sol[sym_obj])
                yield _eq_state(f"{_latex(sym_obj)} = {_latex(val)}", f"Solution set {sol_index}: {sym_key}")
                try:
                    dec = float(val.evalf())
                    summary.append({"label": f"{sym_key}_{sol_index}", "value": str(val), "decimal": dec})
                    solution_lines.append(_format_assignment(sym_obj, val))
                except Exception:
                    summary.append({"label": f"{sym_key}_{sol_index}", "value": str(val)})
                    solution_lines.append(f"{_latex(sym_obj)} = {_latex(val)}")

        if solution_lines:
            result_parts.append(f"**Solution set {sol_index}**\n\n$$\n" + ",\\quad ".join(solution_lines) + "\n$$")

        for i, (eq, eq_l) in enumerate(zip(parsed_eqs, eq_latexes)):
            try:
                verified = sp.simplify(eq.subs(list(sol.items())))
                checks.append({
                    "label": f"Set {sol_index}, equation {i+1}: ${eq_l}$",
                    "passed": bool(verified == True),
                    "detail": f"Substitution gives: {_latex(verified)} {'✓' if verified == True else '✗'}",
                })
            except Exception:
                pass

    if checks:
        yield {"type": "verification", "passed": all(c["passed"] for c in checks), "checks": checks}

    title = "System Solutions" if len(solutions) > 1 else "System Solution"
    yield {
        "type": "final",
        "answer": f"### {title}\n\n" + "\n\n".join(result_parts),
        "summary": summary,
    }


async def _show_2x2_elimination(eqs: list, sym_dict: dict, var_names: list):
    """Show Gaussian elimination steps for a 2×2 system."""
    x_sym = sym_dict[var_names[0]]
    y_sym = sym_dict[var_names[1]]

    try:
        # Extract coefficients a1*x + b1*y = c1 and a2*x + b2*y = c2
        eq1_lhs = sp.expand(eqs[0].lhs - eqs[0].rhs)
        eq2_lhs = sp.expand(eqs[1].lhs - eqs[1].rhs)

        a1 = eq1_lhs.coeff(x_sym)
        b1 = eq1_lhs.coeff(y_sym)
        c1 = -eq1_lhs.subs([(x_sym, 0), (y_sym, 0)])

        a2 = eq2_lhs.coeff(x_sym)
        b2 = eq2_lhs.coeff(y_sym)
        c2 = -eq2_lhs.subs([(x_sym, 0), (y_sym, 0)])

        # Eliminate x: multiply eq1 by a2, eq2 by a1, then subtract
        det = sp.simplify(a1 * b2 - a2 * b1)
        if det == 0:
            return

        y_val = sp.simplify((a1 * c2 - a2 * c1) / det)
        x_val = sp.simplify((c1 - b1 * y_val) / a1) if a1 != 0 else sp.simplify((c2 - b2 * y_val) / a2)

        # Show elimination
        scale1_latex = f"{_latex(a2)} \\times \\text{{Eq.1}}"
        scale2_latex = f"{_latex(a1)} \\times \\text{{Eq.2}}"
        yield _step(
            "elimination",
            f"Eliminate {_latex(x_sym)}: scale equations",
            f"{scale1_latex}: \\ {_latex(a2*a1)}{_latex(x_sym)} + {_latex(a2*b1)}{_latex(y_sym)} = {_latex(a2*c1)}",
            f"{scale2_latex}: \\ {_latex(a1*a2)}{_latex(x_sym)} + {_latex(a1*b2)}{_latex(y_sym)} = {_latex(a1*c2)}",
            f"Scale to make {_latex(x_sym)} coefficients equal",
        )
        combined_lhs = sp.simplify((a1*b2 - a2*b1) * y_sym)
        combined_rhs = sp.simplify(a1*c2 - a2*c1)
        yield _step(
            "subtract_equations",
            "Subtract scaled equations",
            f"{_latex(a1*a2)}{_latex(x_sym)} + {_latex(a1*b2)}{_latex(y_sym)} - ({_latex(a2*a1)}{_latex(x_sym)} + {_latex(a2*b1)}{_latex(y_sym)}) = {_latex(a1*c2)} - {_latex(a2*c1)}",
            f"{_latex(combined_lhs)} = {_latex(combined_rhs)}",
            f"The {_latex(x_sym)} terms cancel, leaving a single equation in {_latex(y_sym)}",
        )
        yield _step(
            "solve_single_variable",
            f"Solve for {_latex(y_sym)}",
            f"{_latex(combined_lhs)} = {_latex(combined_rhs)}",
            f"{_latex(y_sym)} = \\frac{{{_latex(combined_rhs)}}}{{{_latex(sp.simplify(a1*b2 - a2*b1))}}} = {_latex(y_val)}",
            "",
        )
        # Back-substitution
        rhs_substituted = sp.simplify(c1 - b1*y_val)
        yield _step(
            "back_substitution",
            f"Back-substitute {_latex(y_sym)} = {_latex(y_val)} into Equation 1",
            f"{_latex(a1)}{_latex(x_sym)} + {_latex(b1)} \\cdot {_latex(y_val)} = {_latex(c1)}",
            f"{_latex(a1)}{_latex(x_sym)} = {_latex(rhs_substituted)} \\implies {_latex(x_sym)} = {_latex(x_val)}",
            "Direct substitution and simplification",
        )
    except Exception:
        pass


async def _solve_polynomial(expr_str: str, problem_type: str):
    """Solve polynomial or find roots with detailed steps."""
    yield _section("POLYNOMIAL ANALYSIS")

    syms = sorted(set(re.findall(r"\b([a-zA-Z])\b", expr_str)) - {"e"})
    if not syms:
        yield {"type": "error", "message": "No variable found."}
        return

    sym_dict = {s: sp.Symbol(s) for s in syms}
    x = sym_dict[syms[0]]

    if "=" in expr_str:
        lhs_s, rhs_s = expr_str.split("=", 1)
        expr = _parse(lhs_s, sym_dict) - _parse(rhs_s, sym_dict)
    else:
        expr = _parse(expr_str, sym_dict)

    expr_expanded = sp.expand(expr)
    poly = sp.Poly(expr_expanded, x)
    degree = poly.degree()

    yield _eq_state(f"{_latex(expr_expanded)} = 0", f"Degree-{degree} polynomial")

    # Factored form
    factored = sp.factor(expr_expanded)
    if factored != expr_expanded:
        yield _step(
            "factorise",
            "Factorise the polynomial",
            f"{_latex(expr_expanded)} = 0",
            f"{_latex(factored)} = 0",
            "Each factor gives a root when set to zero",
        )

    roots = sp.solve(expr_expanded, x)
    checks = []
    summary = []

    for i, r in enumerate(roots):
        r_s = sp.simplify(r)
        yield _eq_state(f"{_latex(x)} = {_latex(r_s)}", f"Root {i+1}")
        val = sp.simplify(expr_expanded.subs(x, r_s))
        checks.append({
            "label": f"Root {i+1}: ${_latex(x)} = {_latex(r_s)}$",
            "passed": sp.simplify(val) == 0,
            "detail": f"f({_latex(r_s)}) = {_latex(sp.simplify(val))} {'= 0 ✓' if sp.simplify(val) == 0 else '✗'}",
        })
        try:
            summary.append({"label": f"x_{i+1}", "value": str(r_s), "decimal": float(r_s.evalf())})
        except Exception:
            summary.append({"label": f"x_{i+1}", "value": str(r_s)})

    yield {"type": "verification", "passed": all(c["passed"] for c in checks), "checks": checks}

    roots_str = ",\\quad ".join(f"{_latex(x)}_{{{i+1}}} = {_latex(sp.simplify(r))}" for i, r in enumerate(roots))
    yield {
        "type": "final",
        "answer": f"### Polynomial Roots (degree {degree})\n\n$$\n{roots_str}\n$$",
        "summary": summary,
    }


async def _solve_factorisation(expr_str: str):
    """Factorise an expression with steps."""
    yield _section("FACTORISATION")

    syms = sorted(set(re.findall(r"\b([a-zA-Z])\b", expr_str)) - {"e"})
    sym_dict = {s: sp.Symbol(s) for s in syms}

    expr = _parse(expr_str, sym_dict)
    expanded = sp.expand(expr)
    factored = sp.factor(expr)

    yield _eq_state(_latex(expanded), "Expression")

    if factored == expanded:
        yield _eq_state(_latex(expanded), "Already fully factored")
    else:
        yield _step(
            "factor",
            "Factorise completely",
            _latex(expanded),
            _latex(factored),
            "Extract common factors and identify factor patterns",
        )

    yield {
        "type": "final",
        "answer": f"### Factorisation Result\n\n$$\n{_latex(factored)}\n$$",
        "summary": [{"label": "Factored form", "value": str(factored)}],
    }


async def _solve_simplification(expr_str: str):
    """Simplify an expression."""
    yield _section("SIMPLIFICATION")

    syms = sorted(set(re.findall(r"\b([a-zA-Z])\b", expr_str)) - {"e"})
    sym_dict = {s: sp.Symbol(s) for s in syms}

    expr = _parse(expr_str, sym_dict)
    simplified = sp.simplify(expr)
    expanded = sp.expand(expr)

    yield _eq_state(_latex(expr), "Original expression")

    if expanded != expr:
        yield _step("expand", "Expand", _latex(expr), _latex(expanded), "Distribute multiplication over addition")

    if simplified != expanded:
        yield _step("simplify", "Simplify", _latex(expanded), _latex(simplified), "Cancel common factors and reduce")

    yield {
        "type": "final",
        "answer": f"### Simplified Expression\n\n$$\n{_latex(simplified)}\n$$",
        "summary": [{"label": "Simplified", "value": str(simplified)}],
    }


async def _general_solve_steps(eq: sp.Eq, x: sp.Symbol):
    """Fallback solver for higher-degree or transcendental equations."""
    yield _section("GENERAL EQUATION SOLVING")
    yield {"type": "step", "content": f"Applying SymPy general solver for $f({_latex(x)}) = 0$"}

    solutions = sp.solve(eq, x)
    if not solutions:
        yield {"type": "final", "answer": "No closed-form solution found. The equation may require numerical methods."}
        return

    summary = []
    for i, sol in enumerate(solutions):
        sol_s = sp.simplify(sol)
        yield _eq_state(f"{_latex(x)} = {_latex(sol_s)}", f"Solution {i+1}")
        try:
            summary.append({"label": f"x_{i+1}", "value": str(sol_s), "decimal": float(sol_s.evalf())})
        except Exception:
            summary.append({"label": f"x_{i+1}", "value": str(sol_s)})

    sols_latex = "\n\n".join(f"$$\n{_latex(x)}_{{{i+1}}} = {_latex(sp.simplify(s))}\n$$" for i, s in enumerate(solutions))
    yield {
        "type": "final",
        "answer": f"### Solutions\n\n{sols_latex}",
        "summary": summary,
    }
