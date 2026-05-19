"""
backend/methods_registry.py — Method definitions registry

This file contains the complete mapping of domains → problem types → solving methods.

Structure:
  METHODS_REGISTRY[domain][problem_type] = [MethodDefinition, ...]

Add new methods here. Solvers are called by method.solver_name in backend/solvers/.
"""

from .method_generator import MethodDefinition


METHODS_REGISTRY = {
    # ──────────────────────────────────────────────────────────────────────────
    # ALGEBRA
    # ──────────────────────────────────────────────────────────────────────────
    "algebra": {
        "simultaneous_equations": [
            MethodDefinition(
                id="elimination",
                name="Elimination Method",
                description="Multiply equations to cancel variables, then solve sequentially",
                is_recommended=True,
                complexity="basic",
                estimated_steps=8,
                solver_name="solve_algebra_elimination",
                validation_checks=["substitute_back", "all_variables_found"]
            ),
            MethodDefinition(
                id="substitution",
                name="Substitution Method",
                description="Isolate one variable from each equation, then substitute",
                is_recommended=False,
                complexity="intermediate",
                estimated_steps=10,
                solver_name="solve_algebra_substitution",
                validation_checks=["substitute_back", "all_variables_found"]
            ),
            MethodDefinition(
                id="matrix",
                name="Matrix Method (Gaussian Elimination)",
                description="Form augmented matrix [A|b], row-reduce to REF, then back-substitute",
                is_recommended=False,
                complexity="intermediate",
                estimated_steps=12,
                solver_name="solve_algebra_matrix",
                validation_checks=["determinant_nonzero", "substitute_back"]
            ),
            MethodDefinition(
                id="cramers_rule",
                name="Cramer's Rule",
                description="Solve using determinants: x = det(A_x) / det(A)",
                is_recommended=False,
                complexity="advanced",
                estimated_steps=6,
                solver_name="solve_algebra_cramers",
                validation_checks=["determinant_nonzero", "substitute_back"]
            ),
        ],
        "quadratic_equation": [
            MethodDefinition(
                id="quadratic_formula",
                name="Quadratic Formula",
                description="x = (-b ± √(b²-4ac)) / 2a",
                is_recommended=True,
                complexity="basic",
                estimated_steps=4,
                solver_name="solve_quadratic_formula",
                validation_checks=["discriminant", "substitute_back"]
            ),
            MethodDefinition(
                id="factorization",
                name="Factorization (if possible)",
                description="Factor into (px+q)(rx+s) = 0, then solve",
                is_recommended=False,
                complexity="intermediate",
                estimated_steps=5,
                solver_name="solve_quadratic_factor",
                validation_checks=["factorable", "substitute_back"]
            ),
            MethodDefinition(
                id="completing_square",
                name="Completing the Square",
                description="Rewrite as (x+p)² = q, then solve",
                is_recommended=False,
                complexity="intermediate",
                estimated_steps=6,
                solver_name="solve_quadratic_complete_square",
                validation_checks=["substitute_back"]
            ),
        ],
        "polynomial_roots": [
            MethodDefinition(
                id="symbolic",
                name="Symbolic Solver (SymPy)",
                description="Exact algebraic solution for polynomial roots",
                is_recommended=True,
                complexity="basic",
                estimated_steps=3,
                solver_name="solve_polynomial_symbolic",
                validation_checks=["degree_match", "all_roots_real_or_complex"]
            ),
            MethodDefinition(
                id="numerical",
                name="Numerical Method (Newton-Raphson)",
                description="Iterative approximation for complex polynomials",
                is_recommended=False,
                complexity="advanced",
                estimated_steps=15,
                solver_name="solve_polynomial_numerical",
                validation_checks=["convergence", "root_proximity"]
            ),
        ],
        "linear_equation": [
            MethodDefinition(
                id="direct_solve",
                name="Direct Solution",
                description="Isolate variable: ax + b = 0 → x = -b/a",
                is_recommended=True,
                complexity="basic",
                estimated_steps=2,
                solver_name="solve_linear_direct",
                validation_checks=["substitute_back"]
            ),
        ],
        "simplification": [
            MethodDefinition(
                id="algebraic_simplify",
                name="Algebraic Simplification",
                description="Combine like terms, factor, expand as needed",
                is_recommended=True,
                complexity="basic",
                estimated_steps=5,
                solver_name="solve_simplify",
                validation_checks=["expression_equivalent"]
            ),
        ],
        "expansion": [
            MethodDefinition(
                id="expand_brackets",
                name="Expand Brackets (FOIL / Distribution)",
                description="Apply distributive property: a(b+c) = ab + ac",
                is_recommended=True,
                complexity="basic",
                estimated_steps=4,
                solver_name="solve_expand",
                validation_checks=["expression_equivalent"]
            ),
        ],
    },

    # ──────────────────────────────────────────────────────────────────────────
    # CALCULUS
    # ──────────────────────────────────────────────────────────────────────────
    "calculus": {
        "differentiation": [
            MethodDefinition(
                id="symbolic",
                name="Symbolic Differentiation",
                description="Exact derivative using SymPy rules",
                is_recommended=True,
                complexity="basic",
                estimated_steps=5,
                solver_name="solve_differentiate_symbolic",
                validation_checks=["derivative_check"]
            ),
            MethodDefinition(
                id="power_rule",
                name="Power Rule (d/dx x^n = n·x^(n-1))",
                description="Step-by-step application of power rule",
                is_recommended=False,
                complexity="basic",
                estimated_steps=3,
                solver_name="solve_differentiate_power_rule",
                validation_checks=["derivative_check"]
            ),
            MethodDefinition(
                id="product_rule",
                name="Product Rule (d/dx[uv] = u'v + uv')",
                description="For products of functions",
                is_recommended=False,
                complexity="intermediate",
                estimated_steps=6,
                solver_name="solve_differentiate_product",
                validation_checks=["derivative_check"]
            ),
            MethodDefinition(
                id="chain_rule",
                name="Chain Rule (d/dx[f(g(x))] = f'(g)·g')",
                description="For composite functions",
                is_recommended=False,
                complexity="intermediate",
                estimated_steps=7,
                solver_name="solve_differentiate_chain",
                validation_checks=["derivative_check"]
            ),
        ],
        "integration": [
            MethodDefinition(
                id="symbolic",
                name="Symbolic Integration",
                description="Exact antiderivative using SymPy",
                is_recommended=True,
                complexity="basic",
                estimated_steps=4,
                solver_name="solve_integrate_symbolic",
                validation_checks=["integration_check"]
            ),
            MethodDefinition(
                id="substitution",
                name="u-Substitution",
                description="Change of variable: u = g(x), du = g'(x)dx",
                is_recommended=False,
                complexity="intermediate",
                estimated_steps=8,
                solver_name="solve_integrate_substitution",
                validation_checks=["integration_check"]
            ),
            MethodDefinition(
                id="integration_by_parts",
                name="Integration by Parts",
                description="∫u·dv = uv - ∫v·du",
                is_recommended=False,
                complexity="intermediate",
                estimated_steps=9,
                solver_name="solve_integrate_by_parts",
                validation_checks=["integration_check"]
            ),
            MethodDefinition(
                id="partial_fractions",
                name="Partial Fractions",
                description="Decompose P(x)/Q(x) into partial fractions, then integrate",
                is_recommended=False,
                complexity="advanced",
                estimated_steps=12,
                solver_name="solve_integrate_partial_fractions",
                validation_checks=["integration_check"]
            ),
        ],
        "definite_integral": [
            MethodDefinition(
                id="fundamental_theorem",
                name="Fundamental Theorem of Calculus",
                description="∫[a,b] f = F(b) - F(a) where F is antiderivative",
                is_recommended=True,
                complexity="basic",
                estimated_steps=5,
                solver_name="solve_definite_integral",
                validation_checks=["area_positive", "bounds_valid"]
            ),
        ],
        "limit_evaluation": [
            MethodDefinition(
                id="symbolic",
                name="Symbolic Limit (SymPy)",
                description="Exact limit computation",
                is_recommended=True,
                complexity="basic",
                estimated_steps=3,
                solver_name="solve_limit_symbolic",
                validation_checks=[]
            ),
        ],
        "ode_solve": [
            MethodDefinition(
                id="symbolic",
                name="Symbolic ODE Solver",
                description="Exact solution for differential equations (SymPy dsolve)",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=8,
                solver_name="solve_ode_symbolic",
                validation_checks=["ode_check"]
            ),
        ],
    },

    # ──────────────────────────────────────────────────────────────────────────
    # STRUCTURAL MECHANICS
    # ──────────────────────────────────────────────────────────────────────────
    "structural": {
        "simply_supported_beam": [
            MethodDefinition(
                id="equilibrium",
                name="Equilibrium Method (ΣF=0, ΣM=0)",
                description="Apply force and moment equilibrium to find reactions",
                is_recommended=True,
                complexity="basic",
                estimated_steps=6,
                solver_name="solve_beam_equilibrium",
                validation_checks=["force_balance", "moment_balance", "reactions_physical"]
            ),
            MethodDefinition(
                id="macaulay",
                name="Macaulay's Method",
                description="Singularity functions for distributed and point loads",
                is_recommended=False,
                complexity="advanced",
                estimated_steps=14,
                solver_name="solve_beam_macaulay",
                validation_checks=["shear_continuity", "moment_continuity"]
            ),
            MethodDefinition(
                id="direct_integration",
                name="Direct Integration (EI·y″ = M(x))",
                description="Integrate M(x) twice with boundary conditions",
                is_recommended=False,
                complexity="intermediate",
                estimated_steps=10,
                solver_name="solve_beam_direct_integration",
                validation_checks=["boundary_conditions", "deflection_continuous"]
            ),
            MethodDefinition(
                id="moment_area",
                name="Moment-Area Theorems",
                description="Use area of M/EI diagram for slopes and deflections",
                is_recommended=False,
                complexity="advanced",
                estimated_steps=11,
                solver_name="solve_beam_moment_area",
                validation_checks=["area_method_consistency"]
            ),
        ],
        "cantilever_beam": [
            MethodDefinition(
                id="equilibrium",
                name="Equilibrium Method (ΣF=0, ΣM=0)",
                description="Apply equilibrium at fixed end to find reactions",
                is_recommended=True,
                complexity="basic",
                estimated_steps=5,
                solver_name="solve_beam_equilibrium",
                validation_checks=["force_balance", "moment_balance"]
            ),
            MethodDefinition(
                id="macaulay",
                name="Macaulay's Method",
                description="Handle distributed and point loads with singularity functions",
                is_recommended=False,
                complexity="advanced",
                estimated_steps=13,
                solver_name="solve_beam_macaulay",
                validation_checks=["shear_continuity", "moment_continuity"]
            ),
        ],
        "fixed_beam": [
            MethodDefinition(
                id="equilibrium",
                name="Equilibrium Method",
                description="Apply equilibrium at both fixed ends",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=8,
                solver_name="solve_beam_equilibrium",
                validation_checks=["force_balance", "moment_balance"]
            ),
        ],
        "truss_analysis": [
            MethodDefinition(
                id="method_of_joints",
                name="Method of Joints",
                description="Equilibrium at each joint node to find member forces",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=10,
                solver_name="solve_truss_joints",
                validation_checks=["equilibrium_all_joints", "all_members_solved"]
            ),
            MethodDefinition(
                id="method_of_sections",
                name="Method of Sections",
                description="Cut through truss and apply equilibrium to section",
                is_recommended=False,
                complexity="advanced",
                estimated_steps=8,
                solver_name="solve_truss_sections",
                validation_checks=["section_equilibrium"]
            ),
        ],
        "bending_moment": [
            MethodDefinition(
                id="shear_force_integration",
                name="Shear Force Integration",
                description="M(x) = ∫V(x)dx with proper load discontinuity handling",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=8,
                solver_name="solve_bending_moment",
                validation_checks=["moment_continuity", "point_loads_handled"]
            ),
        ],
        "shear_force": [
            MethodDefinition(
                id="equilibrium_method",
                name="Equilibrium (Section Method)",
                description="Cut beam at section, sum forces to find shear",
                is_recommended=True,
                complexity="basic",
                estimated_steps=5,
                solver_name="solve_shear_force",
                validation_checks=["force_balance"]
            ),
        ],
        "beam_deflection": [
            MethodDefinition(
                id="direct_integration",
                name="Direct Integration (EI·y″ = M)",
                description="Integrate bending moment equation twice",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=12,
                solver_name="solve_beam_deflection",
                validation_checks=["boundary_conditions"]
            ),
            MethodDefinition(
                id="virtual_work",
                name="Virtual Work Method",
                description="Apply virtual load and use work-energy principle",
                is_recommended=False,
                complexity="advanced",
                estimated_steps=14,
                solver_name="solve_beam_deflection_virtual",
                validation_checks=["virtual_work_principle"]
            ),
        ],
        "stress_strain": [
            MethodDefinition(
                id="hookes_law",
                name="Hooke's Law (σ = E·ε)",
                description="Calculate stress and strain from load",
                is_recommended=True,
                complexity="basic",
                estimated_steps=4,
                solver_name="solve_stress_strain",
                validation_checks=["elastic_limit"]
            ),
        ],
    },

    # ──────────────────────────────────────────────────────────────────────────
    # MECHANICS
    # ──────────────────────────────────────────────────────────────────────────
    "mechanics": {
        "projectile_motion": [
            MethodDefinition(
                id="kinematic_equations",
                name="Kinematic Equations (SUVAT)",
                description="Apply s=ut+½at² separately for horizontal and vertical components",
                is_recommended=True,
                complexity="basic",
                estimated_steps=8,
                solver_name="solve_projectile_kinematics",
                validation_checks=["time_positive", "range_positive"]
            ),
            MethodDefinition(
                id="energy_method",
                name="Energy Method",
                description="Use kinetic energy and potential energy conservation",
                is_recommended=False,
                complexity="intermediate",
                estimated_steps=7,
                solver_name="solve_projectile_energy",
                validation_checks=["energy_conserved"]
            ),
        ],
        "kinematics": [
            MethodDefinition(
                id="suvat",
                name="SUVAT Equations",
                description="Use s, u, v, a, t equations: v = u + at, s = ut + ½at², etc.",
                is_recommended=True,
                complexity="basic",
                estimated_steps=5,
                solver_name="solve_kinematics",
                validation_checks=["all_equations_consistent"]
            ),
        ],
        "vibrations": [
            MethodDefinition(
                id="shm_equations",
                name="Simple Harmonic Motion (SHM)",
                description="x(t) = A·cos(ωt + φ) with period T = 2π/ω",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=8,
                solver_name="solve_shm",
                validation_checks=["amplitude_positive", "frequency_positive"]
            ),
        ],
        "contact_forces": [
            MethodDefinition(
                id="free_body_diagram",
                name="Free Body Diagram + Newton's 2nd Law",
                description="Draw FBD, identify all forces (friction, normal), apply F=ma",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=7,
                solver_name="solve_friction",
                validation_checks=["friction_valid", "normal_force_positive"]
            ),
        ],
    },

    # ──────────────────────────────────────────────────────────────────────────
    # CIRCUITS
    # ──────────────────────────────────────────────────────────────────────────
    "circuits": {
        "ohms_law": [
            MethodDefinition(
                id="direct_application",
                name="Direct Ohm's Law Application",
                description="V = IR, I = V/R, R = V/I",
                is_recommended=True,
                complexity="basic",
                estimated_steps=2,
                solver_name="solve_ohms_law",
                validation_checks=["positive_values"]
            ),
        ],
        "kvl_analysis": [
            MethodDefinition(
                id="loop_equations",
                name="KVL Loop Equations",
                description="Sum of voltage drops around closed loop = 0",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=8,
                solver_name="solve_kvl",
                validation_checks=["loop_sum_zero"]
            ),
        ],
        "kcl_analysis": [
            MethodDefinition(
                id="node_equations",
                name="KCL Node Equations",
                description="Sum of currents leaving node = 0",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=7,
                solver_name="solve_kcl",
                validation_checks=["current_balance"]
            ),
        ],
        "rc_circuit": [
            MethodDefinition(
                id="differential_equation",
                name="RC Differential Equation",
                description="Solve RC charging/discharging: V(t) = V₀·e^(-t/RC)",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=9,
                solver_name="solve_rc_circuit",
                validation_checks=["time_constant_positive", "asymptotic_behavior"]
            ),
        ],
        "rl_circuit": [
            MethodDefinition(
                id="differential_equation",
                name="RL Differential Equation",
                description="Solve RL transient: I(t) = (V/R)·(1 - e^(-Rt/L))",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=9,
                solver_name="solve_rl_circuit",
                validation_checks=["time_constant_positive"]
            ),
        ],
        "thevenin_equivalent": [
            MethodDefinition(
                id="thevenin_method",
                name="Thévenin Equivalent",
                description="Find V_th (open-circuit), R_th (source-free), simplify network",
                is_recommended=True,
                complexity="advanced",
                estimated_steps=10,
                solver_name="solve_thevenin",
                validation_checks=["network_simplified"]
            ),
        ],
    },

    # ──────────────────────────────────────────────────────────────────────────
    # THERMODYNAMICS
    # ──────────────────────────────────────────────────────────────────────────
    "thermo": {
        "ideal_gas_law": [
            MethodDefinition(
                id="pv_nrt",
                name="Ideal Gas Law (PV = nRT)",
                description="Apply PV = nRT with given constraints",
                is_recommended=True,
                complexity="basic",
                estimated_steps=4,
                solver_name="solve_ideal_gas",
                validation_checks=["values_positive"]
            ),
        ],
        "carnot_cycle": [
            MethodDefinition(
                id="carnot_efficiency",
                name="Carnot Cycle Analysis",
                description="η = 1 - T_C/T_H, compute Q and W",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=7,
                solver_name="solve_carnot",
                validation_checks=["efficiency_valid", "energy_balanced"]
            ),
        ],
        "heat_conduction": [
            MethodDefinition(
                id="fourier_law",
                name="Fourier's Law of Heat Conduction",
                description="Q = kA(ΔT/L) for steady-state conduction",
                is_recommended=True,
                complexity="basic",
                estimated_steps=5,
                solver_name="solve_conduction",
                validation_checks=["heat_flow_positive"]
            ),
        ],
    },

    # ──────────────────────────────────────────────────────────────────────────
    # FLUIDS
    # ──────────────────────────────────────────────────────────────────────────
    "fluids": {
        "bernoulli_equation": [
            MethodDefinition(
                id="bernoulli_direct",
                name="Bernoulli Equation",
                description="P + ½ρv² + ρgh = constant along streamline",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=7,
                solver_name="solve_bernoulli",
                validation_checks=["pressure_positive", "streamline_valid"]
            ),
        ],
        "continuity_equation": [
            MethodDefinition(
                id="continuity_direct",
                name="Continuity Equation (Mass Conservation)",
                description="A₁v₁ = A₂v₂ (incompressible flow)",
                is_recommended=True,
                complexity="basic",
                estimated_steps=3,
                solver_name="solve_continuity",
                validation_checks=["flow_rate_conserved"]
            ),
        ],
    },

    # ──────────────────────────────────────────────────────────────────────────
    # STATISTICS
    # ──────────────────────────────────────────────────────────────────────────
    "statistics": {
        "linear_regression": [
            MethodDefinition(
                id="least_squares",
                name="Least Squares (OLS)",
                description="Fit y = mx + b by minimising residual sum of squares",
                is_recommended=True,
                complexity="intermediate",
                estimated_steps=8,
                solver_name="solve_regression_ols",
                validation_checks=["r_squared", "residual_analysis"]
            ),
        ],
    },

    # ──────────────────────────────────────────────────────────────────────────
    # DATA VISUALIZATION
    # ──────────────────────────────────────────────────────────────────────────
    "data_viz": {
        "function_plot": [
            MethodDefinition(
                id="plot_function",
                name="Plot Function",
                description="Graph y = f(x) over specified domain",
                is_recommended=True,
                complexity="basic",
                estimated_steps=2,
                solver_name="solve_function_plot",
                validation_checks=[]
            ),
        ],
        "scatter_plot": [
            MethodDefinition(
                id="plot_scatter",
                name="Scatter Plot",
                description="Plot (x, y) data points",
                is_recommended=True,
                complexity="basic",
                estimated_steps=2,
                solver_name="solve_scatter_plot",
                validation_checks=[]
            ),
        ],
        "bar_chart": [
            MethodDefinition(
                id="plot_bar",
                name="Bar Chart",
                description="Vertical or horizontal bars for categorical data",
                is_recommended=True,
                complexity="basic",
                estimated_steps=2,
                solver_name="solve_bar_chart",
                validation_checks=[]
            ),
        ],
    },
}
