"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, fileUrl, isNotFound } from "@/lib/api";
import { pretty } from "@/lib/format";
import { ConfidenceBadge, JudgeBadge, ReadinessBar, StatusBadge, SyntheticBadge, ruleConfidence } from "@/components/pa/StatusBadge";

type Question = {
  id: string;
  text: string;
  enabled: boolean;
  value: unknown;
  fill_method?: string | null;
  review_state: string;
  evidence_text?: string | null;
  evidence_source?: { author?: string; date?: string } | null;
  reject_reason?: string | null;
  rejected_ai_value?: unknown;
  attestation?: string | null;
};
type Criterion = {
  id: string;
  requirement_text: string;
  criterion_type: string;
  policy_page: number;
  status: string;
  status_reason?: string | null;
  judge_verdict?: string | null;
  likely_owner?: { full_name: string; reason: string } | null;
  verified_by?: { full_name: string } | null;
  questions: Question[];
};
type RequestView = {
  id: string;
  status: string;
  readiness: number;
  met_count: number;
  total_count: number;
  can_submit: boolean;
  order_text: string;
  service_code?: string;
  service_category?: string;
  insurer?: string;
  plan_name?: string;
  plan_year?: string;
  patient: { id: string; full_name: string; synthetic: boolean };
  ordering_provider: { id: string; full_name: string };
  coverage?: { pa_required: boolean; pa_status?: string; page?: number | null; evidence_text?: string | null; document_url?: string | null; service_label?: string | null } | null;
  pa_determination?: { requirement: string; label: string; pa_required: boolean | null; page?: number | null; evidence_text?: string | null } | null;
  questionnaire?: { resourceType?: string; title?: string; item?: { linkId: string; text?: string; item?: { linkId: string; text?: string; type?: string }[] }[] } | null;
  questionnaire_response?: { resourceType?: string; status?: string; item?: unknown[] } | null;
  criteria_source?: { title?: string; source_kind?: string; policy_id?: string } | null;
  criteria: Criterion[];
  events: { event_type: string; message?: string; actor: string; created_at: string }[];
  match_candidates?: { item_id: string; label: string; page?: number; phrase?: string }[] | null;
};

