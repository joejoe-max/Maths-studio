"""
matrix_engine.py — Matrix operations with step-by-step derivation.
Handles: determinants (cofactor expansion), inverse, eigenvalues/vectors,
         row reduction, linear system via augmented matrix.
"""
from __future__ import annotations

import sympy as sp


def _latex(expr) -> str:
    return sp.latex(expr)


def _mat_latex(M: sp.Matrix) -> str:
    return sp.latex(M)


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


def _parse_matrix(data) -> sp.Matrix | None:
    """Accept list-of-lists, flat list with shape, or dict."""
    if isinstance(data, list):
        if data and isinstance(data[0], list):
            return sp.Matrix([[sp.sympify(v) for v in row] for row in data])
        else:
            n = int(len(data) ** 0.5)
            if n * n == len(data):
                return sp.Matrix(n, n, [sp.sympify(v) for v in data])
    if isinstance(data, dict):
        rows = data.get("rows", [])
        if rows:
            return sp.Matrix([[sp.sympify(v) for v in row] for row in rows])
    return None




def can_solve(problem) -> float:
    domain = getattr(problem, "domain", None) if not isinstance(problem, dict) else problem.get("domain")
    problem_type = getattr(problem, "problem_type", None) if not isinstance(problem, dict) else problem.get("problem_type")
    if domain == "matrix":
        return 1.0 if not problem_type or problem_type in {'matrix_inverse', 'row_reduction', 'linear_system', 'determinant', 'matrix_operations'} else 0.75
    return 0.0

async def solve_matrix(data: dict):
    params = data.get("parameters", {})
    problem_type = data.get("problem_type", "").lower()
    raw = data.get("raw_query", "").lower()

    matrix_data = params.get("matrix", params.get("a", params.get("A")))
    M = _parse_matrix(matrix_data) if matrix_data else None

    if M is None:
        yield {
            "type": "final",
            "answer": (
                "### Matrix Engine — Input Needed\n\n"
                "Supply a matrix as `matrix: [[1, 2], [3, 4]]` or `A = [[...], [...]]`.\n"
                "Supported operations include determinant, inverse, eigenvalues/eigenvectors, row reduction, and `Ax = b` linear systems."
            ),
            "summary": []
        }
        return

    yield _eq_state(_mat_latex(M), f"{M.shape[0]}×{M.shape[1]} matrix A")

    try:
        if any(kw in raw or kw in problem_type for kw in ("determinant", "det")):
            async for evt in _determinant(M):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("eigenvalue", "eigen", "eigenvect")):
            async for evt in _eigenanalysis(M):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("inverse", "invert")):
            async for evt in _inverse(M):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("row reduce", "rref", "gaussian", "echelon")):
            async for evt in _row_reduction(M):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("solve", "system", "linear system")):
            b_data = params.get("b", params.get("rhs"))
            if b_data is not None:
                b_vec = sp.Matrix([sp.sympify(v) for v in (b_data if isinstance(b_data, list) else [b_data])])
                async for evt in _linear_system(M, b_vec):
                    yield evt
            else:
                async for evt in _matrix_overview(M):
                    yield evt
        else:
            async for evt in _matrix_overview(M):
                yield evt
    except Exception as exc:
        yield {"type": "error", "message": f"Matrix computation error: {exc}"}


