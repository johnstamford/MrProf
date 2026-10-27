"use client";

import { useState } from "react";

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

type Saved = { score: number; positive: boolean; version: number; replayed?: boolean };

export default function ScreeningPage() {
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [version, setVersion] = useState<number | null>(null);
  const [answers, setAnswers] = useState<string[]>(Array(6).fill(""));
  const [saved, setSaved] = useState<Saved | null>(null);
  const [error, setError] = useState("");

  function setAnswer(i: number, key: string) {
    setAnswers((prev) => prev.map((v, j) => (j === i ? key : v)));
  }

  async function load() {
    setError("");
    setSaved(null);
    const res = await fetch(`/api/assessments/${encodeURIComponent(id.trim().toUpperCase())}`, {
      headers: { Authorization: `Bearer ${password}` },
    });
    if (res.status === 401) return setError("wrong assessment code or password");
    if (!res.ok) return setError(`load failed: ${res.status}`);
    const body = await res.json();
    setVersion(body.version as number);
    const s = await fetch(`/api/assessments/${encodeURIComponent(id.trim().toUpperCase())}/screening`, {
      headers: { Authorization: `Bearer ${password}` },
    });
    if (s.ok) {
      const data = await s.json();
      setAnswers(data.answers as string[]);
      setSaved({ score: data.score, positive: data.positive, version: data.version });
    }
  }

  async function submit() {
    setError("");
    if (version === null) return setError("load your assessment first");
    if (answers.some((a) => !a)) return setError("all six answers are required");
    const key =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `key-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const res = await fetch(`/api/assessments/${encodeURIComponent(id.trim().toUpperCase())}/screening`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${password}` },
      body: JSON.stringify({ answers, base_version: version, idempotency_key: key }),
    });
    if (res.status === 409) {
      const detail = await res.json().catch(() => null);
      const current = detail?.detail?.current_version;
      return setError(
        current ? `someone else saved first — reload (version ${current}) and try again` : "version conflict — reload and try again",
      );
    }
    if (res.status === 422) return setError("all six answers are required — check each question");
    if (res.status === 401) return setError("wrong assessment code or password");
    if (!res.ok) return setError(`save failed: ${res.status}`);
    const body = (await res.json()) as Saved;
    setSaved(body);
    setVersion(body.version);
  }

  return (
    <main>
      <h1>MrProf — screening questions</h1>
      <p>{INSTRUCTIONS}</p>
      <section>
        <h2>Your assessment</h2>
        <label>Assessment code <input value={id} onChange={(e) => setId(e.target.value)} /></label>{" "}
        <label>Password <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" /></label>{" "}
        <button onClick={load}>Load</button>
        {version !== null && <p>Loaded assessment version {version}.</p>}
      </section>
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
        <button onClick={submit}>Save screening answers</button>
      </section>
      {saved && (
        <p>
          Saved. Score {saved.score} of 6 (original 0–6 method, cutoff 4){saved.replayed ? " — already saved, no duplicate created" : ""}.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <footer>
        <small>{ATTRIBUTION}</small>
      </footer>
    </main>
  );
}