export default function ChecklistPage() {
  const params = useParams<{ id: string }>();
  const [view, setView] = useState<RequestView | null>(null);
  const [error, setError] = useState("");
  const [missing, setMissing] = useState(false);
  const [latestId, setLatestId] = useState<string | null>(null);
  const [docs, setDocs] = useState<{ id: string; file_name: string; in_chart?: number }[]>([]);
  const [packet, setPacket] = useState("");
  const [active, setActive] = useState<Question | null>(null);

  async function load() {
    const data = await api<RequestView>(`/pa/${params.id}`);
    setView(data);
    setMissing(false);
    const docs = await api<{ documents: { id: string; file_name: string; in_chart?: number }[] }>(`/patients/${data.patient.id}/documents`);
    setDocs(docs.documents);
  }

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    async function markMissing() {
      setMissing(true);
      setView(null);
      try {
        const listed = await api<{ requests: { id: string }[] }>("/pa");
        if (!stop) setLatestId(listed.requests[0]?.id || null);
      } catch {
        if (!stop) setLatestId(null);
      }
    }

    async function pull() {
      try {
        const data = await api<RequestView>(`/pa/${params.id}`);
        if (stop) return;
        setView(data);
        setMissing(false);
        const docs = await api<{ documents: { id: string; file_name: string; in_chart?: number }[] }>(`/patients/${data.patient.id}/documents`);
        if (!stop) setDocs(docs.documents);
        setError("");
        if (!timer && !stop) {
          timer = setInterval(pull, 2500);
        }
      } catch (err) {
        if (stop) return;
        if (isNotFound(err)) {
          if (timer) {
            clearInterval(timer);
            timer = null;
          }
          setError(err instanceof Error ? err.message : "No request with that id.");
          await markMissing();
          return;
        }
        setError(err instanceof Error ? err.message : "Could not load this request");
      }
    }

    pull();
    return () => {
      stop = true;
      if (timer) clearInterval(timer);
    };
  }, [params.id]);

  async function post(path: string, body: object) {
    setError("");
    try {
      const data = await api<RequestView>(path, { method: "POST", body: JSON.stringify(body) });
      setView(data);
      setActive(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "That action failed");
    }
  }

  async function addDocument(documentId: string) {
    if (!view) return;
    const body = new FormData();
    body.set("patient_id", view.patient.id);
    body.set("document_id", documentId);
    await api("/reports/extract", { method: "POST", body });
    const data = await api<RequestView>(`/pa/${view.id}/recheck`, { method: "POST" });
    setView(data);
    setDocs((rows) => rows.map((row) => row.id === documentId ? { ...row, in_chart: 1 } : row));
  }

  if (!view && !error) return <p className="muted">Loading checklist...</p>;
  if (!view) {
    return (
      <main>
        <p className="badge amber">{error || "No request with that id."}</p>
        {missing ? (
          <div className="card" style={{ marginTop: 12, display: "grid", gap: 8, maxWidth: 520 }}>
            <p>This prior-auth id is not in the database (stale tab or DB reset).</p>
            <div className="row">
              <Link className="btn" href="/doctor">Start a new order</Link>
              {latestId && <Link className="btn secondary" href={`/doctor/pa/${latestId}`}>Open latest request</Link>}
            </div>
          </div>
        ) : (
          <button className="btn secondary" onClick={load}>Retry</button>
        )}
      </main>
    );
  }

  return (
    <main>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1 className="title">{view.patient.full_name} {view.patient.synthetic && <SyntheticBadge />}  |  {view.order_text}</h1>
          <p className="muted">{view.ordering_provider.full_name}</p>
        </div>
        <StatusBadge status={view.status} />
      </div>
      {error && <p className="badge amber">{error}</p>}
      {view.status === "draft" && (
        <section className="card" style={{ marginTop: 12 }}>
          <p className="title">Confirm ingested order</p>
          <p className="muted">
            Review the pre-filled patient, plan, and treatment from the extraction JSON, then confirm to run PA determination.
          </p>
          <p style={{ marginTop: 8 }}>
            {[view.insurer, view.plan_name, view.plan_year].filter(Boolean).join(" · ") || "Plan not set"}
          </p>
          <p className="muted">Treatment: {view.service_category || view.order_text}{view.service_code ? ` (${view.service_code})` : ""}</p>
          <button
            className="btn"
            style={{ marginTop: 10 }}
            onClick={() => post(`/pa-requests/${view.id}/confirm`, {
              order_text: view.order_text,
              service_category: view.service_category || view.order_text,
              service_code: view.service_code,
            })}
          >
            Confirm and determine PA
          </button>
        </section>
      )}
      {view.pa_determination && view.status !== "draft" && (
        <p className="card" style={{ marginTop: 12, borderColor: view.pa_determination.pa_required ? "#c9a227" : undefined }}>
          <strong>{view.pa_determination.label}</strong>
          {view.pa_determination.requirement ? `  |  ${view.pa_determination.requirement}` : ""}
          {view.pa_determination.page ? `  |  plan coverage p.${view.pa_determination.page}` : ""}
          {view.pa_determination.evidence_text && (
            <span className="quote" style={{ display: "block" }}>{view.pa_determination.evidence_text}</span>
          )}
        </p>
      )}
      {view.coverage && !view.pa_determination && (
        <p className="card" style={{ marginTop: 12 }}>
          {view.coverage.pa_required ? "Prior authorization required" : "Prior authorization is not required"}
          {view.coverage.page ? `  |  plan coverage p.${view.coverage.page}` : ""}
          {view.coverage.evidence_text && <span className="quote" style={{ display: "block" }}>{view.coverage.evidence_text}</span>}
          {view.coverage.document_url && <a href={fileUrl(view.coverage.document_url)}>View source</a>}
        </p>
      )}
      {view.questionnaire && view.status !== "draft" && view.status !== "not_required" && (
        <section className="card" style={{ marginTop: 12 }}>
          <p className="title">Clinical questionnaire (FHIR)</p>
          <p className="muted">{view.questionnaire.title || "Plan- and service-specific questions for this order"}</p>
          {(view.questionnaire.item || []).map((group) => (
            <div key={group.linkId} style={{ marginTop: 10 }}>
              <p className="title" style={{ fontSize: 14 }}>{group.text || group.linkId}</p>
              {(group.item || []).map((q) => (
                <p key={q.linkId} className="muted" style={{ marginTop: 4 }}>
                  {q.text || q.linkId}{q.type ? ` (${q.type})` : ""}
                </p>
              ))}
            </div>
          ))}
          <p className="muted" style={{ marginTop: 8 }}>
            Answer and verify each rule below. Answers are packaged as a QuestionnaireResponse on submit.
          </p>
        </section>
      )}
      {view.status === "not_required" && <p className="badge green">No submission is needed. The plan Evidence of Coverage does not require prior authorization for this order.</p>}
      {view.status === "info_requested" && (
        <p className="card" style={{ marginTop: 12, borderColor: "#c9a227" }}>
          Insurer asked for more information. Upload evidence below, answer the new question, verify, and submit again.
          The insurer reviews the update on their queue and can approve.
        </p>
      )}
      {view.status === "approved" && (
        <p className="badge green" style={{ marginTop: 12 }}>
          Approved by the insurer. The decision is on this timeline and in the patient chart export (`prior_authorizations`).
        </p>
      )}
      {view.status === "in_review" && (
        <p className="badge blue" style={{ marginTop: 12 }}>
          With the insurer queue. Waiting for approve or an information request.{" "}
          <Link href={`/insurer/pa/${view.id}`}>Open insurer view</Link>
        </p>
      )}
      {view.status === "submitted" && (
        <p className="badge blue" style={{ marginTop: 12 }}>
          Submitted. Moving to insurer review.{" "}
          <Link href="/insurer">Open insurer queue</Link>
        </p>
      )}
      {view.criteria_source && <p className="muted">Criteria: {view.criteria_source.title} ({view.criteria_source.source_kind})</p>}
      {view.total_count > 0 && <ReadinessBar met={view.met_count} total={view.total_count} readiness={view.readiness} />}
      {view.status === "matching" && (
        <section className="card">
          <p className="title">Choose the matching policy item</p>
          <p className="muted">
            Pick the benefit chart row for this order. After you choose, the clinical questionnaire for that service appears below so you can answer, verify, upload evidence, and submit.
          </p>
          {(view.match_candidates || []).length === 0 && (
            <div style={{ marginTop: 8 }}>
              <p className="badge amber">No automatic match yet. Add a CPT code (for MRI lumbar try 72148) and retry.</p>
              <button
                className="btn"
                style={{ marginTop: 8 }}
                onClick={() => post(`/pa-requests/${view.id}/confirm`, {
                  order_text: view.order_text,
                  service_category: view.service_category || view.order_text,
                  service_code: view.service_code || "72148",
                })}
              >
                Retry match with CPT 72148
              </button>
            </div>
          )}
          {(view.match_candidates || []).map((candidate) => (
            <button key={candidate.item_id} className="btn secondary" style={{ marginTop: 6 }} onClick={() => post(`/pa/${view.id}/match`, { item_id: candidate.item_id })}>
              {candidate.label} {candidate.page ? `p.${candidate.page}` : ""} {candidate.phrase ? ` "${candidate.phrase}"` : ""}
            </button>
          ))}
        </section>
      )}
      {view.criteria.length === 0 && view.status !== "draft" && view.status !== "matching" && view.status !== "not_required" && (
        <p className="muted" style={{ marginTop: 12 }}>No questionnaire items yet for this order.</p>
      )}
      {view.criteria.length === 0 && (view.status === "needs_info" || view.status === "ready_for_review") && (
        <p className="card" style={{ marginTop: 12 }}>
          Questionnaire questions show as cards below once criteria are built. Use Upload to add chart documents, then Recheck.
        </p>
      )}
      <div className="split" style={{ marginTop: 16 }}>
        <div>
          {view.criteria.map((criterion) => {
            const answered = criterion.questions.filter((question) => question.enabled).every((question) => question.value != null);
            const confidence = ruleConfidence({
              judge_verdict: criterion.judge_verdict,
              grounding: { passed: criterion.status === "met" && answered },
              question_verdict: "complete",
            });
            return (
            <article key={criterion.id} className={confidence.sure ? "card" : "card needs-look"} style={{ marginBottom: 10 }}>
              <div className="row">
                <ConfidenceBadge sure={confidence.sure} />
                <StatusBadge status={criterion.verified_by ? "verified" : criterion.status} />
                <span className="muted">p.{criterion.policy_page}</span>
                <JudgeBadge verdict={criterion.judge_verdict} />
              </div>
              {!confidence.sure && <p className="muted">{criterion.status === "met" ? confidence.detail : "This rule is not fully answered yet."}</p>}
              <p className="title" style={{ marginTop: 8 }}>{criterion.requirement_text}</p>
              {criterion.status_reason && <p>{criterion.status_reason}</p>}
              {criterion.likely_owner && <p className="muted">Likely with {criterion.likely_owner.full_name}. {criterion.likely_owner.reason}.</p>}
              {criterion.questions.filter((q) => q.enabled).map((question) => (
                <div key={question.id} style={{ marginTop: 8 }}>
                  <p className="muted">{question.text}</p>
                  <p>{showValue(question.value)} {question.fill_method === "clinician_entered" ? " |  Clinician attested" : question.fill_method ? " |  Found in chart" : ""}</p>
                  {question.evidence_text && <p className="quote">"{question.evidence_text}" {question.evidence_source?.author} {pretty(question.evidence_source?.date)}</p>}
                  {question.reject_reason && <p className="muted">Set aside: {question.reject_reason}. Earlier value: {showValue(question.rejected_ai_value)}</p>}
                  {question.attestation && <p className="muted">Attestation: {question.attestation}</p>}
                  {!criterion.verified_by && question.review_state !== "clinician_entered" && question.value != null && active?.id !== question.id && (
                    <button type="button" className="btn secondary" onClick={() => setActive(question)}>Set aside</button>
                  )}
                  {!criterion.verified_by && active?.id === question.id && (
                    <form
                      className="edit-panel"
                      style={{ marginTop: 8 }}
                      onSubmit={(e) => {
                        e.preventDefault();
                        const reason = String(new FormData(e.currentTarget).get("reason") || "").trim();
                        if (reason.length < 5) {
                          setError("Set-aside reason needs at least 5 characters.");
                          return;
                        }
                        post(`/pa/${view.id}/answers/${question.id}/reject`, {
                          provider_id: view.ordering_provider.id,
                          reason,
                        });
                      }}
                    >
                      <p className="title">Set this answer aside</p>
                      <p className="muted">Clears the chart/AI answer so you can enter a replacement below.</p>
                      <label className="field">
                        Reason (at least 5 characters)
                        <input name="reason" required minLength={5} autoFocus placeholder="Why this answer is wrong" />
                      </label>
                      <div className="row" style={{ marginTop: 8 }}>
                        <button type="submit" className="btn">Confirm set aside</button>
                        <button type="button" className="btn secondary" onClick={() => setActive(null)}>Cancel</button>
                      </div>
                    </form>
                  )}
                  {!criterion.verified_by && (question.value == null || question.review_state === "clinician_rejected") && (
                    <EnterForm question={question} providerId={view.ordering_provider.id} documents={docs} onSubmit={(body) => post(`/pa/${view.id}/answers/${question.id}/enter`, body)} />
                  )}
                </div>
              ))}
              {criterion.status === "met" && !criterion.verified_by && (
                <button className="btn" style={{ marginTop: 8 }} onClick={() => post(`/pa/${view.id}/criteria/${criterion.id}/verify`, { provider_id: view.ordering_provider.id })}>Verify</button>
              )}
              {criterion.verified_by && <p className="muted">Verified by {criterion.verified_by.full_name}</p>}
            </article>
            );
          })}
          {docs.some((doc) => !doc.in_chart) && (
            <section className="card">
              <p className="title">Synthetic documents not yet in the chart</p>
              {docs.filter((doc) => !doc.in_chart).map((doc) => (
                <button key={doc.id} className="btn secondary" onClick={() => addDocument(doc.id)}>Add {doc.file_name}</button>
              ))}
            </section>
          )}
          {view.status !== "draft" && view.status !== "approved" && view.status !== "not_required" && (
            <section className="card" style={{ marginTop: 10 }}>
              <p className="title">Upload clinical evidence</p>
              <p className="muted">
                Upload a PDF note or report into this patient chart, then the engine rechecks answers against it. That is how missing questionnaire items get filled.
              </p>
              <label className="field">
                PDF
                <input
                  type="file"
                  accept="application/pdf"
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (!file || !view) return;
                    setError("");
                    try {
                      const body = new FormData();
                      body.set("patient_id", view.patient.id);
                      body.set("file", file);
                      await api("/reports/extract", { method: "POST", body });
                      if (view.status !== "matching" && view.status !== "submitted" && view.status !== "in_review") {
                        const data = await api<RequestView>(`/pa/${view.id}/recheck`, { method: "POST" });
                        setView(data);
                      }
                      const listed = await api<{ documents: { id: string; file_name: string; in_chart?: number }[] }>(`/patients/${view.patient.id}/documents`);
                      setDocs(listed.documents);
                    } catch (err) {
                      setError(err instanceof Error ? err.message : "Upload failed");
                    }
                  }}
                />
              </label>
            </section>
          )}
        </div>
        <aside className="card episode-panel">
          <p className="title">Timeline</p>
          <p className="muted">Live updates every few seconds while this request is open.</p>
          <ol className="episode-rail">
            {view.events.map((event, index) => (
              <li key={`${event.created_at}-${index}`} className="episode-item gray">
                <div className="episode-dot" aria-hidden />
                <div className="episode-body">
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span className="episode-stage">{labelEvent(event.event_type)}</span>
                    <span className="muted">{event.actor}</span>
                  </div>
                  <p className="episode-summary">{event.message || labelEvent(event.event_type)}</p>
                </div>
              </li>
            ))}
          </ol>
          {view.events.length === 0 && <p className="muted">No events yet.</p>}
          <button className="btn secondary" disabled={!view.can_submit} onClick={async () => setPacket(JSON.stringify(await api(`/pa/${view.id}/packet`), null, 2))}>Preview submission</button>
          {!view.can_submit && (view.status === "needs_info" || view.status === "ready_for_review") && view.total_count > 0 && <p className="muted">Preview stays off until every rule is verified.</p>}
          <button className="btn" disabled={!view.can_submit} onClick={() => post(`/pa/${view.id}/submit`, { provider_id: view.ordering_provider.id })}>Submit</button>
          {packet && <pre className="episode-json">{packet}</pre>}
        </aside>
      </div>
    </main>
  );
}

