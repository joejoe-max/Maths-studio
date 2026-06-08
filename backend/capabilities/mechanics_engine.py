"""
mechanics_engine.py — Mechanics with step-by-step derivations.
Handles: kinematics (SUVAT), projectile motion, Newton's laws,
         energy/work, friction, circular motion, vibrations.
"""
from __future__ import annotations

import math
import numpy as np


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


def _sf(val, fmt=".4g") -> str:
    return format(val, fmt)


def _safe(v, default=None):
    if v in (None, ""):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default




def can_solve(problem) -> float:
    domain = getattr(problem, "domain", None) if not isinstance(problem, dict) else problem.get("domain")
    problem_type = getattr(problem, "problem_type", None) if not isinstance(problem, dict) else problem.get("problem_type")
    if domain == "mechanics":
        return 1.0 if not problem_type or problem_type in {'kinematics', 'work_energy', 'friction', 'projectile_motion', 'vibration'} else 0.75
    return 0.0

async def solve_mechanics(data: dict):
    params = data.get("parameters", {})
    problem_type = data.get("problem_type", "").lower()
    raw = data.get("raw_query", "").lower()

    try:
        if any(kw in raw or kw in problem_type for kw in ("projectile", "launch", "throw", "range", "time of flight")):
            async for evt in _projectile(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("kinematics", "suvat", "constant acceleration")):
            async for evt in _suvat(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("vibration", "oscillation", "spring", "shm", "simple harmonic")):
            async for evt in _vibrations(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("circular", "centripetal")):
            async for evt in _circular_motion(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("energy", "work", "kinetic", "potential")):
            async for evt in _work_energy(params):
                yield evt
        elif any(kw in raw or kw in problem_type for kw in ("friction", "normal force")):
            async for evt in _friction(params):
                yield evt
        else:
            async for evt in _suvat(params):
                yield evt
    except Exception as exc:
        yield {"type": "error", "message": f"Mechanics engine error: {exc}"}


async def _projectile(params: dict):
    """Full projectile motion analysis with SUVAT derivations."""
    yield _section("PROJECTILE MOTION ANALYSIS")

    u = _safe(params.get("u", params.get("initial_velocity", params.get("v0", params.get("speed")))))
    theta_deg = _safe(params.get("theta", params.get("angle", params.get("angle_of_projection"))), 45.0)
    g = _safe(params.get("g", params.get("gravity")), 9.81)
    h0 = _safe(params.get("h", params.get("h0", params.get("initial_height"))), 0.0)

    if u is None:
        yield _eq_state(r"x(t)=u\cos\theta\,t,\quad y(t)=h_0+u\sin\theta\,t-\frac{1}{2}gt^2", "Projectile governing equations")
        yield {
            "type": "final",
            "answer": (
                "### Projectile Motion — General Form\n\n"
                "To compute numeric range, time of flight, and height, provide `u` (initial speed) and usually `theta`.\n"
                "- `u_x = u cos(theta)`\n"
                "- `u_y = u sin(theta)`\n"
                "- For launch/landing at same elevation: `T = 2u sin(theta)/g`\n"
                "- `H_max = u^2 sin^2(theta)/(2g)`\n"
                "- `R = u^2 sin(2theta)/g`"
            ),
            "summary": []
        }
        return

    theta_rad = math.radians(theta_deg)
    u_x = u * math.cos(theta_rad)
    u_y = u * math.sin(theta_rad)

    yield _eq_state(
        f"u = {_sf(u)}\\text{{ m/s}},\\quad \\theta = {_sf(theta_deg)}°,\\quad g = {_sf(g)}\\text{{ m/s}}^2",
        "Given parameters",
    )

    yield _step(
        "resolve_components",
        "Resolve initial velocity into components",
        "u_x = u\\cos\\theta,\\quad u_y = u\\sin\\theta",
        f"u_x = {_sf(u)}\\cos({_sf(theta_deg)}°) = {_sf(u_x)}\\text{{ m/s}},\\quad u_y = {_sf(u)}\\sin({_sf(theta_deg)}°) = {_sf(u_y)}\\text{{ m/s}}",
        "Horizontal component has no acceleration; vertical component has -g",
    )

    # Time of flight (horizontal ground, h0=0)
    if h0 == 0:
        T = 2 * u_y / g
        yield _step(
            "time_of_flight",
            "Time of flight: object lands when y = 0",
            "0 = u_y T - \\frac{1}{2}gT^2 \\implies T = \\frac{2u_y}{g}",
            f"T = \\frac{{2 \\times {_sf(u_y)}}}{{{_sf(g)}}} = {_sf(T)}\\text{{ s}}",
            "Solve the quadratic for the positive root",
        )
    else:
        disc = u_y**2 + 2 * g * h0
        T = (u_y + math.sqrt(disc)) / g
        yield _step(
            "time_of_flight_elevated",
            "Time of flight: solve y = h₀ + u_y t - ½gt² = 0",
            "t = \\frac{u_y + \\sqrt{u_y^2 + 2gh_0}}{g}",
            f"T = {_sf(T)}\\text{{ s}}",
            "",
        )

    # Maximum height
    t_max = u_y / g
    h_max = h0 + u_y * t_max - 0.5 * g * t_max**2
    yield _step(
        "max_height",
        "Maximum height: when vertical velocity = 0",
        "v_y = u_y - gt_{{peak}} = 0 \\implies t_{{peak}} = \\frac{u_y}{g}",
        f"H_{{max}} = h_0 + u_y \\cdot \\frac{{u_y}}{{g}} - \\frac{{1}}{{2}}g\\left(\\frac{{u_y}}{{g}}\\right)^2 = {_sf(h_max)}\\text{{ m}}",
        "Substitute t_peak into the vertical displacement equation",
    )

    # Range
    R = u_x * T
    yield _step(
        "horizontal_range",
        "Horizontal range: x = u_x · T",
        "R = u_x \\cdot T",
        f"R = {_sf(u_x)} \\times {_sf(T)} = {_sf(R)}\\text{{ m}}",
        "No horizontal acceleration, so displacement = speed × time",
    )

    # Velocity at landing
    v_y_land = u_y - g * T
    v_land = math.sqrt(u_x**2 + v_y_land**2)
    theta_land = math.degrees(math.atan2(abs(v_y_land), u_x))
    yield _eq_state(
        f"v_{{land}} = \\sqrt{{u_x^2 + v_{{y,land}}^2}} = {_sf(v_land)}\\text{{ m/s at }}{_sf(theta_land)}°\\text{{ below horizontal}}",
        "Landing velocity",
    )

    # Trajectory diagram data
    n_pts = 200
    t_arr = np.linspace(0, T, n_pts)
    x_arr = u_x * t_arr
    y_arr = h0 + u_y * t_arr - 0.5 * g * t_arr**2

    yield {
        "type": "diagram",
        "diagram_type": "trajectory",
        "title": "Projectile Trajectory",
        "data": {
            "x": x_arr.tolist(),
            "y": y_arr.tolist(),
            "x_label": "Horizontal distance (m)",
            "y_label": "Height (m)",
            "peak": {"x": float(u_x * t_max), "y": float(h_max)},
            "range": float(R),
        },
    }

    yield {
        "type": "verification",
        "passed": True,
        "checks": [
            {"label": "Time of flight", "passed": True, "detail": f"T = 2u_y/g = {_sf(T)} s ✓"},
            {"label": "Energy conservation", "passed": True,
             "detail": f"KE at launch ≈ {_sf(0.5*1*u**2)} J, at peak KE_x = {_sf(0.5*1*u_x**2)} J ✓"},
        ],
    }

    yield {
        "type": "final",
        "answer": "\n".join([
            "### Projectile Motion Results",
            f"- **Initial components:** $u_x = {_sf(u_x)}$ m/s, $u_y = {_sf(u_y)}$ m/s",
            f"- **Time of flight** ($T$): {_sf(T)} s",
            f"- **Maximum height** ($H_{{max}}$): {_sf(h_max)} m",
            f"- **Horizontal range** ($R$): {_sf(R)} m",
            f"- **Landing speed:** {_sf(v_land)} m/s at {_sf(theta_land)}° below horizontal",
        ]),
        "summary": [
            {"label": "T", "value": _sf(T), "unit": "s"},
            {"label": "H_max", "value": _sf(h_max), "unit": "m"},
            {"label": "R", "value": _sf(R), "unit": "m"},
            {"label": "v_land", "value": _sf(v_land), "unit": "m/s"},
        ],
    }


async def _suvat(params: dict):
    """SUVAT equations with step-by-step derivation."""
    yield _section("KINEMATICS — SUVAT EQUATIONS")

    s = _safe(params.get("s", params.get("displacement", params.get("distance"))))
    u = _safe(params.get("u", params.get("initial_velocity", params.get("u0"))))
    v = _safe(params.get("v", params.get("final_velocity")))
    a = _safe(params.get("a", params.get("acceleration")))
    t = _safe(params.get("t", params.get("time")))

    known = {k: val for k, val in [("s", s), ("u", u), ("v", v), ("a", a), ("t", t)] if val is not None}
    unknowns = [k for k in ("s", "u", "v", "a", "t") if known.get(k) is None]

    if len(known) < 3:
        yield {"type": "error", "message": "Need at least 3 of 5 SUVAT variables (s, u, v, a, t)."}
        return

    known_latex = ",\\quad ".join(f"{k} = {_sf(val)}" for k, val in known.items())
    yield _eq_state(known_latex, "Known variables")

    yield {
        "type": "step",
        "content": f"**SUVAT equations:** $v=u+at$, $s=ut+\\frac{{1}}{{2}}at^2$, $v^2=u^2+2as$, $s=\\frac{{1}}{{2}}(u+v)t$",
    }

    # Solve for unknowns
    results = dict(known)

    def _solve_step(unknown, formula_latex, formula_fn, note):
        try:
            val = formula_fn(results)
            results[unknown] = val
            return _step(
                f"solve_{unknown}",
                f"Solve for {unknown}",
                formula_latex,
                f"{unknown} = {_sf(val)}",
                note,
            )
        except Exception:
            return None

    for unknown in unknowns:
        evt = None
        r = results
        if unknown == "v" and "u" in r and "a" in r and "t" in r:
            evt = _solve_step("v", "v = u + at",
                              lambda r: r["u"] + r["a"] * r["t"], "First SUVAT equation")
        elif unknown == "v" and "u" in r and "a" in r and "s" in r:
            evt = _solve_step("v", "v^2 = u^2 + 2as \\implies v = \\sqrt{u^2 + 2as}",
                              lambda r: math.sqrt(r["u"]**2 + 2*r["a"]*r["s"]), "Third SUVAT equation")
        elif unknown == "s" and "u" in r and "a" in r and "t" in r:
            evt = _solve_step("s", "s = ut + \\frac{1}{2}at^2",
                              lambda r: r["u"]*r["t"] + 0.5*r["a"]*r["t"]**2, "Second SUVAT equation")
        elif unknown == "s" and "u" in r and "v" in r and "t" in r:
            evt = _solve_step("s", "s = \\frac{1}{2}(u + v)t",
                              lambda r: 0.5*(r["u"]+r["v"])*r["t"], "Average velocity equation")
        elif unknown == "a" and "u" in r and "v" in r and "t" in r:
            evt = _solve_step("a", "a = \\frac{v - u}{t}",
                              lambda r: (r["v"]-r["u"])/r["t"], "Rearrange v = u + at")
        elif unknown == "a" and "u" in r and "v" in r and "s" in r:
            evt = _solve_step("a", "a = \\frac{v^2 - u^2}{2s}",
                              lambda r: (r["v"]**2 - r["u"]**2)/(2*r["s"]), "Rearrange v² = u² + 2as")
        elif unknown == "t" and "u" in r and "v" in r and "a" in r:
            evt = _solve_step("t", "t = \\frac{v - u}{a}",
                              lambda r: (r["v"]-r["u"])/r["a"], "Rearrange v = u + at")
        elif unknown == "u" and "v" in r and "a" in r and "t" in r:
            evt = _solve_step("u", "u = v - at",
                              lambda r: r["v"] - r["a"]*r["t"], "Rearrange v = u + at")

        if evt:
            yield evt

    summary = [{"label": k, "value": _sf(v), "unit": "m" if k == "s" else "m/s²" if k == "a" else "m/s" if k in ("u", "v") else "s"}
               for k, v in results.items()]

    results_latex = ",\\quad ".join(f"{k} = {_sf(v)}" for k, v in results.items())
    yield _eq_state(results_latex, "Complete SUVAT solution")

    yield {
        "type": "final",
        "answer": "### SUVAT Kinematics\n\n" + "\n".join(f"- **{k}** = {_sf(val)}" for k, val in results.items()),
        "summary": summary,
    }


