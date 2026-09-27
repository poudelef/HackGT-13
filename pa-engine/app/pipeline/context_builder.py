"""Clean pages without dropping a rule line (F6). Context-only pages are not citable."""

from __future__ import annotations

import re

PROTECTED = re.compile(
    r"unless|except|authorization|criteria|contraindicated|indication|exclusion|"
    r"\b[A-Z]\d{2}(?:\.\d+)?\b|\b\d{5}\b",
    re.I,
)


def clean(pages: list[dict]) -> tuple[list[dict], dict]:
    headers, footers = _repeated_edges(pages)
    tokens_before = 0
    tokens_after = 0
    protected = 0
    removed = 0
    cleaned = []
    for page in pages:
        lines = page.get("text", "").splitlines()
        tokens_before += _tokens("\n".join(lines))
        kept: list[str] = []
        last = len(lines) - 1
        for index, line in enumerate(lines):
            edge = (index == 0 and _digit_free(line) in headers) or (
                index == last and last > 0 and _digit_free(line) in footers
            )
            if edge and not PROTECTED.search(line):
                removed += 1
                continue
            if edge and PROTECTED.search(line):
                protected += 1
            kept.append(line)
        from app.ingest.table_grid import rows_from_words

        grid_rows = rows_from_words(page.get("words") or [], float(page.get("width") or 612))
        table_lines = [row["line"] for row in grid_rows]
        for table in page.get("tables") or []:
            for row in table:
                cells = [(cell or "").strip() for cell in row]
                if any(cells):
                    table_lines.append(" | ".join(cells))
                    protected += 1
        text = "\n".join([ln for ln in kept if ln is not None] + table_lines).strip()
        tokens_after += _tokens(text)
        kept_page = {key: value for key, value in page.items() if key != "words"}
        cleaned.append({**kept_page, "text": text, "grid_rows": grid_rows, "citable": not page.get("context_only", False)})
    report = {
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "protected_lines": protected,
        "removed_lines": removed,
    }
    return cleaned, report


def _repeated_edges(pages: list[dict]) -> tuple[set[str], set[str]]:
    if len(pages) < 2:
        return set(), set()
    from collections import Counter

    firsts: Counter[str] = Counter()
    lasts: Counter[str] = Counter()
    for page in pages:
        lines = [ln for ln in page.get("text", "").splitlines() if ln.strip()]
        if not lines:
            continue
        firsts[_digit_free(lines[0])] += 1
        lasts[_digit_free(lines[-1])] += 1
    need = 2
    return {k for k, v in firsts.items() if k and v >= need}, {k for k, v in lasts.items() if k and v >= need}


def _digit_free(line: str) -> str:
    return re.sub(r"\d", "", line).strip().lower()


def _tokens(text: str) -> int:
    return len(text.split())
