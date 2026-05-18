"""
calculus_engine.py — Calculus with full derivation trace.

Emits derivation_step events showing each calculus operation.
"""
from __future__ import annotations

import re
import sympy as sp

_TRANSFORMS = None
try:
    from sympy.parsing.sympy_parser import standard_transformations, implicit_multiplication_application
    _TRANSFORMS = standard_transformations + (implicit_multiplication_application,)
except ImportError:
    pass


def _latex(expr) -> str:
    return sp.latex(sp.simplify(expr))


def _parse(s: str, sym_dict: dict | None = None):
    s = re.sub(r"(\d)([a-zA-Z])", r"\1*\2", s.strip())
    if _TRANSFORMS:
        from sympy.parsing.sympy_parser import parse_expr
        return parse_expr(s, local_dict=sym_dict or {}, transformations=_TRANSFORMS)
    return sp.sympify(s, locals=sym_dict or {})


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


async def solve_calculus(data: dict):
    params = data.get("parameters", {})
    problem_type = data.get("problem_type", "").lower()
    raw = data.get("raw_query", "").lower()
    expr_raw = params.get("expression", data.get("raw_query", ""))

    # Clean expression
    for kw in ("differentiate", "integrate", "find the derivative", "compute", "evaluate",
                "of", "the", "integral", "derivative", "with respect to"):
        expr_raw = re.sub(r"\b" + re.escape(kw) + r"\b", " ", expr_raw, flags=re.I)
    expr_clean = expr_raw.strip()

    if not expr_clean:
        yield {"type": "error", "message": "No expression found. Please provide an expression to analyse."}
        return

    # Detect variables
    all_syms = sorted(set(re.findall(r"\b([a-zA-Z])\b", expr_clean)) - {"e", "E", "I"})
    if not all_syms:
        all_syms = ["x"]
    sym_dict = {s: sp.Symbol(s) for s in all_syms}
    primary_var = sym_dict[all_syms[0]]

    try:
        if any(kw in problem_type or kw in raw for kw in ("ode", "differential equation", "dsolve")):
            async for evt in _solve_ode(expr_clean, params):
                yield evt
        elif any(kw in problem_type or kw in raw for kw in ("laplace", "laplace transform")):
            async for evt in _laplace_transform(expr_clean, sym_dict, primary_var):
                yield evt
        elif any(kw in problem_type or kw in raw for kw in ("taylor", "maclaurin", "series")):
            async for evt in _taylor_series(expr_clean, sym_dict, primary_var, params):
                yield evt
        elif any(kw in problem_type or kw in raw for kw in ("fourier",)):
            async for evt in _fourier_series(expr_clean, sym_dict, primary_var):
                yield evt
        elif any(kw in problem_type or kw in raw for kw in ("integrate", "integral", "antiderivative", "area")):
            async for evt in _integration(expr_clean, sym_dict, primary_var, params):
                yield evt
        elif any(kw in problem_type or kw in raw for kw in ("differentiate", "derivative", "diff", "gradient")):
            async for evt in _differentiation(expr_clean, sym_dict, primary_var):
                yield evt
        else:
            async for evt in _calculus_overview(expr_clean, sym_dict, primary_var):
                yield evt
    except Exception as exc:
        yield {"type": "error", "message": f"Calculus engine error: {exc}"}


