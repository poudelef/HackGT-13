function clean(value) {
  const text = String(value ?? "").trim();
  return text || null;
}

function keyPart(value) {
  return clean(value)?.toLowerCase() || "";
}

function unique(items, keyFn) {
  const seen = new Set();
  const rows = [];
  for (const item of items) {
    if (!item) continue;
    const key = keyFn(item);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    rows.push(item);
  }
  return rows;
}

function buildFormChart(input) {
  const diagnosis = clean(input.icd10Code)
    ? {
        icd10_code: clean(input.icd10Code),
        icd10_description: clean(input.icd10Description),
        diagnosis_type: clean(input.diagnosisType),
        diagnosis_date: clean(input.diagnosisDate),
        clinical_notes: clean(input.clinicalNotes),
      }
    : null;

  const allergy = clean(input.allergen)
    ? { allergen: clean(input.allergen), reaction: clean(input.reaction) }
    : null;

  const medication = clean(input.drugName)
    ? {
        drug_name: clean(input.drugName),
        dosage: clean(input.dosage),
        frequency: clean(input.frequency),
        status: clean(input.medicationStatus) || "ACTIVE",
        start_date: clean(input.medicationStart),
        end_date: clean(input.medicationEnd),
      }
    : null;

  const surgery = clean(input.procedureName)
    ? { procedure_name: clean(input.procedureName), procedure_date: clean(input.procedureDate) }
    : null;

  const family = clean(input.relation) && clean(input.conditionDesc)
    ? { relation: clean(input.relation), condition_desc: clean(input.conditionDesc) }
    : null;

  const social =
    clean(input.smokingStatus) || clean(input.alcoholUse) || clean(input.occupation)
      ? {
          smoking_status: clean(input.smokingStatus),
          alcohol_use: clean(input.alcoholUse),
          occupation: clean(input.occupation),
        }
      : null;

  const treatment = clean(input.treatmentType)
    ? {
        treatment_type: clean(input.treatmentType),
        description: clean(input.treatmentDescription),
        start_date: clean(input.treatmentStart),
        end_date: clean(input.treatmentEnd),
        outcome: clean(input.treatmentOutcome),
        related_icd10_code: clean(input.icd10Code),
      }
    : null;

  return {
    diagnoses: diagnosis ? [diagnosis] : [],
    allergies: allergy ? [allergy] : [],
    medications: medication ? [medication] : [],
    surgical_history: surgery ? [surgery] : [],
    family_history: family ? [family] : [],
    social_history: social ? [social] : [],
    previous_treatments: treatment ? [treatment] : [],
    lab_results: [],
    imaging_reports: [],
    prior_authorization: {
      cpt_code: clean(input.cptCode),
      cpt_description: clean(input.cptDescription),
      request_type: clean(input.requestType),
      urgency: clean(input.urgency),
      units_requested: Number(input.unitsRequested),
      requested_date: clean(input.requestedDate),
      requested_start_date: clean(input.requestedStartDate),
      icd10_code: clean(input.icd10Code),
    },
    medical_necessity_letter: {
      letter_date: clean(input.letterDate),
      letter_text: clean(input.letterText),
    },
  };
}

function normalizeExtracted(structured) {
  const source = structured?.tables || structured || {};
  const social = source.social_history;
  const imaging = source.imaging_report;
  return {
    diagnoses: source.diagnoses || [],
    allergies: source.allergies || [],
    medications: source.medications || [],
    surgical_history: source.surgical_history || [],
    family_history: source.family_history || [],
    social_history: social && (social.smoking_status || social.alcohol_use || social.occupation) ? [social] : [],
    previous_treatments: source.previous_treatments || [],
    lab_results: source.lab_results || [],
    imaging_reports: imaging ? [imaging] : [],
    prior_authorization: priorAuthorizationFrom(source),
    medical_necessity_letter: source.medical_necessity_letter || null,
    member_id: clean(source.patient_insurance?.member_id),
  };
}

function priorAuthorizationFrom(source) {
  const service = source.requested_service || {};
  const auth = source.prior_authorization || {};
  const cptCode = clean(service.cpt_code);
  if (!cptCode && !auth.requested_date && !auth.request_type) return null;
  return {
    cpt_code: cptCode,
    cpt_description: clean(service.description),
    request_type: clean(auth.request_type),
    urgency: clean(auth.urgency),
    units_requested: auth.units_requested,
    requested_date: clean(auth.requested_date),
    requested_start_date: clean(auth.requested_start_date),
  };
}

function mergeCharts(charts) {
  const diagnoses = [];
  const allergies = [];
  const medications = [];
  const surgicalHistory = [];
  const familyHistory = [];
  const socialHistory = [];
  const treatments = [];
  const labs = [];
  const imaging = [];
  let prior = null;
  let letter = null;
  let memberId = null;

  for (const chart of charts) {
    if (!chart) continue;
    diagnoses.push(...(chart.diagnoses || []));
    allergies.push(...(chart.allergies || []));
    medications.push(...(chart.medications || []));
    surgicalHistory.push(...(chart.surgical_history || []));
    familyHistory.push(...(chart.family_history || []));
    socialHistory.push(...(chart.social_history || []));
    treatments.push(...(chart.previous_treatments || []));
    labs.push(...(chart.lab_results || []));
    imaging.push(...(chart.imaging_reports || []));
    if (!prior && chart.prior_authorization?.cpt_code) prior = chart.prior_authorization;
    if (!letter && chart.medical_necessity_letter?.letter_text) letter = chart.medical_necessity_letter;
    if (!memberId && chart.member_id) memberId = chart.member_id;
  }

  return {
    diagnoses: unique(diagnoses, (row) =>
      [keyPart(row.icd10_code), keyPart(row.diagnosis_type), keyPart(row.diagnosis_date)].join("|")
    ),
    allergies: unique(allergies, (row) => [keyPart(row.allergen), keyPart(row.reaction)].join("|")),
    medications: unique(medications, (row) =>
      [keyPart(row.drug_name), keyPart(row.dosage), keyPart(row.start_date)].join("|")
    ),
    surgical_history: unique(surgicalHistory, (row) =>
      [keyPart(row.procedure_name), keyPart(row.procedure_date)].join("|")
    ),
    family_history: unique(familyHistory, (row) =>
      [keyPart(row.relation), keyPart(row.condition_desc)].join("|")
    ),
    social_history: unique(socialHistory, (row) =>
      [keyPart(row.smoking_status), keyPart(row.alcohol_use), keyPart(row.occupation)].join("|")
    ),
    previous_treatments: unique(treatments, (row) =>
      [keyPart(row.treatment_type), keyPart(row.description), keyPart(row.start_date)].join("|")
    ),
    lab_results: unique(labs, (row) =>
      [keyPart(row.test_code || row.test_name), keyPart(row.collected_date), keyPart(row.result_value)].join("|")
    ),
    imaging_reports: unique(imaging, (row) =>
      [keyPart(row.accession_number || row.exam_type), keyPart(row.exam_date)].join("|")
    ),
    prior_authorization: prior,
    medical_necessity_letter: letter,
    member_id: memberId,
  };
}

module.exports = { buildFormChart, normalizeExtracted, mergeCharts };