async def _matrix_overview(M: sp.Matrix):
    """Provide a full matrix analysis overview."""
    yield _section("MATRIX ANALYSIS")

    rows, cols = M.shape
    yield {"type": "step", "content": f"Matrix dimensions: {rows} × {cols}"}

    if rows == cols:
        det = M.det()
        yield _eq_state(f"\\det(A) = {_latex(det)}", "Determinant")

        rank = M.rank()
        yield _eq_state(f"\\text{{rank}}(A) = {rank}", "Rank")

        if det != 0:
            inv = M.inv()
            yield _eq_state(_mat_latex(inv), "Inverse A⁻¹")

        # Eigenvalues
        try:
            eig_data = M.eigenvects()
            eig_latex = ",\\quad ".join(
                f"\\lambda_{{{i+1}}} = {_latex(sp.simplify(val))}" for i, (val, mult, _) in enumerate(eig_data)
            )
            yield _eq_state(eig_latex, "Eigenvalues")
        except Exception:
            pass

    trace = M.trace() if rows == cols else None
    trace_str = f"\\text{{tr}}(A) = {_latex(trace)}" if trace is not None else ""
    if trace_str:
        yield _eq_state(trace_str, "Trace")

    summary_parts = []
    if rows == cols:
        det = M.det()
        summary_parts.append(f"- **Determinant:** $\\det(A) = {_latex(det)}$")
        summary_parts.append(f"- **Rank:** {M.rank()}")
        if trace is not None:
            summary_parts.append(f"- **Trace:** $\\text{{tr}}(A) = {_latex(trace)}$")
        if det != 0:
            summary_parts.append(f"- **Invertible:** Yes")
        else:
            summary_parts.append(f"- **Singular:** Yes (determinant = 0)")

    yield {
        "type": "final",
        "answer": "### Matrix Overview\n\n" + "\n".join(summary_parts),
    }


async def _determinant(M: sp.Matrix):
    """Compute determinant with cofactor expansion steps for 2×2 and 3×3."""
    yield _section("DETERMINANT")

    rows, cols = M.shape
    if rows != cols:
        yield {"type": "error", "message": "Determinant is only defined for square matrices."}
        return

    det = M.det()
    n = rows

    if n == 2:
        a, b, c, d = M[0,0], M[0,1], M[1,0], M[1,1]
        yield _eq_state(
            f"\\det(A) = ad - bc = {_latex(a)} \\cdot {_latex(d)} - {_latex(b)} \\cdot {_latex(c)}",
            "2×2 determinant formula",
        )
        yield _step(
            "compute_2x2_det",
            "Evaluate",
            f"{_latex(a)} \\cdot {_latex(d)} - {_latex(b)} \\cdot {_latex(c)}",
            f"= {_latex(sp.simplify(a*d))} - {_latex(sp.simplify(b*c))} = {_latex(det)}",
            "Multiply main diagonal, subtract anti-diagonal product",
        )

    elif n == 3:
        yield {"type": "step", "content": "Applying cofactor expansion along the first row."}
        # Cofactor expansion
        row0 = [M[0,0], M[0,1], M[0,2]]
        signs = [1, -1, 1]
        terms = []
        for j in range(3):
            minor = M.minor_submatrix(0, j)
            minor_det = minor.det()
            sign = signs[j]
            term_latex = f"{'+' if sign > 0 else '-'}{_latex(row0[j])} \\cdot \\det{_mat_latex(minor)}"
            terms.append(f"{'+' if sign > 0 else '-'}{_latex(row0[j])} \\cdot ({_latex(minor_det)})")
            yield _step(
                f"cofactor_expansion_col{j}",
                f"Cofactor C_{{{0+1}{j+1}}}: element a_{{1{j+1}}} = {_latex(row0[j])}",
                term_latex,
                f"{'+' if sign > 0 else '-'}{_latex(row0[j])} \\cdot ({_latex(minor_det)}) = {_latex(sp.simplify(sign * row0[j] * minor_det))}",
                f"Minor is the 2×2 matrix obtained by deleting row 1, column {j+1}",
            )

        yield _step(
            "sum_cofactors",
            "Sum all cofactor contributions",
            " + ".join(terms),
            f"\\det(A) = {_latex(det)}",
            "",
        )

    else:
        yield {"type": "step", "content": f"Computing {n}×{n} determinant via LU decomposition."}

    yield _eq_state(f"\\det(A) = {_latex(det)}", "Result")

    if rows == cols:
        if det == 0:
            yield {"type": "step", "content": "Since det(A) = 0, the matrix is **singular** (not invertible)."}
        else:
            yield {"type": "step", "content": f"Since det(A) = {_latex(det)} ≠ 0, the matrix is **invertible**."}

    yield {
        "type": "final",
        "answer": f"### Determinant\n\n$$\\det(A) = {_latex(det)}$$",
        "summary": [{"label": "det(A)", "value": str(det), "decimal": float(det.evalf()) if det.is_number else None}],
    }