async def _differentiation(expr_str: str, sym_dict: dict, x: sp.Symbol):
    """Differentiation with chain/product/quotient rule identification."""
    yield _section("DIFFERENTIATION")

    expr = _parse(expr_str, sym_dict)
    yield _eq_state(f"f({_latex(x)}) = {_latex(expr)}", "Function")

    # First derivative
    d1 = sp.diff(expr, x)
    d1_simplified = sp.simplify(d1)

    # Detect which rule applies
    rule_note = _identify_diff_rule(expr, x)

    yield _step(
        "differentiate",
        f"Differentiate with respect to ${_latex(x)}$",
        f"\\frac{{d}}{{d{_latex(x)}}}\\left[{_latex(expr)}\\right]",
        _latex(d1),
        rule_note,
    )

    if d1 != d1_simplified:
        yield _step(
            "simplify_derivative",
            "Simplify",
            _latex(d1),
            _latex(d1_simplified),
            "",
        )

    yield _eq_state(f"f'({_latex(x)}) = {_latex(d1_simplified)}", "First derivative")

    # Second derivative
    d2 = sp.simplify(sp.diff(d1_simplified, x))
    yield _step(
        "second_derivative",
        "Second derivative",
        f"\\frac{{d^2}}{{d{_latex(x)}^2}}\\left[{_latex(expr)}\\right]",
        _latex(d2),
        "Differentiate the first derivative",
    )

    # Critical points
    try:
        crit = sp.solve(d1_simplified, x)
        if crit:
            crit_latex = ",\\quad ".join(f"{_latex(x)} = {_latex(sp.simplify(c))}" for c in crit)
            yield _eq_state(crit_latex, f"Critical points: f'({_latex(x)}) = 0")
    except Exception:
        pass

    yield {
        "type": "final",
        "answer": f"### Differentiation Result\n\n$$\nf'({_latex(x)}) = {_latex(d1_simplified)}\n$$\n\n$$\nf''({_latex(x)}) = {_latex(d2)}\n$$",
        "summary": [
            {"label": "f'(x)", "value": str(d1_simplified)},
            {"label": "f''(x)", "value": str(d2)},
        ],
    }


def _identify_diff_rule(expr: sp.Expr, x: sp.Symbol) -> str:
    """Identify which differentiation rule applies."""
    if isinstance(expr, sp.Mul):
        factors = expr.args
        x_factors = [f for f in factors if f.has(x)]
        if len(x_factors) >= 2:
            return "Product rule: d(uv)/dx = u'v + uv'"
    if isinstance(expr, sp.Pow) and expr.args[0].has(x) and expr.args[1].has(x):
        return "Logarithmic differentiation: y = u^v → ln y = v ln u"
    if isinstance(expr, sp.Pow) and not expr.args[1].is_integer and expr.args[0].has(x):
        return f"Power rule: d/dx[x^n] = nx^{{n-1}}"
    if isinstance(expr, (sp.sin, sp.cos, sp.tan, sp.exp, sp.log)):
        if expr.args[0] != x:
            return "Chain rule: d/dx[f(g(x))] = f'(g(x)) · g'(x)"
    if isinstance(expr, sp.Add):
        return "Linearity of differentiation: d/dx[u + v] = u' + v'"
    return "Direct application of differentiation rules"


