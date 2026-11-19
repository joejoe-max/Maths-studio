"""
main.py — Engineering Computation Studio.

FastAPI backend for a deterministic engineering computation pipeline:
raw input is normalized, converted into a canonical problem object, classified
with confidence scores, matched against solver capabilities, validated, solved,
verified where supported, and streamed to the render-only frontend.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import importlib
import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
import zipfile
from typing import AsyncGenerator
import xml.etree.ElementTree as ET

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from google import genai
from google.genai import types

from engine.problem_pipeline import (
    build_problem_spec,
    ensure_requested_method,
    normalize_solver_event,
    solver_domain_for,
    structured_error,
)
from engine.interaction import (
    build_method_selection_event,
    build_missing_parameters_event,
    should_prompt_for_method,
)
from engine.engineering_adapters import prepare_engineering_solver_input
from engine.solver_utils import (
    apply_standard_defaults,
    merge_params,
    parse_user_supplied_value,
    polish_final_answer,
    resolve_numeric_expressions,
)

# ──────────────────────────────────────────────────────────────────[...]
# Logging
# ──────────────────────────────────────────────────────────────────[...]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────[...]
# Config
# ──────────────────────────────────────────────────────────────────[...]

MAX_REQUEST_BYTES         = int(os.environ.get("MAX_REQUEST_BYTES",         25 * 1024 * 1024))
MAX_CONCURRENT_SOLVES     = int(os.environ.get("MAX_CONCURRENT_SOLVES",     1000))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", 60))
RATE_LIMIT_MAX_REQUESTS   = int(os.environ.get("RATE_LIMIT_MAX_REQUESTS",   1000))
ROUTER_TIMEOUT_SECONDS    = float(os.environ.get("ROUTER_TIMEOUT_SECONDS",  20.0))
SOLVE_TIMEOUT_SECONDS     = float(os.environ.get("SOLVE_TIMEOUT_SECONDS",   45.0))
EXPLAINER_PROVIDER        = os.environ.get("EXPLAINER_PROVIDER", "groq").lower()
GROQ_API_KEY              = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL                = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_CHAT_URL             = os.environ.get("GROQ_CHAT_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_TIMEOUT_SECONDS      = float(os.environ.get("GROQ_TIMEOUT_SECONDS", 12.0))

# ──────────────────────────────────────────────────────────────────[...]
# App + shared state
# ──────────────────────────────────────────────────────────────────[...]

app = FastAPI(title="Engineering Studio Kernel")

solve_semaphore       = asyncio.Semaphore(MAX_CONCURRENT_SOLVES)
request_windows: dict[str, list[float]] = {}
request_windows_lock  = asyncio.Lock()

GEMINI_API_KEY  = os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
GEMINI_BASE_URL = os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL")

gemini_client = None
try:
    if GEMINI_BASE_URL:
        # Replit AI Integrations — api_version must be empty string
        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options={"api_version": "", "base_url": GEMINI_BASE_URL},
        )
    elif GEMINI_API_KEY:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    else:
        logger.warning("No Gemini API key configured — deterministic canonical parsing will be used.")
except Exception as _ge:
    logger.warning(f"Gemini client init failed: {_ge} — deterministic canonical parsing will be used.")

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]


class ModelRateLimitError(RuntimeError):
    def __init__(self, user_message: str, retryable: bool = True, retry_after: int | None = None):
        super().__init__(user_message)
        self.user_message = user_message
        self.retryable = retryable
        self.retry_after = retry_after


def _classify_model_rate_limit(message: str) -> ModelRateLimitError | None:
    text = (message or "").lower()
    if not any(token in text for token in ("429", "quota", "rate limit", "resource_exhausted", "too many requests", "high demand", "limit has been reached")):
        return None
    if any(token in text for token in ("quota", "limit has been reached", "daily", "monthly", "billing")):
        return ModelRateLimitError(
            "The AI model quota has been reached. Deterministic solvers still work, but AI interpretation/explanation is paused until the provider limit resets.",
            retryable=False,
        )
    return ModelRateLimitError(
        "The AI model is currently experiencing high demand. Deterministic solvers still work; try the AI-assisted explanation again shortly.",
        retryable=True,
        retry_after=60,
    )

# ──────────────────────────────────────────────────────────────────[...]
# Middleware
# ──────────────────────────────────────────────────────────────────[...]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


class SafetyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"

        cl = request.headers.get("content-length")
        if cl:
            try:
                if int(cl) > MAX_REQUEST_BYTES:
                    return JSONResponse({"error": "Request payload too large."}, status_code=413)
            except ValueError:
                pass

        is_sse = (
            request.url.path == "/api/compute/solve"
            and "text/event-stream" in request.headers.get("accept", "").lower()
        )
        limit = (
            int(os.environ.get("RATE_LIMIT_MAX_REQUESTS_STREAM",
                               str(RATE_LIMIT_MAX_REQUESTS * 2)))
            if is_sse else RATE_LIMIT_MAX_REQUESTS
        )
        now = time.monotonic()
        async with request_windows_lock:
            window = [t for t in request_windows.get(client_ip, [])
                      if now - t < RATE_LIMIT_WINDOW_SECONDS]
            if len(window) >= limit:
                msg = "Too many requests — please wait a moment and try again."
                if is_sse:
                    async def _rl():
                        yield _err(msg)
                    return StreamingResponse(_rl(), media_type="text/event-stream", status_code=429)
                return JSONResponse({"error": msg}, status_code=429)
            window.append(now)
            request_windows[client_ip] = window

        resp = await call_next(request)
        resp.headers["X-RateLimit-Limit"]  = str(limit)
        resp.headers["X-RateLimit-Window"] = str(RATE_LIMIT_WINDOW_SECONDS)
        return resp


app.add_middleware(SafetyMiddleware)


# ──────────────────────────────────────────────────────────────────[...]
# SSE helpers
# ──────────────────────────────────────────────────────────────────[...]

def _evt(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

def _err(
    message: str,
    problem_id: str | None = None,
    stage: str = "solving",
    recoverable: bool = True,
    retry_available: bool = True,
) -> str:
    p = structured_error(
        message,
        problem_id=problem_id,
        stage=stage,
        retryable=retry_available and recoverable,
    )
    return f"data: {json.dumps(p)}\n\n"

def _sse(gen) -> StreamingResponse:
    r = StreamingResponse(gen, media_type="text/event-stream")
    r.headers["Access-Control-Allow-Origin"]  = "*"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    r.headers["Cache-Control"]                = "no-cache"
    r.headers["Connection"]                   = "keep-alive"
    return r


# ──────────────────────────────────────────────────────────────────[...]
# Gemini prompts
# ──────────────────────────────────────────────────────────────────[...]

_IMAGE_OCR_PROMPT = """
You are the OCR stage for an engineering/math solver.

Extract ALL readable text from the image, including equations, units, labels,
question numbers, and diagram annotations. Preserve line breaks where useful.

Return ONLY this JSON shape:
{
  "extracted_text": "...",
  "confidence": 0.0,
  "notes": "brief note about unclear regions, if any"
}

If no readable mathematical or textual content exists, return:
{
  "extracted_text": "",
  "confidence": 0.0,
  "notes": "No readable mathematical or textual content detected in image."
}
"""

_DOCUMENT_ANALYSIS_PROMPT = """
You are a rigorous semantic parser for an engineering and mathematics computation
engine. Your job is to understand what the student MEANS, not to match a fixed
sentence template. The same problem may be written as a formal statement, a
conversation, shorthand, passive voice, reordered clauses, a numbered list, or
a paragraph. Treat these as equivalent when their physical meaning is equivalent.

CORE RULES
1. Read the complete statement before extracting anything. Resolve references
   such as "the beam", "at its other end", "the same pipe", and "respectively".
