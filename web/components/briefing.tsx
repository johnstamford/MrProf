"use client";

import { Download, Printer } from "lucide-react";
import {
  CoverageBar,
  EvidenceCard,
  NotConcludedBox,
  StatusDot,
  TopicRail,
  TranscriptView,
  type CoverageEntry,
  type Observation,
  type Segment,
} from "./evidence";

export type BriefingTopicTurn = {
  turn: number;
  question: string;
  answer: string;
  observations: Observation[];
};

export type BriefingTopic = {
  objective: string;
  title: string;
  status: string;
  note: string;
  turns: BriefingTopicTurn[];
};

export type Briefing = {
  report_version: number;
  banner: string;
  completion_note: string;
  turns_answered: number;
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
};

/** Full interview briefing: shared evidence system for the real report (also mirrored by /demo/[id]). */
export default function BriefingView({ briefing }: { briefing: Briefing }) {
  const covered = (briefing.coverage ?? []).filter(
    (c) => c.status.toLowerCase() === "covered",
  ).length;
  const total = (briefing.coverage ?? []).length || (briefing.topics ?? []).length;
  const jsonHref = `data:application/json;charset=utf-8,${encodeURIComponent(
    JSON.stringify(briefing, null, 2),
  )}`;

  return (
    <div>
      <p role="note" className="sticky top-0 z-10 rounded-2xl bg-ink px-4 py-3 text-sm font-medium text-paper">
        {briefing.banner}
      </p>
      <p className="mt-4 max-w-3xl leading-relaxed text-ink-soft">
        {briefing.turns_answered} answers across {total} topics
        {covered ? ` — ${covered} with a detailed account` : ""}.
        Everything below comes from what was written; quotes are exact and line-numbered so each point can be checked.
      </p>
      {briefing.detail_summary && briefing.detail_summary.total_turns > 0 && (
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-faint">
          Answer detail: {briefing.detail_summary.grounded_turns} of{" "}
          {briefing.detail_summary.total_turns} answers included a concrete
          example or stated context;{" "}
          {(briefing.detail_summary.level_counts[0] ?? 0) +
            (briefing.detail_summary.level_counts[1] ?? 0)}{" "}
          were brief or position-only. Thin answers are recorded as gaps, not
          as negative findings.
          {briefing.latency_summary && briefing.latency_summary.count > 0 && (
            <>
              {" "}Question phrasing took a median of{" "}
              {Math.round(briefing.latency_summary.p50_ms)} ms (p95{" "}
              {Math.round(briefing.latency_summary.p95_ms)} ms) on the server;
              your own thinking time is not counted.
            </>
          )}
        </p>
      )}
      {briefing.mode === "taster" && (
        <p role="note" className="mt-2 max-w-3xl rounded-xl border border-primary/30 bg-primary-tint px-4 py-2.5 text-sm font-medium text-primary-deep">
          Short taster — about 6 questions. Topics below marked unexplored were
          not reached and are recorded as gaps, not as negative findings.
        </p>
      )}
      {briefing.support_note && (
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-faint">{briefing.support_note}</p>
      )}

      <div className="mt-6 grid gap-5 lg:grid-cols-[240px_minmax(0,1fr)_260px]">
        <div className="no-print">
          <div className="lg:sticky lg:top-20">
            <TopicRail topics={briefing.topics} />
          </div>
        </div>

        <div className="min-w-0 space-y-8">
          <section aria-label="Coverage">
            <h2 className="font-serif text-xl font-semibold">What was covered</h2>
            <div className="mt-3">
              <CoverageBar coverage={briefing.coverage} />
            </div>
            <p className="mt-2 text-sm text-ink-soft">{briefing.completion_note}</p>
          </section>

          <section aria-label="What you reported">
            <h2 className="font-serif text-xl font-semibold">What you reported</h2>
            <div className="mt-3 space-y-8">
              {(briefing.topics ?? []).map((t) => (
                <section
                  key={t.objective}
                  id={`topic-${t.objective}`}
                  aria-label={t.title}
                  className="scroll-mt-24"
                >
                  <h3 className="flex items-center gap-2 font-serif text-lg font-semibold">
                    <StatusDot status={t.status} label={`${t.title}: ${t.status}`} />
                    {t.title}
                    <span className="text-sm font-normal text-ink-faint">— {t.status}</span>
                  </h3>
                  <p className="mt-1 text-sm text-ink-faint">{t.note}</p>
                  <div className="mt-3 space-y-5">
                    {t.turns.map((s) => (
                      <article key={s.turn} className="rounded-2xl border border-line bg-card p-4 sm:p-5">
                        <p className="text-xs font-semibold uppercase tracking-wider text-ink-faint">
                          Turn {s.turn}
                        </p>
                        <p className="mt-1.5 text-sm leading-relaxed">
                          <span className="font-medium">Asked: </span>
                          {s.question}
                        </p>
                        <p className="mt-1.5 text-sm leading-relaxed">
                          <span className="font-medium">You said: </span>
                          {s.answer}
                        </p>
                        {s.observations.length > 0 && (
                          <div className="mt-3 space-y-2.5">
                            {s.observations.map((o, i) => (
                              <EvidenceCard key={i} observation={o} />
                            ))}
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          </section>

          <TranscriptView segments={briefing.transcript} />

          <details className="print-open rounded-2xl border border-line bg-card px-5 py-4">
            <summary className="cursor-pointer font-serif text-lg font-semibold">
              How this was gathered (system notes — not what you said)
            </summary>
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

        <div className="space-y-5">
          <div className="lg:sticky lg:top-20 lg:space-y-5">
            {(briefing.contradictions ?? []).length > 0 && (
              <section
                aria-label="Accounts in tension"
                className="rounded-2xl border border-tension/40 bg-tension-tint p-4"
              >
                <h2 className="text-sm font-semibold">Accounts in tension — both retained</h2>
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
            <section aria-label="Gaps and open questions" className="rounded-2xl border border-line bg-card p-4">
              <h2 className="text-sm font-semibold">Gaps and open questions</h2>
              <p className="mt-2 text-sm text-ink-soft">{briefing.completion_note}</p>
              {(briefing.gaps ?? []).length === 0 ? (
                <p className="mt-2 text-sm text-ink-soft">
                  No open gaps: every planned topic reached a detailed account, a clear
                  denial, or a documented unable-to-answer.
                </p>
              ) : (
                <ul className="mt-2 space-y-1.5 text-sm text-ink-soft">
                  {briefing.gaps.map((g) => (
                    <li key={g.area}>
                      <strong className="text-ink">{g.area}</strong> — {g.status}
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <NotConcludedBox />
          </div>
        </div>
      </div>

      <div className="no-print mt-6 flex flex-wrap gap-3">
        <a
          href={jsonHref}
          download="mrprof-interview-briefing.json"
          className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card px-4 py-2 text-sm font-medium text-ink-soft hover:border-primary hover:text-primary"
        >
          <Download className="h-4 w-4" aria-hidden /> Download JSON
        </a>
        <button
          onClick={() => window.print()}
          className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card px-4 py-2 text-sm font-medium text-ink-soft hover:border-primary hover:text-primary"
        >
          <Printer className="h-4 w-4" aria-hidden /> Print / save PDF
        </button>
      </div>
    </div>
  );
}
