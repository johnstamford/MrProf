import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";
import {
  CoverageBar,
  EvidenceCard,
  NotConcludedBox,
  StatusDot,
  SyntheticBadge,
  TopicRail,
  TranscriptView,
  type CoverageEntry,
} from "../../../components/evidence";

export const metadata = { title: "Example report — MrProf" };

type DemoFile = {
  meta: {
    synthetic: boolean;
    watermark: string;
    profile_id: string;
    headline: string;
    proves: string;
    screening_score: number;
    screening_method: string;
    model: { provider: string; model: string };
    skill_version: string;
    topic_version: string;
    taxonomy_version: string;
    patient_kind: string;
    turns: number;
    exported_at: string;
    latency_ms: { mean: number; max: number };
    cost: string;
    note: string;
  };
  screening: {
    score: number;
    cutoff: number;
    positive: boolean;
    scoring_method: string;
    answers: { n: string; question: string; answer: string; counted: boolean }[];
    explanation: string;
    interview_offer: { offered: boolean; next_stage: string; note: string };
    next_section: { intro: string; topics: string[] };
  };
  briefing: {
    banner: string;
    completion_note: string;
    turns_answered: number;
    topics: {
      objective: string;
      title: string;
      status: string;
      note: string;
      turns: {
        turn: number;
        question: string;
        answer: string;
        observations: { assertion: string; quote: string; segment_id: string; line: number | null }[];
      }[];
    }[];
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
    transcript: { id: string; turn: number; role: string; n: number; text: string; line: number }[];
  };
};

const ORDER = ["vague-01", "denier-01", "contradictor-01", "recall-01"];

async function loadDemo(id: string): Promise<DemoFile | null> {
  try {
    const mod = await import(`../../../public/demo/${id}.json`);
    return (mod.default ?? mod) as DemoFile;
  } catch {
    return null;
  }
}

export default async function DemoViewer({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const demo = await loadDemo(id);
  if (!demo || demo.meta.synthetic !== true) notFound();
  const { meta, screening, briefing } = demo;
  const idx = ORDER.indexOf(id);
  const prev = idx > 0 ? ORDER[idx - 1] : null;
  const next = idx >= 0 && idx < ORDER.length - 1 ? ORDER[idx + 1] : null;

  return (
    <div className="pt-8 sm:pt-12">
      <p>
        <Link href="/demo" className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">
          <ArrowLeft className="h-4 w-4" aria-hidden /> All example reports
        </Link>
      </p>
      <p className="mt-4">
        <SyntheticBadge />
      </p>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
        {meta.headline}
      </h1>
      <p className="mt-2 max-w-2xl leading-relaxed text-ink-soft">{meta.proves}</p>

      {/* Metrics strip */}
      <dl className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { k: "Screening", v: `${screening.score} of 6 (${screening.scoring_method})` },
          { k: "Interview", v: `${meta.turns} turns` },
          { k: "Model", v: `${meta.model.model}` },
          { k: "Versions", v: `${meta.topic_version} · ${meta.taxonomy_version}` },
        ].map((m) => (
          <div key={m.k} className="rounded-2xl border border-line bg-card px-4 py-3">
            <dt className="text-xs font-semibold uppercase tracking-wider text-ink-faint">{m.k}</dt>
            <dd className="mt-1 text-sm font-semibold">{m.v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-ink-faint">
        Frozen {new Date(meta.exported_at).toLocaleDateString()} · {meta.skill_version} · mean turn
        latency {Math.round(meta.latency_ms.mean)} ms · {meta.cost}
      </p>

      {/* Screening strip */}
      <section aria-label="Screening result" className="mt-6 rounded-2xl border border-line bg-card p-5 sm:p-6">
        <h2 className="font-serif text-xl font-semibold">Screening report</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">{screening.explanation}</p>
        <ul className="mt-3 space-y-1 text-sm">
          {screening.answers.map((a) => (
            <li key={a.n} className="flex gap-2">
              <span className="font-mono text-xs leading-6 text-ink-faint">Q{a.n}</span>
              <span>
                {a.question} — <strong>{a.answer}</strong>
                {a.counted ? "" : ""}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {/* Draft banner */}
      <p role="note" className="sticky top-0 z-10 mt-6 rounded-2xl bg-ink px-4 py-3 text-sm font-medium text-paper">
        {briefing.banner}
      </p>

      {/* Three-column evidence layout */}
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

          {briefing.topics.map((t) => (
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
                      <span className="font-medium">Answered: </span>
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

          <TranscriptView segments={briefing.transcript} />
        </div>

        <div className="space-y-5">
          <div className="lg:sticky lg:top-20 lg:space-y-5">
            {briefing.contradictions.length > 0 && (
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
            <section aria-label="Gaps" className="rounded-2xl border border-line bg-card p-4">
              <h2 className="text-sm font-semibold">Gaps and open questions</h2>
              {briefing.gaps.length === 0 ? (
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

      <nav aria-label="More examples" className="mt-10 flex flex-wrap justify-between gap-3 border-t border-line pt-6">
        {prev ? (
          <Link href={`/demo/${prev}`} className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">
            <ArrowLeft className="h-4 w-4" aria-hidden /> Previous example
          </Link>
        ) : <span />}
        {next && (
          <Link href={`/demo/${next}`} className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">
            Next example <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        )}
      </nav>
    </div>
  );
}
