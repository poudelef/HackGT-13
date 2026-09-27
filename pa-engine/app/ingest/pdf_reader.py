"""Per-page text. A printed page offset is trusted only when two or more pages agree."""

from __future__ import annotations

import re
from pathlib import Path

import pdfplumber


def read_pdf(path: str | Path) -> list[dict]:
    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []
            words = [
                {"text": word.get("text") or "", "x0": word.get("x0") or 0, "top": word.get("top") or 0}
                for word in (page.extract_words() or [])
            ]
            pages.append(
                {
                    "pdf_page": index,
                    "text": text,
                    "tables": tables,
                    "words": words,
                    "width": page.width,
                    "printed": _printed_label(text),
                }
            )
    offset = _trusted_offset(pages)
    for page in pages:
        printed = page["printed"]
        if offset is not None and printed is not None:
            page["page"] = printed
        else:
            page["page"] = page["pdf_page"]
    return pages


def _printed_label(text: str) -> int | None:
    match = re.search(r"printed page\s+(\d+)", text, re.I)
    if match:
        return int(match.group(1))
    return None


def _trusted_offset(pages: list[dict]) -> int | None:
    offsets = []
    for page in pages:
        if page["printed"] is None:
            continue
        offsets.append(page["printed"] - page["pdf_page"])
    if len(offsets) < 2:
        return None
    if len(set(offsets)) == 1:
        return offsets[0]
    return None
