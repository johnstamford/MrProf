"use client";

import { Printer } from "lucide-react";
import {
  AssertionChip,
  CoverageBar,
  EvidenceCard,
  ReviewChip,
  StatusDot,
  TopicRail,
  TranscriptView,
  type CoverageEntry,
  type Observation,
  type ReviewAction,
  type Segment,
} from "./evidence";

export type BriefingTopicTurn = {
  turn: number;
  question: string;
  answer: string;
  correction?: string | null;
  observations: Observation[];
};

export type BriefingTopic = {
  objective: string;
  title: string;
  status: string;
  label?: string;
  note: string;
  coverage_detail?: string;
  turns: BriefingTopicTurn[];
};

export type BriefingArea = {
  key: string;
  title: string;
  status: string;
  label?: string;
  counts: Record<string, number>;
  objectives: string[];
};

export type BriefingScreening = {
  score: number | null;
  scoring_method: string;
  positive: boolean | null;
  completed_at?: string | null;
};

export type BriefingFrontQuote = {
  turn: number;
  objective: string;
  title: string;
  assertion?: string;
  quote: string;
  segment_id: string;
  line?: number | null;
  period?: string;
  review_status?: string;
  review_note?: string;
  user_correction?: string;
  obs_index?: number;
};

export type BriefingOpenArea = {
  kind: string;
  ref: string;
  title: string;
  text: string;
};

export type BriefingProvisionalSketch = {
  experimental: boolean;
  headline: string;
  behaviour_reported: number;
  reported: number;
  denied: number;
  uncertain: number;
  thin_or_missing: number;
  lines: string[];
} | null;

export type BriefingFrontSheet = {
  why: BriefingFrontQuote[];
  timeline: BriefingFrontQuote[];
  impact: BriefingFrontQuote[];
  context: BriefingFrontQuote[];
  open_areas: BriefingOpenArea[];
} | null;

export type Briefing = {
  report_version: number;
  banner: string;
  completion_note: string;
  turns_answered: number;
  screening?: BriefingScreening | null;
  areas?: BriefingArea[];
  front_sheet?: BriefingFrontSheet;
  provisional_sketch?: BriefingProvisionalSketch;
  topics: BriefingTopic[];
  statements: { turn: number; question: string; answer: string }[];
  system_notes: { turn: number; objective: string; reason: string }[];
  coverage: CoverageEntry[];
  contradictions: {
    family: string;
    areas: string[];
    present_turn: number;
    denial_turn: number;
    clarified: boolean;
    note: string;
  }[];
  gaps: { area: string; status: string }[];
  transcript: Segment[];
  detail_summary?: { level_counts: number[]; grounded_turns: number; total_turns: number };
  latency_summary?: { count: number; p50_ms: number; p95_ms: number; max_ms: number };
  support_note?: string;
  mode?: string;
  user_confirmed_at?: string | null;
};

/** Display words for raw topic/area statuses. Denial stays distinct from gaps. */
const STATUS_LABELS: Record<string, string> = {
  covered: "Reported",
  denied: "Explicitly denied",
  unable: "Uncertain",
  thin: "Limited",
  unasked: "Not covered",
  pending: "Not covered",
};

function statusLabel(raw: string, fallback?: string): string {
  if (fallback) return fallback;
  return STATUS_LABELS[raw.toLowerCase()] ?? raw;
}

function formatCounts(counts: Record<string, number>): string {
  const order = ["covered", "denied", "unable", "thin", "unasked", "pending"];
  const parts: string[] = [];
  for (const k of order) {
    const n = counts[k] ?? 0;
    if (n > 0) parts.push(`${n} ${statusLabel(k).toLowerCase()}`);
  }
  return parts.length > 0 ? parts.join(" · ") : "no topics";
}

function quoteTarget(q: BriefingFrontQuote): string {
  return q.line != null ? `#line-${q.line}` : `#seg-${q.segment_id}`;
}

