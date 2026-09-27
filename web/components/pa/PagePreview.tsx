"use client";

export type PagePreviewRow = {
  page: number;
  printed_page?: number | null;
  char_count: number;
  grid_row_count?: number;
  preview: string;
};

export function PagePreview({
  pages,
  live = false,
  source,
}: {
  pages: PagePreviewRow[];
  live?: boolean;
  source?: string;
}) {
  if (!pages.length) {
    if (!live) return null;
    return (
      <section className="page-preview live">
        <p className="title">Extracted pages</p>
        <p className="muted">Waiting for page text... the first pages appear here before rules are judged.</p>
        <div className="page-skeleton-grid">
          <div className="page-skeleton" />
          <div className="page-skeleton" />
          <div className="page-skeleton" />
        </div>
      </section>
    );
  }

  return (
    <section className={`page-preview ${live ? "live" : ""}`}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <p className="title">Extracted pages</p>
          <p className="muted" style={{ marginTop: 4 }}>
            {live
              ? "Shown as soon as the PDF is read - extract and judge continue in the background."
              : "Page text used for grounding and review."}
          </p>
        </div>
        <span className="badge green">
          {pages.length} page{pages.length === 1 ? "" : "s"}
          {source && source !== "none" ? `  |  ${source}` : ""}
        </span>
      </div>
      <div className="page-grid">
        {pages.map((page) => (
          <article key={page.page} className="page-card">
            <div className="row" style={{ justifyContent: "space-between" }}>
              <p className="title">Page {page.page}</p>
              <span className="muted">
                {page.char_count} chars
                {(page.grid_row_count || 0) > 0 ? `  |  ${page.grid_row_count} chart rows` : ""}
              </span>
            </div>
            <p className="page-text">{page.preview || "(empty page)"}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
