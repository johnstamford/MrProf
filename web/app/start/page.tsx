"use client";

import { useState } from "react";

type Created = { assessment_id: string; version: number; stage: string };
type Fetched = { assessment_id: string; version: number; stage: string; status: string };

export default function StartPage() {
  const [newPassword, setNewPassword] = useState("");
  const [created, setCreated] = useState<Created | null>(null);
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [fetched, setFetched] = useState<Fetched | null>(null);
  const [error, setError] = useState("");

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
  }

  async function resume() {
    setError("");
    setFetched(null);
    const res = await fetch(`/api/assessments/${encodeURIComponent(id.trim().toUpperCase())}`, {
      headers: { Authorization: `Bearer ${password}` },
    });
    if (res.status === 401) return setError("wrong assessment code or password");
    if (!res.ok) return setError(`resume failed: ${res.status}`);
    setFetched((await res.json()) as Fetched);
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
            <p>Write down your assessment code — you need it plus your password to resume.</p>
            <p>Assessment code: <code>{created.assessment_id}</code></p>
          </div>
        )}
      </section>
      <section>
        <h2>Resume</h2>
        <label>Assessment code <input value={id} onChange={(e) => setId(e.target.value)} /></label>{" "}
        <label>Password <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" /></label>{" "}
        <button onClick={resume}>Resume</button>
        {fetched && <p>Stage: {fetched.stage}, status: {fetched.status}, version: {fetched.version}</p>}
      </section>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
