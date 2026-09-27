// JSON shapes for the seven clinical PDFs.
// Field names match the future relational tables. Surrogate keys
// (patient_id, provider_id, and the rest) are left out on purpose:
// the database assigns those later. Related rows are nested by name
// and natural keys such as NPI, ICD-10, and CPT.

const date = { type: ["string", "null"], description: "YYYY-MM-DD, or null if absent" };
const text = { type: ["string", "null"] };
const num = { type: ["number", "null"] };
const int = { type: ["integer", "null"] };

const patient = {
  type: "object",
  description: "PATIENTS. Split a full name into first_name and last_name.",
  properties: {
    first_name: text,
    last_name: text,
    dob: date,
    sex: { type: ["string", "null"], enum: ["MALE", "FEMALE", "OTHER", "UNKNOWN", null] },
    phone: text,
    address: text,
  },
};

const clinic = {
  type: ["object", "null"],
  description: "CLINICS",
  properties: {
    name: text,
    address: text,
    phone: text,
    fax: text,
  },
};

const provider = {
  type: ["object", "null"],
  description: "PROVIDERS. clinic is the PROVIDERS.clinic_id relationship, stored by clinic fields.",
  properties: {
    npi: text,
    first_name: text,
    last_name: text,
    specialty: text,
    tax_id: text,
    clinic,
  },
};

const facility = {
  type: ["object", "null"],
  description: "FACILITIES",
  properties: {
    name: text,
    facility_type: {
      type: ["string", "null"],
      enum: ["HOSPITAL", "LABORATORY", "IMAGING_CENTER", "AMBULATORY_SURGERY", "CLINIC", "OTHER", null],
    },
    address: text,
    phone: text,
  },
};

const payer = {
  type: ["object", "null"],
  description: "PAYERS",
  properties: {
    name: text,
    payer_code: text,
    pa_dept_phone: text,
    pa_dept_fax: text,
  },
};

const patientInsurance = {
  type: ["object", "null"],
  description: "PATIENT_INSURANCE plus the related PAYERS row.",
  properties: {
    member_id: text,
    group_number: text,
    effective_date: date,
    termination_date: date,
    payer,
  },
};

const diagnosis = {
  type: "object",
  description: "DIAGNOSES plus ICD10_CODES. icd10_description is ICD10_CODES.description.",
  properties: {
    icd10_code: text,
    icd10_description: text,
    diagnosis_type: {
      type: ["string", "null"],
      enum: ["PRIMARY", "SECONDARY", "ADMITTING", "HISTORICAL", null],
    },
    diagnosis_date: date,
    clinical_notes: text,
    provider,
  },
};

const cpt = {
  type: ["object", "null"],
  description: "CPT_CODES",
  properties: {
    cpt_code: text,
    description: text,
  },
};

