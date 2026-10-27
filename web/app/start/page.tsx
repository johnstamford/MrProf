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
  const [error, setError] = useState("");

  function goToScreening(code: string, pw: string) {
    saveSession(code, pw);
    router.push("/screening");
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
    const res = await fetch(`/api/assessments/${encodeURIComponent(code)}`, {
      headers: { Authorization: `Bearer ${password}` },
    });
    if (res.status === 401) return setError("wrong assessment code or password");
    if (!res.ok) return setError(`resume failed: ${res.status}`);
    const body = (await res.json()) as Fetched;
    setFetched(body);
    // Stay on this screen: confirm the assessment ID and recovery warning first.
  }

  return (
    <main>
      <h1>MrProf — start or resume</h1>
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
            <p>Assessment code: <code>{fetched.assessment_id}</code> (stage: {fetched.stage}, status: {fetched.status})</p>
            <p role="alert">
              Keep your assessment code and password somewhere safe.
              You need both to get back to your assessment — without them it
              cannot be retrieved, and there is no password reset.
            </p>
            <button onClick={() => goToScreening(fetched.assessment_id, password)}>Continue →</button>
          </div>
        )}
      </section>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
