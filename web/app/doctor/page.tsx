"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { SyntheticBadge } from "@/components/pa/StatusBadge";

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
  return /^\d{4,5}[A-Z]?$/i.test(c) || /^[A-Z]\d{4}$/i.test(c);
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
  const fromPolicy = search.get("from_policy");

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
      setPatientId(mitchell?.id || people.patients[0]?.id || "");
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
          // Keep insurer/plan aligned with the prefilled service (avoids UHC + Northwind CPT mismatch).
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
      if (first) {
        setInsurer(first.insurer);
        setPlanKey(pickPlanKey(first));
      }
      setLoaded(true);
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
      <h1 className="title">Order</h1>
      <p className="muted">
        Choose the patient&apos;s insurance company and plan first. Questionnaires and PA rules come only from that live plan.
      </p>
      {fromPolicy && (
        <p className="badge green" style={{ marginTop: 8 }}>
          Questionnaires confirmed from the policy library. Confirm insurance below, pick a service, then start the order.
        </p>
      )}
      {error && <p className="badge amber">{error} <button className="btn secondary" type="button" onClick={load}>Retry</button></p>}
      {loaded && plans.length === 0 && !error && <p>No live policies yet. Upload one in the policy library and Go live.</p>}
      <form className="card" onSubmit={submit} style={{ display: "grid", gap: 12, maxWidth: 640 }}>
        <label className="field">Patient
          <select value={patientId} onChange={(e) => setPatientId(e.target.value)} required>
            {patients.map((patient) => <option key={patient.id} value={patient.id}>{patient.full_name}</option>)}
          </select>
        </label>
        {patients.find((p) => p.id === patientId)?.synthetic && <SyntheticBadge />}
        <label className="field">Ordering clinician
          <select value={providerId} onChange={(e) => setProviderId(e.target.value)} required>
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.full_name}{provider.specialty ? ` · ${provider.specialty}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="field">Insurance company
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
            {insurers.map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <label className="field">Insurance plan
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
              return <option key={key} value={key}>{plan.plan_name} · {plan.plan_year || "—"}</option>;
            })}
          </select>
        </label>
        {selectedPlan && (
          <p className="muted">
            Questionnaires for this order come only from {selectedPlan.insurer} / {selectedPlan.plan_name}
            ({serviceOptions.length} live service rows
            {serviceOptions.filter((o) => o.code).length
              ? `, ${serviceOptions.filter((o) => o.code).length} with a service code`
              : ", no CPT/HCPCS codes in this plan’s live rows"}
            ).
          </p>
        )}
        <label className="field">Service from this plan
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
              setCode(opt.code);
            }}
            disabled={!selectedPlan}
          >
            <option value="">Choose or type below</option>
            {serviceOptions.map((opt) => (
              <option key={opt.key} value={opt.key}>
                {opt.code ? `${opt.label} · ${opt.code}` : opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">Order text
          <input
            value={order}
            onChange={(e) => setOrder(e.target.value)}
            required
            placeholder="Service description"
          />
        </label>
        <label className="field">Service code
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Optional CPT"
          />
        </label>
        <label className="field">Drug (optional — does not change service or code)
          <select value={drug} onChange={(e) => setDrug(e.target.value)}>
            <option value="">None</option>
            {drugs.map((item) => <option key={item.label} value={item.label}>{item.label}</option>)}
          </select>
        </label>
        <button className="btn" disabled={busy || !selectedPlan || !insurer || !order.trim()}>
          {busy ? "Checking..." : "Start order / open questionnaires for this plan"}
        </button>
      </form>
    </main>
  );
}