2. Do not require phrases such as "given", "find", "is subjected to", or "uniform
   distributed load". Recognise synonyms and equivalent descriptions.
3. Separate facts from requests. Identify every stated value, its physical
   quantity, unit, object, location, direction, and condition.
4. Never invent a value, material, support condition, geometry, load position,
   boundary condition, or design code. Do not silently assume a standard case.
5. Convert units to SI only when the source unit is unambiguous. Preserve the
   original value/unit in an additional source note if conversion is performed.
6. Distinguish similar quantities carefully: mass vs weight, pressure vs force,
   total load vs load intensity, diameter vs radius, stress vs force, moment vs
   second moment of area, temperature vs temperature difference.
7. Identify the requested unknown(s) from intent, even when the question says
   "how much", "what will it be", "work out", "obtain", "evaluate", "check",
   "show that", or does not use an explicit command.
8. Keep all linked sub-questions about one physical system together. Do not split
   a beam's reactions, shear force, bending moment, deflection and stress into
   unrelated problems. Split only genuinely independent tasks.
9. If a phrase or value has multiple plausible engineering meanings, preserve
   the ambiguity in missing_information/ambiguities instead of guessing.
10. input_summary MUST be the exact relevant source wording copied from the
    user's input, not an invented or paraphrased replacement. Preserve all
    sentences needed to understand the problem. This lets deterministic parsers
    and audit tools inspect the original evidence.

ENGINEERING EXTRACTION
For structural problems, identify member/system type, supports and restraints,
span/length, cross-section, material, E, I, loads (point/UDL/UVL/moment), load
magnitudes, positions, directions, combinations, and requested responses.
For mechanics, identify bodies, mass, forces, initial/final velocity, acceleration,
time, displacement, angles, motion constraints and reference frame.
For fluids, identify fluid/properties, pipe/duct geometry, flow rate, areas,
velocities, elevations, pressures, head losses and flow regime.
For thermodynamics, identify substance/state, pressure, volume, temperature,
mass/moles, process type, heat and work.
For circuits, identify topology, components, values, source types, polarity,
frequency, initial conditions and requested voltage/current/power.
For every domain, capture constraints, boundary/initial conditions and units.

Use solver-friendly parameter names where they are clear (for example structural:
L, E, I, w, P, a, b, h; mechanics: m, u, v, a, t, s, theta; fluids: Q, A1,
A2, v1, v2, p1, p2, z1, z2; thermo: P, V, T, m, n; circuits: V, I, R, C).
Do not force a quantity into a parameter if its identity is uncertain. Use numeric
JSON values, not numeric strings, and keep units in a separate units object.
Do not output equations unless they are explicitly stated or can be derived
unambiguously from the stated physical relationships. Never fabricate equations.

SEMANTIC EQUIVALENCE EXAMPLE
These all describe the same setup: "a simply supported 6 m beam carries a UDL
of 10 kN/m"; "a beam supported at both ends has a six-metre span and an evenly
distributed load of ten kilonewtons per metre"; "find the end reactions for a
6-metre beam with a uniform load intensity of 10 kN/m". Extract the same support
condition, span, load type, load intensity and requested reactions.

AVAILABLE DOMAINS:
algebra, calculus, structural, mechanics, fluids, thermo, circuits, physics,
controls, statistics, matrix, data_viz, unknown

Return ONLY valid JSON in this shape:
{
  "sub_problems": [
    {
      "id": "p1",
      "domain": "structural",
      "problem_type": "beam_analysis",
      "input_summary": "<exact relevant source wording>",
      "parameters": {
        "L": 6.0,
        "w": 10000.0,
        "support_condition": "simply_supported",
        "load_type": "udl",
        "target_variable": "support_reactions"
      },
      "units": {"L": "m", "w": "N/m"},
      "required_outputs": ["support_reactions"],
      "missing_information": [],
      "ambiguities": [],
      "confidence": 0.0
    }
  ]
}

For EACH engineering-domain sub-problem, place an "engineering_model" object INSIDE that sub-problem object, alongside its parameters and units. Do NOT place it at the response root. This is a solver-independent physical representation,
not another wording classification. Populate it from the meaning of the complete
statement, not from phrase matching. Use this shape:
{
  "entities": [{"id":"beam_1","type":"beam","attributes":{}}, {"id":"support_left","type":"support","attributes":{}}],
  "quantities": [{
    "name":"L","value":6.0,"unit":"m","dimension":"length",
    "role":"known","object":"beam_1","location":null,"direction":null,
    "source_text":"the beam is six metres long","confidence":0.98
  }],
  "relationships": [{"type":"supported_by","source":"beam_1","target":"support_left","attributes":{}}],
  "boundary_conditions": [],
  "initial_conditions": [],
  "requested_outputs": ["support_reactions"],
  "assumptions": [],
  "missing_information": [],
  "ambiguities": [],
  "blocking_issues": []
}
Use entity types and relationship types that describe the actual physical system;
they are open vocabulary, not a closed list. Every extracted quantity should be
attached to the correct object and location when the statement makes that clear.
Keep source_text as an exact evidence excerpt. A value without a reliable unit
must not be assigned a guessed unit. Distinguish explicit facts, derived facts,
and assumptions. Never turn a common textbook convention into an assumption
unless the user states it. If information is ambiguous or absent, record it in
ambiguities or missing_information and do not invent it. Put an issue in
blocking_issues only when the requested result cannot be uniquely determined
without clarification; optional or nonessential omissions must not block a solve.
Keep quantities in parameters too when they map to existing solver parameters.

Use the actual source units and convert to SI in parameters only when certain.
The example above is illustrative; do not assume those values for other inputs.
Return an empty sub_problems list only when there is no solvable math or
engineering task in the input.
"""

# ── Prompt C: student-friendly explanation wrapper ───────────────────────────
_EXPLAIN_PROMPT = """
You are a friendly engineering tutor helping a student understand a solution.

The computation engine has already solved the problem and produced a raw result.
Your job is to rewrite it in clear, encouraging language that a first or
second-year engineering student can follow.

RULES:
1. Keep ALL numerical values EXACTLY as given — do not recalculate or alter them.
2. Walk through the key steps in plain English before giving the final answer.
3. Explain briefly WHY each formula is used (one sentence is enough).
4. Use simple LaTeX math inline ($...$) for equations.
5. End with a short "What this means in practice" sentence.
6. Keep a warm, encouraging tone — like a helpful senior student explaining
   to a classmate, not a textbook.
7. Do NOT add unsolicited warnings, disclaimers, or safety notices.
8. Keep it concise — no more than what is needed to understand the answer.

PROBLEM SUMMARY: {input_summary}

RAW SOLVER OUTPUT:
{raw_answer}

