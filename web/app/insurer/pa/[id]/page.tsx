"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { ReadinessBar, StatusBadge } from "@/components/pa/StatusBadge";

type Question = {
  id: string;
  text: string;
  value?: unknown;
  evidence_text?: string;
  review_state?: string;
};

type Criterion = {
  id: string;
  requirement_text: string;
  status: string;
  origin?: string;
  policy_page?: number;
  questions: Question[];
  verified_by?: { full_name?: string } | null;
};

type View = {
  id: string;
  status: string;
  readiness: number;
  met_count: number;
  total_count: number;
  order_text: string;
  service_code?: string;
  service_category?: string;
  insurer?: string;
  plan_name?: string;
  plan_year?: string;
  patient: { id: string; full_name: string; dob?: string };
  ordering_provider: { full_name: string; specialty?: string };
  criteria: Criterion[];
  events: { event_type?: string; message?: string; created_at?: string; actor?: string }[];
  criteria_source?: { title?: string; insurer?: string } | null;
  pa_determination?: { requirement: string; label: string; pa_required: boolean | null; page?: number | null; evidence_text?: string | null } | null;
  coverage?: { pa_required?: boolean; pa_status?: string; evidence_text?: string | null; page?: number | null; service_label?: string | null } | null;
  questionnaire?: { title?: string; item?: { linkId: string; text?: string; item?: { linkId: string; text?: string }[] }[] } | null;
  questionnaire_response?: { status?: string; item?: { linkId?: string; item?: { linkId?: string; answer?: unknown[] }[] }[] } | null;
};