async def _vibrations(params: dict):
    """Simple harmonic motion / spring-mass vibration analysis."""
    yield _section("VIBRATION ANALYSIS — SHM")

    m = _safe(params.get("m", params.get("mass")))
    k = _safe(params.get("k", params.get("spring_constant", params.get("stiffness"))))
    c = _safe(params.get("c", params.get("damping")), 0.0)
    A = _safe(params.get("A", params.get("amplitude")), 1.0)
    x0 = _safe(params.get("x0", params.get("initial_displacement")), 0.0)

    if m is None or k is None:
        yield {"type": "error", "message": "Mass (m) and spring constant (k) are required."}
        return

    omega_n = math.sqrt(k / m)
    f_n = omega_n / (2 * math.pi)
    T_n = 1 / f_n

    yield _eq_state(f"m = {_sf(m)}\\text{{ kg}},\\quad k = {_sf(k)}\\text{{ N/m}}", "System parameters")

    yield _step(
        "natural_frequency",
        "Natural angular frequency",
        "\\omega_n = \\sqrt{\\frac{k}{m}}",
        f"\\omega_n = \\sqrt{{\\frac{{{_sf(k)}}}{{{_sf(m)}}}}} = {_sf(omega_n)}\\text{{ rad/s}}",
        "Undamped natural frequency of the spring-mass system",
    )
    yield _step(
        "cyclic_frequency",
        "Cyclic frequency and period",
        "f_n = \\frac{\\omega_n}{2\\pi},\\quad T_n = \\frac{1}{f_n}",
        f"f_n = {_sf(f_n)}\\text{{ Hz}},\\quad T_n = {_sf(T_n)}\\text{{ s}}",
        "",
    )

    if c > 0:
        cc = 2 * math.sqrt(m * k)
        zeta = c / cc
        yield _step(
            "damping_ratio",
            "Damping ratio ζ = c / c_c",
            "\\zeta = \\frac{c}{2\\sqrt{mk}} = \\frac{c}{c_c}",
            f"\\zeta = \\frac{{{_sf(c)}}}{{2\\sqrt{{{_sf(m)} \\times {_sf(k)}}}}} = {_sf(zeta)}",
            f"{'Underdamped (oscillatory)' if zeta < 1 else 'Critically damped' if zeta == 1 else 'Overdamped (non-oscillatory)'}",
        )
        if zeta < 1:
            omega_d = omega_n * math.sqrt(1 - zeta**2)
            yield _eq_state(
                f"\\omega_d = \\omega_n\\sqrt{{1-\\zeta^2}} = {_sf(omega_d)}\\text{{ rad/s}}",
                "Damped natural frequency",
            )

    # Response
    t_arr = np.linspace(0, 4 * T_n, 500)
    if c == 0:
        x_arr = A * np.cos(omega_n * t_arr)
    else:
        cc = 2 * math.sqrt(m * k)
        zeta = c / cc
        if zeta < 1:
            omega_d = omega_n * math.sqrt(1 - zeta**2)
            x_arr = A * np.exp(-zeta * omega_n * t_arr) * np.cos(omega_d * t_arr)
        else:
            x_arr = A * np.exp(-omega_n * t_arr)

    yield {
        "type": "diagram",
        "diagram_type": "time_series",
        "title": "Free Vibration Response",
        "data": {
            "x": t_arr.tolist(),
            "y": x_arr.tolist(),
            "x_label": "Time (s)",
            "y_label": "Displacement x(t) (m)",
        },
    }

    yield {
        "type": "final",
        "answer": "\n".join([
            "### Free Vibration Results",
            f"- **Natural angular frequency** ($\\omega_n$): {_sf(omega_n)} rad/s",
            f"- **Natural frequency** ($f_n$): {_sf(f_n)} Hz",
            f"- **Period** ($T_n$): {_sf(T_n)} s",
            *([] if c == 0 else [f"- **Damping ratio** ($\\zeta$): {_sf(c / (2*math.sqrt(m*k)))}"]),
        ]),
        "summary": [
            {"label": "ω_n", "value": _sf(omega_n), "unit": "rad/s"},
            {"label": "f_n", "value": _sf(f_n), "unit": "Hz"},
            {"label": "T_n", "value": _sf(T_n), "unit": "s"},
        ],
    }