function EnterForm({ question, providerId, documents, onSubmit }: { question: Question; providerId: string; documents: { id: string; file_name: string }[]; onSubmit: (body: object) => void }) {
  const [open, setOpen] = useState(false);
  if (!open) return <button className="btn secondary" onClick={() => setOpen(true)}>Enter answer</button>;
  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      const form = new FormData(e.currentTarget);
      const raw = String(form.get("value") || "");
      const value = question.text.toLowerCase().includes("age") || raw !== "" && !Number.isNaN(Number(raw)) && raw.trim() !== "" && !["true", "false"].includes(raw)
        ? (raw === "true" ? true : raw === "false" ? false : Number(raw))
        : raw === "true" ? true : raw === "false" ? false : raw;
      onSubmit({
        provider_id: providerId,
        value,
        source_document_id: form.get("source"),
        evidence_text: form.get("evidence"),
        attestation: form.get("attestation"),
      });
    }}>
      <label className="field">Value<input name="value" required placeholder="true, false, or a number" /></label>
      <label className="field">Source
        <select name="source" required>
          {documents.map((doc) => <option key={doc.id} value={doc.id}>{doc.file_name}</option>)}
        </select>
      </label>
      <label className="field">Evidence text<input name="evidence" required /></label>
      <label className="field">Attestation<input name="attestation" required minLength={10} /></label>
      <button className="btn">Save answer</button>
    </form>
  );
}

function showValue(value: unknown) {
  if (value == null) return "No answer yet";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function labelEvent(event: string) {
  return event.replaceAll("_", " ");
}
