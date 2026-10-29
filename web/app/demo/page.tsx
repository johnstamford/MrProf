import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { SyntheticBadge } from "../../components/evidence";
import indexData from "../../public/demo/index.json";

export const metadata = { title: "Example reports — MrProf" };

type DemoSummary = {
  id: string;
  headline: string;
  proves: string;
  screening_score: number;
  screening_method: string;
  turns: number;
  exported_at: string;
};

const ORDER = ["vague-01", "denier-01", "contradictor-01", "recall-01"];

export default function DemoGallery() {
  const demos = [...(indexData.demos as DemoSummary[])].sort(
    (a, b) => ORDER.indexOf(a.id) - ORDER.indexOf(b.id),
  );
  return (
    <div className="pt-10 sm:pt-14">
      <p>
        <SyntheticBadge />
      </p>
      <h1 className="mt-4 font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
        Example reports
      </h1>
      <p className="mt-3 max-w-2xl leading-relaxed text-ink-soft">
        Four frozen reports, generated through the real interview pipeline with
        scripted synthetic patients. Quotes are exact interview output, never
        hand-edited. Each one proves a different capability.
      </p>
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {demos.map((d) => (
          <Link
            key={d.id}
            href={`/demo/${d.id}`}
            className="group rounded-2xl border border-line bg-card p-5 transition-colors hover:border-primary sm:p-6"
          >
            <p className="text-xs font-semibold uppercase tracking-wider text-uncertain">
              Synthetic demo — not a real person
            </p>
            <h2 className="mt-2 font-serif text-2xl font-semibold group-hover:text-primary">
              {d.headline}
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-soft">{d.proves}</p>
            <dl className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm">
              <div className="flex gap-1.5">
                <dt className="text-ink-faint">Screening</dt>
                <dd className="font-semibold">
                  {d.screening_score} of 6 <span className="font-normal text-ink-faint">({d.screening_method})</span>
                </dd>
              </div>
              <div className="flex gap-1.5">
                <dt className="text-ink-faint">Interview</dt>
                <dd className="font-semibold">{d.turns} turns</dd>
              </div>
            </dl>
            <p className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary">
              Open the report <ArrowRight className="h-4 w-4" aria-hidden />
            </p>
          </Link>
        ))}
      </div>
      <section
        aria-label="About these examples"
        className="mt-8 rounded-2xl border border-line bg-cream p-5 text-sm leading-relaxed text-ink-soft"
      >
        <p>
          Re-running the export re-freezes the whole set with new version stamps;
          nothing here is hand-edited. Ground-truth profiles never reach the viewer
          beyond what the interview saw. Synthetic walkthroughs prove the pipeline
          works — they say nothing about clinical validity.
        </p>
        <p className="mt-3">
          <Link href="/start" className="font-medium text-primary hover:underline">
            Start your own assessment →
          </Link>
        </p>
      </section>
    </div>
  );
}
