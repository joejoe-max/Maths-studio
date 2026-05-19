"""
calculus_engine.py — Calculus with full derivation trace.

Emits derivation_step events showing each calculus operation.
"""
from __future__ import annotations

import re
import logging
import sympy as sp
from sympy import symbols, diff, integrate, simplify, solve, Symbol

logger = logging.getLogger(__name__)

_TRANSFORMS = None
try:
    from sympy.parsing.sympy_parser import standard_transformations, implicit_multiplication_application
    _TRANSFORMS = standard_transformations + (implicit_multiplication_application,)
except ImportError:
    pass


def _latex(expr) -> str:
    """Convert expression to LaTeX with error handling."""
    try:
        return sp.latex(sp.simplify(expr))
    except Exception as e:
        logger.warning(f"LaTeX conversion failed: {e}")
        return str(expr)


def _parse(s: str, sym_dict: dict | None = None):
    """Parse mathematical expression with improved error handling."""
    if not s or not isinstance(s, str):
        raise ValueError("Expression must be a non-empty string")
    
    # Add multiplication between number and letter (e.g., "2x" -> "2*x")
    s = re.sub(r"(\d)([a-zA-Z])", r"\1*\2", s.strip())
    # Add multiplication between closing and opening parentheses (e.g., ")(")
    s = re.sub(r"\)\s*\(", ")*(",s)
    
    try:
        if _TRANSFORMS:
            from sympy.parsing.sympy_parser import parse_expr
            return parse_expr(s, local_dict=sym_dict or {}, transformations=_TRANSFORMS)
        return sp.sympify(s, locals=sym_dict or {})
    except Exception as e:
        logger.error(f"Parse error for '{s}': {e}")
        raise ValueError(f"Could not parse expression: {s}") from e


def _step(operation: str, op_label: str, from_latex: str, to_latex: str, note: str = "") -> dict:
    """Create a derivation step event."""
    return {
        "type": "derivation_step",
        "operation": operation,
        "operation_label": op_label,
        "from_latex": from_latex,
        "to_latex": to_latex,
        "note": note,
    }


def _eq_state(latex_str: str, label: str = "") -> dict:
    """Create an equation state event."""
    return {"type": "equation_state", "latex": latex_str, "label": label}


def _section(title: str) -> dict:
    """Create a section header event."""
    return {"type": "section", "title": title}


async def solve_calculus(data: dict):
    """Main entry point for calculus problem solving."""
    try:
        params = data.get("parameters", {})
        problem_type = data.get("problem_type", "").lower()
        raw = data.get("raw_query", "").lower()
        expr_raw = params.get("expression", data.get("raw_query", ""))

        if not expr_raw:
            yield {"type": "error", "message": "No expression found. Please provide an expression to analyse."}
            return

        # Clean expression
        expr_clean = _clean_expression(expr_raw)

        if not expr_clean:
            yield {"type": "error", "message": "No expression found after cleaning. Please provide a valid expression."}
            return

        # Detect variables
        all_syms = _detect_variables(expr_clean)
        if not all_syms:
            all_syms = ["x"]
        
        sym_dict = {s: sp.Symbol(s, real=True) for s in all_syms}
        primary_var = sym_dict[all_syms[0]]

        # Route to appropriate solver
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
        logger.exception("Calculus engine error")
        yield {"type": "error", "message": f"Calculus engine error: {exc}"}


def _clean_expression(expr_raw: str) -> str:
    """Clean mathematical expression by removing keywords."""
    keywords = (
        "differentiate", "integrate", "find the derivative", "compute", "evaluate",
        "of", "the", "integral", "derivative", "with respect to", "find", "solve"
    )
    expr_clean = expr_raw
    for kw in keywords:
        expr_clean = re.sub(r"\b" + re.escape(kw) + r"\b", " ", expr_clean, flags=re.I)
    return expr_clean.strip()


def _detect_variables(expr_clean: str) -> list:
    """Detect variables from expression, excluding special constants."""
    # Exclude Euler's number, imaginary unit, and common constants
    excluded = {"e", "E", "I", "pi", "pi", "inf", "oo"}
    all_syms = sorted(set(re.findall(r"\b([a-zA-Z])\b", expr_clean)) - excluded)
    return all_syms


