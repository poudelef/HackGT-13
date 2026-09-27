"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { documentRoleLabel } from "@/lib/format";
import { SourceBadge, StatusBadge } from "@/components/pa/StatusBadge";

type Policy = {
  id: string;
  file_name: string;
  document_role: string;
  source_kind: string;
  source_url?: string;
  insurer?: string;
  plan_name?: string;
  plan_year?: string;
  status: string;
  item_count: number;
  pending: number;
  fhir_valid?: boolean;
  ingestion_running?: boolean;
  current_step?: string | null;
};

const TABS = [
  ["clinical_policy", "Clinical policies"],
  ["benefit_summary", "Evidence of Coverage / plan"],
  ["drug_criteria", "Drug criteria"],
] as const;

export default function PolicyLibrary() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("clinical_policy");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [role, setRole] = useState("clinical_policy");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceKind, setSourceKind] = useState("published");
  const [file, setFile] = useState<File | null>(null);

  async function load(quiet = false) {
    if (!quiet) setLoading(true);
    setError("");
    try {
      const data = await api<{ policies: Policy[] }>("/policies?include_drafts=true");
      setPolicies(data.policies);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load policies");
    } finally {
      if (!quiet) setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  // Poll while any policy is still extracting so Status / Working stays live.
  useEffect(() => {
    const working = policies.some((policy) => policy.ingestion_running || policy.status === "ingesting");
    if (!working) return;
    const timer = setInterval(() => { load(true); }, 2000);
    return () => clearInterval(timer);
  }, [policies]);

  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    const body = new FormData();
    body.set("file", file);
    body.set("document_role", role);
    body.set("source_url", sourceUrl);
    body.set("downloaded_at", new Date().toISOString().slice(0, 10));
    body.set("source_kind", sourceKind);
    try {
      const created = await api<{
        id: string;
        cached?: boolean;
        cache_message?: string;
        sha256?: string;
        status?: string;
        accepted?: boolean;
        message?: string;
      }>("/policies", { method: "POST", body });
      const bits = new URLSearchParams();
      if (created.cached) {
        bits.set("cached", "1");
        bits.set("sha", (created.sha256 || "").slice(0, 12));
      } else if (created.accepted || created.status === "ingesting") {
        bits.set("live", "1");
      }
      const query = bits.toString() ? `?${bits}` : "";
      window.location.href = `/admin/policies/${created.id}${query}`;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function loadSample() {
    setBusy(true);
    setError("");
    try {
      await api("/demo/bootstrap?force=true", { method: "POST" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sample library failed");
    } finally {
      setBusy(false);
    }
  }

  async function removePolicy(policy: Policy) {
    const ok = window.confirm(
      `Delete "${policy.file_name}" from the library, database, and stored PDF? This cannot be undone.`
    );
    if (!ok) return;
    setDeleting(policy.id);
    setError("");
    try {
      await api(`/policies/${policy.id}`, { method: "DELETE" });
      setPolicies((rows) => rows.filter((row) => row.id !== policy.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete that policy");
    } finally {
      setDeleting(null);
    }
  }

  const visible = policies.filter((policy) => policy.document_role === tab);
  const workingCount = policies.filter((policy) => policy.ingestion_running || policy.status === "ingesting").length;

  return (
    <main>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1 className="title">Policy library</h1>
        <div className="row">
          {workingCount > 0 && (
            <span className="badge blue library-working">
              <span className="pulse-dot" aria-hidden />
              {workingCount} extracting
            </span>
          )}
          <button className="btn secondary" onClick={loadSample} disabled={busy}>Load sample library</button>
        </div>
      </div>
      <div className="row" style={{ margin: "12px 0" }}>
        {TABS.map(([id, name]) => (
          <button key={id} className={tab === id ? "btn" : "btn secondary"} onClick={() => setTab(id)}>{name}</button>
        ))}
      </div>
      {error && <p className="badge amber">{error} <button className="btn secondary" onClick={() => load()}>Retry</button></p>}
      <div className="card">
        {loading ? <p className="muted">Loading policies...</p> : visible.length === 0 ? (
          <p>No policies in this tab yet. Upload one, or load the sample library.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>Insurer</th>
                <th>Plan</th>
                <th>Year</th>
                <th>Source</th>
                <th>Status</th>
                <th>Items</th>
                <th>Pending</th>
                <th>FHIR</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((policy) => {
                const working = Boolean(policy.ingestion_running || policy.status === "ingesting");
                return (
                  <tr key={policy.id} className={working ? "row-working" : undefined}>
                    <td>
                      <Link href={`/admin/policies/${policy.id}${working ? "?live=1" : ""}`}>
                        {policy.file_name}
                      </Link>
                      {working && policy.current_step && (
                        <p className="muted" style={{ margin: "4px 0 0" }}>
                          <span className="library-working">
                            <span className="pulse-dot" aria-hidden />
                            {policy.current_step}
                          </span>
                        </p>
                      )}
                    </td>
                    <td>{policy.insurer || (working ? "..." : "")}</td>
                    <td>{policy.plan_name || (working ? "..." : "")}</td>
                    <td>{policy.plan_year || (working ? "..." : "")}</td>
                    <td><SourceBadge kind={policy.source_kind} url={policy.source_url} /></td>
                    <td>
                      {working ? (
                        <span className="badge blue library-working">
                          <span className="pulse-dot" aria-hidden />
                          extracting
                        </span>
                      ) : (
                        <StatusBadge status={policy.status} />
                      )}
                    </td>
                    <td>{policy.item_count}</td>
                    <td>{policy.pending}</td>
                    <td>{policy.fhir_valid ? "Valid" : "-"}</td>
                    <td>
                      <button
                        type="button"
                        className="btn secondary"
                        disabled={deleting === policy.id || working}
                        onClick={() => removePolicy(policy)}
                      >
                        {deleting === policy.id ? "Deleting..." : "Delete"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      <form className="card" style={{ marginTop: 16 }} onSubmit={upload}>
        <p className="title">Upload a document</p>
        <p className="muted">Use Evidence of Coverage / plan for plan charts that list services, cost share, and prior authorization. Clinical policy is for medical necessity rules. Drug criteria is for pharmacy PA blocks.</p>
        <p className="muted">The same PDF is never read twice. Upload is keyed by file fingerprint, so a renamed copy of the same plan document opens from cache.</p>
        <div className="row">
          <label className="field">File<input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} required /></label>
          <label className="field">Role
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="clinical_policy">Clinical policy</option>
              <option value="benefit_summary">Evidence of Coverage / plan</option>
              <option value="drug_criteria">Drug criteria</option>
            </select>
          </label>
          <label className="field">Source URL<input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://" /></label>
          <label className="field">Kind
            <select value={sourceKind} onChange={(e) => setSourceKind(e.target.value)}>
              <option value="published">Published</option>
              <option value="fictional_fallback">Fictional fallback</option>
            </select>
          </label>
          <button className="btn" disabled={busy}>{busy ? "Starting..." : "Upload"}</button>
        </div>
        <p className="muted" style={{ marginTop: 8 }}>
          Upload returns right away. Open the document to watch Processing Document... while pages and rules are extracted.
        </p>
      </form>
    </main>
  );
}
