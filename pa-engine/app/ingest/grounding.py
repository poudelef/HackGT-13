"""Evidence has to be on the cited page. Memory is not a source."""

from __future__ import annotations

import re


def check(item: dict, page_text: str) -> dict:
    failures = []
    evidence = item.get("evidence_text") or ""
    if not evidence or evidence not in (page_text or ""):
        failures.append("Evidence text is not on the cited page.")
    blob = page_text or ""
    for number in re.findall(r"\d+(?:\.\d+)?", item.get("requirement_text") or ""):
        if number not in blob:
            failures.append(f"Number {number} is missing from the cited page.")
    for code in item.get("codes") or []:
        if code not in blob:
            failures.append(f"Code {code} is missing from the cited page.")
    exception = any(c.get("kind") == "exception" for c in item.get("conditions") or [])
    if exception and not re.search(r"\b(unless|except|contraindicated)\b", blob, re.I):
        failures.append("An exception word is missing from the cited page.")
    return {"passed": not failures, "failures": failures}
