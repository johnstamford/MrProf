"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { saveSession } from "../../lib/session";

type Created = { assessment_id: string; version: number; stage: string };
type Fetched = { assessment_id: string; version: number; stage: string; status: string };

export default function StartPage() {
  const router = useRouter();
  const [newPassword, setNewPassword] = useState("");
  const [created, setCreated] = useState<Created | null>(null);
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [fetched, setFetched] = useState<Fetched | null>(null);
  const [resumeTarget, setResumeTarget] = useState("/screening");
  const [resumeNote, setResumeNote] = useState("");
  const [error, setError] = useState("");

  function goToScreening(code: string, pw: string) {
    saveSession(code, pw);
    router.push("/screening");
  }

  function goTo(code: string, pw: string, path: string) {
    saveSession(code, pw);
    router.push(path);
  }

  async function start() {
    setError("");
    setCreated(null);
    const res = await fetch("/api/assessments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: newPassword }),
    });
    if (!res.ok) return setError(res.status === 422 ? "password must be at least 10 characters" : `start failed: ${res.status}`);
    const body = (await res.json()) as Created;
    setCreated(body);
    setId(body.assessment_id);
    setPassword(newPassword);
    // Stay on this screen: the user must save code + password before continuing.
  }

  async function resume() {
    setError("");
    setFetched(null);
    const code = id.trim().toUpperCase();
    const headers = { Authorization: `Bearer ${password}` };
    const res = await fetch(`/api/assessments/${encodeURIComponent(code)}`, { headers });
    if (res.status === 401) return setError("wrong assessment code or password");
    if (!res.ok) return setError(`resume failed: ${res.status}`);
    const body = (await res.json()) as Fetched;
    setFetched(body);
    // Route to the furthest progress: an in-progress or finished interview
    // resumes on the interview page (pending question or briefing);
    // otherwise continue with the screening questions.
    const next = await fetch(`/api/assessments/${encodeURIComponent(code)}/interview/next`, { headers });
    if (next.ok) {
      const state = (await next.json()) as { completed?: boolean; question?: unknown };
      setResumeTarget("/interview");
      setResumeNote(
        state.completed
          ? "Interview complete — your reports are ready."
          : state.question
            ? "Interview in progress — pick up where you left off."
            : "Interview in progress.",
      );
    } else {
      setResumeTarget("/screening");
      setResumeNote(
        body.stage === "screening"
          ? "Screening in progress."
          : "Just started — begin with the screening questions.",
      );
    }
    // Stay on this screen: confirm the assessment ID and recovery warning first.
  }

  return (
    <main>
      <h1>MrProf — ADHD screening and evidence briefing</h1>
      <section>
        <h2>What is this?</h2>
        <p>
          MrProf helps you complete a 6-question ADHD screening questionnaire and,
          if you choose, answer follow-up questions about your experiences. You keep
          two reports: a screening summary and an evidence briefing with exact quotes
          from your answers.
        </p>
        <p>
          This is a draft research prototype — it does not diagnose anything, and a
          result below the screening threshold does not rule anything out. Only a
          qualified clinician can determine what explains your experiences.
        </p>
      </section>
      <section>
        <h2>How it works</h2>
        <ol>
          <li>Answer 6 screening questions (a few minutes).</li>
          <li>Get your screening report immediately — either result can continue.</li>
          <li>Optionally continue to the interview: one question at a time, in your own words.</li>
          <li>Get your evidence briefing with supporting quotes.</li>
        </ol>
        <p>Both stages together take most people around 20–30 minutes. There is no time limit, and you can close the browser and resume later with your code and password.</p>
      </section>
      <section>
        <h2>New assessment</h2>
        <label>Choose a password (min 10 characters){" "}
          <input value={newPassword} onChange={(e) => setNewPassword(e.target.value)} type="password" />
        </label>{" "}
        <button onClick={start}>Start</button>
        {created && (
          <div>
            <h3>Save your assessment details</h3>
            <p>Assessment code: <code>{created.assessment_id}</code></p>
            <p role="alert">
              Write down your assessment code and password somewhere safe.
              You need both to get back to your assessment — without them it
              cannot be retrieved, and there is no password reset.
            </p>
            <button onClick={() => goToScreening(created.assessment_id, newPassword)}>
              I have saved my code and password — continue →
            </button>
          </div>
        )}
      </section>
      <section>
        <h2>Resume</h2>
        <label>Assessment code <input value={id} onChange={(e) => setId(e.target.value)} /></label>{" "}
        <label>Password <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" /></label>{" "}
        <button onClick={resume}>Resume</button>
        {fetched && (
          <div>
            <h3>Assessment found</h3>
            <p>{resumeNote || "Assessment found."}</p>
            <p role="alert">
              Keep your assessment code and password somewhere safe.
              You need both to get back to your assessment — without them it
              cannot be retrieved, and there is no password reset.
            </p>
            <button onClick={() => goTo(fetched.assessment_id, password, resumeTarget)}>
              Continue to {resumeTarget === "/interview" ? "interview" : "screening"} →
            </button>
          </div>
        )}
      </section>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