async def _integration(expr_str: str, sym_dict: dict, x: sp.Symbol, params: dict):
    """Integration with method identification and definite/indefinite handling."""
    yield _section("INTEGRATION")

    # Check for definite integral limits
    a_lim = params.get("lower_limit", params.get("a_limit"))
    b_lim = params.get("upper_limit", params.get("b_limit"))

    expr = _parse(expr_str, sym_dict)
    yield _eq_state(
        f"\\int {_latex(expr)}\\, d{_latex(x)}" if not a_lim else f"\\int_{{{a_lim}}}^{{{b_lim}}} {_latex(expr)}\\, d{_latex(x)}",
        "Integral to evaluate",
    )

    # Identify method
    method_note = _identify_integration_method(expr, x)
    yield {"type": "step", "content": f"Method: {method_note}"}

    antideriv = sp.integrate(expr, x)
    antideriv_simplified = sp.simplify(antideriv)

    yield _step(
        "integrate",
        f"Integrate with respect to ${_latex(x)}$",
        f"\\int {_latex(expr)}\\, d{_latex(x)}",
        f"{_latex(antideriv_simplified)} + C",
        method_note,
    )

    if a_lim is not None and b_lim is not None:
        try:
            a_sym = sp.sympify(a_lim)
            b_sym = sp.sympify(b_lim)
            F_b = sp.simplify(antideriv_simplified.subs(x, b_sym))
            F_a = sp.simplify(antideriv_simplified.subs(x, a_sym))
            definite = sp.simplify(F_b - F_a)

            yield _step(
                "evaluate_limits",
                "Evaluate using the Fundamental Theorem of Calculus",
                f"\\left[{_latex(antideriv_simplified)}\\right]_{{{_latex(a_sym)}}}^{{{_latex(b_sym)}}}",
                f"= \\left({_latex(F_b)}\\right) - \\left({_latex(F_a)}\\right) = {_latex(definite)}",
                "Substitute upper and lower limits, then subtract",
            )

            yield _eq_state(
                f"\\int_{{{_latex(a_sym)}}}^{{{_latex(b_sym)}}} {_latex(expr)}\\, d{_latex(x)} = {_latex(definite)}",
                "Definite integral value",
            )
            try:
                decimal_val = float(definite.evalf())
                yield {
                    "type": "final",
                    "answer": f"### Definite Integral\n\n$$\n\\int_{{{_latex(a_sym)}}}^{{{_latex(b_sym)}}} {_latex(expr)}\\, d{_latex(x)} = {_latex(definite)} = {decimal_val:.6g}\n$$",
                    "summary": [{"label": "Definite integral", "value": str(definite), "decimal": decimal_val}],
                }
            except Exception:
                yield {
                    "type": "final",
                    "answer": f"### Definite Integral\n\n$$\n\\int_{{{_latex(a_sym)}}}^{{{_latex(b_sym)}}} {_latex(expr)}\\, d{_latex(x)} = {_latex(definite)}\n$$",
                }
            return
        except Exception:
            pass

    yield _eq_state(f"\\int {_latex(expr)}\\, d{_latex(x)} = {_latex(antideriv_simplified)} + C", "Antiderivative")
    yield {
        "type": "final",
        "answer": f"### Indefinite Integral\n\n$$\n\\int {_latex(expr)}\\, d{_latex(x)} = {_latex(antideriv_simplified)} + C\n$$",
        "summary": [{"label": "Antiderivative", "value": f"{str(antideriv_simplified)} + C"}],
    }


def _identify_integration_method(expr: sp.Expr, x: sp.Symbol) -> str:
    if isinstance(expr, sp.Pow) and expr.args[0] == x:
        return "Power rule: ∫x^n dx = x^(n+1)/(n+1) + C"
    if isinstance(expr, (sp.sin, sp.cos)):
        return "Standard trigonometric integral"
    if isinstance(expr, sp.exp):
        return "Exponential integral: ∫e^x dx = e^x + C"
    if isinstance(expr, sp.log):
        return "Integration by parts: ∫ln(x) dx = x·ln(x) − x + C"
    if isinstance(expr, sp.Mul):
        return "Product form — possibly integration by parts or substitution"
    return "Standard integration technique"