async def _eigenanalysis(M: sp.Matrix):
    """Eigenvalue and eigenvector analysis with characteristic polynomial."""
    yield _section("EIGENVALUE ANALYSIS")

    rows, cols = M.shape
    if rows != cols:
        yield {"type": "error", "message": "Eigenvalues are only defined for square matrices."}
        return

    # Characteristic polynomial: det(A - λI) = 0
    lam = sp.Symbol("lambda")
    char_matrix = M - lam * sp.eye(rows)
    char_poly = char_matrix.det()
    char_poly_expanded = sp.expand(char_poly)

    yield _step(
        "characteristic_polynomial",
        "Form the characteristic polynomial det(A − λI) = 0",
        f"\\det(A - \\lambda I) = \\det{_mat_latex(char_matrix)}",
        f"p(\\lambda) = {_latex(char_poly_expanded)} = 0",
        "Eigenvalues are the roots of the characteristic polynomial",
    )

    eigenvals_raw = M.eigenvals()
    eigenvals_sorted = sorted(eigenvals_raw.keys(), key=lambda e: complex(e.evalf()))

    eig_latex_parts = []
    for i, val in enumerate(eigenvals_sorted):
        mult = eigenvals_raw[val]
        val_s = sp.simplify(val)
        eig_latex_parts.append(f"\\lambda_{{{i+1}}} = {_latex(val_s)}" + (f"\\text{{ (mult. {mult})}}" if mult > 1 else ""))

    yield _eq_state(",\\quad ".join(eig_latex_parts), "Eigenvalues")

    # Eigenvectors
    yield _section("EIGENVECTORS")
    eig_data = M.eigenvects()
    summary = []

    for i, (val, mult, vecs) in enumerate(sorted(eig_data, key=lambda e: complex(e[0].evalf()))):
        val_s = sp.simplify(val)
        yield _step(
            f"eigenvector_lambda{i+1}",
            f"Solve (A − λ_{i+1}I)v = 0 for λ_{i+1} = {sp.latex(val_s)}",
            f"(A - {_latex(val_s)}I)\\mathbf{{v}} = 0",
            f"\\mathbf{{v}}_{{{i+1}}} = {_mat_latex(sp.simplify(vecs[0]))}",
            f"Row reduce the augmented matrix [A − {sp.latex(val_s)}I | 0]",
        )
        try:
            summary.append({
                "label": f"λ_{i+1}",
                "value": str(val_s),
                "decimal": float(val_s.evalf()),
            })
        except Exception:
            summary.append({"label": f"λ_{i+1}", "value": str(val_s)})

    result_str = "\n\n".join(
        f"**$\\lambda_{{{i+1}}} = {_latex(sp.simplify(val))}$**, eigenvector: ${_mat_latex(sp.simplify(vecs[0]))}^T$"
        for i, (val, mult, vecs) in enumerate(sorted(eig_data, key=lambda e: complex(e[0].evalf())))
    )
    yield {
        "type": "final",
        "answer": f"### Eigenanalysis\n\n{result_str}",
        "summary": summary,
    }