async def _differentiation(expr_str: str, sym_dict: dict, x: sp.Symbol):
    """Differentiation with rule identification."""
    yield _section("DIFFERENTIATION")

    try:
        expr = _parse(expr_str, sym_dict)
    except ValueError as e:
        yield {"type": "error", "message": f"Could not parse expression: {e}"}
        return

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
    for evt in _yield_critical_points(d1_simplified, x):
        yield evt

    yield {
        "type": "final",
        "answer": f"### Differentiation Result\n\n$$\nf'({_latex(x)}) = {_latex(d1_simplified)}\n$$\n\n$$\nf''({_latex(x)}) = {_latex(d2)}\n$$",
        "summary": [
            {"label": "f'(x)", "value": str(d1_simplified)},
            {"label": "f''(x)", "value": str(d2)},
        ],
    }


def _yield_critical_points(derivative, x: sp.Symbol):
    """Try to find and yield critical points."""
    try:
        crit = sp.solve(derivative, x)
        if crit:
            crit_latex = ",\\quad ".join(f"{_latex(x)} = {_latex(sp.simplify(c))}" for c in crit)
            yield _eq_state(crit_latex, f"Critical points: f'({_latex(x)}) = 0")
    except Exception as e:
        logger.debug(f"Could not find critical points: {e}")


def _identify_diff_rule(expr: sp.Expr, x: sp.Symbol) -> str:
    """Identify which differentiation rule applies."""
    try:
        # Check for quotient rule (u/v form)
        if isinstance(expr, sp.Mul) and any(isinstance(arg, sp.Pow) and arg.exp == -1 for arg in expr.args):
            return "Quotient rule: d/dx[u/v] = (u'v - uv')/v²"
        
        # Check for product rule (multiple factors with x)
        if isinstance(expr, sp.Mul):
            factors = expr.args
            x_factors = [f for f in factors if f.has(x)]
            if len(x_factors) >= 2:
                return "Product rule: d(uv)/dx = u'v + uv'"
        
        # Check for power with both base and exponent depending on x
        if isinstance(expr, sp.Pow):
            base_has_x = expr.args[0].has(x)
            exp_has_x = expr.args[1].has(x)
            
            if base_has_x and exp_has_x:
                return "Logarithmic differentiation: y = u^v → ln y = v ln u"
            elif base_has_x and not exp_has_x:
                return "Power rule: d/dx[x^n] = nx^(n-1)"
        
        # Check for composite functions (chain rule)
        if isinstance(expr, (sp.sin, sp.cos, sp.tan, sp.exp, sp.log)):
            if expr.args[0].has(x) and expr.args[0] != x:
                return "Chain rule: d/dx[f(g(x))] = f'(g(x)) · g'(x)"
            elif expr.args[0] == x:
                return f"Standard derivative: d/dx[{type(expr).__name__}(x)]"
        
        # Check for sum/difference
        if isinstance(expr, sp.Add):
            return "Linearity of differentiation: d/dx[u + v] = u' + v'"
        
        return "Direct application of differentiation rules"
    except Exception as e:
        logger.debug(f"Error identifying differentiation rule: {e}")
        return "Direct application of differentiation rules"


async def _integration(expr_str: str, sym_dict: dict, x: sp.Symbol, params: dict):
    """Integration with method identification and definite/indefinite handling."""
    yield _section("INTEGRATION")

    # Check for definite integral limits
    a_lim = params.get("lower_limit", params.get("a_limit"))
    b_lim = params.get("upper_limit", params.get("b_limit"))

    try:
        expr = _parse(expr_str, sym_dict)
    except ValueError as e:
        yield {"type": "error", "message": f"Could not parse expression: {e}"}
        return

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

    # Handle definite integral
    if a_lim is not None and b_lim is not None:
        async for evt in _evaluate_definite_integral(antideriv_simplified, a_lim, b_lim, expr, x):
            yield evt
        return

    yield _eq_state(f"\\int {_latex(expr)}\\, d{_latex(x)} = {_latex(antideriv_simplified)} + C", "Antiderivative")
    yield {
        "type": "final",
        "answer": f"### Indefinite Integral\n\n$$\n\\int {_latex(expr)}\\, d{_latex(x)} = {_latex(antideriv_simplified)} + C\n$$",
        "summary": [{"label": "Antiderivative", "value": f"{str(antideriv_simplified)} + C"}],
    }


