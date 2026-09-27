"use client";

import { useMemo, useState } from "react";

export type Episode = {
  seq: number;
  actor: string;
  stage: string;
  status: string;
  summary: string;
  created_at?: string;
  group_no?: number | null;
  detail?: Record<string, unknown> | null;
};

const STAGE_LABEL: Record<string, string> = {
  upload: "Validating",
  cache: "Fingerprint cache",
  pages: "Reading pages",
  clean: "Cleaning",
  precheck: "Pre-check",
  identity: "Identity",
  cascade: "Locating sections",
  extract: "Extracting",
  recover: "Filling gaps",
  recheck: "Rechecking",
  ground: "Grounding",
  judge: "Judging",
  questions: "Building questions",
  fhir: "FHIR",
  save: "Saving draft",
  index: "Indexing blocks",
};

const STALL_MS = 90_000;

function stageLabel(stage: string) {
  return STAGE_LABEL[stage] || stage.replaceAll("_", " ");
}

function statusTone(status: string): "amber" | "blue" | "green" | "gray" {
  if (status === "failed" || status === "timeout") return "amber";
  if (status === "started" || status === "resumed") return "blue";
  if (status === "completed" || status === "cache_hit") return "green";
  return "gray";
}

function ageMs(iso?: string) {
  if (!iso) return 0;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 0;
  return Date.now() - t;
}

export function EpisodeTimeline({
  episodes,
  live = false,
  itemCount = 0,
  stallMs = STALL_MS,
}: {
  episodes: Episode[];
  live?: boolean;
  itemCount?: number;
  stallMs?: number;
}) {
  const [filter, setFilter] = useState("all");
  const [openDetail, setOpenDetail] = useState<number | null>(null);

  const stages = useMemo(() => {
    const seen = new Set<string>();
    for (const episode of episodes) seen.add(episode.stage);
    return ["all", ...Array.from(seen)];
  }, [episodes]);

  const visibleRaw = filter === "all" ? episodes : episodes.filter((e) => e.stage === filter);
  // Hide the noisy "started" twin unless it is the live in-progress step.
  const visible = visibleRaw.filter((episode) => {
    if (episode.status !== "started") return true;
    const isLatest = episode === episodes[episodes.length - 1];
    return live && isLatest;
  });
  const latest = episodes[episodes.length - 1];
  const activeStarted =
    latest?.status === "started" ||
    (live && latest != null && !["completed", "cache_hit", "failed", "skipped"].includes(latest.status));
  const stalled = Boolean(live && latest && ageMs(latest.created_at) > stallMs);
  const failed = episodes.some((e) => e.status === "failed" || e.status === "timeout");
  const cacheHits = episodes.filter((e) => e.status === "cache_hit").length;

  return (
    <section className={`episode-panel ${live ? "live" : ""}`}>
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <p className="title">Episode timeline</p>
          <p className="muted" style={{ marginTop: 4 }}>
            {live
              ? "Reading the PDF and writing structured rows. This list updates as each step finishes."
              : "Append-only log of every step that produced this policy."}
          </p>
        </div>
        <div className="row">
          {live && (
            <span className="badge blue episode-pulse">
              <i />
              Working...
            </span>
          )}
          {cacheHits > 0 && (
            <span className="badge green">
              {cacheHits} cache hit{cacheHits === 1 ? "" : "s"}
            </span>
          )}
          {itemCount > 0 && (
            <span className="badge gray">
              {itemCount} row{itemCount === 1 ? "" : "s"} so far
            </span>
          )}
        </div>
      </div>

      {stalled && (
        <p className="badge amber" style={{ marginTop: 10 }}>
          No new step for {Math.round(stallMs / 1000)}s. A model call may still be running - or it timed
          out. Keep this page open; a failed step is recorded when the engine finishes that unit.
        </p>
      )}
      {failed && !live && (
        <p className="badge amber" style={{ marginTop: 10 }}>
          At least one step failed. Open that row for the error detail.
        </p>
      )}
      {live && activeStarted && !stalled && latest && (
        <p className="episode-now">
          Now: <strong>{stageLabel(latest.stage)}</strong> - {latest.summary}
        </p>
      )}

      <div className="filter-tabs" role="tablist" aria-label="Episode filters">
        {stages.map((stage) => (
          <button
            key={stage}
            type="button"
            role="tab"
            aria-selected={filter === stage}
            className={filter === stage ? "filter-tab active" : "filter-tab"}
            onClick={() => setFilter(stage)}
          >
            {stage === "all" ? "All" : stageLabel(stage)}
          </button>
        ))}
      </div>

      {visible.length === 0 && (
        <p className="muted" style={{ marginTop: 12 }}>
          No episodes yet. Upload starts the first step within a second.
        </p>
      )}

      <ol className="episode-rail">
        {visible.map((episode) => {
          const tone = statusTone(episode.status);
          const hasDetail = episode.detail && Object.keys(episode.detail).length > 0;
          const open = openDetail === episode.seq;
          return (
            <li
              key={episode.seq}
              className={`episode-item ${tone} ${episode.status === "started" ? "pulse" : ""}`}
            >
              <div className="episode-dot" aria-hidden />
              <div className="episode-body">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <div className="row">
                    <span className="episode-seq">#{episode.seq}</span>
                    <span className="episode-stage">{stageLabel(episode.stage)}</span>
                    <span className={`badge ${tone}`}>{episode.status.replaceAll("_", " ")}</span>
                    {episode.group_no != null && (
                      <span className="badge gray">group {episode.group_no}</span>
                    )}
                  </div>
                  <span className="muted">{episode.actor}</span>
                </div>
                <p className="episode-summary">{episode.summary}</p>
                {hasDetail && (
                  <button
                    type="button"
                    className="btn secondary"
                    style={{ marginTop: 6, padding: "4px 10px", fontSize: 12 }}
                    onClick={() => setOpenDetail(open ? null : episode.seq)}
                  >
                    {open ? "Hide JSON" : "Show JSON"}
                  </button>
                )}
                {open && hasDetail && (
                  <pre className="episode-json">{JSON.stringify(episode.detail, null, 2)}</pre>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