Rewrite this now in your friendly tutor style.
"""


# ──────────────────────────────────────────────────────────────────[...]
# History conversion
# ──────────────────────────────────────────────────────────────────[...]

def _history_to_contents(history: list) -> list:
    out = []
    for msg in history:
        role    = "model" if msg.get("role") == "assistant" else "user"
        content = msg.get("content", "").strip()
        if content:
            out.append(types.Content(role=role, parts=[types.Part.from_text(text=content)]))
    return out


# ──────────────────────────────────────────────────────────────────[...]
# Gemini caller  (shared retry logic)
# ──────────────────────────────────────────────────────────────────[...]

async def _gemini_call(
    system_prompt: str,
    user_message:  str,
    history:       list | None = None,
    image_b64:     str  | None = None,
    image_mime:    str  | None = None,
    temperature:   float       = 0.05,
) -> str:
    contents = _history_to_contents(history or [])

    if image_b64:
        raw = image_b64.split(",")[1] if "," in image_b64 else image_b64
        contents.append(types.Content(
            role="user",
            parts=[
                types.Part.from_bytes(data=base64.b64decode(raw), mime_type=image_mime or "image/jpeg"),
                types.Part.from_text(text=user_message),
            ],
        ))
    else:
        contents.append(types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)],
        ))

    if gemini_client is None:
        raise RuntimeError("Gemini client not configured — provide GEMINI_API_KEY to enable AI routing.")

    last_err = "Unknown error"
    last_rate_limit: ModelRateLimitError | None = None
    for model in GEMINI_MODELS:
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(
                    gemini_client.models.generate_content,
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=temperature,
                    ),
                ),
                timeout=ROUTER_TIMEOUT_SECONDS,
            )
            return resp.text

        except asyncio.TimeoutError:
            last_err = "Gemini timed out"
            continue
        except Exception as exc:
            last_err = str(exc)
            rate_limit = _classify_model_rate_limit(last_err)
            if rate_limit:
                last_rate_limit = rate_limit
                continue
            break

    if last_rate_limit:
        raise last_rate_limit
    raise RuntimeError(last_err)


# ──────────────────────────────────────────────────────────────────[...]
# Validation + normalisation firewall  (runs after every Gemini call)
# ──────────────────────────────────────────────────────────────────[...]

# Patterns that indicate a value is English prose, not math
_PROSE_MARKERS = re.compile(
    r"\b(solve|find|calculate|determine|what\s+is|the\s+equation|"
    r"three|four|five|variables|given\s+that|such\s+that|where|"
    r"linear|system|simultaneous|unknown)\b",
    re.IGNORECASE,
)
_MATH_PRESENT  = re.compile(r"[\d=+\-*/^\\()\[\]]")
_IMPLICIT_MUL  = re.compile(r"(\d)([A-Za-z])")

# Engineering domains where multi-ask questions should NOT be split
_MERGE_DOMAINS = {"structural", "mechanics", "fluids", "thermo", "circuits"}


def _normalize_eq(eq: str) -> str:
    """Move RHS to left side and insert explicit multiplication."""
    eq = eq.strip()
    if "=" in eq:
        lhs, rhs = eq.split("=", 1)
        rhs = rhs.strip()
        lhs = lhs.strip()
        eq = f"({lhs}) - ({rhs})" if not rhs.startswith("-") else f"({lhs}) + ({rhs})"
    return _IMPLICIT_MUL.sub(r"\1*\2", eq).strip()


def _extract_equations_from_text(text: str) -> list[str]:
    """
    Last-resort equation extraction directly from free text.
    Finds lines that look like math equations and normalises them.
    """
    _label_strip = re.compile(r"^\s*(?:\d+\s*[\)\.\:]|eq\s*\d+\s*[\)\.\:]?)\s*", re.I)

    # Split on newlines, semicolons, and inline numbering
    lines_raw = re.split(r"[\n;]", text)
    lines = []
    for line in lines_raw:
        parts = re.split(r"(?<=\S)\s+(?=\d+\s*[\)\.])", line)
        lines.extend(p.strip() for p in parts if p.strip())

    equations = []
    for line in lines:
        line = line.strip()
        # Strip leading numbering
        line = _label_strip.sub("", line).strip()
        if not line:
            continue
        if "=" not in line:
            continue
        if not re.search(r"[A-Za-z]", line):
            continue  # no variables
        if _PROSE_MARKERS.search(line) and not re.search(r"\d", line):
            continue  # pure English with no numbers
        equations.append(_normalize_eq(line))
    return equations


def _sanitize_params(params: dict, domain: str, raw_query: str) -> dict:
    """
    Clean a single sub-problem's parameters dict.
    """
    # Flatten nested params
    if "parameters" in params and isinstance(params["parameters"], dict):
        inner = params.pop("parameters")
        params.update(inner)

    # ── expression field sanitation ──────────────────────────────────────────
    expr = params.get("expression", "")
    if isinstance(expr, str) and expr.strip():
        if _PROSE_MARKERS.search(expr) and not _MATH_PRESENT.search(expr):
            logger.warning(f"Dropping English expression: '{expr[:80]}'")
            del params["expression"]
        elif _PROSE_MARKERS.search(expr) and _MATH_PRESENT.search(expr):
            cleaned = re.sub(
                r"^(solve|find|calculate|evaluate|compute|simplify|determine)"
                r"\s*[:\-]?\s*",
                "", expr, flags=re.I,
            ).strip()
            if cleaned and _MATH_PRESENT.search(cleaned):
                params["expression"] = _IMPLICIT_MUL.sub(r"\1*\2", cleaned)
            else:
                del params["expression"]
        else:
            params["expression"] = _IMPLICIT_MUL.sub(r"\1*\2", expr)

    # ── equations array sanitation ───────────────────────────────────────────
    if "equations" in params:
        raw_eqs = params["equations"]
        if isinstance(raw_eqs, str):
            raw_eqs = [raw_eqs]
        cleaned_eqs = []
        for eq in raw_eqs:
            if not isinstance(eq, str):
                continue
            eq = eq.strip()
            if _PROSE_MARKERS.search(eq) and not _MATH_PRESENT.search(eq):
                continue
            cleaned_eqs.append(_normalize_eq(eq) if "=" in eq else
                                _IMPLICIT_MUL.sub(r"\1*\2", eq))
        if cleaned_eqs:
            params["equations"] = cleaned_eqs
        else:
            del params["equations"]

    # ── For algebra/calculus: recover equations from raw text if needed ──────
    if domain in ("algebra", "calculus"):
        has_expr = bool(params.get("expression", "").strip())
        has_eqs  = bool(params.get("equations"))
        if not has_expr and not has_eqs and raw_query:
            recovered = _extract_equations_from_text(raw_query)
            if recovered:
                logger.info(f"Recovered {len(recovered)} equation(s) from raw query text")
                params["equations"] = recovered

    # ── For data_viz: recover expression from plain English if needed ────────
    if domain == "data_viz":
        if not params.get("expression"):
            inferred = _infer_viz_expression(raw_query)
            if inferred:
                params["expression"] = inferred
                logger.info(f"Inferred viz expression from query: '{inferred}'")
        # Set default x_range if not provided
        if "x_range" not in params:
            params["x_range"] = [-10, 10]

    # ── Remove null/empty entries ────────────────────────────────────────────
    params = {k: v for k, v in params.items()
              if v is not None and v != "" and v != [] and v != {}}

    return params


def _infer_viz_expression(text: str) -> str:
    """
    FIX: Extract the mathematical expression to plot from plain English.
    Handles "plot sine graph", "draw cosine", "graph tan(x)", etc.
    """
    t = text.lower().strip()

    # Map common words to SymPy expressions
    _FUNC_MAP = [
        (r"\bsin(e)?\b",       "sin(x)"),
        (r"\bcos(ine)?\b",     "cos(x)"),
        (r"\btan(gent)?\b",    "tan(x)"),
        (r"\barcsin\b",        "asin(x)"),
        (r"\barccos\b",        "acos(x)"),
        (r"\barctan\b",        "atan(x)"),
        (r"\bexp(onential)?\b","exp(x)"),
        (r"\be\^x\b",          "exp(x)"),
        (r"\blog(arithm)?\b",  "log(x)"),
        (r"\bln\b",            "log(x)"),
        (r"\bsqrt\b",          "sqrt(x)"),
        (r"\bsquare root\b",   "sqrt(x)"),
        (r"\bx\^2\b",          "x**2"),
        (r"\bx squared\b",     "x**2"),
        (r"\bx cubed\b",       "x**3"),
        (r"\bx\^3\b",          "x**3"),
        (r"\b1/x\b",           "1/x"),
        (r"\breciprocal\b",    "1/x"),
    ]

    # First try to find an explicit equation like "y = x^2 + 3x" or "f(x) = ..."
    eq_match = re.search(r"(?:y|f\s*\(\s*x\s*\))\s*=\s*([^\n]+)", t)
    if eq_match:
        expr = eq_match.group(1).strip()
        expr = _IMPLICIT_MUL.sub(r"\1*\2", expr)
        expr = expr.replace("^", "**")
        return expr

    # Then try common named function aliases for plotting expressions.
    for pattern, sympy_expr in _FUNC_MAP:
        if re.search(pattern, t):
            return sympy_expr

    return ""


def _prevent_over_splitting(sub_problems: list) -> list:
    """Merge only dependent follow-up engineering chunks, never all same-domain work."""
    if len(sub_problems) <= 1:
        return sub_problems

    merged: list[dict] = []
    for sub_problem in sub_problems:
        if merged and _same_engineering_setup(merged[-1], sub_problem):
            current = dict(merged[-1])
            current["input_summary"] = " | ".join(
                part for part in (current.get("input_summary"), sub_problem.get("input_summary")) if part
            )
            merged_params = dict(current.get("parameters") or {})
            merged_params.update(sub_problem.get("parameters") or {})
            current["parameters"] = merged_params
            merged[-1] = current
        else:
            merged.append(sub_problem)
    return merged


def _same_engineering_setup(left: dict, right: dict) -> bool:
    left_domain = str(left.get("domain") or "").lower()
    right_domain = str(right.get("domain") or "").lower()
    if left_domain != right_domain or left_domain not in _MERGE_DOMAINS:
        return False
    left_text = str(left.get("input_summary") or "").lower()
    right_text = str(right.get("input_summary") or "").lower()
    combined = f"{left_text}\n{right_text}"
    if _has_shell_buckling_context(combined):
        return True
    if not re.search(r"\b(the|same|this)\s+(beam|pipe|gas|circuit|system|member|shell|cylinder)\b", right_text):
        return False
    left_params = left.get("parameters") or {}
    right_params = right.get("parameters") or {}
    setup_keys = {"L", "P", "w", "span", "length", "D", "Q", "V", "I", "R", "mass", "pressure"}
    return bool(set(left_params) & setup_keys) and not bool(set(right_params) & setup_keys)


def validate_and_normalize(routing: dict, raw_query: str = "") -> dict:
    """
    Firewall between Gemini extraction and solver execution.
    """
    subs = routing.get("sub_problems") or []

    cleaned_subs = []
    for sp in subs:
        if not isinstance(sp, dict):
            continue
        sp = dict(sp)
        domain = sp.get("domain", "unknown").lower()
        params = dict(sp.get("parameters") or {})
        sp["parameters"] = _sanitize_params(params, domain, raw_query)
        cleaned_subs.append(sp)

    cleaned_subs = _prevent_over_splitting(cleaned_subs)

    if len(cleaned_subs) > 5:
        cleaned_subs = cleaned_subs[:5]

    routing["sub_problems"] = cleaned_subs
    return routing


def _enrich_semantic_routing(routing: dict, original_text: str) -> dict:
    """
    Fill gaps in AI extraction with deterministic evidence from the original
    statement. AI interpretation owns intent/classification; deterministic
    extraction may only add parameters it independently recognises and never
    overwrites an AI-extracted value.
    """
    try:
        deterministic = _deterministic_routing_skeleton(original_text)
        deterministic_subs = deterministic.get("sub_problems") or []
        semantic_subs = routing.get("sub_problems") or []
        for index, semantic in enumerate(semantic_subs):
            if not isinstance(semantic, dict):
                continue
            domain = str(semantic.get("domain") or "unknown").lower()
            candidates = [
                item for item in deterministic_subs
                if isinstance(item, dict)
                and str(item.get("domain") or "unknown").lower() == domain
            ]
            indexed = deterministic_subs[index] if index < len(deterministic_subs) else None
            if (
                isinstance(indexed, dict)
                and str(indexed.get("domain") or "unknown").lower() == domain
            ):
                fallback = indexed
            elif len(candidates) == 1:
                fallback = candidates[0]
            else:
                # Do not mix extracted quantities from two same-domain tasks.
                fallback = None
            if not isinstance(fallback, dict):
                continue
            fallback_domain = str(fallback.get("domain") or "unknown").lower()
            if domain not in {"unknown", fallback_domain}:
                continue
            extracted = fallback.get("parameters")
            if isinstance(extracted, dict):
                merged = dict(extracted)
                merged.update(semantic.get("parameters") or {})
                semantic["parameters"] = merged
            if not semantic.get("input_summary"):
                semantic["input_summary"] = fallback.get("input_summary") or original_text
        routing["sub_problems"] = semantic_subs
    except Exception as exc:
        logger.warning("Deterministic semantic enrichment skipped: %s", exc)
    return routing


async def _semantic_route_text(user_input: str, history: list | None = None) -> dict:
    if not _has_solvable_signal(user_input):
        return {"sub_problems": []}
    if not gemini_client:
        return _deterministic_routing_skeleton(user_input)
    try:
        raw = await _gemini_call(
            system_prompt=_DOCUMENT_ANALYSIS_PROMPT,
            user_message=(
                "Segment, classify, and extract the solvable math/engineering problems. "
                "Return only JSON.\n\nInput:\n" + user_input
            ),
            history=history or [],
        )
        parsed = _parse_gemini_json(raw, fallback_domain="unknown")
        if isinstance(parsed.get("sub_problems"), list):
            return _enrich_semantic_routing(parsed, user_input)
    except ModelRateLimitError as exc:
        logger.warning("Gemini semantic stage rate-limited; using deterministic parser: %s", exc)
    except Exception as exc:
        logger.warning("Gemini semantic stage unavailable; using deterministic parser: %s", exc)
    return _deterministic_routing_skeleton(user_input)


# ──────────────────────────────────────────────────────────────────[...]
# Routing orchestrator
# ──────────────────────────────────────────────────────────────────[...]

async def route_and_extract(
    user_input:      str,
    is_image:        bool,
    history:         list,
    input_type:      str = "text",
    filename:        str = "",
    mime_type:       str = "",
    auxiliary_text:  str = "",
    l1_result=None,
) -> dict:
    """
    Returns a standard routing dict with sub_problems list.
    """
    if is_image:
        try:
            ocr_raw = await _gemini_call(
                system_prompt=_IMAGE_OCR_PROMPT,
                user_message="Extract readable engineering/math text from this image. Return only JSON.",
                history=history,
                image_b64=user_input,
                image_mime=mime_type or None,
            )
            ocr_payload = _parse_ocr_json(ocr_raw)
            extracted_text = str(ocr_payload.get("extracted_text") or "").strip()
            if auxiliary_text:
                extracted_text = f"{auxiliary_text}\n{extracted_text}".strip()
            if not _has_solvable_signal(extracted_text):
                return {
                    "error": "No solvable mathematical or engineering problem detected.",
                    "retryable": True,
                    "stage": "ocr",
                }
            routing = await _semantic_route_text(extracted_text, history)
            routing["ocr"] = {
                "extracted_text": extracted_text,
                "confidence": ocr_payload.get("confidence", 0.0),
                "notes": ocr_payload.get("notes", ""),
            }
            return routing
        except ModelRateLimitError as exc:
            return {"error": exc.user_message, "retry_after": exc.retry_after, "retryable": exc.retryable}

    if input_type == "document":
        document = _extract_document_text(user_input, filename=filename, mime_type=mime_type)
        extracted_text = str(document.get("extracted_text") or "").strip()
        if auxiliary_text:
            extracted_text = f"{auxiliary_text}\n{extracted_text}".strip()
        if not _has_solvable_signal(extracted_text):
            return {
                "error": "No solvable mathematical or engineering problem detected.",
                "retryable": True,
                "stage": "document_extraction",
            }
        routing = await _semantic_route_text(extracted_text, history)
        document["extracted_text"] = extracted_text
        routing["document"] = document
        return routing

    return await _semantic_route_text(user_input, history)


def _deterministic_routing_skeleton(user_input: str) -> dict:
    """
    Build a routing shell from the canonical problem-understanding pipeline.

    This intentionally avoids deciding from one-off phrases here. The raw text
    is passed through `build_problem_spec`, which reconstructs quantities,
    equations, units, domain evidence, and problem type from the complete
    statement. The returned shape stays compatible with the downstream Gemini
    validation firewall, but it is no longer an `unknown/general` dead-end.
    """
    try:
        problem_spec = build_problem_spec(user_input, {
            "sub_problems": [{
                "id": "p1",
                "domain": "unknown",
                "problem_type": "general",
                "input_summary": user_input,
                "parameters": {},
                "confidence": 0.0,
            }]
        })
        return {
            "sub_problems": [
                {
                    "id": spec.id or f"p{index}",
                    "domain": spec.domain,
                    "problem_type": spec.problem_type,
                    "input_summary": spec.input_summary or spec.raw_query or user_input,
                    "parameters": spec.parameters,
                    "confidence": spec.canonical.domain_confidence[0].confidence if spec.canonical.domain_confidence else 0.0,
                    "isolated_input": True,
                }
                for index, spec in enumerate(problem_spec.sub_problems[:5], start=1)
            ]
        }
    except Exception as exc:
        logger.warning("Deterministic canonical routing failed: %s", exc)
    return {
        "sub_problems": [{
            "id": "p1",
            "domain": "unknown",
            "problem_type": "general",
            "input_summary": user_input,
            "parameters": {},
            "confidence": 0.0,
        }]
    }


# ──────────────────────────────────────────────────────────────────[...]
# FIX: _parse_gemini_json — replaced walrus-operator lambda with explicit helpers
# ──────────────────────────────────────────────────────────────────[...]

def _extract_first_json_block(text: str) -> str | None:
    """Extract the first {...} block from text. Returns None if not found."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group() if m else None


