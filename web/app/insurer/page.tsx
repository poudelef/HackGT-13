"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/pa/StatusBadge";

type RequestRow = {
  id: string;
  status: string;
  order_text?: string;
  service_code?: string;
  insurer?: string;
  plan_name?: string;
  plan_year?: string;
  updated_at?: string;
  submitted_at?: string;
  patient?: { id?: string; full_name?: string };
};

export default function InsurerQueuePage() {
  const [rows, setRows] = useState<RequestRow[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    setBusy(true);
    setError("");
    api<{ requests: RequestRow[] }>("/pa?queue=insurer")
      .then((data) => setRows(data.requests || []))
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load the insurer queue"))
      .finally(() => setBusy(false));
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, []);

  const open = rows.filter((row) => row.status === "submitted" || row.status === "in_review");
  const waiting = rows.filter((row) => row.status === "info_requested");
  const done = rows.filter((row) => row.status === "approved");

  return (
    <main>
      <header className="page-head">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <p className="kicker">Payer desk</p>
            <h1 className="title">Insurer queue</h1>
            <p className="lead">Open packets from clinicians. Approve when complete, or ask for the missing evidence.</p>
          </div>
          <button type="button" className="btn secondary" onClick={load} disabled={busy}>
            {busy ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </header>
      {error && <p className="badge amber">{error}</p>}

      <QueueSection title="Ready for decision" empty="No packets waiting on a decision." rows={open} />
      <QueueSection title="Waiting on clinician" empty="Nothing pending more evidence." rows={waiting} />
      <QueueSection title="Approved" empty="No approvals in this session yet." rows={done} />
    </main>
  );
}

function QueueSection({ title, empty, rows }: { title: string; empty: string; rows: RequestRow[] }) {
  return (
    <section className="section-gap">
      <p className="title">
        {title} <span className="muted">({rows.length})</span>
      </p>
      {rows.length === 0 && <p className="muted">{empty}</p>}
      <div className="stack" style={{ marginTop: "0.75rem" }}>
        {rows.map((row) => (
          <article key={row.id} className="card">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <div>
                <p className="title" style={{ marginBottom: 4 }}>
                  {row.patient?.full_name || "Patient"}  {row.order_text || "Order"}
                </p>
                <p className="muted">
                  {[row.insurer, row.plan_name, row.service_code].filter(Boolean).join("  ")}
                </p>
              </div>
              <div className="row">
                <StatusBadge status={row.status} />
                <Link className="btn" href={`/insurer/pa/${row.id}`}>
                  Open
                </Link>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
