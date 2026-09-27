const { pool } = require("./db");
const { findPatient, loadDashboard } = require("./patientRecords");
const { mergeCharts } = require("./chartMerge");

const DOCUMENT_TYPES = [
  "PA_FORM",
  "DIAGNOSIS_SUMMARY",
  "MEDICAL_HISTORY",
  "LAB_RESULTS",
  "IMAGING_REPORT",
  "PREVIOUS_TREATMENTS",
  "MEDICAL_NECESSITY_LETTER",
];

function clean(value) {
  const text = String(value ?? "").trim();
  return text || null;
}

function today() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function requireDate(value, label) {
  const text = clean(value);
  if (!text) return null;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    const error = new Error(`${label} must be a date.`);
    error.status = 400;
    throw error;
  }
  return text;
}

async function findProvider(providerId, npi) {
  const id = String(providerId ?? "").trim();
  const npiValue = String(npi ?? "").trim();
  if (!/^\d+$/.test(id) || !npiValue) return null;

  const [rows] = await pool.query(
    `SELECT pr.provider_id, TRIM(pr.npi) AS npi, pr.first_name, pr.last_name, pr.specialty,
            c.name AS clinic_name
     FROM providers pr
     LEFT JOIN clinics c ON c.clinic_id = pr.clinic_id
     WHERE pr.provider_id = ? AND TRIM(pr.npi) = ?
     LIMIT 1`,
    [id, npiValue]
  );
  return rows[0] || null;
}

async function loadPatientForDoctor(providerId, npi, patientName, patientId) {
  const provider = await findProvider(providerId, npi);
  if (!provider) {
    const error = new Error("Not authorized. That provider ID and NPI do not match.");
    error.status = 401;
    throw error;
  }

  const record = await loadDashboard(patientName, patientId);
  return { provider, record };
}

async function ensureLookup(conn, table, codeColumn, descriptionColumn, code, description, label) {
  const [existing] = await conn.query(
    `SELECT ${codeColumn} AS code FROM ${table} WHERE ${codeColumn} = ? LIMIT 1`,
    [code]
  );
  if (existing.length) return;
  if (!description) {
    const error = new Error(`Enter a description for new ${label} ${code}.`);
    error.status = 400;
    throw error;
  }
  await conn.query(
    `INSERT INTO ${table} (${codeColumn}, ${descriptionColumn}) VALUES (?, ?)`,
    [code, description]
  );
}

async function ensureSocialHistoryCanStack(conn) {
  const [keys] = await conn.query(
    `SELECT COLUMN_NAME
     FROM information_schema.KEY_COLUMN_USAGE
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'social_history'
       AND CONSTRAINT_NAME = 'PRIMARY'`
  );
  const columns = keys.map((row) => row.COLUMN_NAME);
  if (columns.includes("social_history_id")) return;
  const [indexes] = await conn.query("SHOW INDEX FROM social_history WHERE Key_name = 'idx_social_patient'");
  if (!indexes.length) {
    await conn.query("ALTER TABLE social_history ADD INDEX idx_social_patient (patient_id)");
  }
  await conn.query("ALTER TABLE social_history DROP PRIMARY KEY");
  await conn.query(
    "ALTER TABLE social_history ADD COLUMN social_history_id INT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST"
  );
}

async function existingId(conn, sql, params) {
  const [rows] = await conn.query(sql, params);
  return rows[0]?.id || null;
}

