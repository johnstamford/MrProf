"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight, Download, Printer } from "lucide-react";
import { loadSession } from "../../lib/session";

type Answer = { n: string; question: string; answer: string; counted: boolean };
type Report = {
  score: number;
  cutoff: number;
  positive: boolean;
  scoring_method: string;
  answers: Answer[];
  explanation: string;
  interview_offer: { offered: boolean; next_stage: string; note: string };
  next_section: { intro: string; topics: string[] };
};

export default function ReportPage() {
  const router = useRouter();
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const session = loadSession();
    if (!session) {
      setError("no assessment in this tab — start or resume first");
      return;
    }
    void (async () => {
      const res = await fetch(
        `/api/assessments/${encodeURIComponent(session.code)}/screening/report`,
        { headers: { Authorization: `Bearer ${session.password}` } },
      );
      if (res.status === 404) return setError("no screening report yet — answer the screening questions first");
      if (!res.ok) return setError(`could not load report: ${res.status}`);
      setReport((await res.json()) as Report);
    })();
  }, []);

  if (error)
    return (
      <div className="mx-auto max-w-2xl pt-10">
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Screening report</h1>
        <p role="alert" className="mt-4 rounded-xl border border-tension/40 bg-tension-tint px-4 py-3 text-sm font-medium">{error}</p>
      </div>
    );
  if (!report)
    return (
      <div className="mx-auto max-w-2xl pt-10">
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Screening report</h1>
        <p role="status" className="mt-4 text-ink-soft">Loading…</p>
      </div>
    );

  const jsonHref = `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(report, null, 2))}`;

  return (
    <div className="mx-auto max-w-2xl pt-10 sm:pt-14">
      <h1 className="font-serif text-3xl font-semibold tracking-tight sm:text-4xl">Screening report</h1>

      <section aria-label="Score" className="mt-6 rounded-2xl border border-line bg-card p-5 sm:p-6">
        <p className="text-sm text-ink-soft">
          Score <strong className="font-serif text-3xl text-ink">{report.score}</strong>
          <span className="text-ink"> of 6</span> ({report.scoring_method} method, cutoff {report.cutoff}).
        </p>
        <p className="mt-3 leading-relaxed text-ink-soft">{report.explanation}</p>
      </section>

      <section aria-label="Your answers" className="mt-4 rounded-2xl border border-line bg-card p-5 sm:p-6">
        <h2 className="font-serif text-xl font-semibold">Your answers</h2>
        <ul className="mt-3 space-y-2.5">
          {report.answers.map((a) => (
            <li key={a.n} className="flex gap-3 rounded-xl bg-paper px-3.5 py-2.5 text-sm leading-relaxed">
              <span className="font-mono text-xs leading-6 text-ink-faint">Q{a.n}</span>
              <span>
                {a.question} — <strong>{a.answer}</strong>
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="What happens next" className="mt-4 rounded-2xl border border-line bg-card p-5 sm:p-6">
        <h2 className="font-serif text-xl font-semibold">What happens next</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft sm:text-base">{report.next_section.intro}</p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm leading-relaxed text-ink-soft sm:text-base">
          {report.next_section.topics.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft sm:text-base">{report.interview_offer.note}</p>
        <div className="no-print mt-4 flex flex-wrap gap-3">
          <button
            onClick={() => router.push("/interview")}
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-white hover:bg-primary-deep"
          >
            Continue to interview <ArrowRight className="h-4 w-4" aria-hidden />
          </button>
          <button
            onClick={() => router.push("/interview?mode=taster")}
            className="inline-flex items-center gap-1.5 rounded-full border border-primary px-6 py-3 text-sm font-semibold text-primary hover:bg-primary-tint"
          >
            Try the short taster (6 questions) <ArrowRight className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </section>

      <div className="no-print mt-4 flex flex-wrap gap-3">
        <a
          href={jsonHref}
          download="mrprof-screening-report.json"
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
