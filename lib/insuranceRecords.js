const { pool } = require("./db");

async function loadPayerDashboard(payerId) {
  const id = String(payerId ?? "").trim();
  if (!/^\d+$/.test(id)) return null;

  const [payers] = await pool.query(
    `SELECT payer_id, name, payer_code, pa_dept_phone, pa_dept_fax
     FROM payers
     WHERE payer_id = ?
     LIMIT 1`,
    [id]
  );
  if (!payers.length) return null;

  const [members, requests, monthly, appeals] = await Promise.all([
    pool.query(
      `SELECT p.first_name, p.last_name, pi.member_id, pi.group_number,
              pi.effective_date, pi.termination_date,
              COUNT(pa.pa_id) AS request_count,
              SUM(pa.current_status IN ('SUBMITTED', 'UNDER_REVIEW')) AS open_requests
       FROM patient_insurance pi
       JOIN patients p ON p.patient_id = pi.patient_id
       LEFT JOIN prior_authorizations pa ON pa.patient_insurance_id = pi.patient_insurance_id
       WHERE pi.payer_id = ?
       GROUP BY pi.patient_insurance_id, p.first_name, p.last_name, pi.member_id,
                pi.group_number, pi.effective_date, pi.termination_date
       ORDER BY p.last_name, p.first_name, pi.member_id`,
      [id]
    ),
    pool.query(
      `SELECT pa.pa_id, pa.current_status, pa.urgency, pa.request_type, pa.units_requested,
              pa.requested_date, pa.requested_start_date,
              c.description AS service_description,
              pi.member_id, pi.group_number,
              p.first_name, p.last_name,
              pr.first_name AS provider_first_name, pr.last_name AS provider_last_name,
              cs.deductible_amount, cs.copay_amount, cs.coinsurance_pct, cs.total_patient_responsibility
       FROM prior_authorizations pa
       JOIN patient_insurance pi ON pi.patient_insurance_id = pa.patient_insurance_id
       JOIN patients p ON p.patient_id = pi.patient_id
       LEFT JOIN cpt_codes c ON c.cpt_code = pa.cpt_code
       LEFT JOIN providers pr ON pr.provider_id = pa.requesting_provider_id
       LEFT JOIN (
         SELECT pa_id,
                SUM(deductible_amount) AS deductible_amount,
                SUM(copay_amount) AS copay_amount,
                MAX(coinsurance_pct) AS coinsurance_pct,
                SUM(total_patient_responsibility) AS total_patient_responsibility
         FROM patient_cost_shares
         GROUP BY pa_id
       ) cs ON cs.pa_id = pa.pa_id
       WHERE pi.payer_id = ?
       ORDER BY pa.requested_date DESC, pa.pa_id DESC`,
      [id]
    ),
    pool.query(
      `SELECT DATE_FORMAT(pa.requested_date, '%Y-%m') AS month_key,
              COUNT(DISTINCT pi.patient_id) AS patients,
              COUNT(pa.pa_id) AS requests,
              COALESCE(SUM(cs.copay_amount), 0) AS copay,
              COALESCE(SUM(cs.deductible_amount), 0) AS deductible,
              COALESCE(SUM(cs.total_patient_responsibility), 0) AS responsibility
       FROM prior_authorizations pa
       JOIN patient_insurance pi ON pi.patient_insurance_id = pa.patient_insurance_id
       LEFT JOIN (
         SELECT pa_id,
                SUM(copay_amount) AS copay_amount,
                SUM(deductible_amount) AS deductible_amount,
                SUM(total_patient_responsibility) AS total_patient_responsibility
         FROM patient_cost_shares
         GROUP BY pa_id
       ) cs ON cs.pa_id = pa.pa_id
       WHERE pi.payer_id = ?
       GROUP BY month_key
       ORDER BY month_key DESC`,
      [id]
    ),
    pool.query(
      `SELECT a.appeal_status, a.appeal_date, a.decision_date,
              c.description AS service_description,
              pi.member_id, p.first_name, p.last_name
       FROM appeals a
       JOIN prior_authorizations pa ON pa.pa_id = a.pa_id
       JOIN patient_insurance pi ON pi.patient_insurance_id = pa.patient_insurance_id
       JOIN patients p ON p.patient_id = pi.patient_id
       LEFT JOIN cpt_codes c ON c.cpt_code = pa.cpt_code
       WHERE pi.payer_id = ?
       ORDER BY a.appeal_date DESC`,
      [id]
    ),
  ]);

  return {
    payer: payers[0],
    members: members[0],
    requests: requests[0],
    monthly: monthly[0],
    appeals: appeals[0],
  };
}

module.exports = { loadPayerDashboard };
