"""Find benefit-chart lines the extractor did not return.

Labels come from the document line. No service list is stored here.
"""

from __future__ import annotations

import re

from app.ingest.pa_markers import line_pa_status

_STRONG = re.compile(
    r"\bcopay\b|\bcoinsurance\b|\bnot covered\b|\bcovered\b.+\bcovered\b|\ballowance\b",
    re.I,
)
_NOISE = re.compile(
    r"^(?:depending on(?: your [\w\s]+ eligibility,?)?\s+|your\s+|medicaid may\s+)",
    re.I,
)
_SKIP_HEAD = {
    "may",
    "will",
    "your",
    "the",
    "this",
    "medicaid",
    "medicare",
    "deductible",
    "generic",
    "additional",
    "benefits",
    "sharing",
    "drugs",
    "rates",
    "rays",
    "eligibility",
    "respite",
}
_HEAD = re.compile(r"\$|\bcopay\b|\bcoinsurance\b|\bnot covered\b|\bcovered\b", re.I)


def _line_requires_pa(text: str) -> tuple[bool, str | None]:
    status, marker = line_pa_status(text)
    return status in {"required", "conditional"}, marker


def candidate_lines(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        original = " ".join(raw.split())
        line = _NOISE.sub("", original).strip()
        if len(line) < 18 or len(line) > 240:
            continue
        if not re.match(r"[A-Z]", line):
            continue
        if not _STRONG.search(line):
            continue
        if re.search(r"\bmay have\b|\byou pay\b|\byou will\b|\bin this stage\b|\bthe plan pays\b", line, re.I):
            continue
        if "." in line[:12]:
            continue
        head = _HEAD.split(line, maxsplit=1)[0]
        words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", head)
        if words and all(word.lower().startswith("medicare") or word.lower() == "covered" for word in words):
            continue
        if not words or words[0].lower() in _SKIP_HEAD:
            continue
        if len(words) == 1 and words[0].lower() in {"covered", "medicare-covered", "outpatient"}:
            continue
        key = original.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(original)
    return found


def uncovered_lines(text: str, items: list[dict]) -> list[str]:
    from app.ingest.pa_markers import windows_by_service_line

    labels = []
    evidence = []
    for item in items:
        label = (item.get("service_label") or "").strip().lower()
        if len(label) >= 6:
            labels.append(label)
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        quote = (data.get("evidence_text") or item.get("evidence_text") or "").strip().lower()
        if quote:
            evidence.append(quote)
    missing = []
    seen: set[str] = set()
    # Prefer service-line windows so a dagger on the next line still marks the row.
    window_lines = [row["service_line"] for row in windows_by_service_line(text)]
    for line in window_lines + candidate_lines(text):
        low = line.lower()
        if low in seen:
            continue
        seen.add(low)
        if any(quote and (quote in low or low in quote) for quote in evidence):
            continue
        if any(label in low for label in labels):
            continue
        missing.append(line)
    return missing


def service_label_from_line(line: str) -> str:
    head = _HEAD.split(_NOISE.sub("", line).strip(), maxsplit=1)[0]
    head = head.strip(" .,:;|-")
    head = re.sub(r"\d+$", "", head).strip(" .,:;|-")
    head = re.sub(r"\s+", " ", head)
    if len(head) < 3:
        head = " ".join(line.split()[:6])
    return head[:80]


def clean_label(model_label: str | None, line: str) -> str:
    parsed = service_label_from_line(line)
    label = " ".join(str(model_label or "").split())
    if not label or "$" in label or label.lower().startswith("depending"):
        return parsed
    return label


def coverage_from_line(line: str, page: int, *, window: str | None = None) -> dict:
    """Build a coverage row. Prefer a multi-line window so next-line daggers count."""
    status, marker = line_pa_status(window or line)
    return {
        "service_label": service_label_from_line(line),
        "service_codes": [],
        "pa_required": status in {"required", "conditional"},
        "pa_status": status,
        "page": page,
        "evidence_text": (window or line).splitlines()[0][:240] if window else line,
        "marker_used": marker,
        "reference": None,
    }


def merge_uncovered(lines: list[str], model_items: list, page: int, existing_keys: set[str]) -> list[dict]:
    """One coverage row per missed line. The model row is used only when its quote is that line."""
    from app.ingest.pa_markers import line_pa_status, windows_by_service_line

    by_line = {line: line for line in lines}
    # Map service line -> full window text for next-line marker detection.
    window_for: dict[str, str] = {}
    for row in windows_by_service_line("\n".join(lines)):
        window_for[row["service_line"]] = row["window"]
    chosen: dict[str, dict] = {}
    for item in model_items:
        if not isinstance(item, dict):
            continue
        evidence = " ".join(str(item.get("evidence_text") or "").split())
        if evidence not in by_line:
            continue
        row = {**item, "page": page, "evidence_text": evidence}
        row["service_label"] = clean_label(row.get("service_label"), evidence)
        chosen[evidence] = row
    rows = []
    seen = set(existing_keys)
    for line in lines:
        window = window_for.get(line)
        row = chosen.get(line) or coverage_from_line(line, page, window=window)
        if chosen.get(line) and window:
            status, marker = line_pa_status(window)
            row = {
                **row,
                "pa_required": status in {"required", "conditional"},
                "pa_status": status,
                "marker_used": marker or row.get("marker_used"),
            }
        key = re.sub(r"[^a-z0-9]+", "_", str(row.get("service_label") or "").lower()).strip("_")[:48] or "coverage"
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows
