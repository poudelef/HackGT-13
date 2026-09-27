"""Store the original note, then locate coded facts. Dates are read by code."""

from __future__ import annotations

from app.check.dates import parse_date
from app.llm import complete
from app.repository import get_repo, new_id


def extract(patient_id: str, text: str, document_id: str | None, *, run_id: str) -> list[dict]:
    repo = get_repo()
    found_date = None
    for line in text.splitlines():
        found_date = parse_date(line) or found_date
    if found_date is None:
        found_date = parse_date(text)
    note = repo.insert_record(
        {
            "id": new_id(),
            "patient_id": patient_id,
            "resource_type": "DocumentReference",
            "record_kind": "note",
            "body": text,
            "start_date": found_date.isoformat() if found_date else None,
            "source_document_id": document_id,
            "synthetic": True,
            "fhir_resource": {
                "resourceType": "DocumentReference",
                "status": "current",
                "description": "Synthetic report",
            },
        }
    )
    records = [note]
    try:
        facts = complete(
            "p3",
            {"text": text},
            schema=None,
            stage="facts",
            run_id=run_id,
        )["data"].get("facts") or []
    except Exception:
        facts = []
    for fact in facts:
        if fact.get("kind") == "diagnosis" and fact.get("code"):
            records.append(
                repo.insert_record(
                    {
                        "patient_id": patient_id,
                        "resource_type": "Condition",
                        "record_kind": "diagnosis",
                        "code": fact["code"],
                        "display": fact.get("display") or fact["code"],
                        "source_document_id": document_id,
                        "synthetic": True,
                    }
                )
            )
    if document_id:
        repo.update_document(document_id, {"in_chart": True})
    return records
