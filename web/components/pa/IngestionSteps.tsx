"use client";

export type IngestionStep = {
  id: string;
  label: string;
  status: "pending" | "active" | "done" | "failed";
  detail?: string | null;
};

export function IngestionSteps({ steps, live = false }: { steps: IngestionStep[]; live?: boolean }) {
  const active = steps.find((step) => step.status === "active");
  const title = live || active ? "Processing Document..." : "Document processed";

  return (
    <section className={`processing-doc ${live ? "live" : ""}`} aria-live="polite">
      <h2 className="processing-title">{title}</h2>
      {!steps.length && <p className="muted">Waiting for the first stage...</p>}
      <ul className="processing-list">
        {steps.map((step) => (
          <li key={step.id} className={`processing-row ${step.status}`}>
            <span className={`processing-dot ${step.status}`} aria-hidden>
              {step.status === "done" ? (
                <svg viewBox="0 0 16 16" width="12" height="12">
                  <path
                    d="M3.5 8.2l2.8 2.8 6.2-6.2"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              ) : null}
            </span>
            <span className="processing-label">
              {step.label}
              {step.status === "active" && <span className="processing-progress"> in progress...</span>}
              {step.status === "failed" && <span className="processing-progress"> failed</span>}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export const PENDING_STEPS: IngestionStep[] = [
  { id: "upload", label: "Queued", status: "active" },
  { id: "pages", label: "Extracting pages", status: "pending" },
  { id: "identity", label: "Identifying plan", status: "pending" },
  { id: "precheck", label: "Analyzing document format", status: "pending" },
  { id: "cascade", label: "Locating benefit/coverage chapter", status: "pending" },
  { id: "extract", label: "Extracting benefit rules", status: "pending" },
  { id: "judge", label: "Independent accuracy review", status: "pending" },
  { id: "recheck", label: "Rechecking flagged items", status: "pending" },
  { id: "fhir", label: "Building FHIR output", status: "pending" },
];
