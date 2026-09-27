const { pool } = require("./db");

function namesMatch(entered, first, last) {
  const tokens = String(entered || "")
    .toLowerCase()
    .replace(/[^a-z\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  const firstName = String(first || "")
    .toLowerCase()
    .replace(/[^a-z]/g, "");
  const lastName = String(last || "")
    .toLowerCase()
    .replace(/[^a-z]/g, "");
  if (!tokens.length || !firstName || !lastName) return false;
  return tokens[0] === firstName && tokens[tokens.length - 1] === lastName;
}

async function findPatient(name, id) {
  const idValue = String(id || "").trim();
  const numericId = /^\d+$/.test(idValue);
  const where = numericId ? "p.patient_id = ? OR LOWER(pi.member_id) = LOWER(?)" : "LOWER(pi.member_id) = LOWER(?)";
  const params = numericId ? [idValue, idValue] : [idValue];

  const [rows] = await pool.query(
    `SELECT DISTINCT p.patient_id, p.first_name, p.last_name, p.dob, p.sex, p.phone, p.address
     FROM patients p
     LEFT JOIN patient_insurance pi ON pi.patient_id = p.patient_id
     WHERE ${where}`,
    params
  );

  const matches = [];
  const seen = new Set();
  for (const row of rows) {
    if (!namesMatch(name, row.first_name, row.last_name) || seen.has(row.patient_id)) continue;
    seen.add(row.patient_id);
    matches.push(row);
  }
  return matches.length === 1 ? matches[0] : null;
}

async function loadDashboard(name, id) {
  const patient = await findPatient(name, id);
  if (!patient) return null;

  const patientId = patient.patient_id;
  const [
    [insurance],
    [diagnoses],
    [allergies],
    [medications],
    [surgeries],
    [familyHistory],
    [socialRows],
    [labs],
    [imaging],
    [treatments],
    [authorizations],
    [history],
    [costs],
    [appeals],
    [documents],
    [letters],
  ] = await Promise.all([
    pool.query(
      `SELECT pi.member_id, pi.group_number, pi.effective_date, pi.termination_date,
              py.name AS payer_name, py.pa_dept_phone, py.pa_dept_fax
       FROM patient_insurance pi
       JOIN payers py ON py.payer_id = pi.payer_id
       WHERE pi.patient_id = ?`,
      [patientId]
    ),
    pool.query(
      `SELECT d.diagnosis_type, d.diagnosis_date, d.clinical_notes, d.icd10_code,
              ic.description AS icd10_description,
              pr.first_name AS provider_first_name, pr.last_name AS provider_last_name, pr.specialty
       FROM diagnoses d
       LEFT JOIN icd10_codes ic ON ic.icd10_code = d.icd10_code
       LEFT JOIN providers pr ON pr.provider_id = d.provider_id
       WHERE d.patient_id = ?
       ORDER BY d.diagnosis_date DESC`,
      [patientId]
    ),
    pool.query(
      `SELECT allergen, reaction FROM allergies WHERE patient_id = ? ORDER BY allergen`,
      [patientId]
    ),
    pool.query(
      `SELECT m.drug_name, m.dosage, m.frequency, m.status, m.start_date, m.end_date,
              pr.first_name AS provider_first_name, pr.last_name AS provider_last_name
       FROM medications m
       LEFT JOIN providers pr ON pr.provider_id = m.prescribing_provider_id
       WHERE m.patient_id = ?
       ORDER BY m.start_date DESC`,
      [patientId]
    ),
    pool.query(
      `SELECT procedure_name, procedure_date
       FROM surgical_history
       WHERE patient_id = ?
       ORDER BY procedure_date DESC`,
      [patientId]
    ),
    pool.query(
      `SELECT relation, condition_desc FROM family_history WHERE patient_id = ?`,
      [patientId]
    ),
    pool.query(
      `SELECT smoking_status, alcohol_use, occupation FROM social_history WHERE patient_id = ?`,
      [patientId]
    ),
    pool.query(
      `SELECT lr.result_value, lr.flag, lr.collected_date,
              tc.test_name, tc.unit, tc.ref_range_low, tc.ref_range_high, lp.panel_name,
              f.name AS facility_name
       FROM lab_results lr
       LEFT JOIN lab_test_catalog tc ON tc.test_code = lr.test_code
       LEFT JOIN lab_panels lp ON lp.panel_id = tc.panel_id
       LEFT JOIN facilities f ON f.facility_id = lr.facility_id
       WHERE lr.patient_id = ?
       ORDER BY lr.collected_date DESC`,
      [patientId]
    ),
    pool.query(
      `SELECT ir.exam_type, ir.exam_date, ir.impression, ir.reading_radiologist,
              c.description AS service_description, f.name AS facility_name
       FROM imaging_reports ir
       LEFT JOIN cpt_codes c ON c.cpt_code = ir.cpt_code
       LEFT JOIN facilities f ON f.facility_id = ir.facility_id
       WHERE ir.patient_id = ?
       ORDER BY ir.exam_date DESC`,
      [patientId]
    ),
    pool.query(
      `SELECT t.treatment_type, t.description, t.start_date, t.end_date, t.outcome,
              ic.description AS diagnosis_description
       FROM previous_treatments t
       LEFT JOIN diagnoses d ON d.diagnosis_id = t.related_diagnosis_id
       LEFT JOIN icd10_codes ic ON ic.icd10_code = d.icd10_code
       WHERE t.patient_id = ?
       ORDER BY t.start_date DESC`,
      [patientId]
    ),
    pool.query(
      `SELECT pa.pa_id, pa.request_type, pa.urgency, pa.units_requested,
              pa.requested_date, pa.requested_start_date, pa.current_status,
              c.description AS service_description,
              ic.description AS diagnosis_description,
              pr.first_name AS provider_first_name, pr.last_name AS provider_last_name, pr.specialty,
              py.name AS payer_name
       FROM prior_authorizations pa
       JOIN patient_insurance pi ON pi.patient_insurance_id = pa.patient_insurance_id
       LEFT JOIN cpt_codes c ON c.cpt_code = pa.cpt_code
       LEFT JOIN diagnoses d ON d.diagnosis_id = pa.diagnosis_id
       LEFT JOIN icd10_codes ic ON ic.icd10_code = d.icd10_code
       LEFT JOIN providers pr ON pr.provider_id = pa.requesting_provider_id
       LEFT JOIN payers py ON py.payer_id = pi.payer_id
       WHERE pi.patient_id = ?
       ORDER BY pa.requested_date DESC`,
      [patientId]
    ),
    pool.query(
      `SELECT h.pa_id, h.status, h.status_date, h.notes
       FROM pa_status_history h
       JOIN prior_authorizations pa ON pa.pa_id = h.pa_id
       JOIN patient_insurance pi ON pi.patient_insurance_id = pa.patient_insurance_id
       WHERE pi.patient_id = ?
       ORDER BY h.status_date`,
      [patientId]
    ),
    pool.query(
      `SELECT cs.pa_id, cs.deductible_amount, cs.copay_amount, cs.coinsurance_pct, cs.total_patient_responsibility
       FROM patient_cost_shares cs
       JOIN prior_authorizations pa ON pa.pa_id = cs.pa_id
       JOIN patient_insurance pi ON pi.patient_insurance_id = pa.patient_insurance_id
       WHERE pi.patient_id = ?`,
      [patientId]
    ),
    pool.query(
      `SELECT a.pa_id, a.appeal_date, a.additional_info, a.appeal_status, a.decision_date
       FROM appeals a
       JOIN prior_authorizations pa ON pa.pa_id = a.pa_id
       JOIN patient_insurance pi ON pi.patient_insurance_id = pa.patient_insurance_id
       WHERE pi.patient_id = ?
       ORDER BY a.appeal_date DESC`,
      [patientId]
    ),
    pool.query(
      `SELECT doc.pa_id, dt.type_name, doc.uploaded_date
       FROM pa_documents doc
       JOIN document_types dt ON dt.document_type_id = doc.document_type_id
       JOIN prior_authorizations pa ON pa.pa_id = doc.pa_id
       JOIN patient_insurance pi ON pi.patient_insurance_id = pa.patient_insurance_id
       WHERE pi.patient_id = ?
       ORDER BY doc.uploaded_date DESC`,
      [patientId]
    ),
    pool.query(
      `SELECT l.pa_id, l.letter_date
       FROM medical_necessity_letters l
       JOIN prior_authorizations pa ON pa.pa_id = l.pa_id
       JOIN patient_insurance pi ON pi.patient_insurance_id = pa.patient_insurance_id
       WHERE pi.patient_id = ?`,
      [patientId]
    ),
  ]);

  const byPa = (rows) => {
    const map = new Map();
    for (const row of rows) {
      const list = map.get(row.pa_id) || [];
      list.push(row);
      map.set(row.pa_id, list);
    }
    return map;
  };
  const historyByPa = byPa(history);
  const appealsByPa = byPa(appeals);
  const documentsByPa = byPa(documents);
  const lettersByPa = byPa(letters);
  const costByPa = new Map(costs.map((row) => [row.pa_id, row]));

  return {
    patient: {
      patientId: patient.patient_id,
      firstName: patient.first_name,
      lastName: patient.last_name,
      dob: patient.dob,
      sex: patient.sex,
      phone: patient.phone,
      address: patient.address,
    },
    insurance,
    diagnoses,
    allergies,
    medications,
    surgeries,
    familyHistory,
    socialHistory: socialRows,
    labs,
    imaging,
    treatments,
    priorAuthorizations: authorizations.map((pa) => ({
      ...pa,
      history: historyByPa.get(pa.pa_id) || [],
      cost: costByPa.get(pa.pa_id) || null,
      appeals: appealsByPa.get(pa.pa_id) || [],
      documents: documentsByPa.get(pa.pa_id) || [],
      letterOnFile: (lettersByPa.get(pa.pa_id) || []).length > 0,
      letterDate: (lettersByPa.get(pa.pa_id) || [])[0]?.letter_date || null,
    })),
  };
}

module.exports = { findPatient, loadDashboard };