const DOCUMENT_SCHEMAS = {
  PA_FORM: {
    description: "Prior Authorization Request Form",
    schema: {
      type: "object",
      properties: {
        patient,
        patient_insurance: patientInsurance,
        requesting_provider: provider,
        facility,
        diagnoses: { type: "array", items: diagnosis },
        requested_service: cpt,
        prior_authorization: {
          type: "object",
          description: "PRIOR_AUTHORIZATIONS. Do not invent current_status if the form has no decision.",
          properties: {
            request_type: {
              type: ["string", "null"],
              enum: ["MEDICATION", "IMAGING", "PROCEDURE", "DME", "INPATIENT", "REFERRAL", "OTHER", null],
            },
            urgency: { type: ["string", "null"], enum: ["STANDARD", "URGENT", null] },
            units_requested: int,
            requested_date: date,
            requested_start_date: date,
            current_status: {
              type: ["string", "null"],
              enum: ["PENDING", "APPROVED", "DENIED", "MORE_INFO_NEEDED", "CANCELLED", "APPEALED", null],
            },
          },
        },
        patient_cost_share: {
          type: ["object", "null"],
          description: "PATIENT_COST_SHARES. Null unless dollar amounts are printed.",
          properties: {
            deductible_amount: num,
            copay_amount: num,
            coinsurance_pct: num,
            total_patient_responsibility: num,
          },
        },
        appeal: {
          type: ["object", "null"],
          description: "APPEALS. Null unless the document is an appeal.",
          properties: {
            appeal_date: date,
            additional_info: text,
            appeal_status: {
              type: ["string", "null"],
              enum: ["PENDING", "APPROVED", "DENIED", "WITHDRAWN", null],
            },
            decision_date: date,
          },
        },
      },
      required: ["patient", "prior_authorization"],
    },
  },

  DIAGNOSIS_SUMMARY: {
    description: "Diagnosis Summary",
    schema: {
      type: "object",
      properties: {
        patient,
        provider,
        diagnoses: { type: "array", items: diagnosis },
      },
      required: ["patient", "diagnoses"],
    },
  },

  MEDICAL_HISTORY: {
    description: "Medical History",
    schema: {
      type: "object",
      properties: {
        patient,
        allergies: {
          type: "array",
          description: "ALLERGIES",
          items: {
            type: "object",
            properties: { allergen: text, reaction: text },
          },
        },
        medications: {
          type: "array",
          description: "MEDICATIONS. prescribing_provider maps to prescribing_provider_id.",
          items: {
            type: "object",
            properties: {
              drug_name: text,
              dosage: text,
              frequency: text,
              status: {
                type: ["string", "null"],
                enum: ["ACTIVE", "DISCONTINUED", "COMPLETED", "ON_HOLD", null],
              },
              start_date: date,
              end_date: date,
              prescribing_provider: provider,
            },
          },
        },
        surgical_history: {
          type: "array",
          description: "SURGICAL_HISTORY",
          items: {
            type: "object",
            properties: { procedure_name: text, procedure_date: date },
          },
        },
        family_history: {
          type: "array",
          description: "FAMILY_HISTORY",
          items: {
            type: "object",
            properties: { relation: text, condition_desc: text },
          },
        },
        social_history: {
          type: ["object", "null"],
          description: "SOCIAL_HISTORY. One row per patient.",
          properties: {
            smoking_status: text,
            alcohol_use: text,
            occupation: text,
          },
        },
      },
      required: ["patient"],
    },
  },

  LAB_RESULTS: {
    description: "Laboratory Results",
    schema: {
      type: "object",
      properties: {
        patient,
        ordering_provider: provider,
        facility,
        results: {
          type: "array",
          description: "Each item is one LAB_RESULTS row plus LAB_TEST_CATALOG and LAB_PANELS fields.",
          items: {
            type: "object",
            properties: {
              panel_name: text,
              test_code: text,
              test_name: text,
              unit: text,
              ref_range_low: num,
              ref_range_high: num,
              result_value: num,
              flag: {
                type: ["string", "null"],
                enum: ["NORMAL", "HIGH", "LOW", "CRITICAL", "ABNORMAL", null],
              },
              collected_date: date,
            },
            required: ["test_name"],
          },
        },
      },
      required: ["patient", "results"],
    },
  },

  IMAGING_REPORT: {
    description: "Imaging Report / X-Ray",
    schema: {
      type: "object",
      properties: {
        patient,
        ordering_provider: provider,
        facility,
        cpt,
        imaging_report: {
          type: "object",
          description: "IMAGING_REPORTS",
          properties: {
            exam_type: text,
            exam_date: date,
            accession_number: text,
            findings: text,
            impression: text,
            reading_radiologist: text,
          },
          required: ["exam_type", "findings", "impression"],
        },
      },
      required: ["patient", "imaging_report"],
    },
  },

  PREVIOUS_TREATMENTS: {
    description: "Previous Treatments Log",
    schema: {
      type: "object",
      properties: {
        patient,
        treatments: {
          type: "array",
          description: "PREVIOUS_TREATMENTS. related_diagnosis maps to related_diagnosis_id via ICD-10.",
          items: {
            type: "object",
            properties: {
              treatment_type: text,
              description: text,
              start_date: date,
              end_date: date,
              outcome: text,
              related_diagnosis: {
                type: ["object", "null"],
                properties: {
                  icd10_code: text,
                  icd10_description: text,
                },
              },
            },
            required: ["treatment_type"],
          },
        },
      },
      required: ["patient", "treatments"],
    },
  },

  MEDICAL_NECESSITY_LETTER: {
    description: "Letter of Medical Necessity",
    schema: {
      type: "object",
      properties: {
        patient,
        provider,
        patient_insurance: patientInsurance,
        diagnoses: { type: "array", items: diagnosis },
        requested_service: cpt,
        medical_necessity_letter: {
          type: "object",
          description: "MEDICAL_NECESSITY_LETTERS. letter_text should be the letter body, not a summary.",
          properties: {
            letter_date: date,
            letter_text: text,
          },
          required: ["letter_date", "letter_text"],
        },
        prior_authorization: {
          type: ["object", "null"],
          description: "PRIOR_AUTHORIZATIONS fields mentioned in the letter.",
          properties: {
            request_type: {
              type: ["string", "null"],
              enum: ["MEDICATION", "IMAGING", "PROCEDURE", "DME", "INPATIENT", "REFERRAL", "OTHER", null],
            },
            urgency: { type: ["string", "null"], enum: ["STANDARD", "URGENT", null] },
            units_requested: int,
            requested_date: date,
            requested_start_date: date,
          },
        },
      },
      required: ["patient", "provider", "medical_necessity_letter"],
    },
  },
};

