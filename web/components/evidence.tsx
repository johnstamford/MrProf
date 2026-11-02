"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  MinusCircle,
} from "lucide-react";

export type Assertion = "present" | "denied" | "uncertain" | string;

export type ReviewState = "pending" | "accepted" | "amended" | "rejected" | string;

export type Observation = {
  assertion: Assertion;
  quote: string;
  segment_id: string;
  line: number | null;
  /** Extractor's one-sentence explainer (system interpretation, not a quote). */
  note?: string;
  obs_index?: number;
  review_status?: ReviewState;
  review_note?: string;
};

export type ReviewAction = "accept" | "amend" | "reject";

export type TopicStatus = string;

export function statusTone(status: string): "covered" | "denied" | "uncertain" | "gap" {
  const s = status.toLowerCase();
  if (s.includes("denied")) return "denied";
  if (s.includes("uncertain")) return "uncertain";
  if (s.includes("unasked") || s.includes("thin") || s.includes("pending") || s.includes("gap"))
    return "gap";
  return "covered";
}

const DOT: Record<string, string> = {
  covered: "bg-primary",
  denied: "bg-ink-faint",
  uncertain: "bg-uncertain",
  gap: "border border-dashed border-ink-faint bg-transparent",
};

/** Small status dot for the topic rail. */
export function StatusDot({ status, label }: { status: string; label?: string }) {
  const tone = statusTone(status);
  return (
    <span
      className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${DOT[tone]}`}
      role="img"
      aria-label={label ?? status}
      title={label ?? status}
    />
  );
}

/** Assertion chip: reported present / explicitly denied / uncertain. */
export function AssertionChip({ assertion }: { assertion: Assertion }) {
  const a = assertion.toLowerCase();
  if (a.includes("deni"))
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-cream px-2.5 py-0.5 text-xs font-medium text-ink-soft">
        <MinusCircle className="h-3.5 w-3.5" aria-hidden /> explicitly denied
      </span>
    );
  if (a.includes("uncertain"))
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-uncertain-tint px-2.5 py-0.5 text-xs font-medium text-uncertain">
        <AlertTriangle className="h-3.5 w-3.5" aria-hidden /> uncertain
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-primary-tint px-2.5 py-0.5 text-xs font-medium text-primary-deep">
      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> reported present
    </span>
  );
}

/** One grounded observation: serif quote, chip, line + segment ref. Click jumps to the transcript line. */
export function EvidenceCard({
  observation,
  onReview,
  reviewing,
  reviewError,
}: {
  observation: Observation;
  onReview?: (action: ReviewAction, note: string) => Promise<void> | void;
  reviewing?: boolean;
  reviewError?: string | null;
}) {
  const [amending, setAmending] = useState(false);
  const [note, setNote] = useState("");
  const line = observation.line;
  const target = line != null ? `#line-${line}` : `#seg-${observation.segment_id}`;
  const review = (observation.review_status ?? "pending").toLowerCase();
  return (
    <div className="rounded-2xl border border-line bg-card p-4 shadow-[0_1px_2px_rgba(20,32,29,0.05)]">
      <a
        href={target}
        className="block transition-colors hover:border-primary"
        aria-label={`Quote${line != null ? `, line ${line}` : ""}, ${observation.segment_id}. Jump to transcript.`}
      >
        <blockquote className="font-serif text-[17px] leading-relaxed text-ink">
          &ldquo;{observation.quote}&rdquo;
        </blockquote>
        {observation.note && (
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            <span className="font-medium text-ink">Why this is here: </span>
            {observation.note}{" "}
            <span className="text-ink-faint">(system interpretation, not a quote)</span>
          </p>
        )}
        <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
          <AssertionChip assertion={observation.assertion} />
          <span className="text-xs text-ink-faint">
            {line != null ? `line ${line} · ` : ""}segment {observation.segment_id}
          </span>
        </p>
      </a>
      <p className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        <ReviewChip review={review} />
        {observation.review_note && (
          <span className="text-ink-soft">Reviewer note: {observation.review_note}</span>
        )}
      </p>
      {onReview && review === "pending" && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {!amending ? (
            <>
              <button
                onClick={() => void onReview("accept", "")}
                disabled={reviewing}
                className="rounded-full border border-line px-3 py-1 text-xs font-semibold text-ink-soft hover:border-primary hover:text-primary disabled:opacity-50"
              >
                Accept
              </button>
              <button
                onClick={() => setAmending(true)}
                disabled={reviewing}
                className="rounded-full border border-line px-3 py-1 text-xs font-semibold text-ink-soft hover:border-primary hover:text-primary disabled:opacity-50"
              >
                Amend
              </button>
              <button
                onClick={() => void onReview("reject", "")}
                disabled={reviewing}
                className="rounded-full border border-line px-3 py-1 text-xs font-semibold text-ink-soft hover:border-tension hover:text-tension disabled:opacity-50"
              >
                Reject
              </button>
            </>
          ) : (
            <form
              className="flex w-full flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (note.trim()) {
                  void onReview("amend", note.trim());
                  setAmending(false);
                }
              }}
            >
              <label className="text-xs font-semibold">
                Amended interpretation
                <input
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-line bg-paper px-3 py-2 text-sm font-normal"
                  placeholder="What should this say instead?"
                  maxLength={500}
                />
              </label>
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={reviewing || !note.trim()}
                  className="rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                >
                  Save amendment
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setAmending(false);
                    setNote("");
                  }}
                  className="rounded-full border border-line px-4 py-1.5 text-xs font-semibold text-ink-soft"
                >
                  Cancel
                </button>
              </div>
            </form>
          )}
          {reviewError && (
            <p role="alert" className="w-full text-xs font-medium text-tension">
              {reviewError}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/** Review state chip: pending review vs accepted / amended / rejected. */
export function ReviewChip({ review }: { review: string }) {
  if (review === "accepted")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-primary-tint px-2.5 py-0.5 font-medium text-primary-deep">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> reviewer accepted
      </span>
    );
  if (review === "amended")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-primary-tint px-2.5 py-0.5 font-medium text-primary-deep">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> reviewer amended
      </span>
    );
  if (review === "rejected")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-tension-tint px-2.5 py-0.5 font-medium text-tension">
        <MinusCircle className="h-3.5 w-3.5" aria-hidden /> reviewer rejected
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-cream px-2.5 py-0.5 font-medium text-ink-soft">
      <CircleDashed className="h-3.5 w-3.5" aria-hidden /> awaiting review
    </span>
  );
}

