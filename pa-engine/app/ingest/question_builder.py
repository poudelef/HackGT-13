"""Code builds questions, types, enableWhen, and pass conditions. The model only phrases text."""

from __future__ import annotations

import re

from app import llm

LEADING = re.compile(r"meet|qualif|satisf|eligib", re.I)
_PASTE = ("this requirement", "the following", "named in this", "excluded situation")


def build(rule: dict, *, run_id: str) -> dict:
    key = rule["criterion_key"]
    questions, condition = _template(rule, key)
    slots = [_slot(rule, question) for question in questions]
    try:
        phrased = llm.complete(
            "p5",
            {"requirement_text": rule.get("requirement_text") or "", "slots": slots},
            schema=None,
            stage="phrase",
            run_id=run_id,
            item_key=key,
        )["data"]
        texts = phrased.get("texts") or {}
        for question, slot in zip(questions, slots):
            if question.get("text_edited_by_human"):
                continue
            accepted = accept_phrasing(texts.get(question["link_id"]), slot, rule.get("requirement_text") or "")
            question["text"] = accepted or accept_phrasing(slot["default_text"], slot, rule.get("requirement_text") or "") or fallback_text(slot)
    except Exception:
        for question, slot in zip(questions, slots):
            if question.get("text_edited_by_human"):
                continue
            question["text"] = accept_phrasing(question["text"], slot, rule.get("requirement_text") or "") or fallback_text(slot)
    verdict, reason = _code_checks(rule, questions, condition)
    try:
        judged = llm.complete(
            "p6",
            {
                "requirement_text": rule.get("requirement_text") or "",
                "conditions": rule.get("conditions") or [],
                "questions": [{"link_id": q["link_id"], "text": q["text"], "answer_type": q["answer_type"]} for q in questions],
                "coverage": 1 if verdict == "complete" else 0,
                "leading": verdict == "leading",
            },
            schema=None,
            stage="question_judge",
            run_id=run_id,
            provider_kind="judge",
            item_key=key,
        )["data"]
        if judged.get("verdict") in {"complete", "missing_condition", "added_condition", "leading"}:
            if verdict == "complete":
                verdict = judged["verdict"]
    except Exception:
        if verdict == "complete":
            verdict = "unavailable"
    return {"questions": questions, "pass_condition": condition, "question_verdict": verdict, "question_reason": reason}


def accept_phrasing(text: str | None, slot: dict, requirement: str) -> str | None:
    """Keep a question only when it asks a fact and does not repeat the policy sentence."""
    cleaned = " ".join(str(text or "").split())
    if not cleaned.endswith("?"):
        return None
    if LEADING.search(cleaned):
        return None
    low = cleaned.lower()
    if any(phrase in low for phrase in _PASTE):
        return None
    req = " ".join((requirement or "").split()).strip(" .?").lower()
    if req and len(req) > 24 and req in low:
        return None
    allowed: set[str] = set()
    value = slot.get("value")
    if isinstance(value, (int, float)):
        allowed.add(str(int(value)) if float(value).is_integer() else str(value))
        allowed.add(str(value))
    for number in re.findall(r"\d+(?:\.\d+)?", cleaned):
        if number not in allowed:
            return None
    return cleaned


def fallback_text(slot: dict) -> str:
    kind = slot.get("answer_type")
    unit = slot.get("unit") or "units"
    subject = slot.get("subject") or "the finding"
    if kind == "coding":
        return "Which diagnosis code is documented?"
    if kind == "quantity":
        return f"How many {unit} of {subject} are documented?"
    if kind == "date":
        return f"What date is documented for {subject}?"
    if kind == "string":
        return f"What is documented about {subject}?"
    return f"Is {subject} documented in the chart?"


def _slot(rule: dict, question: dict) -> dict:
    covered = set(question.get("covers") or [])
    cond = next((c for c in rule.get("conditions") or [] if c.get("condition_key") in covered), None)
    text = (cond or {}).get("text") or rule.get("requirement_text") or ""
    return {
        "link_id": question["link_id"],
        "answer_type": question["answer_type"],
        "unit": question.get("unit"),
        "condition_text": text,
        "value": (cond or {}).get("value"),
        "default_text": question["text"],
        "subject": _subject(rule, text),
    }


def _draft_slot(link: str, answer_type: str, cond: dict, rule: dict) -> dict:
    return {
        "link_id": link,
        "answer_type": answer_type,
        "unit": cond.get("unit"),
        "condition_text": cond.get("text"),
        "value": cond.get("value"),
        "subject": _subject(rule, cond.get("text") or ""),
        "default_text": "",
    }