const CLINICAL_DOCUMENT_SCHEMA = {
  type: "object",
  description:
    "All tables a clinical PDF might fill. The doctor does not pick a type. Use null or an empty array for any section the PDF does not contain.",
  properties: {
    document_type: {
      type: "string",
      enum: [...Object.keys(DOCUMENT_SCHEMAS), "OTHER"],
      description: "Closest document type for this PDF.",
    },
    patient,
    provider,
    facility,
    patient_insurance: patientInsurance,
    diagnoses: { type: "array", items: diagnosis },
    allergies: DOCUMENT_SCHEMAS.MEDICAL_HISTORY.schema.properties.allergies,
    medications: DOCUMENT_SCHEMAS.MEDICAL_HISTORY.schema.properties.medications,
    surgical_history: DOCUMENT_SCHEMAS.MEDICAL_HISTORY.schema.properties.surgical_history,
    family_history: DOCUMENT_SCHEMAS.MEDICAL_HISTORY.schema.properties.family_history,
    social_history: DOCUMENT_SCHEMAS.MEDICAL_HISTORY.schema.properties.social_history,
    lab_results: DOCUMENT_SCHEMAS.LAB_RESULTS.schema.properties.results,
    imaging_report: {
      ...DOCUMENT_SCHEMAS.IMAGING_REPORT.schema.properties.imaging_report,
      type: ["object", "null"],
    },
    requested_service: cpt,
    previous_treatments: DOCUMENT_SCHEMAS.PREVIOUS_TREATMENTS.schema.properties.treatments,
    prior_authorization: DOCUMENT_SCHEMAS.PA_FORM.schema.properties.prior_authorization,
    patient_cost_share: DOCUMENT_SCHEMAS.PA_FORM.schema.properties.patient_cost_share,
    appeal: DOCUMENT_SCHEMAS.PA_FORM.schema.properties.appeal,
    medical_necessity_letter: {
      ...DOCUMENT_SCHEMAS.MEDICAL_NECESSITY_LETTER.schema.properties.medical_necessity_letter,
      type: ["object", "null"],
    },
  },
  required: ["document_type"],
};

module.exports = { DOCUMENT_SCHEMAS, CLINICAL_DOCUMENT_SCHEMA };
