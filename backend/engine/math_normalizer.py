from __future__ import annotations

import re
from typing import Any

_UNICODE_REPLACEMENTS = {
    "−": "-",
    "–": "-",
    "—": "-",
    "×": "*",
    "·": "*",
    "÷": "/",
    "∕": "/",
    "⁄": "/",
    "√": "sqrt",
    "π": "pi",
    "θ": "theta",
    "τ": "tau",
    "ω": "omega",
    "μ": "mu",
    "²": "**2",
    "³": "**3",
    "⁴": "**4",
    "⁵": "**5",
    "⁶": "**6",
    "⁷": "**7",
    "⁸": "**8",
    "⁹": "**9",
    "⁰": "**0",
}

_FUNCTION_NAMES = (
    "sin",
    "cos",
    "tan",
    "cot",
    "sec",
    "csc",
    "asin",
    "acos",
    "atan",
    "sinh",
    "cosh",
    "tanh",
    "log",
    "ln",
    "exp",
    "sqrt",
    "pi",
)


def normalize_math_text(text: Any) -> str:
    if text is None:
        return ""
    if isinstance(text, list):
        text = "; ".join(str(item) for item in text if item is not None)

    value = str(text).strip()
    for src, dst in _UNICODE_REPLACEMENTS.items():
        value = value.replace(src, dst)

    value = value.replace("^", "**")
    value = re.sub(r"(?<=\d)\s+(?=[A-Za-z(])", "*", value)
    value = re.sub(r"(?<=[A-Za-z0-9_)])\s+(?=[A-Za-z(])", " ", value)

    for fn in _FUNCTION_NAMES:
        value = re.sub(
            rf"\b{fn}\s+([A-Za-z0-9_]+)\b",
            rf"{fn}(\1)",
            value,
            flags=re.IGNORECASE,
        )

    value = re.sub(r"(\d)([A-Za-z])", r"\1*\2", value)
    value = re.sub(r"([A-Za-z])\(", r"\1(", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value



def _split_compact_variable_products(value: str) -> str:
    def split_token(match: re.Match) -> str:
        token = match.group(0)
        lowered = token.lower()
        if lowered in _FUNCTION_NAMES or lowered in {"pi", "e"}:
            return token
        if len(token) == 2 and token.isalpha():
            return "*".join(token)
        return token
    return re.sub(r"\b[A-Za-z]{2,4}\b", split_token, value)


def _strip_equation_intent_suffix(value: str) -> str:
    value = re.sub(r"\s*\*?\s*for\s+[A-Za-z]\b\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bsolve\s+for\s+[A-Za-z]\b.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bmake\s+[A-Za-z]\s+the\s+subject\b.*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bexpress\s+[A-Za-z]\s+in\s+terms\s+of\b.*$", "", value, flags=re.IGNORECASE)
    return re.sub(r"[\s+*/-]+$", "", value).strip()


def normalize_equation_text(text: str) -> str:
    value = normalize_math_text(text)
    value = re.sub(r"^\s*(?:solve|find|determine|calculate|compute)\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b([A-Z])\b", lambda match: match.group(1).lower(), value)
    value = _strip_equation_intent_suffix(value)
    value = _split_compact_variable_products(value)
    value = re.sub(r"^\s*(?:eq(?:uation)?\s*\d*[:.)-]?\s*)", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^\s*\d+\s*[).:-]\s*", "", value)
    value = re.sub(r"(?<=\d)\.(?=\s*$)", "", value)
    return value.strip(" ;,?.")


def _looks_like_equation(raw_piece: str, normalized_piece: str) -> bool:
    if not normalized_piece or normalized_piece.count("=") != 1:
        return False

    cleaned_raw_piece = _strip_equation_intent_suffix(raw_piece)
    if cleaned_raw_piece.count("=") != 1:
        cleaned_raw_piece = raw_piece

    raw_lhs, raw_rhs = cleaned_raw_piece.split("=", 1)
    lhs, rhs = normalized_piece.split("=", 1)
    if not lhs.strip() or not rhs.strip():
        return False

    if (
        not re.match(r"^\s*[A-Za-z][A-Za-z0-9_]*(?:\s*\([^)]*\))?\s*$", raw_lhs)
        and re.search(r"\b(has|contains|with|given|where|assume|assumes|at|of|for|is|are)\b", raw_lhs, flags=re.IGNORECASE)
    ):
        return False

    value_pattern = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?"
    if re.match(rf"^\s*{value_pattern}\s*[A-Za-z°Ωμ]", raw_rhs, flags=re.IGNORECASE):
        return False

    ignored_words = {"sin", "cos", "tan", "log", "ln", "exp", "sqrt", "theta", "alpha", "beta", "gamma", "sigma", "omega", "delta"}
    prose_lhs = [word.lower() for word in re.findall(r"\b[A-Za-z]{3,}\b", raw_lhs) if word.lower() not in ignored_words]
    prose_rhs = [word.lower() for word in re.findall(r"\b[A-Za-z]{3,}\b", raw_rhs) if word.lower() not in ignored_words]
    if len(prose_lhs) > 2 or len(prose_rhs) > 3:
        return False

    return bool(re.search(r"[+\-*/^()]|\b[A-Za-z][A-Za-z0-9_]*\b", normalized_piece))


def extract_equations(text: str, params: dict[str, Any] | None = None) -> list[str]:
    params = params or {}
    equations: list[str] = []

    raw_equations = params.get("equations")
    if isinstance(raw_equations, list):
        equations.extend(str(item) for item in raw_equations if str(item).strip())

    expression = params.get("expression")
    if not equations and expression and ("=" in str(expression) or re.search(r"\bsolve\b", text or "", re.I)):
        equations.append(str(expression))

    if not equations and text:
        lines = re.split(r"[\n;]", text)
        for line in lines:
            line = re.sub(
                r"^\s*(solve|find|determine|calculate)\s+(?:the\s+)?(?:simultaneous\s+equations?|equations?|system)\s*:\s*",
                "",
                line,
                flags=re.IGNORECASE,
            )
            line = re.sub(
                r"^\s*(?:solve|find|determine|calculate)\s+(?:the\s+)?(?:value\s+of\s+)?[A-Za-z][A-Za-z0-9_]*\s+(?:if|when|where|from)\s+",
                "",
                line,
                flags=re.IGNORECASE,
            )
            line = re.sub(r"^\s*(solve|find|determine|calculate)\s+", "", line, flags=re.IGNORECASE)
            line = re.sub(
                r"^\s*(?:what\s+is|what's|find|determine|calculate)\s+(?:the\s+)?(?:value\s+of\s+)?[A-Za-z][A-Za-z0-9_]*\s+(?:if|when|where|from)\s+",
                "",
                line,
                flags=re.IGNORECASE,
            )
            line = re.sub(
                r"^.*?\b(?:if|when|where|from|given\s+that|such\s+that)\b\s+(?=[-+]?(?:\d*\.?\d+\s*)?[A-Za-z(][^=]*=)",
                "",
                line,
                flags=re.IGNORECASE,
            )
            if re.search(r"[A-Za-z]\s*''|[A-Za-z]\s*'", line) and not re.match(r"^\s*[A-Za-z]\s*'", line):
                line = re.sub(r"^.*?(?=[A-Za-z]\s*''|[A-Za-z]\s*')", "", line)
                line = re.sub(r"\s+\bwith\b.*$", "", line, flags=re.IGNORECASE)
            line = re.sub(r"^.*?:\s*(?=(?:\d+\s*[).:-]\s*)?[-+]?(?:\d*\.?\d+\s*)?[A-Za-z(])", "", line)
            line = re.sub(
                r"(=\s*[-+]?\d*\.?\d+)\s+(?=(?:\d+\s*[).:-]\s*)?[-+]?(?:\d*\.?\d+\s*)?[A-Za-z(][^,=]*=)",
                r"\1, ",
                line,
            )
            raw_pieces = re.split(r"\s*(?:,|\band\b)\s*(?=(?:\d+\s*[).:-]\s*)?[^,=]+=[^,=]+)", line, flags=re.IGNORECASE)
            for piece in raw_pieces:
                normalized_piece = normalize_equation_text(piece)
                if _looks_like_equation(piece, normalized_piece):
                    equations.append(normalized_piece)

    if not equations and text:
        equations.extend(_extract_plain_language_linear_equations(text))

    deduped: list[str] = []
    seen = set()
    for eq in equations:
        normalized = normalize_equation_text(eq)
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    return deduped


def _extract_plain_language_linear_equations(text: str) -> list[str]:
    source = str(text or "").lower()
    number_word = r"(?:(?:a|the)\s+(?:unknown\s+)?number|[a-z])"
    numeric = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)"
    op_map = {"plus": "+", "add": "+", "added to": "+", "minus": "-", "less": "-", "subtract": "-"}
    equations: list[str] = []

    patterns = [
        rf"({numeric})\s*(?:times|multiplied by)\s+{number_word}\s+(plus|minus|add|subtract)\s+({numeric})\s+(?:is|equals|equal to|=)\s+({numeric})",
        rf"(?:twice|two times)\s+{number_word}\s+(plus|minus|add|subtract)\s+({numeric})\s+(?:is|equals|equal to|=)\s+({numeric})",
    ]

    first = re.search(patterns[0], source, flags=re.IGNORECASE)
    if first:
        coefficient, operator_word, constant, rhs = first.groups()
        operator = op_map.get(operator_word.lower(), "+")
        equations.append(f"{coefficient}*x {operator} {constant} = {rhs}")

    second = re.search(patterns[1], source, flags=re.IGNORECASE)
    if second:
        operator_word, constant, rhs = second.groups()
        operator = op_map.get(operator_word.lower(), "+")
        equations.append(f"2*x {operator} {constant} = {rhs}")

    return equations