function FrontQuoteCard({ q }: { q: BriefingFrontQuote }) {
  const review = (q.review_status ?? "pending").toLowerCase();
  return (
    <div className="rounded-2xl border border-line bg-card p-4">
      <a
        href={quoteTarget(q)}
        className="block"
        aria-label={`Quote${q.line != null ? `, line ${q.line}` : ""}, ${q.segment_id}. Jump to transcript.`}
      >
        <blockquote className="font-serif text-[17px] leading-relaxed text-ink">
          &ldquo;{q.quote}&rdquo;
        </blockquote>
        <p className="mt-2 text-xs text-ink-faint">
          {q.title} · turn {q.turn}
          {q.line != null ? ` · line ${q.line}` : ""} · segment {q.segment_id}
          {q.period ? ` · ${q.period}` : ""}
        </p>
      </a>
      <p className="mt-2 flex flex-wrap items-center gap-2">
        {q.assertion && <AssertionChip assertion={q.assertion} />}
        <ReviewChip review={review} />
        {q.review_note && <span className="text-xs text-ink-soft">Reviewer note: {q.review_note}</span>}
        {q.user_correction && <span className="text-xs text-ink-soft">You noted: {q.user_correction}</span>}
      </p>
    </div>
  );
}

/** One-page front sheet: why they came, screening, timeline, impact,
 * context, and worth-exploring-together — all assembled from stored
 * evidence, every point linking down to its evidence card. */
