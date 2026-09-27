"""Deterministic completions used when no model key is configured.

Real documents go through the provider path in llm.py. This reader only copies
text that is already on the page, so grounding can still reject it.
"""

from __future__ import annotations

import re
from typing import Any


def complete(prompt_name: str, user: dict) -> dict:
    name = prompt_name.replace("-", "_")
    fn = {
        "p_id": _identity,
        "p0": _coverage,
        "p1": _rules,
        "p1d": _drug,
        "p2": _judge,
        "p3": _facts,
        "p4": _quote,
        "p4b": _quote_value,
        "p5": _phrase,
        "p6": _question_judge,
        "p_svc": _service_match,
        "p_note": _note,
    }.get(name)
    if fn is None:
        raise KeyError(prompt_name)
    return fn(user)


def _pages(user: dict) -> list[dict]:
    return [p for p in user.get("pages") or [] if p.get("role") != "context"]


def _identity(user: dict) -> dict:
    pages = user.get("pages") or []
    first = pages[0]["text"] if pages else ""
    page_no = pages[0]["page"] if pages else None
    lines = [ln.strip() for ln in first.splitlines() if ln.strip()]

    def verified(evidence: str | None) -> str | None:
        if not evidence:
            return None
        blob = "\n".join(p.get("text") or "" for p in pages)
        return evidence if evidence in blob else None

    insurer_line = lines[0] if lines else None
    plan_line = next((ln for ln in lines if ln.lower().startswith("plan:")), None)
    eff = next((ln for ln in lines if "effective" in ln.lower()), None)
    year = None
    if eff and (m := re.search(r"(20\d{2})", eff)):
        year = m.group(1)
    title = next(
        (
            ln
            for ln in lines
            if any(w in ln.lower() for w in ("policy", "summary of benefits", "authorization criteria"))
        ),
        None,
    )

    def field(value: str | None, evidence: str | None) -> dict:
        ev = verified(evidence)
        if ev is None:
            return {"value": None, "evidence": None, "page": None}
        return {"value": value, "evidence": ev, "page": page_no}

    plan_value = plan_line.split(":", 1)[1].strip() if plan_line else None
    return {
        "insurer": field(insurer_line, insurer_line),
        "plan_name": field(plan_value, plan_line),
        "plan_year": field(year, eff),
        "document_title": field(title, title),
    }


def _coverage(user: dict) -> dict:
    entries = []
    for page in _pages(user):
        for line in page["text"].splitlines():
            if "Service:" not in line or "Authorization:" not in line:
                continue
            service = line.split("Service:", 1)[1].split("|", 1)[0].strip()
            auth = line.split("Authorization:", 1)[1].strip()
            auth_l = auth.lower()
            if "no prior authorization" in auth_l:
                pa = False
            elif any(w in auth_l for w in ("prior authorization", "preauthorization", "precertification", "prior approval")):
                pa = True
            else:
                pa = True
            entries.append(
                {
                    "service_label": service,
                    "service_codes": re.findall(r"\b\d{5}\b", line),
                    "pa_required": pa,
                    "page": page["page"],
                    "evidence_text": line.strip(),
                    "marker_used": None,
                    "reference": None,
                }
            )
    return {"coverage": entries, "memory_updates": _empty_memory()}


def _rules(user: dict) -> dict:
    criteria = []
    applies: list[str] = []
    service_codes: list[str] = []
    for page in _pages(user):
        lines = [ln.strip() for ln in page["text"].splitlines() if ln.strip()]
        buffer: list[str] = []

        def flush() -> None:
            if not buffer:
                return
            exact = " ".join(buffer)
            body = re.sub(r"^\d+\.\d+\s+", "", exact)
            criteria.append(_criterion(body, page["page"], exact))
            buffer.clear()

        for line in lines:
            if re.match(r"^\d+\.\d+\s+\S", line):
                flush()
                buffer = [line]
            elif buffer and not re.match(r"^\d+\.?\s", line) and not line.endswith(":"):
                buffer.append(line)
            else:
                flush()
                if re.search(r"\bapplies to\b", line, re.I):
                    applies.append(re.sub(r"^.*\bapplies to\b\s*", "", line, flags=re.I).strip(" ."))
                    service_codes.extend(re.findall(r"\b\d{5}\b", line))
        flush()
    for item in criteria:
        if applies and not item["applies_to"]:
            item["applies_to"] = applies + [c for c in service_codes if c not in applies]
        if service_codes:
            for code in service_codes:
                if code not in item["applies_to"]:
                    item["applies_to"].append(code)
    return {"criteria": criteria, "memory_updates": _empty_memory()}


