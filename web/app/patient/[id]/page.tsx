"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { pretty } from "@/lib/format";

type HistoryItem = {
  status: string;
  actor?: string;
  note?: string;
  timestamp?: string;
};

type PaRow = {
  pa_request_id: string;
  treatment?: string;
  service_code?: string;
  insurer?: string;
  plan_name?: string;
  plan_year?: string;
  status: string;
  internal_status?: string;
  decided_at?: string | null;
  reviewer_note?: string | null;
  history: HistoryItem[];
  updated_at?: string;
};

type StatusPayload = {
  patient: { id: string; full_name?: string; dob?: string; member_id?: string };
  requests: PaRow[];
};

function patientFacingLabel(status: string) {
  // G1: never surface denied to the patient UI.
  const normalized = status === "denied" ? "under_review" : status;
  const map: Record<string, string> = {
    no_pa_needed: "No prior auth needed",
    submitted: "Submitted",
    under_review: "Under review",
    approved: "Approved",
    additional_info_requested: "More information requested",
    questionnaire_pending: "Clinician checklist in progress",
    draft: "Draft",
    created: "Request opened",
  };
  return map[normalized] || normalized.replaceAll("_", " ");
}

export default function PatientStatusPage() {
  const params = useParams<{ id: string }>();
  const [view, setView] = useState<StatusPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let stop = false;
    async function pull() {
      try {
        const data = await api<StatusPayload>(`/patients/${params.id}/pa-status`);
        if (!stop) {
          setView(data);
          setError("");
        }
      } catch (err) {
        if (!stop) setError(err instanceof Error ? err.message : "Could not load status");
      }
    }
    pull();
    const timer = setInterval(pull, 3000);
    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, [params.id]);

  if (!view && !error) return <main><p className="muted">Loading your status...</p></main>;
  if (!view) {
    return (
      <main>
        <p className="badge amber">{error}</p>
        <Link className="btn secondary" href="/">Back home</Link>
      </main>
    );
  }

  return (
    <main>
      <header className="page-head">
        <p className="kicker">Patient</p>
        <h1 className="title">{view.patient.full_name || "Your care status"}</h1>
        <p className="lead">
          Live updates from the same prior-auth record your care team uses. No separate copy of the truth.
        </p>
      </header>

      <section className="card" style={{ marginBottom: "1rem" }}>
        <p className="title">Your info</p>
        <p className="muted">
          {[view.patient.full_name, view.patient.dob ? `DOB ${pretty(view.patient.dob)}` : null, view.patient.member_id ? `Member ${view.patient.member_id}` : null]
            .filter(Boolean)
            .join(" | ")}
        </p>
      </section>

      {view.requests.length === 0 && (
        <p className="card muted">No prior authorization requests yet for this patient.</p>
      )}

      <div className="stack">
        {view.requests.map((row) => (
          <article key={row.pa_request_id} className="card">
            <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <p className="title">{row.treatment || "Treatment request"}</p>
                <p className="muted">
                  {[row.insurer, row.plan_name, row.plan_year, row.service_code].filter(Boolean).join(" | ")}
                </p>
              </div>
              <span className="badge green">{patientFacingLabel(row.status)}</span>
            </div>
            {row.reviewer_note && <p className="quote" style={{ marginTop: 10 }}>{row.reviewer_note}</p>}
            <p className="kicker-sm" style={{ marginTop: 14 }}>History</p>
            <ol className="episode-rail">
              {(row.history || []).length === 0 && <p className="muted">No events yet.</p>}
              {(row.history || []).map((event, index) => (
                <li key={`${event.timestamp}-${index}`} className="episode-item gray">
                  <div className="episode-dot" aria-hidden />
                  <div className="episode-body">
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <span className="episode-stage">{patientFacingLabel(event.status)}</span>
                      <span className="muted">{event.timestamp ? pretty(event.timestamp) : ""}</span>
                    </div>
                    <p className="episode-summary">{event.note || patientFacingLabel(event.status)}</p>
                    {event.actor && <p className="muted">{event.actor}</p>}
                  </div>
                </li>
              ))}
            </ol>
            {row.internal_status && row.internal_status !== "draft" && (
              <p style={{ marginTop: 10 }}>
                <Link href={`/doctor/pa/${row.pa_request_id}`}>Open clinician view</Link>
              </p>
            )}
          </article>
        ))}
      </div>
    </main>
  );
}