function FrontSheet({
  sheet,
  screening,
}: {
  sheet: Exclude<BriefingFrontSheet, null>;
  screening?: BriefingScreening | null;
}) {
  return (
    <section aria-label="Front sheet" className="print-page rounded-2xl border border-line bg-card p-5 sm:p-6">
      <h2 className="font-serif text-xl font-semibold">1 · At a glance</h2>
      {sheet.why.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-faint">Why they came</h3>
          <div className="mt-2 space-y-2.5">
            {sheet.why.map((q, i) => (
              <FrontQuoteCard key={`${q.segment_id}-${i}`} q={q} />
            ))}
          </div>
        </div>
      )}
      {screening != null && screening.score != null && (
        <p className="mt-4 rounded-xl bg-paper px-4 py-3 text-sm leading-relaxed">
          <span className="font-medium">Screening: </span>
          {screening.score}/6 ({screening.scoring_method}
          {screening.positive == null
            ? ""
            : screening.positive
              ? ", above threshold — further assessment may be useful"
              : ", below threshold — does not exclude ADHD or other conditions"}
          ).
        </p>
      )}
      {sheet.timeline.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-faint">History and course</h3>
          <div className="mt-2 space-y-2.5">
            {sheet.timeline.map((q, i) => (
              <FrontQuoteCard key={`${q.segment_id}-${i}`} q={q} />
            ))}
          </div>
        </div>
      )}
      {sheet.impact.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-faint">Where it lands</h3>
          <div className="mt-2 space-y-2.5">
            {sheet.impact.map((q, i) => (
              <FrontQuoteCard key={`${q.segment_id}-${i}`} q={q} />
            ))}
          </div>
        </div>
      )}
      {sheet.context.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-faint">Relevant context</h3>
          <div className="mt-2 space-y-2.5">
            {sheet.context.map((q, i) => (
              <FrontQuoteCard key={`${q.segment_id}-${i}`} q={q} />
            ))}
          </div>
        </div>
      )}
      <div className="mt-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-faint">
          Worth exploring together
        </h3>
        {sheet.open_areas.length === 0 ? (
          <p className="mt-2 text-sm text-ink-soft">
            No open gaps: every planned topic reached a detailed account, a clear
            denial, or a documented unable-to-answer.
          </p>
        ) : (
          <ul className="mt-2 space-y-1.5 text-sm text-ink-soft">
            {sheet.open_areas.map((a, i) => (
              <li key={`${a.ref}-${i}`}>
                <a
                  href={a.kind === "tension" ? "#tensions" : `#topic-${a.ref}`}
                  className="hover:text-primary hover:underline"
                >
                  <strong className="font-medium text-ink">{a.title}</strong> — {a.text}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

/** Full interview briefing: shared evidence system for the real report (also mirrored by /demo/[id]).
 * Pass onReview to enable reviewer accept/amend/reject controls (reviewer mode only);
 * omit it for read-only surfaces (the patient's own briefing, frozen synthetic demos). */
export default function BriefingView({
  briefing,
  onReview,
  reviewingKey,
  reviewError,
}: {
  briefing: Briefing;
  onReview?: (turn: number, obsIndex: number, action: ReviewAction, note: string) => Promise<void> | void;
  reviewingKey?: string | null;
  reviewError?: string | null;
}) {
  const covered = (briefing.coverage ?? []).filter(
    (c) => c.status.toLowerCase() === "covered",
  ).length;
  const total = (briefing.coverage ?? []).length || (briefing.topics ?? []).length;
  const jsonHref = `data:application/json;charset=utf-8,${encodeURIComponent(
    JSON.stringify(briefing, null, 2),
  )}`;

  const byObjective: Record<string, BriefingTopic> = Object.fromEntries(
    (briefing.topics ?? []).map((t) => [t.objective, t]),
  );
  const areas: BriefingArea[] = (briefing.areas ?? []).filter((a) =>
    (a.objectives ?? []).some((o) => byObjective[o]),
  );

  return (
    <div>
      <p className="inline-block rounded-full border border-tension/40 bg-tension-tint px-3 py-1 text-xs font-bold uppercase tracking-wider text-tension">
        Unreviewed — not clinician-approved
      </p>
      <p className="mt-4 max-w-3xl leading-relaxed text-ink-soft">
        {briefing.turns_answered} answers across {total} topics
        {covered ? ` — ${covered} with a detailed account` : ""}.
        Everything below comes from what was written; quotes are exact and line-numbered so each point can be checked.
      </p>
      {briefing.user_confirmed_at && (
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-soft">
          Prepared from your answers · every point links to your transcript ·
          checked and confirmed by you on{" "}
          {new Date(briefing.user_confirmed_at).toLocaleDateString()}.
        </p>
      )}
      {briefing.mode === "taster" && (
        <p role="note" className="mt-2 max-w-3xl rounded-xl border border-primary/30 bg-primary-tint px-4 py-2.5 text-sm font-medium text-primary-deep">
          Short taster — about 6 questions. Topics below marked unexplored were
          not reached and are recorded as gaps.
        </p>
      )}
      {briefing.support_note && (
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-faint">{briefing.support_note}</p>
      )}

      <div className="mt-6 grid gap-5 lg:grid-cols-[240px_minmax(0,1fr)]">
        <div className="no-print">
          <div className="lg:sticky lg:top-20">
            <TopicRail
              topics={briefing.topics}
              groups={(briefing.areas ?? []).map((a) => ({
                key: a.key,
                title: a.title,
                objectives: a.objectives,
              }))}
            />
          </div>
        </div>

        <div className="min-w-0 space-y-8">
          {briefing.front_sheet ? (
            <FrontSheet sheet={briefing.front_sheet} screening={briefing.screening} />
          ) : (
            <section aria-label="Summary">
              <h2 className="font-serif text-xl font-semibold">1 · Summary</h2>
              {briefing.screening != null && briefing.screening.score != null && (
                <p className="mt-3 rounded-2xl border border-line bg-card p-4 text-sm leading-relaxed">
                  <span className="font-medium">Screening: </span>
                  {briefing.screening.score}/6 ({briefing.screening.scoring_method}
                  {briefing.screening.positive == null
                    ? ""
                    : briefing.screening.positive
                      ? ", above threshold — further assessment may be useful"
                      : ", below threshold — does not exclude ADHD or other conditions"}
                  ).
                </p>
              )}
              {areas.length > 0 ? (
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {areas.map((a) => (
                    <a
                      key={a.key}
                      href={`#area-${a.key}`}
                      className="block rounded-2xl border border-line bg-card p-4 transition-colors hover:border-primary"
                    >
                      <p className="flex items-center gap-2 font-medium">
                        <StatusDot status={a.status} label={`${a.title}: ${statusLabel(a.status, a.label)}`} />
                        {a.title}
                      </p>
                      <p className="mt-1 text-sm text-ink-soft">{statusLabel(a.status, a.label)}</p>
                      <p className="mt-0.5 text-xs text-ink-faint">{formatCounts(a.counts)}</p>
                    </a>
                  ))}
                </div>
              ) : (
                <div className="mt-3">
                  <CoverageBar coverage={briefing.coverage} />
                </div>
              )}
            </section>
          )}

          {briefing.provisional_sketch && (
            <section
              aria-label="Provisional sketch (experimental)"
              className="rounded-2xl border border-dashed border-uncertain bg-uncertain-tint p-5"
            >
              <p className="inline-block rounded-full bg-uncertain px-3 py-1 text-xs font-bold uppercase tracking-wider text-white">
                Experimental demo feature
              </p>
              <h2 className="mt-2 font-serif text-xl font-semibold">
                {briefing.provisional_sketch.headline}
              </h2>
              <div className="mt-2 space-y-1.5 text-sm leading-relaxed text-ink">
                {(briefing.provisional_sketch.lines ?? []).map((line, i) => (
                  <p key={i}>{line}</p>
                ))}
              </div>
            </section>
          )}

          <section aria-label="Evidence by area">
            <h2 className="font-serif text-xl font-semibold">
              {briefing.front_sheet ? "2 · Evidence" : "2 · Evidence by area"}
            </h2>
            <p className="mt-1 text-sm text-ink-faint">
              Why this is here — the system&apos;s one-line reading; the quote is your words.
            </p>
            <div className="mt-3 space-y-8">
              {(areas.length > 0
                ? areas
                : [
                    {
                      key: "all",
                      title: "All topics",
                      status: "",
                      label: "",
                      counts: {},
                      objectives: (briefing.topics ?? []).map((t) => t.objective),
                    } as BriefingArea,
                  ]
              ).map((a) => (
                <section
                  key={a.key}
                  id={`area-${a.key}`}
                  aria-label={a.title}
                  className="scroll-mt-24"
                >
                  {areas.length > 0 && (
                    <>
                      <h3 className="flex items-center gap-2 font-serif text-lg font-semibold">
                        <StatusDot status={a.status} label={`${a.title}: ${statusLabel(a.status, a.label)}`} />
                        {a.title}
                        <span className="text-sm font-normal text-ink-faint">
                          — {statusLabel(a.status, a.label)}
                        </span>
                      </h3>
                      <p className="mt-1 text-sm text-ink-faint">{formatCounts(a.counts)}</p>
                    </>
                  )}
                  <div className="mt-3 space-y-5">
                    {a.objectives.map((oid) => {
                      const t = byObjective[oid];
                      if (!t) return null;
                      const turns = t.turns ?? [];
                      return (
                        <section
                          key={t.objective}
                          id={`topic-${t.objective}`}
                          aria-label={t.title}
                          className="scroll-mt-24 rounded-2xl border border-line bg-paper p-4 sm:p-5"
                        >
                          <h4 className="flex items-center gap-2 font-serif text-base font-semibold">
                            <StatusDot status={t.status} label={`${t.title}: ${statusLabel(t.status, t.label)}`} />
                            {t.title}
                            <span className="text-sm font-normal text-ink-faint">
                              — {statusLabel(t.status, t.label)}
                            </span>
                          </h4>
                          <p className="mt-1 text-sm text-ink-faint">{t.note}</p>
                          {t.coverage_detail && (
                            <p className="mt-1 text-xs text-ink-faint">{t.coverage_detail}</p>
                          )}
                          {turns.some((s) => (s.observations ?? []).length > 0) ? (
                            <div className="mt-3 space-y-2.5">
                              {turns.map((s) => (
                                <div key={s.turn}>
                                  {(s.observations ?? []).map((o, i) => (
                                    <div key={`${s.turn}:${o.obs_index ?? i}`} className="mt-2.5 first:mt-0">
                                      <EvidenceCard
                                        observation={o}
                                        turn={s.turn}
                                        onReview={
                                          onReview
                                            ? (action, note) => onReview(s.turn, o.obs_index ?? i, action, note)
                                            : undefined
                                        }
                                        reviewing={reviewingKey === `${s.turn}:${o.obs_index ?? i}`}
                                        reviewError={reviewError}
                                      />
                                    </div>
                                  ))}
                                  {s.correction && (
                                    <p className="mt-2 rounded-xl bg-primary-tint px-3 py-2 text-sm leading-relaxed">
                                      <span className="font-medium text-primary-deep">
                                        You added (correction to turn {s.turn}):{" "}
                                      </span>
                                      {s.correction}
                                    </p>
                                  )}
                                </div>
                              ))}
                            </div>
                          ) : (
                            <p className="mt-2 text-sm text-ink-soft">
                              Nothing recorded here yet — see the open areas above.
                            </p>
                          )}
                        </section>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          </section>

          {(briefing.contradictions ?? []).length > 0 && (
            <section
              id="tensions"
              aria-label="Accounts in tension"
              className="scroll-mt-24 rounded-2xl border border-tension/40 bg-tension-tint p-4"
            >
              <h2 className="font-serif text-lg font-semibold">Accounts in tension — both retained</h2>
              <ul className="mt-2 space-y-2 text-sm leading-relaxed">
                {briefing.contradictions.map((c) => (
                  <li key={c.family}>
                    {c.areas.join(" / ")}: turn {c.denial_turn} reported no difficulty,
                    turn {c.present_turn} described difficulty — {c.note}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section aria-label="Full transcript">
            <h2 className="font-serif text-xl font-semibold">3 · Full transcript</h2>
            <p className="mt-1 text-sm text-ink-soft">
              Numbered lines for quick lookup — every quote above jumps to its line here.
              The full questions and answers live here, once.
            </p>
            <div className="mt-3">
              <TranscriptView segments={briefing.transcript} />
            </div>
          </section>

          <details className="print-open rounded-2xl border border-line bg-card px-5 py-4">
            <summary className="cursor-pointer font-serif text-lg font-semibold">
              How this was gathered (system notes — not what you said)
            </summary>
            <p className="mt-3 text-sm text-ink-soft">{briefing.completion_note}</p>
            {briefing.detail_summary && briefing.detail_summary.total_turns > 0 && (
              <p className="mt-2 text-sm leading-relaxed text-ink-faint">
                Answer detail: {briefing.detail_summary.grounded_turns} of{" "}
                {briefing.detail_summary.total_turns} answers included a concrete
                example or stated context;{" "}
                {(briefing.detail_summary.level_counts[2] ?? 0)} gave a substantive
                account without one;{" "}
                {(briefing.detail_summary.level_counts[0] ?? 0) +
                  (briefing.detail_summary.level_counts[1] ?? 0)}{" "}
                were brief or position-only.
                {briefing.latency_summary && briefing.latency_summary.count > 0 &&
                  briefing.latency_summary.max_ms >= 1 && (
                  <>
                    {" "}Question phrasing took a median of{" "}
                    {Math.round(briefing.latency_summary.p50_ms)} ms (p95{" "}
                    {Math.round(briefing.latency_summary.p95_ms)} ms) on the server;
                    your own thinking time is not counted.
                  </>
                )}
              </p>
            )}
            <ul className="mt-3 space-y-1.5 text-sm text-ink-soft">
              {briefing.system_notes.map((n) => (
                <li key={n.turn}>
                  Q{n.turn}: topic <code className="rounded bg-cream px-1 font-mono text-[13px]">{n.objective}</code> — {n.reason}
                </li>
              ))}
            </ul>
            <h3 className="mt-4 font-semibold">Coverage — what was explored</h3>
            <ul className="mt-2 space-y-1.5 text-sm text-ink-soft">
              {(briefing.coverage ?? []).map((c) => (
                <li key={c.objective}>
                  {c.title} — {c.status} ({c.note}
                  {c.turns?.length ? `, turns ${c.turns.join(", ")}` : ""})
                </li>
              ))}
            </ul>
          </details>
        </div>
      </div>

      <div className="no-print mt-6 flex flex-wrap items-center gap-4">
        <button
          onClick={() => window.print()}
          className="inline-flex items-center gap-1.5 rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-white hover:bg-primary-deep"
        >
          <Printer className="h-4 w-4" aria-hidden /> Print / save PDF
        </button>
        <a
          href={jsonHref}
          download="mrprof-interview-briefing.json"
          className="text-sm font-medium text-ink-soft underline-offset-4 hover:text-primary hover:underline"
        >
          Download JSON
        </a>
      </div>
    </div>
  );
}