def extract_units(text: str, params: dict[str, Any] | None = None) -> dict[str, str]:
    scalar_parts = []
    for key, value in (params or {}).items():
        if isinstance(value, (str, int, float)) and value not in (None, ""):
            scalar_parts.append(f"{key}={value}")
    source = "; ".join(filter(None, [text, "; ".join(scalar_parts)]))
    units: dict[str, str] = {}
    unit_pattern = r"([A-Za-z°Ωμ][A-Za-z°Ωμ/^0-9]*)"
    value_pattern = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?"
    unit_stopwords = {"and", "or", "with", "the", "for", "from", "into", "when", "then", "where", "is", "are", "in", "of", "to"}
    for name, unit in re.findall(
        rf"\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*{value_pattern}\s*{unit_pattern}\b",
        source,
        flags=re.IGNORECASE,
    ):
        if unit.lower() in unit_stopwords:
            continue
        units[name] = unit
    return units


def extract_unknowns(text: str, params: dict[str, Any] | None = None, equations: list[str] | None = None) -> list[str]:
    unknowns: list[str] = []

    for token in re.findall(r"\bsolve\s+for\s+([A-Za-z][A-Za-z0-9_]*)\b", text or "", flags=re.IGNORECASE):
        unknowns.append(token)

    if not unknowns and params:
        for key, value in params.items():
            if value in (None, "", "?"):
                unknowns.append(key)

    if not unknowns and equations:
        names = []
        for eq in equations:
            names.extend(re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)\b", eq))
        ignore = {"sin", "cos", "tan", "log", "ln", "exp", "sqrt", "pi"}
        unknowns = [name for name in names if name not in ignore]

    ordered: list[str] = []
    seen = set()
    for item in unknowns:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def split_knowns_unknowns(params: dict[str, Any], unknowns: list[str]) -> tuple[dict[str, Any], list[str]]:
    knowns = {}
    inferred_unknowns = list(unknowns)
    unknown_set = set(unknowns)

    for key, value in (params or {}).items():
        if key in unknown_set or value in (None, "", "?"):
            if key not in unknown_set:
                inferred_unknowns.append(key)
                unknown_set.add(key)
            continue
        knowns[key] = value

    return knowns, inferred_unknowns
