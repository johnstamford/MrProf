"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { loadSession } from "../start/page";

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

  if (error) return <main><h1>MrProf — screening report</h1><p role="alert">{error}</p></main>;
  if (!report) return <main><h1>MrProf — screening report</h1><p>Loading…</p></main>;

  return (
    <main>
      <h1>MrProf — screening report</h1>
      <p>
        Score {report.score} of 6 ({report.scoring_method} method, cutoff {report.cutoff}).
      </p>
      <p>{report.explanation}</p>
      <section>
        <h2>Your answers</h2>
        <ul>
          {report.answers.map((a) => (
            <li key={a.n}>Q{a.n}. {a.question} — {a.answer}</li>
          ))}
        </ul>
      </section>
      <section>
        <h2>What happens next</h2>
        <p>{report.next_section.intro}</p>
        <ul>
          {report.next_section.topics.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
        <p>{report.interview_offer.note}</p>
        <button onClick={() => router.push("/interview")}>Continue to interview →</button>
      </section>
    </main>
  );
}
