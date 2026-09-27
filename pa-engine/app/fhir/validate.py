"""Every emitted resource is parsed with fhir.resources and checked for link consistency."""

from __future__ import annotations

from fhir.resources.R4B.insuranceplan import InsurancePlan
from fhir.resources.R4B.questionnaire import Questionnaire
from fhir.resources.R4B.questionnaireresponse import QuestionnaireResponse


def validate_resource(resource: dict) -> list[str]:
    errors: list[str] = []
    kind = resource.get("resourceType")
    model = {"Questionnaire": Questionnaire, "InsurancePlan": InsurancePlan, "QuestionnaireResponse": QuestionnaireResponse}.get(kind)
    if model is None:
        return [f"Unsupported resource {kind}"]
    try:
        model.model_validate(resource)
    except Exception as exc:
        errors.append(str(exc).split("\n")[0][:500])
    if kind == "Questionnaire":
        errors.extend(_questionnaire_rules(resource))
    if kind == "QuestionnaireResponse":
        errors.extend(_response_rules(resource))
    return errors


def _questionnaire_rules(resource: dict) -> list[str]:
    errors = []
    seen = []

    def walk(items, earlier: list[str]) -> None:
        for item in items or []:
            link = item.get("linkId")
            if link in seen:
                errors.append(f"Duplicate linkId {link}")
            seen.append(link)
            for gate in item.get("enableWhen") or []:
                if gate.get("question") not in earlier:
                    errors.append(f"enableWhen points at {gate.get('question')} which is not earlier")
            earlier.append(link)
            walk(item.get("item"), earlier)

    walk(resource.get("item"), [])
    return errors


def _response_rules(resource: dict) -> list[str]:
    errors = []
    if not resource.get("questionnaire"):
        errors.append("QuestionnaireResponse is missing questionnaire")
    return errors