async def _inverse(M: sp.Matrix):
    """Compute matrix inverse with adjugate method for 2×2/3×3."""
    yield _section("MATRIX INVERSE")

    rows, cols = M.shape
    if rows != cols:
        yield {"type": "error", "message": "Inverse is only defined for square matrices."}
        return

    det = M.det()
    yield _eq_state(f"\\det(A) = {_latex(det)}", "Determinant (required for invertibility check)")

    if det == 0:
        yield {"type": "final", "answer": "Matrix is **singular** (det = 0) — inverse does not exist."}
        return

    yield {"type": "step", "content": "Since det(A) ≠ 0, the matrix is invertible."}

    if rows <= 3:
        adj = M.adjugate()
        yield _step(
            "adjugate",
            "Compute the adjugate matrix (transpose of cofactor matrix)",
            "\\text{adj}(A) = C^T",
            _mat_latex(adj),
            "Each element C_{ij} is (-1)^{i+j} × (minor determinant)",
        )
        yield _step(
            "apply_inverse_formula",
            "Apply: A⁻¹ = adj(A) / det(A)",
            f"A^{{-1}} = \\frac{{1}}{{{_latex(det)}}} {_mat_latex(adj)}",
            _mat_latex(sp.simplify(M.inv())),
            "Scale the adjugate by 1/det(A)",
        )
    else:
        yield {"type": "step", "content": "Computing via Gauss-Jordan elimination on [A | I]."}

    inv = sp.simplify(M.inv())
    yield _eq_state(_mat_latex(inv), "A⁻¹")

    # Verify
    product = sp.simplify(M * inv)
    is_identity = product == sp.eye(rows)
    yield {
        "type": "verification",
        "passed": is_identity,
        "checks": [{
            "label": "Verify A × A⁻¹ = I",
            "passed": is_identity,
            "detail": f"A \\cdot A^{{-1}} = {_mat_latex(product)} {'= I ✓' if is_identity else '≠ I ✗'}",
        }],
    }

    yield {
        "type": "final",
        "answer": f"### Matrix Inverse\n\n$$A^{{-1}} = {_mat_latex(inv)}$$",
    }


async def _row_reduction(M: sp.Matrix):
    """Perform row reduction to RREF with step-by-step row operations."""
    yield _section("ROW REDUCTION (RREF)")
    yield {"type": "step", "content": "Applying elementary row operations to reach reduced row echelon form."}

    current = M.copy().tolist()
    n_rows = M.rows
    n_cols = M.cols

    current_sym = sp.Matrix(current)
    yield _eq_state(_mat_latex(current_sym), "Initial augmented matrix")

    rref, pivots = M.rref()
    yield _eq_state(_mat_latex(rref), "Reduced Row Echelon Form (RREF)")

    rank = len(pivots)
    yield _eq_state(f"\\text{{rank}}(A) = {rank}", f"Rank = number of pivot columns = {rank}")

    if rank < n_rows:
        nullity = n_cols - rank
        yield _eq_state(f"\\dim(\\text{{null}}(A)) = {nullity}", f"Nullity = columns − rank = {nullity}")

    yield {
        "type": "final",
        "answer": f"### RREF Result\n\n$$\n{_mat_latex(rref)}\n$$\n\n- **Rank:** {rank}\n- **Pivot columns:** {list(pivots)}",
    }


async def _linear_system(A: sp.Matrix, b: sp.Matrix):
    """Solve Ax = b with augmented matrix and RREF."""
    yield _section("LINEAR SYSTEM: Ax = b")

    n = A.rows
    augmented = A.row_join(b)
    yield _eq_state(_mat_latex(augmented), "Augmented matrix [A | b]")

    rref, pivots = augmented.rref()
    yield _step(
        "rref",
        "Row reduce augmented matrix to RREF",
        _mat_latex(augmented),
        _mat_latex(rref),
        "Apply Gaussian elimination with back-substitution",
    )

    solution = sp.linsolve((A, b))
    if not solution:
        yield {"type": "final", "answer": "System has **no solution** (inconsistent)."}
        return

    sol_tuple = list(solution)[0]
    n_vars = len(sol_tuple)
    var_names = [f"x_{i+1}" for i in range(n_vars)]
    syms = [sp.Symbol(v) for v in var_names]

    summary = []
    result_parts = []
    for sym, val in zip(syms, sol_tuple):
        val_s = sp.simplify(val)
        yield _eq_state(f"{_latex(sym)} = {_latex(val_s)}", f"Solution for {_latex(sym)}")
        try:
            summary.append({"label": str(sym), "value": str(val_s), "decimal": float(val_s.evalf())})
        except Exception:
            summary.append({"label": str(sym), "value": str(val_s)})
        result_parts.append(f"$$\n{_latex(sym)} = {_latex(val_s)}\n$$")

    yield {
        "type": "final",
        "answer": "### System Solution Ax = b\n\n" + "\n\n".join(result_parts),
        "summary": summary,
    }
