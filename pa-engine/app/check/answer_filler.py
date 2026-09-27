"""Fill questions from the chart. Free-text answers keep a quote that was verified on the original note."""

from __future__ import annotations

import json
import re

from app import llm
from app.check.dates import age_years, parse_date, today
from app.check.quote import value_digits_inside, verify
from app.repository import get_repo

_STOP = {"this", "that", "with", "from", "have", "been", "were", "requirement", "chart", "named"}


def fill(item: dict, records: list[dict], patient: dict, *, run_id: str) -> list[dict]:
    questions = (item.get("data") or {}).get("questions") or []
    answers = [_blank(question, index) for index, question in enumerate(questions)]
    by_link = {answer["link_id"]: answer for answer in answers}
    for _ in range(4):
        for question, answer in zip(questions, answers):
            answer["enabled"] = _enabled(question, by_link)
            if not answer["enabled"]:
                answer["value"] = None
                answer["evidence_text"] = None
                answer["fill_method"] = None
                answer["review_state"] = "unanswered"
                continue
            if answer.get("value") is not None or answer.get("edited_by_human"):
                continue
            _fill_one(question, answer, item, records, patient, run_id)
    for answer in answers:
        if isinstance(answer.get("value"), (dict, list, bool, int, float)):
            answer["value"] = json.dumps(answer["value"])
        answer["enabled"] = 1 if answer["enabled"] else 0
    return answers


def _fill_one(question, answer, item, records, patient, run_id: str) -> None:
    method = question["fill_method"]
    rule = item["data"]
    if method == "code_lookup" and question["answer_type"] == "coding" and rule["criterion_type"] == "diagnosis":
        hits = [
            record for record in records
            if record["record_kind"] == "diagnosis" and record.get("code")
            and any(str(record["code"]).startswith(str(code)) for code in (rule.get("codes") or [record["code"]]))
        ]
        if len(hits) > 1:
            answer["conflict"] = True
        if hits:
            code = hits[0]["code"]
            answer["value"] = {"code": code, "display": hits[0].get("display")}
            answer["evidence_text"] = hits[0].get("display") or code
            answer["evidence_record_id"] = hits[0]["id"]
            answer["fill_method"] = "code_lookup"
            answer["review_state"] = "ai_filled"
        return
    if method == "code_lookup" and rule["criterion_type"] == "prescriber":
        return
    if method == "date_math":
        _date_math(question, answer, rule, records, patient)
        return
    if method in {"llm_quote", "llm_quote_value"}:
        _quote(question, answer, rule, records, run_id, want_value=method == "llm_quote_value")


def _date_math(question, answer, rule, records, patient) -> None:
    link = question["link_id"]
    if link.endswith(".age") and patient.get("dob"):
        born = parse_date(patient["dob"])
        if born:
            answer["value"] = age_years(born)
            answer["unit"] = "years"
            answer["fill_method"] = "date_math"
            answer["review_state"] = "ai_filled"
            answer["evidence_text"] = f"Date of birth {patient['dob']}"
        return
    if link.endswith(".onset"):
        dates = [record["start_date"] for record in records if record["record_kind"] == "diagnosis" and record.get("start_date")]
        if dates:
            answer["value"] = sorted(dates)[0]
            answer["fill_method"] = "date_math"
            answer["review_state"] = "ai_filled"
            answer["evidence_text"] = f"Onset recorded {answer['value']}"
        return
    if link.endswith(".last_date"):
        words = {
            w
            for w in _words(rule.get("requirement_text") or "")
            if len(w) >= 6 and w not in {"weeks", "months", "days", "years"}
        }
        dated = []
        for record in records:
            blob = " ".join(filter(None, [record.get("display"), record.get("body"), record.get("value")])).lower()
            if words and not any(word in blob for word in words):
                continue
            for raw in (record.get("end_date"), record.get("start_date")):
                if raw:
                    dated.append(raw)
        if dated:
            answer["value"] = sorted(dated)[-1]
            answer["fill_method"] = "date_math"
            answer["review_state"] = "ai_filled"
            answer["evidence_text"] = f"Most recent related date {answer['value']}"


def _quote(question, answer, rule, records, run_id: str, want_value: bool) -> None:
    notes = []
    providers = {p["id"]: p for p in get_repo().list_providers()}
    for record in records:
        if not record.get("body"):
            continue
        author = providers.get(record.get("author_provider_id") or "")
        notes.append(
            {
                "id": record["id"],
                "body": record["body"],
                "author": author["full_name"] if author else None,
                "date": record.get("start_date"),
            }
        )
    notes.sort(key=lambda note: note.get("date") or "", reverse=True)
    if not notes:
        return
    prompt = "p4b" if want_value else "p4"
    search = " ".join(
        [
            question["text"],
            rule.get("requirement_text") or "",
            " ".join(c.get("text") or "" for c in rule.get("conditions") or []),
        ]
    )
    try:
        found = llm.complete(
            prompt,
            {"question": search, "notes": notes, "want_value": want_value, "unit": question.get("unit")},
            schema=None,
            stage="quote",
            run_id=run_id,
            item_key=question["link_id"],
        )["data"]
    except Exception:
        return
    quote = found.get("quote")
    record = next((note for note in notes if note["id"] == found.get("record_id")), None)
    original = record["body"] if record else ""
    if not verify(quote, original):
        return
    if want_value:
        value = found.get("value")
        if not value_digits_inside(quote, value):
            return
        answer["value"] = value
    elif rule.get("criterion_type") == "exclusion":
        answer["value"] = not bool(re.search(r"\b(no|not|without|denies)\b", quote or "", re.I))
    else:
        answer["value"] = True
    answer["evidence_text"] = quote
    answer["evidence_record_id"] = found.get("record_id")
    answer["fill_method"] = "llm_quote_value" if want_value else "llm_quote"
    answer["review_state"] = "ai_filled"


def _enabled(question: dict, by_link: dict) -> bool:
    gate = question.get("enable_when")
    if not gate:
        return True
    parent = by_link.get(gate["question"])
    parent_value = None if parent is None else parent.get("value")
    if isinstance(parent_value, str):
        try:
            parent_value = json.loads(parent_value)
        except json.JSONDecodeError:
            pass
    if gate["operator"] == "=":
        return parent_value == gate["answer"]
    if gate["operator"] == "!=":
        return parent_value != gate["answer"]
    return True


def _blank(question: dict, index: int) -> dict:
    return {
        "link_id": question["link_id"],
        "seq": index,
        "question_text": question["text"],
        "answer_type": question["answer_type"],
        "enabled": True,
        "value": None,
        "unit": question.get("unit"),
        "fill_method": None,
        "evidence_text": None,
        "evidence_record_id": None,
        "review_state": "unanswered",
        "edited_by_human": 0,
        "rejected_ai_value": None,
        "reject_reason": None,
        "attestation": None,
    }


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOP}


def decode_value(raw):
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw
