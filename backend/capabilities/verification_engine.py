"""
verification_engine.py — Solution verification utilities.
"""
from __future__ import annotations

import sympy as sp
import numpy as np


def verify_equation_solution(equation_str: str, solution: dict) -> dict:
    """
    Verify that a solution dict satisfies the given equation.
    Returns a verification event dict.
    """
    try:
        syms = {k: sp.Symbol(k) for k in solution.keys()}
        if "=" in equation_str:
            lhs_s, rhs_s = equation_str.split("=", 1)
            lhs = sp.sympify(lhs_s.strip(), locals=syms)
            rhs = sp.sympify(rhs_s.strip(), locals=syms)
            expr = lhs - rhs
        else:
            expr = sp.sympify(equation_str, locals=syms)

        subst = {sp.Symbol(k): sp.sympify(v) for k, v in solution.items()}
        val = sp.simplify(expr.subs(subst))
        passed = val == 0

        return {
            "type": "verification",
            "passed": passed,
            "checks": [{
                "label": "Solution check",
                "passed": passed,
                "detail": f"Substitution gives: {sp.latex(val)} {'= 0 ✓' if passed else '≠ 0 ✗'}",
            }],
        }
    except Exception as exc:
        return {
            "type": "verification",
            "passed": False,
            "checks": [{"label": "Verification error", "passed": False, "detail": str(exc)}],
        }


def verify_equilibrium(reactions: list[float], loads: list[float]) -> dict:
    """Verify force equilibrium ΣF = 0."""
    total_reactions = sum(reactions)
    total_loads = sum(loads)
    diff = abs(total_reactions - total_loads)
    passed = diff < 1e-6

    return {
        "type": "verification",
        "passed": passed,
        "checks": [{
            "label": "Force equilibrium ΣF = 0",
            "passed": passed,
            "detail": f"Sum of reactions: {total_reactions:.4g}, Sum of loads: {total_loads:.4g} {'✓' if passed else '✗'}",
        }],
    }
