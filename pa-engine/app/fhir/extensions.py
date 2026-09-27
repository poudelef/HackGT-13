"""Demo extension URLs. They are identifiers, not a published HL7 guide."""

from app.config import settings

BASE = "https://clearpath.example/fhir/StructureDefinition"
POLICY_PAGE = f"{BASE}/policy-page"
POLICY_SOURCE = f"{BASE}/policy-source"
EVIDENCE_TEXT = f"{BASE}/evidence-text"
EVIDENCE_QUOTE = f"{BASE}/evidence-quote"
EVIDENCE_SOURCE = f"{BASE}/evidence-source"
CLINICIAN_ATTESTATION = f"{BASE}/clinician-attestation"
REVIEW_STATE = f"{BASE}/review-state"
CRITERIA_QUESTIONNAIRE = f"{BASE}/criteria-questionnaire"
PA_STATUS = f"{BASE}/pa-requirement-status"
UNIT = "http://hl7.org/fhir/StructureDefinition/questionnaire-unit"


def ext(url: str, key: str, value) -> dict:
    return {"url": url, key: value}


def canonical(policy_id: str, version: str, block_key: str | None = None) -> str:
    suffix = f"-{block_key}" if block_key else ""
    return f"{settings.fhir_base_url}/Questionnaire/{policy_id}{suffix}|{version}"
