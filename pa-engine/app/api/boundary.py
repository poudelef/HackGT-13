"""Teammate boundary + PA-request alias routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.boundary.export_pa import buildOutputForTeammate
from app.boundary.ingest_extracted import ingestExtractedDocument
from app.boundary.pa_rules import lookup_requirement, pa_rules_from_coverage
from app.check import service

router = APIRouter()


@router.post("/ingest/patient-extraction")
def ingest_patient_extraction(body: dict):
    return ingestExtractedDocument(body)


@router.get("/pa-requests/{pa_id}/export")
def export_pa_request(pa_id: str):
    return buildOutputForTeammate(pa_id)


@router.get("/pa-requests/{pa_id}/questionnaire")
def pa_questionnaire(pa_id: str):
    return service.get_questionnaire(pa_id)


@router.post("/pa-requests/{pa_id}/questionnaire")
def pa_questionnaire_submit(pa_id: str, body: dict):
    return service.submit_questionnaire_response(pa_id, body)


@router.post("/pa-requests/{pa_id}/confirm")
def pa_confirm(pa_id: str, body: dict | None = None):
    return service.confirm_draft(pa_id, body or {})


@router.post("/pa-requests/{pa_id}/submit")
def pa_submit(pa_id: str, body: dict):
    return service.submit(pa_id, body["provider_id"])


@router.get("/reviewer/pa-requests")
def reviewer_queue():
    return service.list_recent(queue="insurer")


@router.post("/pa-requests/{pa_id}/decision")
def pa_decision(pa_id: str, body: dict):
    return service.reviewer_decision(pa_id, body)


@router.get("/patients/{patient_id}/pa-requests")
def patient_pa_requests(patient_id: str):
    return service.list_patient_pa_requests(patient_id)


@router.get("/pa-rules")
def list_pa_rules(insurance_plan_id: str | None = None, service_category: str | None = None, service_code: str | None = None):
    if service_category:
        return {"rule": lookup_requirement(insurance_plan_id=insurance_plan_id, service_category=service_category, service_code=service_code)}
    return {"rules": pa_rules_from_coverage(insurance_plan_id=insurance_plan_id, service_code=service_code)}


@router.get("/pa-requests/{pa_id}/pa-required")
def pa_required_recheck(pa_id: str):
    return service.reconfirm_pa_required(pa_id)