def _subject(rule: dict, text: str) -> str:
    source = text or ""
    if any(phrase in source.lower() for phrase in ("named in", "this requirement", "the following")):
        source = rule.get("requirement_text") or source
    source = re.split(r"\b(unless|except)\b", source, maxsplit=1, flags=re.I)[0]
    source = re.sub(r"\([^)]*\)", " ", source)
    source = re.sub(r"\b\d+(?:\.\d+)?\b", " ", source)
    source = re.sub(
        r"\b(days|weeks|months|years|percent|at least|documented|diagnosis|patient|must|not|have|had|been|for|the|past|older|and|with|from|that|this|was|were|are)\b",
        " ",
        source,
        flags=re.I,
    )
    words = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", source)
    if not words:
        return "the finding"
    return " ".join(words[:4]).lower()


def _template(rule: dict, key: str) -> tuple[list[dict], dict]:
    ctype = rule["criterion_type"]
    subtype = rule.get("subtype")
    conditions = rule.get("conditions") or []
    requirements = [c for c in conditions if c.get("kind") != "exception"]
    exceptions = [c for c in conditions if c.get("kind") == "exception"]
    primary = requirements[0]["text"] if requirements else rule["requirement_text"]

    if ctype == "diagnosis":
        questions = [_q(f"{key}.codes", "Which diagnosis code is documented?", "coding", "code_lookup", ["dx"])]
        return questions, {"all": [{"q": f"{key}.codes", "op": "prefix_in", "value": rule.get("codes") or []}]}

    if ctype == "clinical_note":
        subject = _subject(rule, requirements[0]["text"] if requirements else primary)
        questions = [_q(f"{key}.documented", f"Is {subject} documented in the chart?", "boolean", "llm_quote", [requirements[0]["condition_key"] if requirements else "documented"])]
        return questions, {"all": [{"q": f"{key}.documented", "op": "eq", "value": True, "missing": f"No documentation found that {primary}"}]}

    if ctype == "duration":
        cond = next((c for c in requirements if c.get("value") is not None), requirements[0])
        questions = [_q(f"{key}.onset", fallback_text(_draft_slot(f"{key}.onset", "date", cond, rule)), "date", "date_math", [cond["condition_key"]])]
        return questions, {"all": [_leaf(f"{key}.onset", "at_least_ago", cond, f"The onset is {{value}}; the policy requires {cond.get('value')} {cond.get('unit')}")]}

    if ctype == "prior_treatment" and subtype == "therapy":
        week = next((c for c in requirements if c.get("unit") in {"weeks", "days", "months"} and c.get("condition_key") == "duration"), None)
        window = next((c for c in requirements if c.get("condition_key") == "recency"), None)
        received_key = next((c["condition_key"] for c in requirements if c["condition_key"] == "received"), "received")
        questions = [
            _q(f"{key}.received", f"Has {_subject(rule, rule.get('requirement_text') or primary)} been received?", "boolean", "llm_quote", [received_key]),
        ]
        leaves = [{"q": f"{key}.received", "op": "eq", "value": True, "missing": f"No documentation found that {rule['requirement_text']}"}]
        if week:
            questions.append(
                _q(
                    f"{key}.weeks",
                    f"How many {week.get('unit') or 'weeks'} of {_subject(rule, week.get('text') or primary)} were completed?",
                    "quantity",
                    "llm_quote_value",
                    [week["condition_key"]],
                    unit=week.get("unit") or "weeks",
                    enable_when={"question": f"{key}.received", "operator": "=", "answer": True},
                )
            )
            leaves.append(_leaf(f"{key}.weeks", "gte", week, f"Completed: {{value}} {week.get('unit')}; policy requires {week.get('value')} {week.get('unit')}"))
        if window:
            questions.append(
                _q(
                    f"{key}.last_date",
                    f"What was the date of the most recent {_subject(rule, window.get('text') or primary)}?",
                    "date",
                    "date_math",
                    [window["condition_key"]],
                    enable_when={"question": f"{key}.received", "operator": "=", "answer": True},
                )
            )
            leaves.append(_leaf(f"{key}.last_date", "within", window, f"Most recent treatment on {{value}}; policy requires within {window.get('value')} {window.get('unit')}"))
        branches = [{"all": leaves}]
        if exceptions:
            exc = exceptions[0]
            questions.append(
                _q(
                    f"{key}.exception",
                    f"Is {_subject(rule, exc['text'])} documented?",
                    "boolean",
                    "llm_quote",
                    [exc["condition_key"]],
                    enable_when={"question": f"{key}.received", "operator": "!=", "answer": True},
                )
            )
            questions.append(
                _q(
                    f"{key}.exception_reason",
                    f"What reason is documented for {_subject(rule, exc['text'])}?",
                    "string",
                    "llm_quote",
                    [exc["condition_key"]],
                    enable_when={"question": f"{key}.exception", "operator": "=", "answer": True},
                )
            )
            branches.append(
                {
                    "all": [
                        {"q": f"{key}.exception", "op": "eq", "value": True, "missing": f"No documentation found that {exc['text']}"},
                        {"q": f"{key}.exception_reason", "op": "exists", "missing": "No documentation found for the exception reason"},
                    ]
                }
            )
        return questions, {"any": branches} if len(branches) > 1 else branches[0]

    if ctype == "exclusion":
        questions = [_q(f"{key}.present", f"Is {_subject(rule, primary)} present in the chart?", "boolean", "llm_quote", [requirements[0]["condition_key"] if requirements else "absent"])]
        return questions, {"all": [{"q": f"{key}.present", "op": "eq", "value": False, "fail": f"The chart documents: {{value}}", "missing": f"No documentation found that {primary}"}]}

    if ctype == "age":
        cond = next((c for c in requirements if c.get("value") is not None), {"condition_key": "age", "value": None, "unit": "years", "text": primary})
        questions = [_q(f"{key}.age", "What is the patient's age in years?", "quantity", "date_math", [cond["condition_key"]], unit="years")]
        return questions, {"all": [_leaf(f"{key}.age", "gte", cond, f"Age is {{value}} years; policy requires {cond.get('value')} years")]}

    if ctype == "prescriber":
        questions = [_q(f"{key}.specialty", f"What specialty is documented for {_subject(rule, primary)}?", "coding", "code_lookup", ["specialty"])]
        return questions, {"all": [{"q": f"{key}.specialty", "op": "in", "value": _specialties(primary), "missing": f"No documentation found that {primary}"}]}

    if ctype == "lab":
        cond = next((c for c in requirements if c.get("value") is not None), requirements[0] if requirements else {"condition_key": "value", "text": primary, "value": None, "unit": None})
        questions = [_q(f"{key}.value", f"What value is documented for {_subject(rule, cond.get('text') or primary)}?", "quantity", "code_lookup", [cond["condition_key"]], unit=cond.get("unit"))]
        return questions, {"all": [_leaf(f"{key}.value", "gte", cond, f"Result is {{value}}; policy requires {cond.get('value')}")]}

    questions = [_q(f"{key}.documented", f"Is {_subject(rule, primary)} documented in the chart?", "boolean", "llm_quote", ["documented"])]
    return questions, {"all": [{"q": f"{key}.documented", "op": "eq", "value": True}]}


def _code_checks(rule: dict, questions: list[dict], condition: dict) -> tuple[str, str]:
    covered = {c for q in questions for c in q["covers"]}
    missing = [c["condition_key"] for c in rule.get("conditions") or [] if c["condition_key"] not in covered]
    if missing:
        return "missing_condition", "Missing questions for: " + ", ".join(missing)
    for question in questions:
        if LEADING.search(question["text"]):
            return "leading", "A question asks for a verdict."
        numbers = re.findall(r"\d+(?:\.\d+)?", question["text"])
        allowed = []
        for cond in rule.get("conditions") or []:
            if cond["condition_key"] in question["covers"] and cond.get("value") is not None:
                allowed.append(str(cond["value"]).rstrip("0").rstrip(".") if isinstance(cond["value"], float) else str(cond["value"]))
                allowed.append(str(int(cond["value"])) if isinstance(cond["value"], float) and cond["value"].is_integer() else str(cond["value"]))
        for number in numbers:
            if number not in allowed and str(float(number)) not in allowed:
                return "missing_condition", f"Question text contains {number}, which is not a condition value."
    leaves = _leaves(condition)
    ids = {q["link_id"] for q in questions}
    if any(leaf["q"] not in ids for leaf in leaves):
        return "missing_condition", "A pass condition points at a missing question."
    exceptions = [c for c in rule.get("conditions") or [] if c.get("kind") == "exception"]
    if exceptions and "any" not in condition:
        return "missing_condition", "An exception is not reachable."
    return "complete", ""


def _leaves(node: dict) -> list[dict]:
    if "all" in node:
        return [leaf for child in node["all"] for leaf in _leaves(child)]
    if "any" in node:
        return [leaf for child in node["any"] for leaf in _leaves(child)]
    return [node]


def _leaf(link: str, op: str, cond: dict, fail: str) -> dict:
    return {
        "q": link,
        "op": op,
        "value": cond.get("value"),
        "unit": cond.get("unit"),
        "fail": fail,
        "missing": f"No documentation found that {cond.get('text')}",
    }


def _specialties(text: str) -> list[str]:
    match = re.search(r"includes\s+([^,\.]+)", text, re.I)
    if match:
        return [match.group(1).strip().lower()]
    return []


def _q(link: str, text: str, answer_type: str, fill: str, covers: list[str], unit: str | None = None, enable_when: dict | None = None) -> dict:
    return {
        "link_id": link,
        "text": text,
        "answer_type": answer_type,
        "unit": unit,
        "fill_method": fill,
        "covers": covers,
        "enable_when": enable_when,
        "text_edited_by_human": False,
    }


def plain_english(condition: dict | None) -> str:
    if not condition:
        return "No pass condition."
    if "any" in condition:
        return "Any of: " + "; or ".join(plain_english(part) for part in condition["any"])
    if "all" in condition:
        return "All of: " + "; and ".join(plain_english(part) for part in condition["all"])
    op = condition.get("op")
    return f"{condition.get('q')} {op} {condition.get('value')}"