async function createAuthorization(input, files, pdfCharts = []) {
  const provider = await findProvider(input.providerId, input.npi);
  if (!provider) {
    const error = new Error("Not authorized. That provider ID and NPI do not match.");
    error.status = 401;
    throw error;
  }

  const patient = await findPatient(input.patientName, input.patientId);
  if (!patient) {
    const error = new Error("Patient not found.");
    error.status = 404;
    throw error;
  }

  if (!files.length) {
    const error = new Error("Upload at least one PDF.");
    error.status = 400;
    throw error;
  }

  const merged = mergeCharts(pdfCharts);
  const primaryDiagnosis =
    merged.diagnoses.find((row) => row.icd10_code && row.diagnosis_type === "PRIMARY") ||
    merged.diagnoses.find((row) => row.icd10_code);
  if (!primaryDiagnosis) {
    const error = new Error("The PDF does not include a diagnosis, so a prior authorization cannot be filed.");
    error.status = 400;
    throw error;
  }
  const prior = merged.prior_authorization;
  if (!prior?.cpt_code) {
    const error = new Error("The PDF does not include a CPT code, so a prior authorization cannot be filed.");
    error.status = 400;
    throw error;
  }

  const icd10Code = primaryDiagnosis.icd10_code;
  const cptCode = prior.cpt_code;
  const diagnosisType = ["PRIMARY", "SECONDARY"].includes(primaryDiagnosis.diagnosis_type)
    ? primaryDiagnosis.diagnosis_type
    : "PRIMARY";
  const diagnosisDate = requireDate(primaryDiagnosis.diagnosis_date, "Diagnosis date");
  const requestType = ["INITIAL", "RENEWAL"].includes(clean(prior.request_type)) ? clean(prior.request_type) : "INITIAL";
  const urgency = clean(prior.urgency) === "URGENT" ? "URGENT" : "STANDARD";
  const unitsNumber = Number(prior.units_requested);
  const units = Number.isInteger(unitsNumber) && unitsNumber >= 1 ? unitsNumber : 1;
  const requestedDate = requireDate(prior.requested_date, "Requested date") || today();
  const requestedStartDate = requireDate(prior.requested_start_date, "Requested start date") || requestedDate;

  const conn = await pool.getConnection();
  try {
    await ensureSocialHistoryCanStack(conn);
    await conn.beginTransaction();

    const [plans] = await conn.query(
      `SELECT patient_insurance_id, member_id
       FROM patient_insurance
       WHERE patient_id = ?`,
      [patient.patient_id]
    );
    const memberId = clean(merged.member_id);
    let insuranceId = null;
    if (!plans.length) {
      const error = new Error("Patient found, but no insurance is on file, so a prior authorization cannot be filed.");
      error.status = 400;
      throw error;
    } else if (memberId) {
      const match = plans.find((plan) => String(plan.member_id).toLowerCase() === memberId.toLowerCase());
      if (!match) {
        const error = new Error("The PDF member ID is not on this patient's insurance.");
        error.status = 400;
        throw error;
      }
      insuranceId = match.patient_insurance_id;
    } else if (plans.length === 1) {
      insuranceId = plans[0].patient_insurance_id;
    } else {
      const error = new Error("This patient has more than one insurance plan, and the PDF does not include a member ID.");
      error.status = 400;
      throw error;
    }

    await ensureLookup(
      conn,
      "cpt_codes",
      "cpt_code",
      "description",
      cptCode,
      clean(prior.cpt_description),
      "CPT code"
    );

    const diagnosisIds = new Map();
    for (const row of merged.diagnoses) {
      if (!row.icd10_code) continue;
      const type = ["PRIMARY", "SECONDARY"].includes(row.diagnosis_type) ? row.diagnosis_type : "PRIMARY";
      const date = requireDate(row.diagnosis_date, "Diagnosis date");
      let diagnosisId = await existingId(
        conn,
        `SELECT diagnosis_id AS id FROM diagnoses
         WHERE patient_id = ? AND icd10_code = ? AND diagnosis_type = ? AND diagnosis_date <=> ?
         LIMIT 1`,
        [patient.patient_id, row.icd10_code, type, date]
      );
      if (!diagnosisId) {
        await ensureLookup(
          conn,
          "icd10_codes",
          "icd10_code",
          "description",
          row.icd10_code,
          clean(row.icd10_description),
          "ICD-10 code"
        );
        const [inserted] = await conn.query(
          `INSERT INTO diagnoses
            (patient_id, provider_id, icd10_code, diagnosis_type, diagnosis_date, clinical_notes)
           VALUES (?, ?, ?, ?, ?, ?)`,
          [patient.patient_id, provider.provider_id, row.icd10_code, type, date, clean(row.clinical_notes)]
        );
        diagnosisId = inserted.insertId;
      }
      diagnosisIds.set(`${row.icd10_code}|${type}|${date || ""}`, diagnosisId);
    }

    const primaryDiagnosisId =
      diagnosisIds.get(`${icd10Code}|${diagnosisType}|${diagnosisDate || ""}`) ||
      [...diagnosisIds.values()][0];

    for (const row of merged.allergies) {
      if (!row.allergen) continue;
      const found = await existingId(
        conn,
        `SELECT allergy_id AS id FROM allergies
         WHERE patient_id = ? AND LOWER(allergen) = LOWER(?) AND reaction <=> ?
         LIMIT 1`,
        [patient.patient_id, row.allergen, clean(row.reaction)]
      );
      if (!found) {
        await conn.query(
          `INSERT INTO allergies (patient_id, allergen, reaction) VALUES (?, ?, ?)`,
          [patient.patient_id, row.allergen, clean(row.reaction)]
        );
      }
    }

    for (const row of merged.medications) {
      if (!row.drug_name) continue;
      const status = ["ACTIVE", "DISCONTINUED"].includes(row.status) ? row.status : "ACTIVE";
      const start = requireDate(row.start_date, "Medication start date");
      const found = await existingId(
        conn,
        `SELECT medication_id AS id FROM medications
         WHERE patient_id = ? AND LOWER(drug_name) = LOWER(?) AND dosage <=> ? AND start_date <=> ?
         LIMIT 1`,
        [patient.patient_id, row.drug_name, clean(row.dosage), start]
      );
      if (!found) {
        await conn.query(
          `INSERT INTO medications
            (patient_id, prescribing_provider_id, drug_name, dosage, frequency, status, start_date, end_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
          [
            patient.patient_id,
            provider.provider_id,
            row.drug_name,
            clean(row.dosage),
            clean(row.frequency),
            status,
            start,
            requireDate(row.end_date, "Medication end date"),
          ]
        );
      }
    }

    for (const row of merged.surgical_history) {
      if (!row.procedure_name) continue;
      const procedureDate = requireDate(row.procedure_date, "Procedure date");
      const found = await existingId(
        conn,
        `SELECT surgery_id AS id FROM surgical_history
         WHERE patient_id = ? AND LOWER(procedure_name) = LOWER(?) AND procedure_date <=> ?
         LIMIT 1`,
        [patient.patient_id, row.procedure_name, procedureDate]
      );
      if (!found) {
        await conn.query(
          `INSERT INTO surgical_history (patient_id, procedure_name, procedure_date) VALUES (?, ?, ?)`,
          [patient.patient_id, row.procedure_name, procedureDate]
        );
      }
    }

    for (const row of merged.family_history) {
      if (!row.relation || !row.condition_desc) continue;
      const found = await existingId(
        conn,
        `SELECT family_history_id AS id FROM family_history
         WHERE patient_id = ? AND LOWER(relation) = LOWER(?) AND LOWER(condition_desc) = LOWER(?)
         LIMIT 1`,
        [patient.patient_id, row.relation, row.condition_desc]
      );
      if (!found) {
        await conn.query(
          `INSERT INTO family_history (patient_id, relation, condition_desc) VALUES (?, ?, ?)`,
          [patient.patient_id, row.relation, row.condition_desc]
        );
      }
    }

    for (const row of merged.social_history) {
      const found = await existingId(
        conn,
        `SELECT social_history_id AS id FROM social_history
         WHERE patient_id = ? AND smoking_status <=> ? AND alcohol_use <=> ? AND occupation <=> ?
         LIMIT 1`,
        [patient.patient_id, clean(row.smoking_status), clean(row.alcohol_use), clean(row.occupation)]
      );
      if (!found) {
        await conn.query(
          `INSERT INTO social_history (patient_id, smoking_status, alcohol_use, occupation) VALUES (?, ?, ?, ?)`,
          [patient.patient_id, clean(row.smoking_status), clean(row.alcohol_use), clean(row.occupation)]
        );
      }
    }

    for (const row of merged.previous_treatments) {
      if (!row.treatment_type) continue;
      const start = requireDate(row.start_date, "Treatment start date");
      const found = await existingId(
        conn,
        `SELECT treatment_id AS id FROM previous_treatments
         WHERE patient_id = ? AND LOWER(treatment_type) = LOWER(?) AND description <=> ? AND start_date <=> ?
         LIMIT 1`,
        [patient.patient_id, row.treatment_type, clean(row.description), start]
      );
      if (!found) {
        const relatedId = row.related_icd10_code
          ? await existingId(
              conn,
              `SELECT diagnosis_id AS id FROM diagnoses
               WHERE patient_id = ? AND icd10_code = ?
               ORDER BY diagnosis_id DESC LIMIT 1`,
              [patient.patient_id, row.related_icd10_code]
            )
          : primaryDiagnosisId;
        await conn.query(
          `INSERT INTO previous_treatments
            (patient_id, related_diagnosis_id, treatment_type, description, start_date, end_date, outcome)
           VALUES (?, ?, ?, ?, ?, ?, ?)`,
          [
            patient.patient_id,
            relatedId,
            row.treatment_type,
            clean(row.description),
            start,
            requireDate(row.end_date, "Treatment end date"),
            clean(row.outcome),
          ]
        );
      }
    }

    let paId = await existingId(
      conn,
      `SELECT pa.pa_id AS id
       FROM prior_authorizations pa
       JOIN diagnoses d ON d.diagnosis_id = pa.diagnosis_id
       WHERE pa.patient_insurance_id = ? AND pa.cpt_code = ? AND pa.request_type = ?
         AND pa.requested_date = ? AND d.icd10_code = ?
       LIMIT 1`,
      [insuranceId, cptCode, requestType, requestedDate, icd10Code]
    );
    if (!paId) {
      const [paInsert] = await conn.query(
        `INSERT INTO prior_authorizations
          (patient_insurance_id, requesting_provider_id, diagnosis_id, cpt_code, request_type, urgency,
           units_requested, requested_date, requested_start_date, current_status)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNDER_REVIEW')`,
        [
          insuranceId,
          provider.provider_id,
          primaryDiagnosisId,
          cptCode,
          requestType,
          urgency,
          units,
          requestedDate,
          requestedStartDate,
        ]
      );
      paId = paInsert.insertId;
      await conn.query(
        `INSERT INTO pa_status_history (pa_id, status, status_date, notes)
         VALUES (?, 'SUBMITTED', NOW(), 'Submitted by the requesting provider')`,
        [paId]
      );
    }

    const letter = merged.medical_necessity_letter;
    if (letter?.letter_text) {
      const letterDate = requireDate(letter.letter_date, "Letter date") || requestedDate;
      const letterFound = await existingId(
        conn,
        `SELECT letter_id AS id FROM medical_necessity_letters
         WHERE pa_id = ? AND letter_date = ? AND letter_text = ?
         LIMIT 1`,
        [paId, letterDate, letter.letter_text]
      );
      if (!letterFound) {
        await conn.query(
          `INSERT INTO medical_necessity_letters (pa_id, provider_id, letter_date, letter_text)
           VALUES (?, ?, ?, ?)`,
          [paId, provider.provider_id, letterDate, letter.letter_text]
        );
      }
    }

    for (const file of files) {
      const typeName = DOCUMENT_TYPES.includes(file.documentType) ? file.documentType : "PA_FORM";
      const [types] = await conn.query(
        `SELECT document_type_id FROM document_types WHERE type_name = ? LIMIT 1`,
        [typeName]
      );
      if (!types.length) {
        const error = new Error("That document type is not in the database.");
        error.status = 400;
        throw error;
      }
      const filePath = `uploads/${file.filename}`.replace(/\\/g, "/");
      await conn.query(
        `INSERT INTO pa_documents (pa_id, document_type_id, file_path, uploaded_date, extracted_at)
         VALUES (?, ?, ?, NOW(), NULL)`,
        [paId, types[0].document_type_id, filePath]
      );
    }

    await conn.commit();
    return { paId, provider, patientId: patient.patient_id, chart: merged };
  } catch (error) {
    await conn.rollback();
    throw error;
  } finally {
    conn.release();
  }
}

module.exports = {
  DOCUMENT_TYPES,
  findProvider,
  loadPatientForDoctor,
  createAuthorization,
};
