"""The only module that decides met or missing (G6). Three-valued logic. Unknown is never yes (G9)."""

from __future__ import annotations

from datetime import date

from app.check.dates import at_least_ago, parse_date, today, within


def evaluate(pass_condition: dict | None, answers: dict, *, judge_verdict: str | None = None, uses_llm: bool = False) -> dict:
    if not pass_condition:
        return {"state": None, "status": "missing", "reason": "No pass condition is defined."}
    state, reason = _eval(pass_condition, answers, today())
    if state is True and judge_verdict == "VAGUE" and uses_llm:
        return {"state": True, "status": "unclear", "reason": "Policy wording flagged as vague; review"}
    if state is True:
        return {"state": True, "status": "met", "reason": None}
    if state is False:
        return {"state": False, "status": "missing", "reason": reason or "A documented fact is short of the policy value."}
    return {"state": None, "status": "missing", "reason": reason or "No documentation found that this requirement is recorded."}


def _eval(node: dict, answers: dict, clock: date):
    if "all" in node:
        results = [_eval(child, answers, clock) for child in node["all"] if not _disabled(child, answers)]
        if not results:
            return None, "No documentation found that this requirement is recorded."
        if any(state is False for state, _ in results):
            return next((state, reason) for state, reason in results if state is False)
        if any(state is None for state, _ in results):
            return next((state, reason) for state, reason in results if state is None)
        return True, None
    if "any" in node:
        results = [_eval(child, answers, clock) for child in node["any"] if not _disabled(child, answers)]
        if not results:
            return None, "No documentation found that this requirement is recorded."
        if any(state is True for state, _ in results):
            return True, None
        if any(state is None for state, _ in results):
            return next((state, reason) for state, reason in results if state is None)
        return next((state, reason) for state, reason in results if state is False)
    return _leaf(node, answers, clock)


def _disabled(node: dict, answers: dict) -> bool:
    leaves = _leaves(node)
    if not leaves:
        return False
    return all(not _enabled(leaf["q"], answers) for leaf in leaves)


def _leaves(node: dict) -> list[dict]:
    if "all" in node:
        return [leaf for child in node["all"] for leaf in _leaves(child)]
    if "any" in node:
        return [leaf for child in node["any"] for leaf in _leaves(child)]
    return [node]


def _enabled(link: str, answers: dict) -> bool:
    answer = answers.get(link)
    if answer is None:
        return False
    return bool(answer.get("enabled", True))


def _leaf(node: dict, answers: dict, clock: date):
    answer = answers.get(node["q"])
    missing = node.get("missing") or "No documentation found that this fact is recorded."
    if answer is None or not answer.get("enabled", True) or answer.get("value") is None:
        return None, missing
    value = answer["value"]
    op = node["op"]
    expected = node.get("value")
    unit = node.get("unit")
    ok = _compare(op, value, expected, unit, clock, answers, node)
    if ok is None:
        return None, missing
    if ok:
        return True, None
    fail = node.get("fail") or "Documented value {value} is short of the policy value."
    return False, fail.replace("{value}", _show(value))


def _compare(op, value, expected, unit, clock, answers, node):
    if op == "eq":
        return value == expected
    if op in {"gte", "gt", "lte", "lt"}:
        try:
            number = float(value)
            target = float(expected)
        except (TypeError, ValueError):
            return None
        return {"gte": number >= target, "gt": number > target, "lte": number <= target, "lt": number < target}[op]
    if op == "exists":
        return value is not None and str(value).strip() != ""
    if op == "in":
        options = [str(item).lower() for item in expected or []]
        return str(value).lower() in options
    if op == "prefix_in":
        code = value.get("code") if isinstance(value, dict) else str(value)
        return any(str(code).startswith(str(prefix)) for prefix in (expected or []))
    parsed = parse_date(str(value)) if not isinstance(value, date) else value
    if parsed is None:
        return None
    if op == "within":
        return within(parsed, int(expected), unit, clock)
    if op == "at_least_ago":
        return at_least_ago(parsed, int(expected), unit, clock)
    if op == "duration_gte":
        return None
    return None


def _show(value) -> str:
    if isinstance(value, dict):
        return str(value.get("code") or value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)