export default function InsurerPaPage() {
  const params = useParams<{ id: string }>();
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [packet, setPacket] = useState("");
  const [chart, setChart] = useState("");
  const [busy, setBusy] = useState("");

  function load() {
    setError("");
    api<View>(`/pa/${params.id}`)
      .then(setView)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load this request"));
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [params.id]);

  async function act(path: string, body?: object) {
    setBusy(path);
    setError("");
    try {
      const data = await api<View>(path, { method: "POST", body: JSON.stringify(body || {}) });
      setView(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The action failed");
    } finally {
      setBusy("");
    }
  }

  if (!view && !error) return <main><p className="muted">Loading insurer review...</p></main>;
  if (!view) {
    return (
      <main>
        <p className="badge amber">{error}</p>
        <Link className="btn secondary" href="/insurer">Back to queue</Link>
      </main>
    );
  }

  const canDecide = view.status === "submitted" || view.status === "in_review";

  return (
    <main>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <p className="muted"><Link href="/insurer">Insurer review</Link> | packet</p>
          <h1 className="title">{view.patient.full_name} | {view.order_text}</h1>
          <p className="muted">
            {[view.ordering_provider.full_name, view.ordering_provider.specialty, view.service_code, view.criteria_source?.title].filter(Boolean).join(" | ")}
          </p>
        </div>
        <StatusBadge status={view.status} />
      </div>
      {error && <p className="badge amber" style={{ marginTop: 8 }}>{error}</p>}
      <div style={{ marginTop: 12 }}>
        <ReadinessBar met={view.met_count} total={view.total_count} readiness={view.readiness} />
      </div>

      {view.pa_determination && (
        <section className="card" style={{ marginTop: 12, borderColor: view.pa_determination.pa_required ? "#c9a227" : undefined }}>
          <p className="title">PA determination for this treatment</p>
          <p><strong>{view.pa_determination.label}</strong></p>
          <p className="muted">
            {[view.insurer, view.plan_name, view.plan_year].filter(Boolean).join(" | ")}
            {view.service_category || view.order_text ? ` | ${view.service_category || view.order_text}` : ""}
            {view.service_code ? ` (${view.service_code})` : ""}
            {view.pa_determination.requirement ? ` | ${view.pa_determination.requirement}` : ""}
            {view.pa_determination.page ? ` | coverage p.${view.pa_determination.page}` : ""}
          </p>
          {view.pa_determination.evidence_text && (
            <p className="quote" style={{ marginTop: 8 }}>{view.pa_determination.evidence_text}</p>
          )}
        </section>
      )}

      {view.status === "approved" && (
        <p className="badge green" style={{ marginTop: 12 }}>
          Approved. The decision is on the clinician request timeline and in the patient chart export.
        </p>
      )}
      {view.status === "info_requested" && (
        <p className="badge amber" style={{ marginTop: 12 }}>
          Waiting for the ordering clinician to upload evidence and resubmit. This page refreshes when they do.
        </p>
      )}

      <section style={{ marginTop: 16 }}>
        <p className="title">Doctor questionnaire</p>
        <p className="muted">
          Clinical questions the ordering clinician answered for this order (order-scoped). Re-check confirms PA is still required before you decide.
        </p>
        {view.questionnaire && (view.questionnaire.item || []).length > 0 && (
          <div className="card" style={{ marginTop: 8 }}>
            <p className="muted">{view.questionnaire.title || "FHIR Questionnaire"}</p>
            {(view.questionnaire.item || []).map((group) => (
              <div key={group.linkId} style={{ marginTop: 8 }}>
                <p>{group.text || group.linkId}</p>
                {(group.item || []).map((q) => (
                  <p key={q.linkId} className="muted" style={{ marginLeft: 8 }}>{q.text || q.linkId}</p>
                ))}
              </div>
            ))}
          </div>
        )}
        {view.criteria.map((criterion) => (
          <article key={criterion.id} className="card" style={{ marginTop: 8 }}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <p className="title">{criterion.requirement_text}</p>
              <StatusBadge status={criterion.status} />
            </div>
            <p className="muted">
              {criterion.origin === "insurer_request" ? "Insurer evidence request | " : ""}
              {criterion.policy_page ? `Policy p.${criterion.policy_page} | ` : ""}
              {criterion.verified_by?.full_name ? `Verified by ${criterion.verified_by.full_name}` : "Not verified"}
            </p>
            {criterion.questions.map((question) => (
              <div key={question.id} style={{ marginTop: 8 }}>
                <p>{question.text}</p>
                <p className="muted">Answer: {String(question.value ?? "-")} | {question.review_state}</p>
                {question.evidence_text && <p className="muted">&quot;{question.evidence_text}&quot;</p>}
              </div>
            ))}
          </article>
        ))}
        {view.criteria.length === 0 && (
          <p className="muted" style={{ marginTop: 8 }}>No questionnaire items on this packet yet.</p>
        )}
      </section>

      {canDecide && (
        <section className="card" style={{ marginTop: 16 }}>
          <p className="title">Insurer decision</p>
          <p className="muted">Approve when the packet is sufficient, or ask for additional evidence. There is no deny action here (G1).</p>
          <button
            type="button"
            className="btn secondary"
            style={{ marginTop: 8 }}
            disabled={!!busy}
            onClick={async () => {
              try {
                const rule = await api<{ requirement?: string; condition_notes?: string }>(`/pa-requests/${view.id}/pa-required`);
                setNote((n) => n || (rule.condition_notes ? `Re-check: ${rule.requirement}. ${rule.condition_notes}` : `Re-check: ${rule.requirement}`));
              } catch (err) {
                setError(err instanceof Error ? err.message : "PA re-check failed");
              }
            }}
          >
            Re-check PA required
          </button>
          <label className="field" style={{ marginTop: 8 }}>
            Note to clinician (optional for approve; used as the evidence request text)
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
          </label>
          <div className="row" style={{ marginTop: 10 }}>
            <button
              type="button"
              className="btn"
              disabled={!!busy}
              onClick={() => act(`/pa-requests/${view.id}/decision`, { action: "approve", note: note || null })}
            >
              {busy.includes("decision") || busy.includes("approve") ? "Approving..." : "Approve"}
            </button>
            <button
              type="button"
              className="btn secondary"
              disabled={!!busy}
              onClick={() => act(`/pa-requests/${view.id}/decision`, { action: "request_info", note: note || null })}
            >
              {busy.includes("request") ? "Sending..." : "Ask for additional evidence"}
            </button>
          </div>
        </section>
      )}

      <section className="row" style={{ marginTop: 16, gap: 8 }}>
        <button
          type="button"
          className="btn secondary"
          onClick={async () => {
            try {
              setPacket(JSON.stringify(await api(`/pa/${view.id}/packet`), null, 2));
            } catch (err) {
              setError(err instanceof Error ? err.message : "Packet unavailable");
            }
          }}
        >
          Show submission packet
        </button>
        <button
          type="button"
          className="btn secondary"
          onClick={async () => {
            try {
              setChart(JSON.stringify(await api(`/patients/${view.patient.id}/chart`), null, 2));
            } catch (err) {
              setError(err instanceof Error ? err.message : "Chart unavailable");
            }
          }}
        >
          Patient chart JSON
        </button>
        <Link className="btn secondary" href={`/doctor/pa/${view.id}`}>Open clinician view</Link>
      </section>

      {packet && <pre className="card" style={{ marginTop: 12, overflow: "auto", fontSize: 12, maxHeight: 320 }}>{packet}</pre>}
      {chart && <pre className="card" style={{ marginTop: 12, overflow: "auto", fontSize: 12, maxHeight: 320 }}>{chart}</pre>}

      <section style={{ marginTop: 16 }}>
        <p className="title">Timeline</p>
        {(view.events || []).slice().reverse().map((event, index) => (
          <p key={`${event.created_at}-${index}`} className="muted">
            {event.created_at} | {event.actor || "system"} | {event.message || event.event_type}
          </p>
        ))}
      </section>
    </main>
  );
}
