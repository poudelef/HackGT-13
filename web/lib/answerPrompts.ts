/** Derive clinician answer hints from question text - no service-specific hardcoding. */

export function subjectFromQuestion(text: string): string {
  const cleaned = (text || "").trim().replace(/\s+/g, " ");
  const patterns = [
    /^Is (.+?) present in the chart\??$/i,
    /^Is (.+?) documented in the chart\??$/i,
    /^Has the patient (.+?)\??$/i,
    /^Has (.+?) been received\??$/i,
    /^Does the patient (.+?)\??$/i,
    /^Was (.+?)\??$/i,
  ];
  for (const pattern of patterns) {
    const match = cleaned.match(pattern);
    if (match?.[1]) return match[1].trim();
  }
  return "this finding";
}

export function isExclusionQuestion(questionText: string, criterionType?: string): boolean {
  if ((criterionType || "").toLowerCase() === "exclusion") return true;
  return /present in the chart/i.test(questionText || "");
}

export function isBooleanQuestion(questionText: string, answerType?: string): boolean {
  if ((answerType || "").toLowerCase() === "boolean") return true;
  return /^(is|has|does|was)\b/i.test((questionText || "").trim());
}

export type SourceKind = "chart_document" | "clinician_note" | "not_in_chart";

/** Source choices when a PDF may be missing - still creates an auditable chart source. */
export function sourceKindOptions(input: {
  questionText: string;
  criterionType?: string;
  hasDocuments: boolean;
}): { value: SourceKind; label: string; hint: string }[] {
  const subject = subjectFromQuestion(input.questionText);
  const exclusion = isExclusionQuestion(input.questionText, input.criterionType);
  const options: { value: SourceKind; label: string; hint: string }[] = [
    {
      value: "chart_document",
      label: input.hasDocuments ? "Existing chart document" : "Existing chart document (none on file yet)",
      hint: "Use a PDF already on the chart, or upload one below.",
    },
    {
      value: "clinician_note",
      label: "Clinician note (no PDF)",
      hint: "ClearPath files a labeled note from your evidence and attestation.",
    },
    {
      value: "not_in_chart",
      label: exclusion ? `Not documented: ${subject}` : "Not documented in chart",
      hint: "Choose this when the chart simply does not show the finding (typical for No / exclusions).",
    },
  ];
  return options;
}

/** Placeholders only - never invent chart facts. */
export function answerFieldHints(input: {
  questionText: string;
  criterionType?: string;
  requirementText?: string;
  sourceKind?: SourceKind;
}): {
  hint: string | null;
  evidencePlaceholder: string;
  attestationPlaceholder: string;
  preferNo: boolean;
} {
  const subject = subjectFromQuestion(input.questionText);
  const exclusion = isExclusionQuestion(input.questionText, input.criterionType);
  if (input.sourceKind === "not_in_chart" || exclusion) {
    return {
      preferNo: true,
      hint:
        input.sourceKind === "not_in_chart"
          ? `Confirm that ${subject} is not in the chart, then attest.`
          : `Choose No when the chart does not show ${subject}, including when it never occurred.`,
      evidencePlaceholder: `Chart reviewed; ${subject} is not documented.`,
      attestationPlaceholder: `I reviewed the chart; ${subject} is not documented.`,
    };
  }
  if (input.sourceKind === "clinician_note") {
    return {
      preferNo: false,
      hint: "No PDF required. Your note becomes the chart source for this answer.",
      evidencePlaceholder: `Clinical rationale for ${subject}`,
      attestationPlaceholder: "I entered this note from my review of the patient.",
    };
  }
  return {
    preferNo: false,
    hint: null,
    evidencePlaceholder: "Quote or short paraphrase from the source document",
    attestationPlaceholder: "I reviewed the chart and this answer is accurate.",
  };
}
