"""Working memory is context for later pages. It is never evidence (F5)."""

from __future__ import annotations


def empty() -> dict:
    return {"definitions": [], "markers": [], "open_item": None, "items_found": []}


def apply_updates(memory: dict, updates: dict | None, page_text_by_page: dict[int, str]) -> dict:
    memory = {
        "definitions": list(memory.get("definitions") or []),
        "markers": list(memory.get("markers") or []),
        "open_item": memory.get("open_item"),
        "items_found": list(memory.get("items_found") or []),
    }
    updates = updates or {}
    if not isinstance(updates, dict):
        return budget(memory)
    for bucket in ("definitions", "markers"):
        raw = updates.get(bucket) or []
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            continue
        for entry in raw:
            kept = _grounded_entry(entry, page_text_by_page)
            if kept:
                memory[bucket].append(kept)
    if "open_item" in updates:
        item = updates.get("open_item")
        memory["open_item"] = item if isinstance(item, dict) else None
    return budget(memory)


def _grounded_entry(entry, page_text_by_page: dict[int, str]) -> dict | None:
    """Keep a memory note only when its words are on a cited page. Strings are allowed."""
    if isinstance(entry, str):
        evidence = entry.strip()
        if len(evidence) < 8:
            return None
        for page, source in page_text_by_page.items():
            if evidence in (source or ""):
                return {"page": page, "evidence": evidence, "term": evidence, "text": evidence, "marker": evidence, "meaning": evidence}
        return None
    if not isinstance(entry, dict):
        return None
    page = entry.get("page")
    if isinstance(page, str) and page.isdigit():
        page = int(page)
        entry = {**entry, "page": page}
    evidence = entry.get("evidence") or entry.get("text") or ""
    source = page_text_by_page.get(page, "") if isinstance(page, int) else ""
    if evidence and evidence in source:
        return entry
    return None


def budget(memory: dict, max_tokens: int = 1500) -> dict:
    """Drop oldest context entries until the rendered memory fits. Items already found stay."""
    rendered = render(memory)
    while _tokens(rendered) > max_tokens and (memory["definitions"] or memory["markers"]):
        if memory["definitions"]:
            memory["definitions"] = memory["definitions"][1:]
        elif memory["markers"]:
            memory["markers"] = memory["markers"][1:]
        rendered = render(memory)
    return memory


def render(memory: dict) -> str:
    lines = ["CONTEXT ONLY. Memory is not evidence and must not be cited."]
    for entry in memory.get("definitions") or []:
        lines.append(f"Definition: {entry.get('term')}: {entry.get('text')}")
    for entry in memory.get("markers") or []:
        lines.append(f"Marker: {entry.get('marker')} means {entry.get('meaning')}")
    if memory.get("open_item"):
        lines.append("Open item from an earlier page is still unfinished.")
    found = memory.get("items_found") or []
    if found:
        lines.append("items_found: " + ", ".join(found))
    return "\n".join(lines)


def remember_items(memory: dict, keys: list[str]) -> dict:
    found = list(memory.get("items_found") or [])
    for key in keys:
        if key not in found:
            found.append(key)
    memory["items_found"] = found
    return memory


def merge_open_item(memory: dict, new_items: list[dict]) -> list[dict]:
    """A rule that started on an earlier page is completed once, not duplicated."""
    open_item = memory.get("open_item")
    if not isinstance(open_item, dict) or not new_items or not isinstance(new_items[0], dict):
        return new_items
    first = new_items[0]
    if first.get("criterion_key") == open_item.get("criterion_key") or first.get("continues"):
        merged = {**open_item, **first, "policy_page": open_item.get("policy_page", first.get("policy_page"))}
        memory["open_item"] = None
        return [merged, *new_items[1:]]
    return new_items


def _tokens(text: str) -> int:
    return max(1, len(text.split()))
