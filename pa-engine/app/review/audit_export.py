"""Markdown audit of identity, items, decisions, and the episode timeline."""

from __future__ import annotations

from app.ingest.question_builder import plain_english
from app.repository import get_repo


def render(policy_id: str) -> str:
    repo = get_repo()
    policy = repo.get_policy(policy_id)
    if policy is None:
        return ""
    identity = policy.get("identity_evidence") or {}
    lines = [
        f"# Audit: {policy.get('file_name')}",
        "",
        f"- Role: {policy['document_role']}",
        f"- Source: {policy['source_kind']}",
        f"- URL: {policy.get('source_url') or ''}",
        f"- Status: {policy['status']}",
        f"- Insurer: {_field(identity.get('insurer'))}",
        f"- Plan: {_field(identity.get('plan_name'))}",
        f"- Year: {_field(identity.get('plan_year'))}",
        "",
        "## Sections",
        "",
        f"```json",
        __import__("json").dumps(policy.get("sections") or {}, indent=2),
        "```",
        "",
        "## Items",
        "",
    ]
    for item in repo.items_for(policy_id):
        data = item["data"]
        lines += [
            f"### {item['item_key']} ({item['review_state']})",
            "",
            f"- Page: {item['page']}",
            f"- Judge: {item.get('judge_verdict')} — {item.get('judge_reason') or ''}",
            f"- Reviewer: {item.get('reviewed_by') or 'pending'} {item.get('reviewed_at') or ''}",
            f"- Note: {item.get('review_note') or ''}",
            f"- Evidence: {data.get('evidence_text') or ''}",
            "",
        ]
        if item["item_type"] == "rule":
            lines.append(plain_english(data.get("pass_condition")))
            lines.append("")
    lines += ["## Episodes", ""]
    for episode in repo.episodes_for("policy", policy_id):
        lines.append(f"- #{episode['seq']} {episode['actor']} {episode['stage']} {episode['status']}: {episode['summary']}")
    report = policy.get("validation_report") or {}
    lines += ["", "## FHIR", "", f"Valid: {(report.get('fhir') or {}).get('valid')}"]
    return "\n".join(lines) + "\n"


def _field(entry) -> str:
    if not entry:
        return ""
    return f"{entry.get('value')} (p.{entry.get('page')}: {entry.get('evidence')})"