def _truncate_to_last_brace(text: str) -> str | None:
    """Truncate text to the last '}'. Returns None if no '}' found."""
    idx = text.rfind("}")
    return text[:idx + 1] if idx >= 0 else None


def _parse_gemini_json(raw: str, fallback_domain: str) -> dict:
    """
    Parse Gemini JSON response with four fallback strategies.

    FIX v3: Replaced the Python 3.8/3.9-incompatible walrus-operator-inside-
    lambda pattern with explicit helper functions (_extract_first_json_block,
    _truncate_to_last_brace). This eliminates the crash:
      "_parse_gemini_json.<locals>.<lambda>() missing 1 required positional
       argument: 'm'"
    """
    text = raw.strip()
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$",       "", text, flags=re.MULTILINE)
    text = text.strip()

    # Strategy 1: direct parse
    candidates = [text]
    # Strategy 2: first {...} block (using explicit helper, not lambda)
    candidates.append(_extract_first_json_block(text))
    # Strategy 3: up to last "}"
    candidates.append(_truncate_to_last_brace(text))

    for attempt, candidate in enumerate(candidates):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            return _normalize_routing_shape(data, fallback_domain)
        except json.JSONDecodeError:
            logger.debug(f"JSON parse strategy {attempt + 1} failed")

    logger.warning(f"All JSON strategies failed — using skeleton. Raw[:200]: {raw[:200]}")
    return {
        "sub_problems": [{
            "id":            "p1",
            "domain":        fallback_domain,
            "problem_type":  "general",
            "input_summary": "",
            "parameters":    {},
            "confidence":    0.50,
        }]
    }


