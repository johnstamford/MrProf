import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";
import BriefingView, { type Briefing } from "../../../components/briefing";
import { SyntheticBadge } from "../../../components/evidence";

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
  briefing: Briefing;
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
                {a.counted && (
                  <span className="ml-2 inline-block rounded-full bg-primary-tint px-2 py-0.5 text-xs font-medium text-primary-deep">
                    counted toward the score
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {/* Shared briefing layout (read-only demo: no reviewer controls). */}
      <div className="mt-6">
        <BriefingView briefing={briefing} />
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