/** Left rail: topic list with status dots, anchor-linked to sections. */
export function TopicRail({
  topics,
  groups,
  idPrefix = "topic-",
}: {
  topics: { objective: string; title: string; status: string }[];
  groups?: { key: string; title: string; objectives: string[] }[];
  idPrefix?: string;
}) {
  const byObjective: Record<string, { objective: string; title: string; status: string }> =
    Object.fromEntries(topics.map((t) => [t.objective, t]));
  const sections =
    groups && groups.length > 0
      ? groups
          .map((g) => ({
            key: g.key,
            title: g.title,
            topics: g.objectives.map((o) => byObjective[o]).filter(Boolean),
          }))
          .filter((g) => g.topics.length > 0)
      : [{ key: "all", title: "", topics }];
  return (
    <nav aria-label="Topics" className="rounded-2xl border border-line bg-card p-4">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-faint">Topics</h2>
      {sections.map((s) => (
        <div key={s.key} className="mt-3 first:mt-3">
          {s.title && (
            <p className="px-2 text-xs font-semibold text-ink-soft">{s.title}</p>
          )}
          <ul className="mt-1 space-y-1">
            {s.topics.map((t) => (
              <li key={t.objective}>
                <a
                  href={`#${idPrefix}${t.objective}`}
                  className="flex items-start gap-2.5 rounded-lg px-2 py-1.5 text-sm text-ink-soft hover:bg-paper hover:text-ink"
                >
                  <span className="mt-1.5">
                    <StatusDot status={t.status} label={`${t.title}: ${t.status}`} />
                  </span>
                  <span>
                    <span className="block font-medium leading-snug">{t.title}</span>
                    <span className="block text-xs text-ink-faint">{t.status}</span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <p className="mt-3 flex items-start gap-1.5 border-t border-line pt-3 text-xs text-ink-faint">
        <CircleDashed className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        Hollow dots are gaps: unexplored or thinly covered, not negative findings.
      </p>
    </nav>
  );
}

export type CoverageEntry = { objective: string; title: string; status: string; note: string; turns?: number[] };

/** Coverage summary: counts only, never percentages. */
export function CoverageBar({ coverage }: { coverage: CoverageEntry[] }) {
  const counts = { covered: 0, denied: 0, uncertain: 0, gap: 0 };
  for (const c of coverage) counts[statusTone(c.status)] += 1;
  const total = coverage.length || 1;
  const segs = [
    { key: "covered", n: counts.covered, cls: "bg-primary", label: "with a detailed account" },
    { key: "denied", n: counts.denied, cls: "bg-ink-faint", label: "explicitly denied" },
    { key: "uncertain", n: counts.uncertain, cls: "bg-uncertain", label: "uncertain" },
    { key: "gap", n: counts.gap, cls: "bg-line", label: "gaps" },
  ];
  return (
    <div>
      <div
        className="flex h-2.5 w-full overflow-hidden rounded-full bg-cream"
        role="img"
        aria-label={`Coverage: ${counts.covered} of ${coverage.length} topics with a detailed account, ${counts.denied} explicitly denied, ${counts.uncertain} uncertain, ${counts.gap} gaps.`}
      >
        {segs.map(
          (s) =>
            s.n > 0 && (
              <span key={s.key} className={s.cls} style={{ width: `${(s.n / total) * 100}%` }} />
            ),
        )}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-soft">
        {segs.map((s) => (
          <li key={s.key}>
            <strong className="text-ink">
              {s.n} of {coverage.length}
            </strong>{" "}
            {s.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

export type Segment = { id: string; turn: number; role: string; n: number; text: string; line: number };

/** Collapsible line-numbered transcript. Every line is an anchor target for evidence cards. */
export function TranscriptView({ segments }: { segments: Segment[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-2xl border border-line bg-card">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 rounded-2xl px-5 py-4 text-left"
      >
        <span>
          <span className="block font-serif text-lg font-semibold">
            Full transcript — check any quote
          </span>
          <span className="block text-sm text-ink-faint">
            {segments.length} numbered lines. Quotes above jump to their line here.
          </span>
        </span>
        <ChevronDown
          className={`h-5 w-5 shrink-0 text-ink-faint transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden
        />
      </button>
      {open && (
        <ol className="max-h-[32rem] space-y-1 overflow-y-auto border-t border-line px-5 py-4">
          {segments.map((s) => (
            <li
              key={s.id}
              id={`line-${s.line}`}
              className="transcript-line flex gap-3 px-2 py-1 text-sm leading-relaxed"
            >
              <a
                href={`#line-${s.line}`}
                id={`seg-${s.id}`}
                className="w-12 shrink-0 scroll-mt-24 text-right font-mono text-xs leading-6 text-ink-faint hover:text-primary"
                aria-label={`Line ${s.line}`}
              >
                {s.line}
              </a>
              <p>
                <span className="font-medium">{s.role === "Q" ? "Interviewer" : "You"}: </span>
                {s.text}
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** Box stating what the briefing did NOT conclude. Fixed wording, no clinical claims. */
export function NotConcludedBox() {
  return (
    <section
      aria-label="What this briefing did not conclude"
      className="rounded-2xl border border-line bg-cream p-4"
    >
      <h2 className="text-sm font-semibold">What we did NOT conclude</h2>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-soft">
        <li>No statement about whether these experiences meet any clinical criteria.</li>
        <li>A result below the screening threshold does not exclude ADHD or other conditions.</li>
        <li>Gaps below are missing information, not negative findings.</li>
        <li>Only a qualified clinician can determine what explains your experiences.</li>
      </ul>
    </section>
  );
}

/** Watermark shown on every synthetic demo surface. */
export function SyntheticBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-uncertain bg-uncertain-tint px-3 py-1 text-xs font-semibold uppercase tracking-wider text-uncertain">
      Synthetic demo — not a real person
    </span>
  );
}