def _normalize_routing_shape(data: dict, fallback_domain: str) -> dict:
    """Ensure output always has the sub_problems list structure."""
    if "sub_problems" not in data:
        return {"sub_problems": [{
            "id":            "p1",
            "domain":        data.get("domain", fallback_domain),
            "problem_type":  data.get("problem_type", "general"),
            "input_summary": data.get("input_summary", ""),
            "parameters":    data.get("parameters", {}),
            "confidence":    data.get("confidence", 0.80),
            "engineering_model": data.get("engineering_model", {}),
        }]}

    subs = data["sub_problems"]
    if not isinstance(subs, list):
        subs = [subs] if isinstance(subs, dict) else []
    data["sub_problems"] = [s for s in subs if isinstance(s, dict) and s]
    # Accept a root-level model from older/loose model responses only when
    # there is exactly one sub-problem; never smear one model across many tasks.
    if len(data["sub_problems"]) == 1 and isinstance(data.get("engineering_model"), dict):
        if not data["sub_problems"][0].get("engineering_model"):
            data["sub_problems"][0]["engineering_model"] = data["engineering_model"]
    return data


def _parse_ocr_json(raw: str) -> dict:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE).strip()
    candidates = [text, _extract_first_json_block(text), _truncate_to_last_brace(text)]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            break
        return {
            "extracted_text": str(data.get("extracted_text") or data.get("text") or "").strip(),
            "confidence": data.get("confidence", 0.0),
            "notes": data.get("notes", ""),
        }
    return {"extracted_text": "", "confidence": 0.0, "notes": "OCR response was not valid JSON."}


def _decode_data_url(data: str) -> tuple[bytes, str]:
    """Decode a base64 data URL or plain base64 payload."""
    value = str(data or "")
    mime = "application/octet-stream"
    if value.startswith("data:") and "," in value:
        header, value = value.split(",", 1)
        mime_match = re.match(r"data:([^;]+)", header)
        if mime_match:
            mime = mime_match.group(1)
    try:
        return base64.b64decode(value, validate=False), mime
    except (binascii.Error, ValueError):
        return value.encode("utf-8", errors="ignore"), mime


def _extract_text_from_txt(payload: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return payload.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="ignore").strip()


