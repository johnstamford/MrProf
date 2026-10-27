"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { loadSession } from "../../lib/session";

const QUESTIONS = [
  "How often do you have trouble wrapping up the final details of a project, once the challenging parts have been done?",
  "How often do you have difficulty getting things in order when you have to do a task that requires organization?",
  "How often do you have problems remembering appointments or obligations?",
  "When you have a task that requires a lot of thought, how often do you avoid or delay getting started?",
  "How often do you fidget or squirm with your hands or feet when you have to sit down for a long time?",
  "How often do you feel overly active and compelled to do things, like you were driven by a motor?",
];

const RESPONSES = [
  { key: "never", label: "Never" },
  { key: "rarely", label: "Rarely" },
  { key: "sometimes", label: "Sometimes" },
  { key: "often", label: "Often" },
  { key: "very_often", label: "Very often" },
];

const INSTRUCTIONS =
  "Please answer the questions below, rating yourself on each of the criteria shown using the scale on the right side of the page. As you answer each question, place an X in the box that best describes how you have felt and conducted yourself over the past 6 months.";

const ATTRIBUTION =
  "The 6-question Adult Self-Report Scale-Version1.1 (ASRS-V1.1) Screener is a subset of the 18-question Adult ADHD Self-Report Scale-Version1.1 Symptom Checklist. © New York University and the President and Fellows of Harvard College.";

export default function ScreeningPage() {
  const router = useRouter();
  const [version, setVersion] = useState<number | null>(null);
  const [answers, setAnswers] = useState<string[]>(Array(6).fill(""));
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const session = loadSession();
    if (!session) {
      router.replace("/start");
      return;
    }
    void (async () => {
      const res = await fetch(`/api/assessments/${encodeURIComponent(session.code)}`, {
        headers: { Authorization: `Bearer ${session.password}` },
      });
      if (!res.ok) {
        setError("could not load your assessment — please start again");
        return;
      }
      const body = await res.json();
      setVersion(body.version as number);
      const s = await fetch(
        `/api/assessments/${encodeURIComponent(session.code)}/screening`,
        { headers: { Authorization: `Bearer ${session.password}` } },
      );
      if (s.ok) setAnswers((await s.json()).answers as string[]);
    })();
  }, [router]);

  function setAnswer(i: number, key: string) {
    setAnswers((prev) => prev.map((v, j) => (j === i ? key : v)));
  }

  async function next() {
    setError("");
    if (answers.some((a) => !a)) return setError("please answer all six questions");
    const session = loadSession();
    if (!session || version === null) return setError("session lost — please start again");
    setSaving(true);
    try {
      const key =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `key-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      let res = await fetch(`/api/assessments/${encodeURIComponent(session.code)}/screening`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.password}` },
        body: JSON.stringify({ answers, base_version: version, idempotency_key: key }),
      });
      if (res.status === 409) {
        // State moved on underneath us — reload the version and retry once.
        const fresh = await fetch(`/api/assessments/${encodeURIComponent(session.code)}`, {
          headers: { Authorization: `Bearer ${session.password}` },
        });
        if (!fresh.ok) return setError("could not save — please try again");
        const body = await fresh.json();
        setVersion(body.version as number);
        res = await fetch(`/api/assessments/${encodeURIComponent(session.code)}/screening`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.password}` },
          body: JSON.stringify({
            answers,
            base_version: body.version,
            idempotency_key: `key-${Date.now()}-${Math.random().toString(36).slice(2)}`,
          }),
        });
      }
      if (res.status === 422) return setError("please answer all six questions");
      if (!res.ok) return setError("could not save — please try again");
      router.push("/report");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main>
      <h1>MrProf — screening questions</h1>
      <p>{INSTRUCTIONS}</p>
      <section>
        {QUESTIONS.map((q, i) => (
          <fieldset key={i}>
            <legend>Q{i + 1}. {q}</legend>
            {RESPONSES.map((r) => (
              <label key={r.key}>
                <input
                  type="radio"
                  name={`q${i}`}
                  checked={answers[i] === r.key}
                  onChange={() => setAnswer(i, r.key)}
                />{" "}
                {r.label}
              </label>
            ))}
          </fieldset>
        ))}
        <button onClick={next} disabled={saving}>{saving ? "Saving…" : "Next →"}</button>
      </section>
      {error && <p role="alert">{error}</p>}
      <footer>
        <small>{ATTRIBUTION}</small>
      </footer>
    </main>
  );
}