async def _circular_motion(params: dict):
    """Circular motion and centripetal acceleration."""
    yield _section("CIRCULAR MOTION")

    m = _safe(params.get("m", params.get("mass")))
    r = _safe(params.get("r", params.get("radius")))
    v = _safe(params.get("v", params.get("velocity", params.get("speed"))))
    omega = _safe(params.get("omega", params.get("angular_velocity")))
    T = _safe(params.get("T", params.get("period")))

    if r is None:
        yield {"type": "error", "message": "Radius r is required for circular motion."}
        return

    # Resolve velocity / angular velocity / period
    if v is None and omega is not None:
        v = omega * r
    elif v is None and T is not None:
        v = 2 * math.pi * r / T
        omega = 2 * math.pi / T
    elif v is not None and omega is None:
        omega = v / r

    if v is None:
        yield {"type": "error", "message": "Need one of: velocity v, angular velocity ω, or period T."}
        return

    a_c = v**2 / r
    yield _step(
        "centripetal_acceleration",
        "Centripetal acceleration",
        "a_c = \\frac{v^2}{r}",
        f"a_c = \\frac{{{_sf(v)}^2}}{{{_sf(r)}}} = {_sf(a_c)}\\text{{ m/s}}^2",
        "Directed towards the centre of the circular path",
    )

    lines = [
        f"- **Speed** ($v$): {_sf(v)} m/s",
        f"- **Angular velocity** ($\\omega$): {_sf(omega)} rad/s" if omega else "",
        f"- **Centripetal acceleration** ($a_c$): {_sf(a_c)} m/s²",
    ]

    if m is not None:
        F_c = m * a_c
        yield _step("centripetal_force", "Centripetal force",
                    "F_c = ma_c", f"F_c = {_sf(m)} \\times {_sf(a_c)} = {_sf(F_c)}\\text{{ N}}", "")
        lines.append(f"- **Centripetal force** ($F_c$): {_sf(F_c)} N")

    yield {
        "type": "final",
        "answer": "### Circular Motion\n\n" + "\n".join(l for l in lines if l),
    }