async def _evaluate_definite_integral(antideriv, a_lim, b_lim, expr, x):
    """Evaluate a definite integral using the fundamental theorem of calculus."""
    try:
        a_sym = sp.sympify(a_lim)
        b_sym = sp.sympify(b_lim)
        F_b = sp.simplify(antideriv.subs(x, b_sym))
        F_a = sp.simplify(antideriv.subs(x, a_sym))
        definite = sp.simplify(F_b - F_a)

        yield _step(
            "evaluate_limits",
            "Evaluate using the Fundamental Theorem of Calculus",
            f"\\left[{_latex(antideriv)}\\right]_{{{_latex(a_sym)}}}^{{{_latex(b_sym)}}}",
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
                "answer": f"### Definite Integral\n\n$$\n\\int_{{{_latex(a_sym)}}}^{{{_latex(b_sym)}}} {_latex(expr)}\\, d{_latex(x)} = {_latex(definite)} \\approx {decimal_val:.6g}\n$$",
                "summary": [{"label": "Definite integral", "value": str(definite), "decimal": decimal_val}],
            }
        except (ValueError, TypeError):
            yield {
                "type": "final",
                "answer": f"### Definite Integral\n\n$$\n\\int_{{{_latex(a_sym)}}}^{{{_latex(b_sym)}}} {_latex(expr)}\\, d{_latex(x)} = {_latex(definite)}\n$$",
                "summary": [{"label": "Definite integral", "value": str(definite)}],
            }
    except Exception as e:
        logger.debug(f"Could not evaluate definite integral: {e}")


def _identify_integration_method(expr: sp.Expr, x: sp.Symbol) -> str:
    """Identify the appropriate integration method."""
    try:
        # Power rule
        if isinstance(expr, sp.Pow) and expr.args[0] == x:
            return "Power rule: ∫x^n dx = x^(n+1)/(n+1) + C (n ≠ -1)"
        
        # Trigonometric
        if isinstance(expr, (sp.sin, sp.cos)):
            return "Trigonometric integral"
        
        # Exponential
        if isinstance(expr, sp.exp):
            return "Exponential integral: ∫e^x dx = e^x + C"
        
        # Logarithm
        if isinstance(expr, sp.log):
            return "Integration by parts: ∫ln(x) dx = x·ln(x) − x + C"
        
        # Product (could be integration by parts or substitution)
        if isinstance(expr, sp.Mul):
            return "Product form — possibly integration by parts or substitution"
        
        # Rational function
        if isinstance(expr, sp.Add):
            return "Sum of terms — integrate term by term"
        
        return "Standard integration technique"
    except Exception as e:
        logger.debug(f"Error identifying integration method: {e}")
        return "Standard integration technique"


async def _taylor_series(expr_str: str, sym_dict: dict, x: sp.Symbol, params: dict):
    """Taylor/Maclaurin series expansion."""
    yield _section("TAYLOR SERIES EXPANSION")

    try:
        x0 = float(params.get("point", params.get("expansion_point", 0)))
        order = max(2, int(params.get("order", params.get("n", 6))))  # Minimum order of 2
    except (ValueError, TypeError):
        x0 = 0.0
        order = 6

    # Clean keywords from expression
    for kw in ("taylor", "maclaurin", "series", "expansion", "around", "order"):
        expr_str = re.sub(r"\b" + kw + r"\b.*", "", expr_str, flags=re.I).strip()

    try:
        expr = _parse(expr_str.strip(), sym_dict)
    except ValueError as e:
        yield {"type": "error", "message": f"Could not parse expression: {e}"}
        return

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
        try:
            dn = sp.diff(expr, x, n_ord)
            dn_at_x0 = sp.simplify(dn.subs(x, x0))
            
            if dn_at_x0 != 0 or n_ord == 0:  # Always show n=0 term
                factorial_n = sp.factorial(n_ord)
                term_coeff = sp.simplify(dn_at_x0 / factorial_n)
                
                yield _eq_state(
                    f"\\frac{{f^{{({n_ord})}}({x0})}}{{{n_ord}!}} = \\frac{{{_latex(dn_at_x0)}}}{{{_latex(factorial_n)}}} = {_latex(term_coeff)}",
                    f"Term n={n_ord}",
                )
        except Exception as e:
            logger.debug(f"Error computing derivative at x0: {e}")
            continue

    try:
        series = sp.series(expr, x, x0, order)
        series_no_O = series.removeO()

        yield _step(
            "series_result",
            f"Taylor series (order {order})",
            f"f(x) \\approx \\text{{...}}",
            _latex(series_no_O),
            "Full polynomial approximation",
        )

        yield _eq_state(f"f(x) = {_latex(series)}", "Series with error term O((x-x₀)^n)")

        yield {
            "type": "final",
            "answer": f"### Taylor Series of ${_latex(expr)}$ about $x_0 = {x0}$\n\n$$\nf(x) = {_latex(series_no_O)} + O\\left((x-{x0})^{{{order}}}\\right)\n$$",
            "summary": [{"label": "Series", "value": str(series_no_O)}],
        }
    except Exception as e:
        yield {"type": "error", "message": f"Could not compute Taylor series: {e}"}


