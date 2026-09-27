"""In-house patient-report extraction.

Isolate PDF/image text -> structured JSON here so a better extractor (or the
teammate service) can replace this file without touching Order Desk / PA flow.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPORT_JSON_SHAPE = {
    "patient": {"id": "string", "name": "string", "dob": "YYYY-MM-DD"},
    "treatment_requested": {
        "service_category": "string",
        "diagnosis_codes": ["string"],
        "clinical_notes": "string",
    },
    "source_document_reference": "string",
}


def extractReportToJson(
    *,
    file_bytes: bytes,
    file_name: str,
    storage_path: str | Path | None = None,
) -> dict[str, Any]:
    """Convert an uploaded report into the teammate-compatible extraction shape.

    Returns:
      {
        "extracted": { patient, treatment_requested, source_document_reference },
        "extraction_status": "success" | "partial" | "failed",
        "raw_text": str,
      }
    """
    text = _clean_ocr(_read_text(file_bytes, file_name, storage_path))
    source_ref = file_name or "uploaded-report"
    empty = {
        "patient": {"id": "", "name": "", "dob": ""},
        "treatment_requested": {
            "service_category": "",
            "diagnosis_codes": [],
            "clinical_notes": "",
        },
        "source_document_reference": source_ref,
    }
    if not (text or "").strip():
        return {"extracted": empty, "extraction_status": "failed", "raw_text": ""}

    heuristic = _heuristic_extract(text, source_ref)
    llm_overlay = _llm_extract(text, source_ref)
    merged = _merge(heuristic, llm_overlay, source_ref, text)
    status = _status(merged)
    return {"extracted": merged, "extraction_status": status, "raw_text": text[:20000]}


def _read_text(file_bytes: bytes, file_name: str, storage_path: str | Path | None) -> str:
    name = (file_name or "").lower()
    path = Path(storage_path) if storage_path else None
    if name.endswith(".pdf") or (path and path.suffix.lower() == ".pdf"):
        try:
            from app.ingest.pdf_reader import read_pdf

            target = path
            if target is None:
                import tempfile

                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp.write(file_bytes)
                tmp.close()
                target = Path(tmp.name)
            pages = read_pdf(target)
            return "\n".join((p.get("text") or "") for p in pages)
        except Exception:
            pass
    # Plain text / failed PDF: best-effort UTF-8
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1", errors="ignore")


def _heuristic_extract(text: str, source_ref: str) -> dict:
    name = _find_name(text)
    dob = _find_dob(text)
    codes = _find_codes(text)
    service = _find_service(text)
    notes = _clip_notes(text)
    return {
        "patient": {"id": "", "name": name or "", "dob": dob or ""},
        "treatment_requested": {
            "service_category": service or "",
            "diagnosis_codes": codes,
            "clinical_notes": notes,
        },
        "source_document_reference": source_ref,
    }


def _llm_extract(text: str, source_ref: str) -> dict | None:
    try:
        from app.config import settings
        from app.llm import _http_complete, _parse_json, _use_offline

        if _use_offline("extract") or not settings.openai_api_key:
            return None
        system = (
            "Extract patient demographics and the treatment requested from a clinical report. "
            "Return JSON only with keys patient{name,dob,id} and "
            "treatment_requested{service_category,diagnosis_codes,clinical_notes}. "
            "service_category is the service being ordered, requested, or recommended for the "
            "patient, not a study that was already performed. Copy wording from the report. "
            "Do not invent facts. Use empty strings when unknown."
        )
        user = f"Source file: {source_ref}\n\nReport text:\n{text[:12000]}"
        raw_text = _http_complete("extract", system, user, timeout=45.0)
        raw = _parse_json(raw_text)
        if not isinstance(raw, dict):
            return None
        return raw
    except Exception:
        return None


def _merge(base: dict, overlay: dict | None, source_ref: str, text: str) -> dict:
    out = json.loads(json.dumps(base))
    if not overlay:
        out["source_document_reference"] = source_ref
        return out
    patient = overlay.get("patient") or {}
    treatment = overlay.get("treatment_requested") or {}
    if patient.get("name"):
        out["patient"]["name"] = str(patient["name"]).strip()
    if patient.get("dob"):
        out["patient"]["dob"] = _normalize_dob(str(patient["dob"])) or out["patient"]["dob"]
    if patient.get("id"):
        out["patient"]["id"] = str(patient["id"]).strip()
    service = str(treatment.get("service_category") or "").strip()
    # G3: an extracted service only replaces the grounded one when its words are in the report.
    if service and _grounded_in(service, text):
        out["treatment_requested"]["service_category"] = service
    if treatment.get("clinical_notes"):
        out["treatment_requested"]["clinical_notes"] = str(treatment["clinical_notes"]).strip()
    codes = treatment.get("diagnosis_codes") or []
    if codes:
        merged = list(out["treatment_requested"]["diagnosis_codes"])
        for code in codes:
            c = str(code).strip()
            if c and c not in merged and c in text:
                merged.append(c)
        out["treatment_requested"]["diagnosis_codes"] = merged
    out["source_document_reference"] = source_ref
    return out


def _grounded_in(value: str, text: str) -> bool:
    from app.ingest.pa_markers import significant_words

    words = significant_words(value)
    if not words:
        return False
    haystack = (text or "").lower()
    return all(word in haystack for word in words)


def _status(payload: dict) -> str:
    patient = payload.get("patient") or {}
    treatment = payload.get("treatment_requested") or {}
    has_name = bool((patient.get("name") or "").strip())
    has_service = bool((treatment.get("service_category") or "").strip())
    has_notes = bool((treatment.get("clinical_notes") or "").strip())
    if has_name and has_service:
        return "success"
    if has_name or has_service or has_notes:
        return "partial"
    return "failed"


def _find_name(text: str) -> str | None:
    patterns = [
        r"(?i)patient\s*(?:name)?\s*[:\-]\s*([A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*){1,3})",
        r"(?i)(?:^|\n)\s*name\s*[:\-]\s*([A-Za-z][A-Za-z'.-]*(?:\s+[A-Za-z][A-Za-z'.-]*){1,3})",
    ]
    stop_words = {"dob", "date", "of", "birth", "mrn", "id", "sex", "gender", "age"}
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            parts = [p for p in re.split(r"\s+", match.group(1).strip()) if p.lower() not in stop_words]
            name = " ".join(parts).strip(" ,;")
            if len(parts) >= 2:
                return name
    return None


def _find_dob(text: str) -> str | None:
    patterns = [
        r"(?i)(?:dob|date of birth|birth\s*date)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})",
        r"(?i)(?:dob|date of birth|birth\s*date)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _normalize_dob(match.group(1))
    return None


def _normalize_dob(value: str) -> str | None:
    value = (value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", value)
    if not match:
        return None
    month, day, year = match.groups()
    year_i = int(year)
    if year_i < 100:
        year_i += 1900 if year_i >= 30 else 2000
    return f"{year_i:04d}-{int(month):02d}-{int(day):02d}"


def _find_codes(text: str) -> list[str]:
    found: list[str] = []
    for match in re.finditer(r"\b([A-TV-Z]\d{2}(?:\.\d{1,4})?)\b", text):  # ICD-10-ish
        code = match.group(1)
        if code not in found:
            found.append(code)
    for code in _find_service_codes(text):
        if code not in found:
            found.append(code)
    return found[:12]


# A billing code sits on its own; accession and member numbers hang off letters or hyphens.
_CODE_LABEL = re.compile(r"(?i)(?:cpt|hcpcs|cdt|procedure code|service code|billing code|code)\D{0,12}$")
_STATE_ZIP = re.compile(r"\b[A-Z]{2}\s+$")
_ID_LINE = re.compile(
    r"(?i)accession|member|mrn|medical record|patient\s*id|policy|group\s*#|claim|npi"
    r"|fax|phone|tel\b|zip|invoice|account|authorization\s*#"
)


def _find_service_codes(text: str) -> list[str]:
    """Five-digit codes that can be a CPT: labelled ones first, ID fragments never."""
    labelled: list[str] = []
    plain: list[str] = []
    for match in re.finditer(r"\d{5}", text):
        start, end = match.span()
        before = text[start - 1] if start else ""
        after = text[end] if end < len(text) else ""
        if before.isalnum() or before in "-/.$%" or after.isalnum() or after in "-/.%":
            continue
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)
        line = text[line_start : line_end if line_end != -1 else len(text)]
        if _ID_LINE.search(line):
            continue
        window = text[max(0, start - 40) : start]
        if _STATE_ZIP.search(window):
            continue
        code = match.group(0)
        bucket = labelled if (_CODE_LABEL.search(window) or before == "(") else plain
        if code not in bucket:
            bucket.append(code)
    return labelled + [code for code in plain if code not in labelled]


# Labels for a service the patient is being sent for, then for one already performed.
_REQUEST_LABELS = (
    "ordered",
    "order",
    "orders",
    "requested",
    "request",
    "procedure requested",
    "service requested",
    "treatment requested",
    "planned procedure",
)
_PERFORMED_LABELS = ("exam", "examination", "procedure", "study", "service", "treatment", "test")
_RECOMMEND_PATTERNS = (
    r"(?i)([^.\n,;:]{5,90}?)\s+(?:is|are|was|were)\s+recommend",
    r"(?i)recommend(?:s|ed|ation)?(?:\s+(?:for|that\s+the\s+patient\s+(?:undergo|have)))?\s*[:\-]?\s*([^.\n;]{5,90})",
)


def _find_service(text: str) -> str | None:
    """The service being asked for. A recommendation beats the study this report documents."""
    return (
        _labelled_service(text, _REQUEST_LABELS)
        or _recommended_service(text)
        or _labelled_service(text, _PERFORMED_LABELS)
    )


def _labelled_service(text: str, labels: tuple[str, ...]) -> str | None:
    pattern = (
        r"(?im)(?:^|[\u00b7|;\u2022]\s*)(?:"
        + "|".join(sorted(labels, key=len, reverse=True))
        + r")\s*[:\-]\s*([^\n]{3,120})"
    )
    for match in re.finditer(pattern, text):
        value = _trim_service(match.group(1))
        if value:
            return value
    return None


def _recommended_service(text: str) -> str | None:
    for pattern in _RECOMMEND_PATTERNS:
        for match in re.finditer(pattern, text):
            value = _trim_service(match.group(1))
            if value:
                return value
    return None


def _trim_service(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    # Reports pack several fields on one line; stop at the next "Some Label:".
    cut = re.search(r"\s(?:[A-Z][A-Za-z]{2,}\s?){1,3}#?\s*:", text)
    if cut:
        text = text[: cut.start()]
    text = text.strip(" -:;,.")
    if len(text) < 3 or not re.search(r"[A-Za-z]{3,}", text):
        return ""
    return text[:100]


def _clean_ocr(text: str) -> str:
    """Remove rotated-watermark residue that pdfplumber interleaves into report lines.

    A diagonal stamp lands as lone capitals: whole noise lines ("E L"), letters trailing
    a sentence, and letters wedged inside words ("iFdentified"). Only letters the document
    itself shows as lone tokens are removed, and only when several such lines prove a
    watermark is there, so ordinary text ("vitamin D") survives.
    """
    body = re.sub(r"\(cid:\d+\)", "-", text or "")
    lines = body.splitlines()
    noise_lines = [line for line in lines if _is_lone_letters(line)]
    noise = {token.upper() for line in noise_lines for token in line.split()}
    if len(noise_lines) < 3 or len(noise) < 3:
        return body
    noise |= _repeated_trailing_letters(lines)
    kept: list[str] = []
    for line in lines:
        if _is_lone_letters(line):
            continue
        tokens = [t for t in line.split() if not (len(t) == 1 and t.isalpha() and t.upper() in noise)]
        rebuilt = _unwedge(" ".join(tokens), noise)
        if rebuilt.strip():
            kept.append(rebuilt)
    return "\n".join(kept)


def _repeated_trailing_letters(lines: list[str]) -> set[str]:
    """Stamp letters that always land on a text line instead of alone ("Technique I")."""
    counts: dict[str, int] = {}
    for line in lines:
        tokens = line.split()
        if len(tokens) < 2:
            continue
        last = tokens[-1]
        if len(last) == 1 and last.isupper():
            counts[last] = counts.get(last, 0) + 1
    return {letter for letter, count in counts.items() if count >= 2}


def _is_lone_letters(line: str) -> bool:
    tokens = line.split()
    return bool(tokens) and all(len(t) == 1 and t.isalpha() for t in tokens)


def _unwedge(line: str, noise: set[str]) -> str:
    def inner(match: re.Match) -> str:
        if match.group(2).upper() not in noise:
            return match.group(0)
        return match.group(1) + match.group(3)

    def prefix(match: re.Match) -> str:
        if match.group(1).upper() not in noise:
            return match.group(0)
        return match.group(2)

    def doubled(match: re.Match) -> str:
        if match.group(1).upper() not in noise:
            return match.group(0)
        return match.group(1) + match.group(2)

    line = re.sub(r"\b([a-z]+)([A-Z])([a-z]+)\b", inner, line)  # asRsociated -> associated
    line = re.sub(r"\b([A-Z])\1([A-Z]{2,})\b", doubled, line)  # MMRI -> MRI
    return re.sub(r"\b([A-Z])([A-Z][a-z]{2,})\b", prefix, line)  # SElectronically -> Electronically


def _clip_notes(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:1500]