def _criterion(text: str, page: int, exact: str) -> dict:
    low = text.lower()
    main, exc = text, ""
    split = re.split(r"\b(unless|except)\b", text, maxsplit=1, flags=re.I)
    if len(split) >= 3:
        main, exc = split[0].strip(" ,."), split[2].strip(" ,.")
    codes = re.findall(r"\b[A-TV-Z]\d{2}(?:\.\d{1,4})?\b", text)
    conditions: list[dict] = []
    subtype = None
    if re.search(r"\bdiagnosis\b", low) or codes:
        ctype = "diagnosis"
        conditions.append(_cond("dx", main, kind="requirement"))
    elif re.search(r"(\d+)\s+weeks of\b", low) or re.search(r"(\d+)\s+months of\b", low):
        ctype, subtype = "prior_treatment", "therapy"
        conditions.append(_cond("received", "The treatment named in the requirement was received"))
        if m := re.search(r"(\d+)\s+(weeks|months|days)", low):
            conditions.append(_cond("duration", main, value=float(m.group(1)), unit=m.group(2)))
        if m := re.search(r"(\d+)\s+months", low):
            conditions.append(_cond("recency", main, value=float(m.group(1)), unit="months"))
    elif m := re.search(r"at least\s+(\d+)\s+(weeks|months|days|years)", low):
        ctype = "duration"
        conditions.append(_cond("onset", main, value=float(m.group(1)), unit=m.group(2)))
    elif re.search(r"\bmust not\b|\bexclusion\b", low):
        ctype = "exclusion"
        conditions.append(_cond("absent", main))
    elif re.search(r"\bage\b", low) and (m := re.search(r"(\d+)\s+years", low)):
        ctype = "age"
        conditions.append(_cond("age", main, value=float(m.group(1)), unit="years"))
    elif "specialty" in low or "prescriber" in low:
        ctype = "prescriber"
        conditions.append(_cond("specialty", main))
    else:
        ctype = "clinical_note"
        conditions.append(_cond("documented", main))
    if exc:
        conditions.append(_cond("exception", exc, kind="exception"))
    return {
        "criterion_key": _slug(main),
        "requirement_text": text.strip(),
        "criterion_type": ctype,
        "subtype": subtype,
        "logic": "any_of" if exc else "all_of",
        "policy_page": page,
        "applies_to": [],
        "codes": codes,
        "conditions": conditions,
        "evidence_text": exact,
    }


def _drug(user: dict) -> dict:
    text = "\n".join(p["text"] for p in _pages(user))
    label = user.get("block_label") or ""
    if m := re.search(r"^Drug:\s*(.+)$", text, re.M):
        label = m.group(1).strip()
    criteria = []
    fields = {
        "covered uses": "diagnosis",
        "exclusion criteria": "exclusion",
        "age restrictions": "age",
        "prescriber restrictions": "prescriber",
        "required medical information": "clinical_note",
    }
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if ":" not in line:
            continue
        name, body = line.split(":", 1)
        kind = fields.get(name.strip().lower())
        if not kind or not body.strip():
            continue
        if kind == "diagnosis":
            item = _criterion(f"Diagnosis documented: {body.strip()}", user["pages"][0]["page"], line)
            item["criterion_type"] = "diagnosis"
            item["codes"] = re.findall(r"\b[A-TV-Z]\d{2}(?:\.\d{1,4})?\b", body)
            item["conditions"] = [_cond("dx", body.strip())]
        elif kind == "age":
            years = re.search(r"(\d+)\s+years", body)
            item = _criterion(body.strip(), user["pages"][0]["page"], line)
            item["criterion_type"] = "age"
            item["conditions"] = [
                _cond("age", body.strip(), value=float(years.group(1)) if years else None, unit="years")
            ]
        elif kind == "exclusion":
            item = _criterion(body.strip(), user["pages"][0]["page"], line)
            item["criterion_type"] = "exclusion"
        elif kind == "prescriber":
            item = _criterion(body.strip(), user["pages"][0]["page"], line)
            item["criterion_type"] = "prescriber"
        else:
            item = _criterion(body.strip(), user["pages"][0]["page"], line)
            item["criterion_type"] = "clinical_note"
        item["evidence_text"] = line
        item["criterion_key"] = _slug(name + " " + body)[:48]
        criteria.append(item)
    duration = None
    if m := re.search(r"Coverage duration:\s*(.+)", text):
        duration = {"text": m.group(1).strip(), "page": user["pages"][0]["page"]}
    return {"block_label": label, "criteria": criteria, "coverage_duration": duration, "memory_updates": _empty_memory()}


def _judge(user: dict) -> dict:
    item = user["item"]
    page = user.get("page_text") or ""
    evidence = item.get("evidence_text") or ""
    if not evidence or evidence not in page:
        return {"verdict": "HALLUCINATED", "reason": "The evidence sentence is not on the cited page."}
    for number in re.findall(r"\d+(?:\.\d+)?", item.get("requirement_text") or ""):
        if number not in page:
            return {"verdict": "WRONG_VALUE", "reason": f"The value {number} is not on the cited page."}
    for code in item.get("codes") or []:
        if code not in page:
            return {"verdict": "WRONG_VALUE", "reason": f"The code {code} is not on the cited page."}
    if len(evidence) < 12:
        return {"verdict": "VAGUE", "reason": "The evidence is too short to apply."}
    label = item.get("requirement_text") or item.get("service_label") or "This row"
    snippet = evidence if len(evidence) < 120 else evidence[:117] + "…"
    return {"verdict": "ACCURATE", "reason": f"The page states {label}. Quote: “{snippet}”"}


def _facts(user: dict) -> dict:
    text = user.get("text") or ""
    facts = []
    for code in re.findall(r"\b[A-TV-Z]\d{2}(?:\.\d{1,4})?\b", text):
        facts.append({"kind": "diagnosis", "code": code, "display": code})
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(%|mg|weeks|months|days)", text, re.I):
        facts.append({"kind": "quantity", "value": m.group(1), "unit": m.group(2)})
    return {"facts": facts}


def _quote(user: dict) -> dict:
    return _pick_quote(user, want_value=False)


def _quote_value(user: dict) -> dict:
    return _pick_quote(user, want_value=True)


def _pick_quote(user: dict, want_value: bool) -> dict:
    words = list(dict.fromkeys(w for w in re.findall(r"[a-z]{4,}", (user.get("question") or "").lower()) if w not in _STOP))
    unit = (user.get("unit") or "").lower()
    best = None
    best_score = 0
    for note in user.get("notes") or []:
        for sent in _sentences(note.get("body") or ""):
            if len(sent) < 12:
                continue
            score = sum(1 for w in words if w in sent.lower())
            if want_value and not re.search(r"\d", sent):
                continue
            if want_value and score < 2:
                continue
            if want_value and unit and unit[:4] not in sent.lower():
                continue
            if score > best_score:
                best_score = score
                best = (sent, note)
    if not best or best_score < 1:
        return {"quote": None, "value": None, "record_id": None}
    sent, note = best
    value = None
    if want_value and (m := re.search(r"(\d+(?:\.\d+)?)", sent)):
        value = float(m.group(1)) if "." in m.group(1) else int(m.group(1))
    return {
        "quote": sent,
        "value": value,
        "record_id": note.get("id"),
        "author": note.get("author"),
        "date": note.get("date"),
    }


def _phrase(user: dict) -> dict:
    return {"texts": {slot["link_id"]: slot["default_text"] for slot in user.get("slots") or []}}


def _question_judge(user: dict) -> dict:
    if user.get("leading"):
        return {"verdict": "leading", "reason": "Question text asks for a verdict."}
    if user.get("coverage", 1) < 1:
        return {"verdict": "missing_condition", "reason": "A condition has no question."}
    return {"verdict": "complete", "reason": "Every condition has a question."}


def _service_match(user: dict) -> dict:
    order = (user.get("order_text") or "").lower()
    found = []
    for cand in user.get("candidates") or []:
        label = cand.get("label") or ""
        phrase = _shared_phrase(order, label.lower())
        if phrase and phrase in label.lower():
            found.append(
                {
                    "item_id": cand["id"],
                    "phrase": phrase,
                    "page": cand.get("page"),
                    "score": len(phrase),
                }
            )
    found.sort(key=lambda row: (-row["score"], row["item_id"]))
    return {"candidates": found}


def _note(user: dict) -> dict:
    required = user.get("required_sentences") or []
    body = "\n".join(required)
    return {"body": body}


def _sentences(body: str) -> list[str]:
    parts = re.split(r"(?<=[.])\s+", body.strip())
    return [p.strip() for p in parts if p.strip()]


def _shared_phrase(order: str, label: str) -> str | None:
    order_words = re.findall(r"[a-z0-9]+", order)
    label_words = re.findall(r"[a-z0-9]+", label)
    best = ""
    for size in range(len(label_words), 0, -1):
        for i in range(0, len(label_words) - size + 1):
            gram = label_words[i : i + size]
            if gram[0] in _STOP:
                continue
            if all(w in order_words for w in gram) and len(" ".join(gram)) > len(best):
                best = " ".join(gram)
        if best and size >= 2:
            break
    return best or None


def _cond(key: str, text: str, value: float | None = None, unit: str | None = None, kind: str = "requirement") -> dict:
    return {"condition_key": key, "text": text, "kind": kind, "value": value, "unit": unit}


def _slug(text: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and not w.isdigit()]
    return "_".join(words[:5]) or "criterion"


def _empty_memory() -> dict:
    return {"definitions": [], "markers": [], "open_item": None}


_STOP = {
    "the", "a", "an", "of", "is", "for", "at", "least", "in", "past", "have", "been",
    "must", "not", "patient", "documented", "within", "unless", "and", "or", "to",
    "this", "are", "was", "with", "that", "from", "had", "has", "following", "here",
    "described", "been", "into", "than", "then", "when", "what", "which", "does",
    "did", "its", "their", "there", "these", "those", "such", "only", "also", "any",
    "all", "each", "per", "via", "over", "under", "after", "before", "during",
}
