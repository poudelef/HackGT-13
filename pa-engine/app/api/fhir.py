"""FHIR reads. Resources are validated before they are returned."""

from __future__ import annotations

from fastapi import APIRouter

from app.errors import ApiError
from app.fhir.builders import insurance_plan, questionnaire, questionnaire_response
from app.fhir.validate import validate_resource
from app.repository import get_repo

router = APIRouter()


@router.get("/policies/{policy_id}/fhir")
def policy_fhir(policy_id: str):
    repo = get_repo()
    policy = repo.get_policy(policy_id)
    if policy is None:
        raise ApiError("POLICY_NOT_FOUND", "No policy with that id.", 404)
    if policy.get("fhir_questionnaire"):
        return policy["fhir_questionnaire"]
    if policy.get("fhir_insurance_plan"):
        return policy["fhir_insurance_plan"]
    items = [item for item in repo.items_for(policy_id) if item["review_state"] != "rejected"]
    if policy["document_role"] == "benefit_summary":
        resource = insurance_plan(policy, items, status="draft")
    else:
        resource = questionnaire(policy, items, status="active" if policy["status"] == "live" else "draft")
    errors = validate_resource(resource)
    if errors:
        raise ApiError("FHIR_INVALID", "; ".join(errors), 409)
    return resource


@router.get("/pa/{pa_id}/fhir/questionnaire-response")
def qr(pa_id: str):
    repo = get_repo()
    pa = repo.get_pa(pa_id)
    if pa is None:
        raise ApiError("POLICY_NOT_FOUND", "No request with that id.", 404)
    policy = repo.get_policy(pa["criteria_policy_id"]) if pa.get("criteria_policy_id") else None
    criteria = []
    for criterion in repo.criteria_for(pa_id):
        criteria.append({**criterion, "questions": repo.answers_for(criterion["id"]), "answers": repo.answers_for(criterion["id"])})
    patient = repo.get_patient(pa["patient_id"])
    resource = questionnaire_response({**pa, "patient": patient}, criteria, policy or {"id": "none", "sha256": "0"}, completed=pa["status"] in {"submitted", "in_review", "approved"})
    errors = validate_resource(resource)
    if errors:
        raise ApiError("FHIR_INVALID", "; ".join(errors), 409)
    return resource


@router.get("/pa/{pa_id}/fhir/bundle")
def bundle(pa_id: str):
    response = qr(pa_id)
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": response}],
    }