async def _laplace_transform(expr_str: str, sym_dict: dict, x: sp.Symbol):
    """Laplace transform with standard pair identification."""
    yield _section("LAPLACE TRANSFORM")

    t = sp.Symbol("t", positive=True, real=True)
    s = sp.Symbol("s", real=True)
    local_sym = {**sym_dict, "t": t, "s": s}

    # Clean expression
    for kw in ("laplace", "transform", "of"):
        expr_str = re.sub(r"\b" + kw + r"\b", " ", expr_str, flags=re.I)
    expr_str = expr_str.strip()

    try:
        expr = _parse(expr_str, local_sym)
    except ValueError as e:
        yield {"type": "error", "message": f"Could not parse expression: {e}"}
        return

    yield _eq_state(f"f(t) = {_latex(expr)}", "Time-domain function")
    yield _eq_state(f"F(s) = \\mathcal{{L}}\\{{f(t)\\}} = \\int_0^{{\\infty}} f(t)\\, e^{{-st}}\\, dt", "Laplace transform definition")

    try:
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
    except Exception as e:
        yield {"type": "error", "message": f"Could not compute Laplace transform: {e}"}


async def _fourier_series(expr_str: str, sym_dict: dict, x: sp.Symbol):
    """Fourier series expansion."""
    yield _section("FOURIER SERIES")

    for kw in ("fourier", "series", "of"):
        expr_str = re.sub(r"\b" + kw + r"\b", " ", expr_str, flags=re.I)
    expr_str = expr_str.strip()

    try:
        expr = _parse(expr_str, sym_dict)
    except ValueError as e:
        yield {"type": "error", "message": f"Could not parse expression: {e}"}
        return

    yield _eq_state(f"f(x) = {_latex(expr)}", "Function on $[-\\pi, \\pi]$")

    try:
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
    except Exception as e:
        yield {"type": "error", "message": f"Could not compute Fourier series: {e}"}


async def _solve_ode(expr_str: str, params: dict):
    """Solve an ODE with general solution derivation."""
    yield _section("ORDINARY DIFFERENTIAL EQUATION")

    t = sp.Symbol("t", real=True)
    y = sp.Function("y")(t)

    # Normalize notation (handle various input formats)
    notation_map = [
        ("y'''", "Derivative(y(t),t,3)"),
        ("y''", "Derivative(y(t),t,2)"),
        ("y'", "Derivative(y(t),t)"),
        ("dy/dt", "Derivative(y(t),t)"),
        ("d^2y/dt^2", "Derivative(y(t),t,2)"),
        ("d^3y/dt^3", "Derivative(y(t),t,3)"),
    ]
    
    for notation, replacement in notation_map:
        expr_str = expr_str.replace(notation, replacement)

    try:
        parts = expr_str.split("=", 1)
        if len(parts) != 2:
            yield {"type": "error", "message": "ODE must be in format: equation_lhs = equation_rhs"}
            return
            
        lhs_s = parts[0].strip()
        rhs_s = parts[1].strip()

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

    try:
        expr = _parse(expr_str, sym_dict)
    except ValueError as e:
        yield {"type": "error", "message": f"Could not parse expression: {e}"}
        return

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