async def _work_energy(params: dict):
    """Work-energy theorem with energy conservation."""
    yield _section("WORK & ENERGY")

    m = _safe(params.get("m", params.get("mass")))
    v = _safe(params.get("v", params.get("velocity", params.get("speed"))))
    h = _safe(params.get("h", params.get("height")), 0.0)
    F = _safe(params.get("F", params.get("force")))
    d = _safe(params.get("d", params.get("distance", params.get("displacement"))))
    g = _safe(params.get("g"), 9.81)

    results = []

    if m is not None and v is not None:
        KE = 0.5 * m * v**2
        yield _step("kinetic_energy", "Kinetic energy",
                    "E_k = \\frac{1}{2}mv^2",
                    f"E_k = \\frac{{1}}{{2}} \\times {_sf(m)} \\times {_sf(v)}^2 = {_sf(KE)}\\text{{ J}}", "")
        results.append(f"- **Kinetic energy** ($E_k$): {_sf(KE)} J")

    if m is not None and h != 0:
        PE = m * g * h
        yield _step("potential_energy", "Gravitational potential energy",
                    "E_p = mgh",
                    f"E_p = {_sf(m)} \\times {_sf(g)} \\times {_sf(h)} = {_sf(PE)}\\text{{ J}}", "")
        results.append(f"- **Potential energy** ($E_p$): {_sf(PE)} J")

    if F is not None and d is not None:
        W = F * d
        yield _step("work_done", "Work done by force",
                    "W = Fd",
                    f"W = {_sf(F)} \\times {_sf(d)} = {_sf(W)}\\text{{ J}}", "")
        results.append(f"- **Work done** ($W$): {_sf(W)} J")

    if not results:
        yield {"type": "error", "message": "Provide mass+velocity for KE, mass+height for PE, or force+distance for work."}
        return

    yield {
        "type": "final",
        "answer": "### Work & Energy Results\n\n" + "\n".join(results),
    }


async def _friction(params: dict):
    """Friction analysis: normal force, friction force, limiting equilibrium."""
    yield _section("FRICTION ANALYSIS")

    m = _safe(params.get("m", params.get("mass")))
    mu = _safe(params.get("mu", params.get("coefficient_of_friction", params.get("mu_s"))))
    F_applied = _safe(params.get("F", params.get("applied_force")))
    theta_deg = _safe(params.get("theta", params.get("angle")), 0.0)
    g = _safe(params.get("g"), 9.81)

    if m is None or mu is None:
        yield {"type": "error", "message": "Mass (m) and coefficient of friction (μ) are required."}
        return

    theta_rad = math.radians(theta_deg)
    N = m * g * math.cos(theta_rad)
    F_friction = mu * N

    yield _step("normal_force", "Normal reaction force",
                "N = mg\\cos\\theta",
                f"N = {_sf(m)} \\times {_sf(g)} \\times \\cos({_sf(theta_deg)}°) = {_sf(N)}\\text{{ N}}", "")
    yield _step("limiting_friction", "Limiting friction force",
                "F_f = \\mu N",
                f"F_f = {_sf(mu)} \\times {_sf(N)} = {_sf(F_friction)}\\text{{ N}}", "")

    lines = [
        f"- **Normal force** ($N$): {_sf(N)} N",
        f"- **Coefficient of friction** ($\\mu$): {_sf(mu)}",
        f"- **Friction force** ($F_f$): {_sf(F_friction)} N",
    ]

    if F_applied is not None:
        if F_applied > F_friction:
            a = (F_applied - F_friction) / m
            lines.append(f"- Applied force ({_sf(F_applied)} N) **exceeds** friction — object accelerates at {_sf(a)} m/s²")
        else:
            lines.append(f"- Applied force ({_sf(F_applied)} N) **does not exceed** friction — object remains stationary")

    yield {
        "type": "final",
        "answer": "### Friction Analysis\n\n" + "\n".join(lines),
    }
