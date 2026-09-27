"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

type Patient = { id: string; full_name: string; synthetic: boolean };
type Provider = { id: string; full_name: string; specialty?: string };
type Plan = { insurer: string; plan_name: string; plan_year: string; benefit_summary_id?: string };
type Service = {
  label: string;
  codes: string[];
  kind: string;
  insurer?: string;
  plan_name?: string;
  plan_year?: string;
};

type ServiceOption = { key: string; label: string; code: string };

function looksLikeServiceCode(value: string): boolean {
  const c = value.trim();
  // CPT (digits), HCPCS Level II (letter+4), CDT (D####)
  return (
    /^\d{4,5}[A-Z]?$/i.test(c) ||
    /^[A-Z]\d{4}$/i.test(c) ||
    /^D\d{4}$/i.test(c)
  );
}

function codeFromLabel(label: string): string {
  const paren = label.match(/\((\d{4,5}[A-Z]?)\)/i);
  if (paren) return paren[1];
  const bare = label.match(/\b(\d{5})\b/);
  return bare ? bare[1] : "";
}

function yearsMatch(serviceYear?: string | null, planYear?: string | null): boolean {
  const a = serviceYear ?? "";
  const b = planYear ?? "";
  if (!a || !b) return true;
  return a === b;
}

/** Prefer CPT/HCPCS, else first catalog code (pre-drug-fix behavior), else code in the label. */
function pickCodeForRow(row: Service): string {
  const codes = (row.codes || []).map(String).map((c) => c.trim()).filter(Boolean);
  const cpt = codes.find(looksLikeServiceCode);
  if (cpt) return cpt;
  if (codes[0]) return codes[0];
  return codeFromLabel(row.label || "");
}

function resolveServiceCode(label: string, rows: Service[]): string {
  if (!label) return "";
  const matches = rows.filter((s) => s.label === label);
  const ordered = [
    ...matches.filter((s) => s.kind === "coverage"),
    ...matches.filter((s) => s.kind !== "coverage"),
  ];
  for (const row of ordered) {
    const code = pickCodeForRow(row);
    if (code) return code;
  }
  return codeFromLabel(label);
}