async def _taylor_series(expr_str: str, sym_dict: dict, x: sp.Symbol, params: dict):
    """Taylor/Maclaurin series expansion."""
    yield _section("TAYLOR SERIES EXPANSION")

    x0 = float(params.get("point", params.get("expansion_point", 0)))
    order = int(params.get("order", params.get("n", 6)))

    # Clean keywords from expression
    for kw in ("taylor", "maclaurin", "series", "expansion", "around", "order"):
        expr_str = re.sub(r"\b" + kw + r"\b.*", "", expr_str, flags=re.I).strip()

    expr = _parse(expr_str.strip(), sym_dict)
    yield _eq_state(f"f({_latex(x)}) = {_latex(expr)}", "Function")
    yield _eq_state(f"x_0 = {x0},\\quad n = {order}", "Expansion parameters")

    # Show the general formula
    yield _step(
        "general_taylor_formula",
        "Apply Taylor series formula",
        f"f(x) = \\sum_{{n=0}}^{{\\infty}} \\frac{{f^{{(n)}}(x_0)}}{{n!}}(x - x_0)^n",
        f"\\text{{Expanding }} {_latex(expr)} \\text{{ about }} x_0 = {x0}",
        "Each term requires evaluating the n-th derivative at x₀",
    )

    # Show first few derivatives at x0
    for n_ord in range(min(4, order)):
        dn = sp.diff(expr, x, n_ord)
        dn_at_x0 = sp.simplify(dn.subs(x, x0))
        if dn_at_x0 != 0:
            factorial_n = sp.factorial(n_ord)
            term_coeff = sp.simplify(dn_at_x0 / factorial_n)
            if n_ord == 0:
                term_latex = _latex(term_coeff)
            elif n_ord == 1:
                term_latex = f"{_latex(term_coeff)}(x - {x0})"
            else:
                term_latex = f"\\frac{{{_latex(dn_at_x0)}}}{{{_latex(factorial_n)}}}(x - {x0})^{{{n_ord}}} = {_latex(term_coeff)}(x-{x0})^{{{n_ord}}}"
            yield _eq_state(
                f"\\frac{{f^{{({n_ord})}}({x0})}}{{{n_ord}!}} = \\frac{{{_latex(dn_at_x0)}}}{{{_latex(factorial_n)}}} = {_latex(term_coeff)}",
                f"Term n={n_ord}",
            )

    series = sp.series(expr, x, x0, order)
    series_no_O = series.removeO()

    yield _step(
        "series_result",
        f"Taylor series (order {order})",
        f"f(x) \\approx \\text{{...}}",
        _latex(series_no_O),
        "Full polynomial approximation",
    )

    yield _eq_state(f"f(x) = {_latex(series)}", "Series with error term O(x^n)")

    yield {
        "type": "final",
        "answer": f"### Taylor Series of ${_latex(expr)}$ about $x_0 = {x0}$\n\n$$\nf(x) = {_latex(series_no_O)} + O\\left((x-{x0})^{{{order}}}\\right)\n$$",
        "summary": [{"label": "Series", "value": str(series_no_O)}],
    }


async def _laplace_transform(expr_str: str, sym_dict: dict, x: sp.Symbol):
    """Laplace transform with standard pair identification."""
    yield _section("LAPLACE TRANSFORM")

    t = sp.Symbol("t", positive=True)
    s = sp.Symbol("s")
    local_sym = {**sym_dict, "t": t, "s": s}

    # Clean expression
    for kw in ("laplace", "transform", "of"):
        expr_str = re.sub(r"\b" + kw + r"\b", " ", expr_str, flags=re.I)
    expr_str = expr_str.strip()

    expr = _parse(expr_str, local_sym)
    yield _eq_state(f"f(t) = {_latex(expr)}", "Time-domain function")
    yield _eq_state(f"F(s) = \\mathcal{{L}}\\{{f(t)\\}} = \\int_0^{{\\infty}} f(t)\\, e^{{-st}}\\, dt", "Laplace transform definition")

    result = sp.laplace_transform(expr, t, s, noconds=True)

    yield _step(
        "laplace",
        "Apply Laplace transform",
        f"\\mathcal{{L}}\\{{{_latex(expr)}\\}}",
        _latex(result),
        "Use standard Laplace transform pairs and properties",
    )

    yield _eq_state(f"F(s) = {_latex(result)}", "Laplace transform F(s)")

    yield {
        "type": "final",
        "answer": f"### Laplace Transform\n\n$$\n\\mathcal{{L}}\\{{f(t)\\}} = F(s) = {_latex(result)}\n$$",
        "summary": [{"label": "F(s)", "value": str(result)}],
    }


