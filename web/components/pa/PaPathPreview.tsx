"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

const PA_STEPS = [
  {
    letter: "1",
    name: "Know if PA is needed",
    role: "Stop guessing. See what the plan actually requires.",
    time: "Seconds",
    next: "Patient path is clear when PA is not required",
  },
  {
    letter: "2",
    name: "See what is missing",
    role: "Only the questions that stand between order and care.",
    time: "Checklist",
    next: "Clinician focuses on what still blocks access",
  },
  {
    letter: "3",
    name: "Prove it once",
    role: "Chart evidence or a short attestation. No busywork.",
    time: "Evidence",
    next: "Answers stick so the case does not restart",
  },
  {
    letter: "4",
    name: "Send a clean packet",
    role: "Get the request out the door and keep therapy moving.",
    time: "Submit",
    next: "Fewer delays between decision and treatment",
  },
] as const;

export function PaPathPreview() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [highlight, setHighlight] = useState({ top: 0, height: 0, ready: false });
  const trackRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    const track = trackRef.current;
    const item = itemRefs.current[active];
    if (!track || !item) return;

    const measure = () => {
      const trackBox = track.getBoundingClientRect();
      const itemBox = item.getBoundingClientRect();
      setHighlight({
        top: itemBox.top - trackBox.top + track.scrollTop,
        height: itemBox.height,
        ready: true,
      });
    };

    measure();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    ro?.observe(track);
    ro?.observe(item);
    window.addEventListener("resize", measure);
    return () => {
      ro?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [active]);

  useEffect(() => {
    if (paused) return;
    const timer = window.setInterval(() => {
      setActive((i) => (i + 1) % PA_STEPS.length);
    }, 2800);
    return () => window.clearInterval(timer);
  }, [paused]);

  const step = PA_STEPS[active];

  return (
    <aside
      className="room-card"
      aria-label="Prior authorization workflow preview"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="room-head">
        <div>
          <p className="room-kicker">Built for access</p>
          <h2 className="room-title">Less delay</h2>
        </div>
        <span className="room-online">
          <span className="dot" aria-hidden />
          Care still in your hands
        </span>
      </div>

      <div ref={trackRef} className="room-track">
        <span
          className={`room-highlight${highlight.ready ? " ready" : ""}`}
          aria-hidden
          style={{
            transform: `translateY(${highlight.top}px)`,
            height: highlight.height,
          }}
        />
        <span className="room-rail" aria-hidden />
        <div className="room-steps" role="list">
          {PA_STEPS.map((s, index) => (
            <button
              key={s.letter}
              type="button"
              role="listitem"
              ref={(el) => {
                itemRefs.current[index] = el;
              }}
              className={`room-item${index === active ? " active" : ""}`}
              onMouseEnter={() => setActive(index)}
              onFocus={() => setActive(index)}
            >
              <span className="room-avatar">{s.letter}</span>
              <span className="room-copy">
                <span className="room-name">{s.name}</span>
                <span className="room-role">{s.role}</span>
              </span>
              <span className="room-time">{s.time}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="room-foot">
        <div>
          <p className="room-foot-label">Next step</p>
          <p className="room-foot-text room-foot-text-swap" key={step.letter}>
            {step.next}
          </p>
        </div>
        <Link className="room-foot-cta" href="/doctor">
          Help a patient -&gt;
        </Link>
      </div>
    </aside>
  );
}