export default function OrderPage() {
  const router = useRouter();
  const search = useSearchParams();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [drugs, setDrugs] = useState<{ label: string }[]>([]);
  const [patientId, setPatientId] = useState("");
  const [providerId, setProviderId] = useState("");
  const [insurer, setInsurer] = useState("");
  const [planKey, setPlanKey] = useState("");
  const [order, setOrder] = useState("");
  const [code, setCode] = useState("");
  const [drug, setDrug] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [uploadNote, setUploadNote] = useState("");
  const [sourceUploadId, setSourceUploadId] = useState("");
  const [clinicalNotes, setClinicalNotes] = useState("");
  const fromPolicy = search.get("from_policy");
  const uploadId = search.get("upload_id");

  const insurers = useMemo(
    () => [...new Set(plans.map((p) => p.insurer).filter(Boolean))].sort(),
    [plans],
  );
  const plansForInsurer = useMemo(
    () => plans.filter((p) => !insurer || p.insurer === insurer),
    [plans, insurer],
  );
  const selectedPlan = useMemo(() => {
    if (!planKey) return null;
    const [i, n, y] = planKey.split("|");
    // Never keep a plan from a different insurer (dropdown value can look blank while state is stale).
    if (insurer && i !== insurer) return null;
    return plans.find((p) => p.insurer === i && p.plan_name === n && p.plan_year === y) || null;
  }, [plans, planKey, insurer]);
  const servicesForPlan = useMemo(() => {
    if (!selectedPlan) return [];
    return services.filter(
      (s) =>
        s.insurer === selectedPlan.insurer &&
        s.plan_name === selectedPlan.plan_name &&
        yearsMatch(s.plan_year, selectedPlan.plan_year),
    );
  }, [services, selectedPlan]);
  /** One option per label, using the best code available for that label on this plan. */
  const serviceOptions = useMemo(() => {
    const ordered = [
      ...servicesForPlan.filter((s) => s.kind === "coverage"),
      ...servicesForPlan.filter((s) => s.kind !== "coverage"),
    ];
    const best = new Map<string, ServiceOption>();
    for (const row of ordered) {
      if (!row.label) continue;
      const code = pickCodeForRow(row);
      const prev = best.get(row.label);
      if (!prev) {
        best.set(row.label, { key: row.label, label: row.label, code });
        continue;
      }
      // Prefer a real CPT/HCPCS over empty or non-code placeholders.
      if (!prev.code && code) best.set(row.label, { key: row.label, label: row.label, code });
      else if (code && looksLikeServiceCode(code) && !looksLikeServiceCode(prev.code)) {
        best.set(row.label, { key: row.label, label: row.label, code });
      }
    }
    return [...best.values()].sort((a, b) => a.label.localeCompare(b.label));
  }, [servicesForPlan]);
  const selectedServiceKey =
    serviceOptions.find((o) => o.label === order && o.code === code)?.key ||
    serviceOptions.find((o) => o.label === order)?.key ||
    "";
  const selectedServiceOption = serviceOptions.find((o) => o.key === selectedServiceKey) || null;

  // If the dropdown shows a coded service but the code field is empty/stale, sync it.
  useEffect(() => {
    if (!selectedServiceOption?.code) return;
    if (code === selectedServiceOption.code) return;
    if (order === selectedServiceOption.label) setCode(selectedServiceOption.code);
  }, [selectedServiceOption, order, code]);

  function pickPlanKey(plan: Plan | undefined): string {
    if (!plan) return "";
    return `${plan.insurer}|${plan.plan_name}|${plan.plan_year}`;
  }

  function load() {
    setError("");
    Promise.all([
      api<{ patients: Patient[] }>("/patients"),
      api<{ providers: Provider[] }>("/providers"),
      api<{ insurers: Plan[]; services: Service[]; drugs: { label: string }[] }>("/policies"),
    ]).then(([people, clinicians, catalog]) => {
      setPatients(people.patients);
      setProviders(clinicians.providers);
      setPlans(catalog.insurers);
      setServices(catalog.services);
      setDrugs(catalog.drugs);
      const mitchell = people.patients.find((p) => /mitchell/i.test(p.full_name));
      const anderson = clinicians.providers.find((p) => /anderson/i.test(p.full_name));
      setProviderId(anderson?.id || clinicians.providers[0]?.id || "");
      const qInsurer = search.get("insurer");
      const qPlan = search.get("plan_name");
      const qYear = search.get("plan_year");
      const fromQuery = catalog.insurers.find(
        (p) =>
          (!qInsurer || p.insurer === qInsurer) &&
          (!qPlan || p.plan_name === qPlan) &&
          (!qYear || p.plan_year === qYear),
      );
      const northwind = catalog.insurers.find((p) => /northwind/i.test(p.insurer || ""));
      let first = fromQuery || northwind || catalog.insurers[0];

      if (!uploadId) {
        setPatientId(mitchell?.id || people.patients[0]?.id || "");
        if (mitchell) {
          const mri =
            catalog.services.find(
              (s) =>
                /mri/i.test(s.label || "") &&
                /lumbar/i.test(s.label || "") &&
                (!first || s.insurer === first.insurer),
            ) ||
            catalog.services.find((s) => /mri/i.test(s.label || "") && /lumbar/i.test(s.label || ""));
          if (mri?.label) {
            const mriPlan =
              catalog.insurers.find(
                (p) => p.insurer === mri.insurer && p.plan_name === mri.plan_name,
              ) || catalog.insurers.find((p) => p.insurer === mri.insurer);
            if (mriPlan) first = mriPlan;
            setOrder(mri.label);
            setCode(resolveServiceCode(mri.label, catalog.services.filter((s) => s.insurer === mri.insurer)) || "72148");
          } else {
            setOrder("MRI lumbar spine without contrast");
            setCode("72148");
          }
        }
      }

      if (first) {
        setInsurer(first.insurer);
        setPlanKey(pickPlanKey(first));
      }
      setLoaded(true);

      if (uploadId) {
        api<{
          extraction_status: string;
          order_desk: {
            patient_id: string;
            order_text: string;
            service_code: string;
            insurer: string;
            plan_name: string;
            plan_year: string;
            catalog_status: string;
            clinical_notes: string;
            source_upload_id: string;
          };
        }>(`/uploads/${uploadId}`)
          .then((upload) => {
            const desk = upload.order_desk;
            // Refresh patients in case extraction created one.
            api<{ patients: Patient[] }>("/patients").then((fresh) => {
              setPatients(fresh.patients);
              if (desk.patient_id) setPatientId(desk.patient_id);
            });
            // Plan first: the Service dropdown only lists services for the selected plan.
            const resolvedPlan = desk.insurer
              ? catalog.insurers.find(
                  (p) =>
                    p.insurer === desk.insurer &&
                    (!desk.plan_name || p.plan_name === desk.plan_name) &&
                    (!desk.plan_year || p.plan_year === desk.plan_year),
                ) || catalog.insurers.find((p) => p.insurer === desk.insurer)
              : undefined;
            if (resolvedPlan) {
              setInsurer(resolvedPlan.insurer);
              setPlanKey(pickPlanKey(resolvedPlan));
            }
            if (desk.order_text) setOrder(desk.order_text);
            if (desk.service_code) setCode(desk.service_code);
            setClinicalNotes(desk.clinical_notes || "");
            setSourceUploadId(desk.source_upload_id || uploadId);
            const matched = desk.catalog_status === "matched" && !!resolvedPlan;
            setUploadNote(
              matched
                ? "Report extracted and matched to a live plan service. Review the prefilled fields, then run coverage."
                : upload.extraction_status === "failed"
                  ? "Extraction was incomplete. Enter the order manually, then run coverage."
                  : "Report extracted, but the service is not in a live plan catalog yet. Choose the plan and service, then run coverage.",
            );
          })
          .catch((err) => {
            setError(err instanceof Error ? err.message : "Could not load the uploaded report");
          });
      }
    }).catch((err) => setError(err instanceof Error ? err.message : "The catalog could not be loaded"));
  }

  useEffect(() => { load(); }, [search]);

  useEffect(() => {
    if (!insurer || !plansForInsurer.length) return;
    const stillValid = plansForInsurer.some((p) => pickPlanKey(p) === planKey);
    if (!stillValid) setPlanKey(pickPlanKey(plansForInsurer[0]));
  }, [insurer, plansForInsurer, planKey]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const [planInsurer, plan_name, plan_year] = planKey.split("|");
    setBusy(true);
    setError("");
    try {
      const created = await api<{ id: string }>("/pa/check", {
        method: "POST",
        body: JSON.stringify({
          patient_id: patientId,
          ordering_provider_id: providerId,
          insurer: planInsurer,
          plan_name,
          plan_year,
          order_text: order,
          service_code: code || null,
          drug_name: drug || null,
          service_category: order || null,
          source_upload_id: sourceUploadId || null,
          source_document_reference: sourceUploadId ? `upload:${sourceUploadId}` : null,
        }),
      });
      router.push(`/doctor/pa/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The order could not be checked");
      setBusy(false);
    }
  }

  return (
    <main>
      <header className="page-head">
        <p className="kicker">Order desk</p>
        <h1 className="title">New order</h1>
        <p className="lead">Choose the patient, plan, and service. ClearPath checks coverage from live documents.</p>
        <p style={{ marginTop: "0.75rem" }}>
          <Link className="btn secondary" href="/doctor/upload">Upload a patient report first</Link>
        </p>
      </header>
      {uploadNote && (
        <p className="badge green" style={{ marginBottom: "1rem" }}>
          {uploadNote}
        </p>
      )}
      {fromPolicy && (
        <p className="badge green" style={{ marginBottom: "1rem" }}>
          Questionnaires from your live policies are ready to use.
        </p>
      )}
      {error && (
        <p className="badge amber" style={{ marginBottom: "1rem" }}>
          {error}{" "}
          <button className="btn secondary" type="button" onClick={load}>
            Retry
          </button>
        </p>
      )}
      {loaded && plans.length === 0 && !error && (
        <p className="muted">No live plans yet. Upload a published PDF in the policy library first.</p>
      )}
      <form className="card form-card" onSubmit={submit}>
        <label className="field">
          Patient
          <select value={patientId} onChange={(e) => setPatientId(e.target.value)} required>
            {patients.map((patient) => (
              <option key={patient.id} value={patient.id}>
                {patient.full_name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Ordering clinician
          <select value={providerId} onChange={(e) => setProviderId(e.target.value)} required>
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.full_name}
                {provider.specialty ? ` | ${provider.specialty}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Insurance company
          <select
            value={insurer}
            onChange={(e) => {
              const next = e.target.value;
              setInsurer(next);
              setOrder("");
              setCode("");
              const nextPlans = plans.filter((p) => p.insurer === next);
              setPlanKey(pickPlanKey(nextPlans[0]));
            }}
            required
          >
            <option value="">Select insurer</option>
            {insurers.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Insurance plan
          <select
            value={plansForInsurer.some((p) => pickPlanKey(p) === planKey) ? planKey : ""}
            onChange={(e) => {
              setPlanKey(e.target.value);
              setOrder("");
              setCode("");
            }}
            required
            disabled={!insurer}
          >
            <option value="">Select plan</option>
            {plansForInsurer.map((plan) => {
              const key = pickPlanKey(plan);
              return (
                <option key={key} value={key}>
                  {plan.plan_name}
                  {plan.plan_year ? ` | ${plan.plan_year}` : ""}
                </option>
              );
            })}
          </select>
        </label>
        <label className="field">
          Service
          <select
            value={selectedServiceKey}
            onChange={(e) => {
              const opt = serviceOptions.find((o) => o.key === e.target.value);
              if (!opt) {
                setOrder("");
                setCode("");
                return;
              }
              setOrder(opt.label);
              setCode(opt.code || "");
            }}
            disabled={!selectedPlan}
          >
            <option value="">Choose or type below</option>
            {serviceOptions.map((opt) => (
              <option key={opt.key} value={opt.key}>
                {opt.code ? `${opt.label} | ${opt.code}` : opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Order text
          <input
            value={order}
            onChange={(e) => setOrder(e.target.value)}
            required
            placeholder="Service description"
          />
        </label>
        <label className="field">
          Service code
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="CPT / HCPCS / CDT"
          />
        </label>
        <label className="field">
          Drug
          <select value={drug} onChange={(e) => setDrug(e.target.value)}>
            <option value="">Not required</option>
            {drugs.map((item) => (
              <option key={item.label} value={item.label}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        {clinicalNotes && (
          <label className="field">
            Notes from uploaded report
            <textarea value={clinicalNotes} readOnly rows={3} />
          </label>
        )}
        <button className="btn" disabled={busy || !selectedPlan || !insurer || !order.trim()}>
          {busy ? "Running coverage..." : "Run coverage check"}
        </button>
      </form>
    </main>
  );
}