def _extract_text_from_docx(payload: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        document_xml = archive.read("word/document.xml")
    root = ET.fromstring(document_xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    parts: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if text.strip():
            parts.append(text.strip())
    return "\n".join(parts).strip()


def _extract_text_from_pdf(payload: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(io.BytesIO(payload))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception:
        pass

    text = payload.decode("latin-1", errors="ignore")
    literal_strings = re.findall(r"\(([^()]{2,})\)\s*Tj", text)
    array_strings = re.findall(r"\[((?:\([^()]*\)\s*)+)\]\s*TJ", text)
    for array in array_strings:
        literal_strings.append("".join(re.findall(r"\(([^()]*)\)", array)))
    cleaned = [re.sub(r"\\([()\\])", r"\1", item).strip() for item in literal_strings]
    return "\n".join(item for item in cleaned if item).strip()


def _extract_document_text(document_data: str, filename: str = "", mime_type: str = "") -> dict:
    payload, detected_mime = _decode_data_url(document_data)
    mime = (mime_type or detected_mime or "").lower()
    name = (filename or "").lower()
    try:
        if mime.startswith("text/") or name.endswith(".txt"):
            text = _extract_text_from_txt(payload)
        elif "wordprocessingml" in mime or name.endswith(".docx"):
            text = _extract_text_from_docx(payload)
        elif mime == "application/pdf" or name.endswith(".pdf"):
            text = _extract_text_from_pdf(payload)
        else:
            text = _extract_text_from_txt(payload)
    except Exception as exc:
        logger.warning("Document text extraction failed: %s", exc)
        text = ""
    return {"extracted_text": text.strip(), "mime_type": mime, "filename": filename}


def _has_solvable_signal(text: str) -> bool:
    source = str(text or "")
    if not source.strip():
        return False
    return bool(re.search(
        r"=|\b(?:solve|find|calculate|determine|compute|differentiate|integrate|plot|graph|"
        r"beam|stress|moment|deflection|thermo|gas|heat|turbine|pipe|flow|bernoulli|"
        r"circuit|voltage|current|resistance|transfer\s+function|bode|matrix|eigen|"
        r"mean|variance|projectile|velocity|acceleration|buckl\w*)\b|\d\s*[A-Za-z°Ωμ]",
        source,
        re.I,
    ))


# ──────────────────────────────────────────────────────────────────[...]
# Student-friendly explainer
# ──────────────────────────────────────────────────────────────────[...]

async def _explain_for_student(input_summary: str, raw_answer: str) -> str:
    if EXPLAINER_PROVIDER != "groq" or not GROQ_API_KEY:
        return raw_answer

    prompt = _EXPLAIN_PROMPT.format(input_summary=input_summary, raw_answer=raw_answer)
    try:
        explained = await asyncio.to_thread(_groq_chat_completion, prompt)
        return explained.strip()
    except Exception as exc:
        logger.warning(f"Groq explainer failed, using raw engine answer: {exc}")
        return raw_answer


def _groq_chat_completion(prompt: str) -> str:
    payload = {
        "model": GROQ_MODEL,
        "temperature": 0.2,
        "max_tokens": 1400,
        "messages": [
            {
                "role": "system",
                "content": "You are an explainer only. Never change the engine's numerical or symbolic result.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    request = urllib.request.Request(
        GROQ_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=GROQ_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")[:300]
        raise RuntimeError(f"Groq HTTP {exc.code}: {body}") from exc

    return data["choices"][0]["message"]["content"]


# ──────────────────────────────────────────────────────────────────[...]
# Solver dispatcher
# ──────────────────────────────────────────────────────────────────[...]

_SOLVER_MAP: dict[str, tuple[str, str]] = {
    # ── New derivation-first capability engines ────────────────────────────
    "algebra":    ("capabilities.symbolic_engine",  "solve_algebra"),
    "calculus":   ("capabilities.calculus_engine",  "solve_calculus"),
    "mechanics":  ("capabilities.mechanics_engine", "solve_mechanics"),
    "structural": ("capabilities.beam_engine",      "solve_beam"),
    "shell_buckling": ("capabilities.shell_engine", "solve_shell_buckling"),
    "advanced_structural": ("capabilities.advanced_structural_engine", "solve_advanced_structural"),
    "thermo":     ("capabilities.thermo_engine",    "solve_thermo"),
    "circuits":   ("capabilities.circuit_engine",   "solve_circuits"),
    # ── Matrix sub-domain selected by canonical structure/capability matching
    "matrix":     ("capabilities.matrix_engine",    "solve_matrix"),
    # ── Canonical capability engines ───────────────────────────────────────
    "fluids":     ("capabilities.fluids_engine",     "solve_fluids"),
    "physics":    ("capabilities.physics_engine",    "solve_physics"),
    "controls":   ("capabilities.controls_engine",   "solve_controls"),
    "statistics": ("capabilities.statistics_engine", "solve_statistics"),
    "data_viz":   ("capabilities.data_viz_engine",   "solve_data_viz"),
}

_PT_DOMAIN_OVERRIDE: dict[str, str] = {
    "projectile_motion":     "mechanics",
    "kinematics":            "mechanics",
    "beam_deflection":       "structural",
    "cantilever_beam":       "structural",
    "simply_supported_beam": "structural",
    "fixed_beam":            "structural",
    "truss_analysis":        "structural",
    "shell_buckling":        "shell_buckling",
    "euler_column_buckling": "advanced_structural",
    "shaft_torsion":         "advanced_structural",
    "thin_pressure_vessel":  "advanced_structural",
    "bernoulli_equation":    "fluids",
    "hydrostatics":          "fluids",
    "buoyancy":              "fluids",
    "snells_law":            "physics",
    "doppler_effect":        "physics",
    "wave_mechanics":        "physics",
    "bode_plot":             "controls",
    "step_response":         "controls",
    "linear_regression":     "statistics",
    "hypothesis_test":       "statistics",
    # Matrix sub-domain
    "matrix_operations":     "matrix",
    "eigenvalue_analysis":   "matrix",
    "determinant":           "matrix",
    "matrix_inverse":        "matrix",
    "row_reduction":         "matrix",
    # Linear equation systems stay in algebra so step-by-step symbolic
    # elimination/substitution remains available. Matrix is selected only
    # when the canonical domain itself is matrix.
    # FIX: ensure function_plot routes to data_viz
    "function_plot":         "data_viz",
    "scatter_plot":          "data_viz",
    "bar_chart":             "data_viz",
    "histogram":             "data_viz",
}


def _get_solver(domain: str, problem_type: str, raw_query: str = "", spec=None):
    effective = _PT_DOMAIN_OVERRIDE.get(problem_type, domain).lower()
    entry = _SOLVER_MAP.get(effective) or _SOLVER_MAP.get(domain.lower())
    if entry is None:
        logger.error(f"No solver for domain='{domain}' type='{problem_type}'")
        return None
    module_path, fn_name = entry
    try:
        module = importlib.import_module(module_path)
        if spec is not None and hasattr(module, "can_solve"):
            capability_score = float(module.can_solve(spec.canonical))
            if capability_score <= 0:
                logger.error(
                    "Solver capability rejected domain='%s' type='%s' module='%s' score=%.3f",
                    domain,
                    problem_type,
                    module_path,
                    capability_score,
                )
                return None
        return getattr(module, fn_name)
    except (ImportError, AttributeError) as exc:
        logger.error(f"Cannot load {module_path}.{fn_name}: {exc}")
        return None


# ──────────────────────────────────────────────────────────────────[...]
# Step filter
# ──────────────────────────────────────────────────────────────────[...]

_BOILERPLATE = [
    re.compile(r"^initializ(ing|ation)", re.I),
    re.compile(r"^(applying|computing|analyzing|evaluating|executing|running)"
               r"\s+(the\s+)?(kernel|engine|solver|system|module)", re.I),
    re.compile(r"(kernel|engine|solver)\s*\.{2,3}$", re.I),
]

def _is_real_step(content: str) -> bool:
    c = (content or "").strip()
    if len(c) < 15:
        return False
    if any(p.search(c) for p in _BOILERPLATE):
        return False
    return bool(re.search(r"[\d$=+\-*/^\\()\[\]]", c))


# ──────────────────────────────────────────────────────────────────[...]
# Sub-problem pre-processing
# ──────────────────────────────────────────────────────────────────[...]

def _clean(domain: str, sub: dict) -> dict:
    """
    Domain-aware parameter cleaning called AFTER validate_and_normalize().
    """
    sub    = dict(sub)
    params = dict(sub.get("parameters") or {})
    expr   = params.get("expression", "")

    if isinstance(expr, str) and expr.strip():
        word_count   = len(re.findall(r"[A-Za-z]{3,}", expr))
        has_sentence = any(t in expr.lower() for t in (
            "what", "find", "minimum", "maximum", "problem",
            "value of", "how much", "determine",
        ))

        if domain not in {"algebra", "calculus", "data_viz"}:
            if word_count > 6 or has_sentence:
                params.pop("expression", None)
        else:
            if word_count > 10 and not _MATH_PRESENT.search(expr):
                params.pop("expression", None)

    sub["parameters"] = params
    return sub


# ──────────────────────────────────────────────────────────────────[...]
# Friendly error messages
# ───────────────────────────────────────────────────────────���──────[...]

_FRIENDLY_ERRORS: dict[str, str] = {
    "mass":         "It looks like the mass wasn't specified. Try adding e.g. 'm = 5 kg'.",
    "velocity":     "The velocity doesn't seem to be given. Try adding e.g. 'v = 10 m/s'.",
    "length":       "The length or span wasn't found. Try adding e.g. 'L = 3 m'.",
    "force":        "No force value was detected. Try adding e.g. 'F = 50 N'.",
    "expression":   "No mathematical expression was found. Please type the equation or function.",
    "angle":        "The angle is missing. Try adding e.g. 'at 30°' or 'theta = 45'.",
}

def _friendly_missing(missing: list) -> str:
    def _hint(p) -> str:
        if isinstance(p, dict):
            label = p.get("label") or p.get("key") or str(p)
            unit  = p.get("unit", "")
            hint  = p.get("hint", "")
            base  = _FRIENDLY_ERRORS.get(label.lower(), f"'{label}' is needed but wasn't found.")
            if unit and unit not in base:
                base = base.rstrip(".") + f" (unit: {unit})."
            if hint:
                base = base.rstrip(".") + f" Hint: {hint}."
            return base
        key = str(p)
        return _FRIENDLY_ERRORS.get(key.lower(), f"'{key}' is needed but wasn't found.")
    hints = [_hint(p) for p in missing]
    if len(hints) == 1:
        return f"One thing missing: {hints[0]}"
    return (
        "A few things are needed to solve this:\n"
        + "\n".join(f"  • {h}" for h in hints)
        + "\n\nJust add them to your message and try again!"
    )


# ────────────────────────────────────────────────────────���─────────[...]
# HTTP endpoints
# ──────────────────────────────────────────────────────────────────[...]

# ──────────────────────────────────────────────────────────────────[...]
# Method catalogue — single source of truth (moved from frontend)
# ──────────────────────────────────────────────────────────────────[...]

_POPUP_DOMAINS = {"algebra", "calculus", "structural", "mechanics", "circuits", "thermo", "fluids"}


# ──────────────────────────────────────────────────────────────────[...]
# HTTP endpoints
# ──────────────────────────────────────────────────────────────────[...]

@app.get("/health")
async def health():
    return {"status": "ok", "service": "engineering-studio"}


@app.post("/api/compute/analyze")
async def analyze(request: Request):
    """
    Backend-owned analysis endpoint: normalize input, build the canonical
    problem object, classify with confidence scores, and return feasible
    methods. The frontend may display this data but must not infer it.
    """
    try:
        raw_data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    user_input = raw_data.get("input", "").strip()
    if not user_input:
        return JSONResponse({
            "domain": None, "problem_structure": None,
            "methods": [], "needs_selection": False,
            "auto_selected": True, "selected_method": None, "confidence": 0.0,
        })

    routing = {"sub_problems": [{"id": "p1", "domain": "unknown", "problem_type": "general", "input_summary": user_input, "parameters": {}}]}
    problem_spec = build_problem_spec(user_input, routing)
    sub_spec = problem_spec.sub_problems[0] if problem_spec.sub_problems else None
    methods = [method.model_dump() for method in (sub_spec.feasible_methods if sub_spec else [])]

    # Case A: single method → auto-select
    # Case B: multiple methods + popup domain → ask user
    # Case C/D: user-specified method handled in /solve
    needs_selection = (
        bool(sub_spec and should_prompt_for_method(sub_spec, _POPUP_DOMAINS))
    )
    auto_selected = not needs_selection
    selected_method = None
    if sub_spec and auto_selected:
        selected_method = sub_spec.requested_method or sub_spec.selected_method

    return JSONResponse({
        "domain":            sub_spec.domain if sub_spec else None,
        "problem_structure": sub_spec.problem_type if sub_spec else None,
        "canonical_problem": sub_spec.canonical.model_dump() if sub_spec else None,
        "methods":           methods,
        "needs_selection":   needs_selection,
        "auto_selected":     auto_selected,
        "selected_method":   selected_method,
        "confidence":        sub_spec.canonical.domain_confidence[0].confidence if sub_spec and sub_spec.canonical.domain_confidence else 0.0,
        "domain_confidence": [score.model_dump() for score in (sub_spec.canonical.domain_confidence if sub_spec else [])],
    })


@app.options("/api/compute/solve")
async def options_solve():
    return {}


@app.post("/api/compute/solve")
async def solve(request: Request):
    logger.info("Solve request received")

    try:
        raw_data = await request.json()
    except Exception as exc:
        async def _bad():
            yield _err("Couldn't read the request — is it valid JSON?")
        return _sse(_bad())

    user_input = raw_data.get("input", "").strip()
    attached_text = raw_data.get("text", "").strip()
    input_type = raw_data.get("type", "text")
    filename   = raw_data.get("filename", "")
    mime_type  = raw_data.get("mime_type", "") or raw_data.get("file_type", "")
    history    = raw_data.get("history", [])
    is_image   = input_type == "image"
    is_document = input_type == "document"

    if not user_input and not is_image and not is_document:
        async def _empty():
            yield _err("Nothing was sent! Type a question or upload an image.")
        return _sse(_empty())

    async def event_stream() -> AsyncGenerator[str, None]:
        acquired = False
        try:
            try:
                await asyncio.wait_for(solve_semaphore.acquire(), timeout=3.0)
                acquired = True
            except asyncio.TimeoutError:
                yield _err(
                    "The server is handling several requests right now — "
                    "please wait a moment and try again."
                )
                return

            if input_type == "data":
                routing = {"sub_problems": [{
                    "id":            "p1",
                    "domain":        "data_viz",
                    "problem_type":  "table_plot",
                    "input_summary": raw_data.get("filename", "Uploaded dataset"),
                    "parameters":    {"table_data": user_input},
                    "confidence":    1.0,
                }]}
            else:
                try:
                    routing = await route_and_extract(
                        user_input,
                        is_image,
                        history,
                        input_type=input_type,
                        filename=filename,
                        mime_type=mime_type,
                        auxiliary_text=attached_text,
                    )
                except Exception as exc:
                    yield _err(
                        f"Hmm, I had trouble understanding the input: {exc}\n"
                        "Try rephrasing and make sure you've included numbers and units."
                    )
                    return

            if "error" in routing:
                yield _err(
                    routing["error"],
                    stage=routing.get("stage", "model_routing"),
                    retry_available=routing.get("retryable", True),
                )
                return

            solve_input = user_input
            if is_image and isinstance(routing.get("ocr"), dict):
                solve_input = str(routing["ocr"].get("extracted_text") or "").strip()
                yield _evt({
                    "type": "ocr_extracted",
                    "stage": "ocr",
                    "extracted_text": solve_input,
                    "confidence": routing["ocr"].get("confidence", 0.0),
                    "notes": routing["ocr"].get("notes", ""),
                })
            elif is_document and isinstance(routing.get("document"), dict):
                solve_input = str(routing["document"].get("extracted_text") or "").strip()
                yield _evt({
                    "type": "document_extracted",
                    "stage": "document_extraction",
                    "extracted_text": solve_input,
                    "filename": routing["document"].get("filename", filename),
                    "mime_type": routing["document"].get("mime_type", mime_type),
                })

            # ── VALIDATION FIREWALL ───────────────────────────────────────────
            routing = validate_and_normalize(routing, raw_query=solve_input)
            problem_spec = build_problem_spec(solve_input, routing)

            specs_to_solve = problem_spec.sub_problems
            if not specs_to_solve:
                if not routing.get("sub_problems"):
                    yield _err("No solvable mathematical or engineering problem detected.", stage="problem_segmentation", retry_available=False)
                else:
                    yield _err(
                        "I couldn't build a canonical problem from the input. "
                        "Try adding explicit equations, known values, units, and the quantity to solve."
                    )
                return

            for idx, initial_spec in enumerate(specs_to_solve):
                domain       = solver_domain_for(initial_spec)
                problem_type = initial_spec.problem_type
                problem_id   = initial_spec.id or f"p{idx + 1}"
                input_summary = initial_spec.input_summary or initial_spec.raw_query or solve_input
                sub = {
                    "id": problem_id,
                    "domain": initial_spec.domain,
                    "problem_type": initial_spec.problem_type,
                    "input_summary": input_summary,
                    "raw_query": initial_spec.raw_query,
                    "parameters": dict(initial_spec.parameters or {}),
                    "canonical_problem": initial_spec.canonical.model_dump(),
                    "engineering_model": initial_spec.engineering_model,
                    "isolated_input": True,
                }

                sub = _clean(domain, sub)
                sub.setdefault("parameters", {})

                supplemental = {
                    k: parse_user_supplied_value(v)
                    for k, v in raw_data.get("supplemental_params", {}).items()
                }
                sub["parameters"] = resolve_numeric_expressions(
                    apply_standard_defaults(merge_params(sub["parameters"], supplemental))
                )
                if raw_data.get("plot_config"):
                    sub["parameters"]["plot_config"] = raw_data["plot_config"]

                sub["raw_query"]        = input_summary
                sub["topic"]            = domain
                sub["requested_method"] = (
                    sub["parameters"].get("method") or raw_data.get("method")
                )
                spec = build_problem_spec(solve_input, {"sub_problems": [sub]}).sub_problems[0]
                if spec:
                    domain = solver_domain_for(spec)
                    problem_type = spec.problem_type
                    problem_id = spec.id
                    sub["domain"] = spec.domain
                    sub["problem_type"] = spec.problem_type
                    sub["raw_query"] = spec.raw_query
                    sub["input_summary"] = spec.input_summary
                    sub["topic"] = spec.domain
                    sub["parameters"] = spec.parameters
                    sub["canonical_problem"] = spec.canonical.model_dump()
                    sub["engineering_model"] = spec.engineering_model
                    spec.requested_method = sub["requested_method"]
                    if should_prompt_for_method(spec, _POPUP_DOMAINS):
                        yield _evt(build_method_selection_event(spec))
                        continue
                    method_error = ensure_requested_method(spec, sub["requested_method"])
                    if method_error:
                        yield _evt(method_error.model_dump())
                        continue
                    missing_preview = build_missing_parameters_event(spec) if spec else None
                    parser_debug = {
                        "extracted_equations": [eq.normalized for eq in spec.equations],
                        "extracted_variables": spec.unknowns,
                        "detected_units": spec.units,
                        "detected_domain": spec.domain,
                        "problem_type": spec.problem_type,
                        "routing_scores": [score.model_dump() for score in spec.canonical.domain_confidence],
                        "missing_parameters": (missing_preview or {}).get("fields", []),
                    }
                    logger.info("Parser debug: %s", parser_debug)
                    yield _evt({
                        "type": "problem_parsed",
                        "problem_id": problem_id,
                        "domain": spec.domain,
                        "problem_type": spec.problem_type,
                        "canonical_problem": spec.canonical.model_dump(),
                        "engineering_model": spec.engineering_model,
                        "domain_confidence": [score.model_dump() for score in spec.canonical.domain_confidence],
                        "parser_debug": parser_debug,
                        "normalized_text": spec.normalized_text,
                        "knowns": spec.knowns,
                        "unknowns": spec.unknowns,
                        "constraints": spec.constraints,
                        "units": spec.units,
                        "capabilities": [method.id for method in spec.feasible_methods],
                        "selected_method": spec.selected_method,
                    })

                if spec and spec.engineering_model:
                    engineering_validation = spec.engineering_model.get("validation", {})
                    validation_status = engineering_validation.get("status")
                    if validation_status in {"invalid", "blocked"}:
                        is_blocked = validation_status == "blocked"
                        yield _evt(structured_error(
                            (
                                "The requested engineering result cannot be determined without clarification."
                                if is_blocked
                                else "The extracted engineering model contains contradictory or physically invalid data."
                            ),
                            problem_id=problem_id,
                            stage="engineering_validation",
                            suggestion=(
                                "Clarify the blocking engineering information listed in the parsed problem before solving."
                                if is_blocked
                                else "Review the extracted quantities, units and physical relationships before solving."
                            ),
                        ).model_dump())
                        continue

                missing_event = missing_preview if spec else None
                if missing_event:
                    yield _evt(missing_event)
                    continue

                sub["domain"] = domain
                sub["problem_type"] = problem_type
                sub["raw_query"] = solve_input
                sub["parameters"] = dict(sub.get("parameters") or (spec.parameters if spec else {}))
                sub["engineering_model"] = spec.engineering_model if spec else sub.get("engineering_model", {})
                sub, adapter_error = prepare_engineering_solver_input(sub)
                if adapter_error:
                    yield _evt(structured_error(
                        adapter_error,
                        problem_id=problem_id,
                        stage="engineering_adapter",
                        suggestion="Provide the missing physical properties and boundary conditions explicitly.",
                    ).model_dump())
                    continue

                solver_fn = _get_solver(domain, problem_type, raw_query=solve_input, spec=spec)
                if not solver_fn:
                    yield _evt(structured_error(
                        f"No solver is available for {domain} / {problem_type}.",
                        problem_id=problem_id,
                        stage="solver_selection",
                        suggestion="Rephrase the problem with explicit equations, known values, and the quantity to solve.",
                    ))
                    continue

                raw_answer_parts: list[str] = []

                try:
                    async with asyncio.timeout(SOLVE_TIMEOUT_SECONDS):
                        async for chunk in solver_fn(sub):
                            if spec:
                                chunk = normalize_solver_event(chunk, spec)
                            else:
                                chunk["problem_id"] = problem_id

                            if chunk.get("type") == "step":
                                if not _is_real_step(chunk.get("content", "")):
                                    continue

                            if chunk.get("type") == "final":
                                raw_answer_parts.append(chunk.get("answer", ""))

                            if len(specs_to_solve) > 1 and chunk.get("type") == "final":
                                chunk["answer"] = (
                                    f"### Question {idx + 1}: {input_summary}\n\n"
                                    + chunk.get("answer", "")
                                )

                            if chunk.get("type") == "final":
                                chunk["answer"] = polish_final_answer(
                                    chunk.get("answer", ""),
                                    domain=domain,
                                    problem_type=problem_type,
                                )
                                chunk["answer"] = await _explain_for_student(input_summary, chunk["answer"])

                            if chunk.get("type") == "final" and sub.get("options"):
                                ans = str(chunk.get("answer", ""))
                                matched = False
                                for opt in sub["options"]:
                                    if (str(opt.get("label","")).lower() in ans.lower()
                                            or str(opt.get("val","")) in ans):
                                        chunk["answer"] = ans + f"\n\n**Answer: {opt['label']}**"
                                        matched = True
                                        break
                                if not matched:
                                    chunk["answer"] = ans + "\n\n*(None of the provided options matched.)*"

                            yield _evt(chunk)

                except asyncio.TimeoutError:
                    yield _evt(structured_error(
                        f"The {domain} solver exceeded the time limit ({int(SOLVE_TIMEOUT_SECONDS)}s).",
                        problem_id=problem_id,
                        stage="solving",
                        suggestion="Simplify the problem or split it into smaller parts.",
                    ))
                    continue
                except Exception as exc:
                    logger.error(f"Solver error [{domain}]: {exc}", exc_info=True)
                    yield _evt(structured_error(
                        str(exc),
                        problem_id=problem_id,
                        stage="solving",
                        suggestion="Check input values and units, then retry.",
                    ))
                    continue

        except Exception as exc:
            logger.error(f"Unexpected error in event_stream: {exc}", exc_info=True)
            yield _err("An unexpected engine error occurred. Please retry with a simpler, explicit problem statement.")
        finally:
            if acquired:
                solve_semaphore.release()

    return _sse(event_stream())


# ──────────────────────────────────────────────────────────────────[...]
# Static frontend
# ──────────────────────────────────────────────────────────────────[...]

_here         = os.path.dirname(os.path.abspath(__file__))
_frontend_dir = os.path.abspath(os.path.join(_here, "..", "frontend", "dist"))
if os.path.exists(_frontend_dir):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="static")


# ──────────────────────────────────────────────────────────────────[...]
# Dev server
# ──────────────────────────────────────────────────────────────────[...]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))
