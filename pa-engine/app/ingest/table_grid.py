"""Turn a benefit chart into one labeled row per service.

Column positions come from the header on the page (in-network, out-of-network,
you pay, authorization). No service list is stored here.
"""

from __future__ import annotations

import re

_COST = re.compile(r"\$|\bcopay\b|\bcoinsurance\b|\bnot covered\b|\bcovered\b|\ballowance\b", re.I)
_FOOTNOTE = re.compile(
    r"^(?:depending|medicaid|your|if|see|this|the|copay|coinsurance|for|of|and)\b",
    re.I,
)
_HEADER_LABELS = (
    ("in-network", "In-network"),
    ("out-of-network", "Out-of-network"),
    ("you pay", "You pay"),
    ("what you pay", "You pay"),
    ("authorization", "Authorization"),
)
_SKIP_SERVICE = re.compile(
    r"^(medical benefits|benefits|medical premium|in-network|out-of-network|you pay)$",
    re.I,
)


def rows_from_words(words: list[dict], width: float = 612) -> list[dict]:
    lines = _lines(words)
    anchors = _anchors(lines) or _covered_anchors(lines)
    if len(anchors) < 2:
        return []
    bounds = _bounds(anchors, width)
    rows: list[dict] = []
    current: dict | None = None
    pending: str | None = None
    for line in lines:
        cells = _cells(line, bounds)
        service = _service_name(_strip_marker(cells[0]))
        costs = cells[1:]
        cost_blob = " ".join(costs)
        if _starts_service(service, costs):
            if current:
                rows.append(_finish(current, anchors))
            current = {"service": _clean_service(service), "costs": [c.strip() for c in costs], "notes": ""}
            pending = None
            continue
        if _COST.search(cost_blob) and pending and (_FOOTNOTE.match(service) or not service):
            if current:
                rows.append(_finish(current, anchors))
            current = {"service": pending, "costs": [c.strip() for c in costs], "notes": service}
            pending = None
            continue
        if not _COST.search(cost_blob) and _name_line(service):
            pending = _clean_service(service)
            continue
        if current is None:
            continue
        if service:
            current["notes"] = (current["notes"] + " " + service).strip()
        for index, text in enumerate(costs):
            text = text.strip()
            if text:
                current["costs"][index] = (current["costs"][index] + " " + text).strip()
    if current:
        rows.append(_finish(current, anchors))
    return [row for row in rows if row["service"] and _COST.search(row["line"])]


def _lines(words: list[dict]) -> list[list[dict]]:
    ordered = sorted(words, key=lambda word: (float(word.get("top") or 0), float(word.get("x0") or 0)))
    lines: list[list[dict]] = []
    for word in ordered:
        if not str(word.get("text") or "").strip():
            continue
        if lines and abs(float(word.get("top") or 0) - float(lines[-1][0].get("top") or 0)) <= 3:
            lines[-1].append(word)
        else:
            lines.append([word])
    for line in lines:
        line.sort(key=lambda word: float(word.get("x0") or 0))
    return lines


def _anchors(lines: list[list[dict]]) -> list[tuple[float, str]]:
    for line in lines[:20]:
        found: list[tuple[float, str]] = []
        low_line = " ".join(str(word.get("text") or "") for word in line).lower()
        seen: set[str] = set()
        for needle, label in _HEADER_LABELS:
            if needle not in low_line or label in seen:
                continue
            start = None
            for word in line:
                if needle.split()[0] in str(word.get("text") or "").lower():
                    start = float(word.get("x0") or 0)
                    break
            if start is None:
                continue
            found.append((start, label))
            seen.add(label)
        if len(found) >= 2:
            return sorted(found, key=lambda item: item[0])
    return []


def _covered_anchors(lines: list[list[dict]]) -> list[tuple[float, str]]:
    """A two-column covered chart whose header is not 'in-network'."""
    xs = sorted(
        float(word.get("x0") or 0)
        for line in lines
        for word in line
        if str(word.get("text") or "").lower() == "covered"
    )
    clusters: list[list[float]] = []
    for x in xs:
        if clusters and x - clusters[-1][-1] < 40:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    clusters = [cluster for cluster in clusters if len(cluster) >= 3]
    if len(clusters) < 2:
        return []
    anchors = []
    for index, cluster in enumerate(clusters[:2]):
        center = sum(cluster) / len(cluster)
        anchors.append((center, "You pay" if index == 0 else "Other"))
    return anchors


def _bounds(anchors: list[tuple[float, str]], width: float) -> list[float]:
    edges = [0.0]
    for index, (start, _label) in enumerate(anchors):
        edges.append(max(0.0, start - 8))
    edges.append(float(width) + 20)
    return edges


def _cells(line: list[dict], bounds: list[float]) -> list[str]:
    cells = [""] * (len(bounds) - 1)
    for word in line:
        x = float(word.get("x0") or 0)
        bucket = 0
        for index in range(len(bounds) - 1):
            if bounds[index] <= x < bounds[index + 1]:
                bucket = index
                break
        cells[bucket] = (cells[bucket] + " " + str(word.get("text") or "")).strip()
    return cells


def _service_name(service: str) -> str:
    """A footnote can sit on the same line as the service name."""
    service = service.strip()
    if not _FOOTNOTE.match(service):
        return service
    match = re.search(r"\b([A-Z][A-Za-z]{3,}\d*)\s*$", service)
    if not match:
        return service
    word = match.group(1)
    if word.lower() in {"depending", "medicaid", "medicare", "your"}:
        return service
    return word


def _strip_marker(service: str) -> str:
    return re.sub(r"^\d+\s*", "", service.strip())


def _name_line(service: str) -> bool:
    service = _strip_marker(service)
    if len(service) < 3 or _FOOTNOTE.match(service) or _SKIP_SERVICE.match(service):
        return False
    if "$" in service or _COST.search(service):
        return False
    return bool(re.match(r"[A-Z]", service))


def _starts_service(service: str, costs: list[str]) -> bool:
    service = service.strip()
    if len(service) < 3 or _SKIP_SERVICE.match(service) or _FOOTNOTE.match(service):
        return False
    if not re.match(r"[A-Z]", service):
        return False
    blob = " ".join(costs)
    return bool(_COST.search(blob))


def _clean_service(service: str) -> str:
    service = re.sub(r"\s+", " ", service).strip(" .,:;|-")
    service = re.sub(r"\d+$", "", service).strip()
    return service


def _finish(current: dict, anchors: list[tuple[float, str]]) -> dict:
    from app.ingest.pa_markers import line_pa_status

    parts = [f"Service: {current['service']}"]
    for (_start, label), text in zip(anchors, current["costs"]):
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            parts.append(f"{label}: {text}")
    line = " | ".join(parts)
    blob = line + " " + current.get("notes", "")
    status, marker = line_pa_status(blob)
    return {
        "service": current["service"],
        "line": line,
        "pa_required": status in {"required", "conditional"},
        "pa_status": status,
        "marker_used": marker,
    }
