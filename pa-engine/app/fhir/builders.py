"""Pure builders from stored ClearPath data to FHIR JSON."""

from __future__ import annotations

from app.config import settings
from app.fhir.extensions import (
    CLINICIAN_ATTESTATION,
    EVIDENCE_QUOTE,
    EVIDENCE_SOURCE,
    EVIDENCE_TEXT,
    PA_STATUS,
    POLICY_PAGE,
    POLICY_SOURCE,
    REVIEW_STATE,
    UNIT,
    canonical,
    ext,
)
from app.fhir.mappings import TYPES, UNITS
from app.check.answer_filler import decode_value


def build_for_policy(policy: dict, items: list[dict], *, block_id: str | None = None, status: str = "draft") -> dict:
    if policy["document_role"] == "benefit_summary" and not block_id:
        return insurance_plan(policy, items, status="active" if status == "active" else "draft")
    return questionnaire(policy, items, status=status, block_id=block_id)


def questionnaire(policy: dict, items: list[dict], *, status: str, block_id: str | None = None) -> dict:
    version = (policy.get("sha256") or "0" * 12)[:12]
    block_key = None
    title = policy.get("plan_name") or policy.get("file_name")
    resource = {
        "resourceType": "Questionnaire",
        "url": canonical(policy["id"], version, block_key).split("|")[0],
        "version": version,
        "status": "active" if status == "active" else "draft",
        "title": title,
        "publisher": policy.get("insurer"),
        "date": (policy.get("went_live_at") or "")[:10] or None,
        "extension": [
            ext(POLICY_SOURCE, "valueString", policy.get("source_url") or policy.get("file_name") or "")
        ],
        "item": [],
    }
    if resource["date"] is None:
        resource.pop("date")
    for item in items:
        if item["item_type"] != "rule" or item["review_state"] == "rejected":
            continue
        data = item["data"]
        group = {
            "linkId": data["criterion_key"],
            "text": data["requirement_text"],
            "type": "group",
            "extension": [
                ext(POLICY_PAGE, "valueInteger", item["page"]),
                ext(REVIEW_STATE, "valueString", item["review_state"]),
            ],
            "item": [],
        }
        for question in data.get("questions") or []:
            nested = {
                "linkId": question["link_id"],
                "text": question["text"],
                "type": TYPES[question["answer_type"]],
                "required": question.get("enable_when") is None,
            }
            if question.get("enable_when"):
                gate = question["enable_when"]
                nested["enableWhen"] = [
                    {
                        "question": gate["question"],
                        "operator": gate["operator"],
                        "answerBoolean": bool(gate["answer"]),
                    }
                ]
            if question["answer_type"] == "quantity" and question.get("unit"):
                nested["extension"] = [
                    ext(
                        UNIT,
                        "valueCoding",
                        {"system": "http://unitsofmeasure.org", "code": UNITS.get(question["unit"], question["unit"])},
                    )
                ]
            group["item"].append(nested)
        resource["item"].append(group)
    return resource


def insurance_plan(policy: dict, items: list[dict], *, status: str = "active") -> dict:
    year = policy.get("plan_year") or "2026"
    benefits = []
    for item in items:
        if item["item_type"] != "coverage" or item["review_state"] == "rejected":
            continue
        data = item["data"] if isinstance(item.get("data"), dict) else {}
        pa_status = data.get("pa_status")
        if not pa_status:
            pa_status = "required" if data.get("pa_required") else "not_required"
        if pa_status == "conditional":
            requirement = "Prior authorization may be required"
        elif data.get("pa_required"):
            requirement = "Prior authorization required"
        else:
            requirement = "No prior authorization required"
        benefit = {
            "type": {"text": data.get("service_label") or item.get("service_label")},
            "requirement": requirement,
            "extension": [
                ext(POLICY_PAGE, "valueInteger", item["page"]),
                ext(EVIDENCE_TEXT, "valueString", data.get("evidence_text") or ""),
                ext(PA_STATUS, "valueCode", pa_status),
            ],
        }
        if data.get("reference") or data.get("note"):
            benefit["extension"].append(
                ext(EVIDENCE_QUOTE, "valueString", data.get("reference") or data.get("note") or "")
            )
        codes = [code for code in (data.get("service_codes") or []) if code]
        if codes:
            benefit["type"]["coding"] = [{"code": code} for code in codes]
        benefits.append(benefit)
    return {
        "resourceType": "InsurancePlan",
        "status": "active" if status == "active" else "draft",
        "name": policy.get("plan_name") or "Plan",
        "ownedBy": {"display": policy.get("insurer") or "Insurer"},
        "period": {"start": f"{year}-01-01"},
        "identifier": [
            {"system": f"{settings.fhir_base_url}/plan-id", "value": policy["id"]}
        ],
        "coverage": [{"type": {"text": "Medical"}, "benefit": benefits or [{"type": {"text": "Medical"}}]}],
    }


def questionnaire_response(pa: dict, criteria: list[dict], policy: dict, *, completed: bool) -> dict:
    version = (policy.get("sha256") or "0" * 12)[:12] if policy else "draft"
    policy_id = policy["id"] if policy else "unknown"
    items = []
    for criterion in criteria:
        if criterion.get("verified_by") is None and completed:
            continue
        nested = []
        for answer in criterion.get("questions") or criterion.get("answers") or []:
            if not answer.get("enabled", True):
                continue
            value = decode_value(answer.get("value"))
            if value is None:
                continue
            entry = {"linkId": answer["link_id"], "answer": [_value(answer.get("answer_type"), value, answer.get("unit"))]}
            extensions = []
            if answer.get("evidence_text"):
                extensions.append(ext(EVIDENCE_QUOTE, "valueString", answer["evidence_text"]))
            if answer.get("attestation"):
                extensions.append(ext(CLINICIAN_ATTESTATION, "valueString", answer["attestation"]))
            if answer.get("evidence_record_id"):
                extensions.append(
                    ext(EVIDENCE_SOURCE, "valueReference", {"reference": f"DocumentReference/{answer['evidence_record_id']}"})
                )
            if extensions:
                entry["extension"] = extensions
            nested.append(entry)
        items.append({"linkId": criterion["criterion_key"], "item": nested})
    return {
        "resourceType": "QuestionnaireResponse",
        "questionnaire": canonical(policy_id, version),
        "status": "completed" if completed else "in-progress",
        "subject": {"display": (pa.get("patient") or {}).get("full_name", "Synthetic patient")},
        "authored": pa.get("submitted_at") or pa.get("updated_at"),
        "item": items,
    }


def _value(answer_type: str | None, value, unit: str | None) -> dict:
    if isinstance(value, dict) and "code" in value:
        return {"valueCoding": {"code": value["code"], "display": value.get("display")}}
    if answer_type == "boolean" or isinstance(value, bool):
        return {"valueBoolean": bool(value)}
    if answer_type == "quantity" or isinstance(value, (int, float)):
        return {
            "valueQuantity": {
                "value": float(value),
                "unit": unit or "",
                "system": "http://unitsofmeasure.org",
                "code": UNITS.get(unit or "", unit or ""),
            }
        }
    if answer_type == "date":
        return {"valueDate": str(value)[:10]}
    return {"valueString": str(value)}