async def _fourier_series(expr_str: str, sym_dict: dict, x: sp.Symbol):
    """Fourier series expansion."""
    yield _section("FOURIER SERIES")

    for kw in ("fourier", "series", "of"):
        expr_str = re.sub(r"\b" + kw + r"\b", " ", expr_str, flags=re.I)
    expr_str = expr_str.strip()

    expr = _parse(expr_str, sym_dict)
    yield _eq_state(f"f(x) = {_latex(expr)}", "Function on $[-\\pi, \\pi]$")

    fs = sp.fourier_series(expr, (x, -sp.pi, sp.pi))
    truncated = fs.truncate(5)

    yield _step(
        "fourier",
        "Compute Fourier series coefficients",
        "f(x) = \\frac{a_0}{2} + \\sum_{n=1}^{\\infty}\\left[a_n\\cos(nx) + b_n\\sin(nx)\\right]",
        _latex(truncated),
        "First 5 non-zero terms of the Fourier series",
    )

    yield _eq_state(f"f(x) \\approx {_latex(truncated)}", "Fourier series (5 terms)")

    yield {
        "type": "final",
        "answer": f"### Fourier Series\n\n$$\nf(x) \\approx {_latex(truncated)}\n$$",
        "summary": [{"label": "Fourier series (5 terms)", "value": str(truncated)}],
    }


async def _solve_ode(expr_str: str, params: dict):
    """Solve an ODE with general solution derivation."""
    yield _section("ORDINARY DIFFERENTIAL EQUATION")

    t = sp.Symbol("t")
    y = sp.Function("y")(t)

    # Normalize notation
    for notation, replacement in (
        ("y'''", "Derivative(y(t),t,3)"),
        ("y''", "Derivative(y(t),t,2)"),
        ("y'", "Derivative(y(t),t)"),
        ("dy/dt", "Derivative(y(t),t)"),
    ):
        expr_str = expr_str.replace(notation, replacement)

    try:
        parts = expr_str.split("=", 1)
        lhs_s = parts[0].strip()
        rhs_s = parts[1].strip() if len(parts) > 1 else "0"

        lhs_sym = sp.sympify(lhs_s, locals={"y": y, "t": t})
        rhs_sym = sp.sympify(rhs_s, locals={"t": t})
        ode_eq = sp.Eq(lhs_sym, rhs_sym)

        yield _eq_state(sp.latex(ode_eq), "ODE")
        yield {"type": "step", "content": "Classifying the ODE: checking order and linearity."}

        sol = sp.dsolve(ode_eq, y)
        yield _step(
            "solve_ode",
            "Find the general solution",
            sp.latex(ode_eq),
            sp.latex(sol),
            "Using SymPy's ODE solver (integrating factors / characteristic equation)",
        )
        yield _eq_state(sp.latex(sol), "General solution")

        yield {
            "type": "final",
            "answer": f"### General Solution\n\n$$\n{sp.latex(sol)}\n$$",
            "summary": [{"label": "y(t)", "value": str(sol.rhs)}],
        }
    except Exception as exc:
        yield {"type": "error", "message": f"Could not solve ODE: {exc}. Expected format: `y'' + 2*y' + y = sin(t)`"}


async def _calculus_overview(expr_str: str, sym_dict: dict, x: sp.Symbol):
    """Auto-detect and perform differentiation + integration."""
    yield _section("CALCULUS ANALYSIS")

    expr = _parse(expr_str, sym_dict)
    yield _eq_state(f"f({_latex(x)}) = {_latex(expr)}", "Expression")

    d1 = sp.simplify(sp.diff(expr, x))
    integral = sp.simplify(sp.integrate(expr, x))

    yield _step("differentiate", f"Differentiate w.r.t. {_latex(x)}", _latex(expr), _latex(d1), "")
    yield _step("integrate", f"Integrate w.r.t. {_latex(x)}", _latex(expr), f"{_latex(integral)} + C", "")

    yield {
        "type": "final",
        "answer": f"### Calculus Overview\n\n**Derivative:** $f'({_latex(x)}) = {_latex(d1)}$\n\n**Antiderivative:** $\\displaystyle\\int f\\, d{_latex(x)} = {_latex(integral)} + C$",
        "summary": [
            {"label": "f'(x)", "value": str(d1)},
            {"label": "∫f dx", "value": f"{str(integral)} + C"},
        ],
    }
