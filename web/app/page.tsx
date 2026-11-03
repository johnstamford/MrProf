import Link from "next/link";
import { ArrowRight, FileCheck2, MessagesSquare, ScanSearch } from "lucide-react";

export const dynamic = "force-dynamic";

const DEMO_CARDS = [
  {
    id: "vague-01",
    headline: "Vague short answers",
    proves: "Follow-ups turn thin answers into checkable evidence.",
  },
  {
    id: "denier-01",
    headline: "Denies difficulties",
    proves: "Denials are recorded as denied — never flipped into absence of evidence.",
  },
  {
    id: "contradictor-01",
    headline: "Conflicting accounts",
    proves: "Contradictions stay visible with both turns retained.",
  },
  {
    id: "recall-01",
    headline: "Incomplete recall",
    proves: "“I cannot remember” is respected and logged as a gap.",
  },
];

const STEPS = [
  {
    icon: ScanSearch,
    title: "1. Answer 6 screening questions",
    body: "The official ASRS v1.1 screener, word for word, with an immediate report. Either result can continue.",
  },
  {
    icon: MessagesSquare,
    title: "2. Talk through your experiences",
    body: "One question at a time, in your own words. No time limit. Close the browser and resume any time.",
  },
  {
    icon: FileCheck2,
    title: "3. Keep a briefing your doctor can check",
    body: "Every point carries an exact quote with a line number in your transcript — denials, uncertainty, and gaps included.",
  },
];

export default async function Home() {
  return (
    <div className="pt-10 sm:pt-16">
      {/* Hero */}
      <section className="max-w-3xl">
        <h1 className="font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
          Prepare for your ADHD assessment — in your own words, with evidence
          your doctor can check.
        </h1>
        <p className="mt-5 max-w-2xl text-lg leading-relaxed text-ink-soft">
          MrProf guides you through a short screening and a one-question-at-a-time
          interview, then assembles a briefing grounded in your exact words —
          quotes, line numbers, denials, and gaps included. It organizes what
          you report for clinician review — it does not diagnose or rule anything out.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/start"
            className="inline-flex items-center gap-2 rounded-full bg-primary px-6 py-3 text-base font-semibold text-white hover:bg-primary-deep"
          >
            Start my assessment <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
          <Link
            href="/demo"
            className="inline-flex items-center gap-2 rounded-full border border-ink/20 bg-card px-6 py-3 text-base font-semibold text-ink hover:border-primary hover:text-primary"
          >
            See example reports
          </Link>
        </div>
      </section>

      {/* How it works */}
      <section aria-label="How it works" className="mt-14 sm:mt-20">
        <h2 className="font-serif text-2xl font-semibold tracking-tight">How it works</h2>
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.title} className="rounded-2xl border border-line bg-card p-5">
              <s.icon className="h-6 w-6 text-primary" aria-hidden />
              <h3 className="mt-3 font-semibold">{s.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Demo cards */}
      <section aria-label="Example synthetic reports" className="mt-12 sm:mt-16">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="font-serif text-2xl font-semibold tracking-tight">Example reports</h2>
          <Link href="/demo" className="text-sm font-medium text-primary hover:underline">
            Open the gallery →
          </Link>
        </div>
        <p className="mt-2 max-w-2xl text-sm text-ink-soft">
          Four frozen synthetic reports, generated through the real interview pipeline
          with scripted patients. Each proves a different capability.
        </p>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          {DEMO_CARDS.map((c) => (
            <Link
              key={c.id}
              href={`/demo/${c.id}`}
              className="group rounded-2xl border border-line bg-card p-5 transition-colors hover:border-primary"
            >
              <p className="text-xs font-semibold uppercase tracking-wider text-uncertain">
                Synthetic demo — not a real person
              </p>
              <h3 className="mt-2 font-serif text-xl font-semibold group-hover:text-primary">
                {c.headline}
              </h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{c.proves}</p>
              <p className="mt-3 text-sm font-medium text-primary">
                Open the report <span aria-hidden>→</span>
              </p>
            </Link>
          ))}
        </div>
      </section>

    </div>
  );
}
