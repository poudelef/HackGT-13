"""Pydantic shapes for extracted rules, coverage, and model payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvidenceField(BaseModel):
    value: str | None = None
    evidence: str | None = None
    page: int | None = None


class IdentityResult(BaseModel):
    insurer: EvidenceField
    plan_name: EvidenceField
    plan_year: EvidenceField
    document_title: EvidenceField = Field(default_factory=EvidenceField)


class CoverageEntry(BaseModel):
    service_label: str
    service_codes: list[str] = Field(default_factory=list)
    pa_required: bool
    page: int
    evidence_text: str
    marker_used: str | None = None
    reference: str | None = None


class Condition(BaseModel):
    condition_key: str
    text: str
    kind: Literal["requirement", "exception", "alternative"]
    value: float | None = None
    unit: str | None = None


class Question(BaseModel):
    link_id: str
    text: str
    answer_type: Literal["boolean", "quantity", "date", "string", "coding"]
    unit: str | None = None
    fill_method: Literal["code_lookup", "date_math", "llm_quote", "llm_quote_value"]
    covers: list[str]
    enable_when: dict | None = None
    text_edited_by_human: bool = False


class Rule(BaseModel):
    criterion_key: str
    requirement_text: str
    criterion_type: Literal[
        "diagnosis",
        "lab",
        "prior_treatment",
        "duration",
        "clinical_note",
        "exclusion",
        "age",
        "prescriber",
    ]
    subtype: Literal["medication", "therapy"] | None = None
    logic: Literal["all_of", "any_of"] = "all_of"
    policy_page: int
    applies_to: list[str] = Field(default_factory=list)
    codes: list[str] = Field(default_factory=list)
    conditions: list[Condition]
    questions: list[Question] = Field(default_factory=list)
    pass_condition: dict | None = None
    evidence_text: str = ""


class JudgeResult(BaseModel):
    verdict: Literal["ACCURATE", "WRONG_VALUE", "HALLUCINATED", "VAGUE"]
    reason: str


class QuestionJudgeResult(BaseModel):
    verdict: Literal["complete", "missing_condition", "added_condition", "leading"]
    reason: str = ""
