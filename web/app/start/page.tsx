"use client";

import { useState } from "react";

type Created = { assessment_id: string; access_secret: string; version: number; stage: string };
type Fetched = { assessment_id: string; version: number; stage: string; status: string };

export default function StartPage() {
  const [created, setCreated] = useState<Created | null>(null);
  const [id, setId] = useState("");
  const [secret, setSecret] = useState("");
  const [fetched, setFetched] = useState<Fetched | null>(null);
  const [error, setError] = useState("");

  async function start() {
    setError("");
    const res = await fetch("/api/assessments", { method: "POST" });
    if (!res.ok) return setError(`start failed: ${res.status}`);
    const body = (await res.json()) as Created;
    setCreated(body);
    localStorage.setItem(`mrprof:${body.assessment_id}`, body.access_secret);
  }

  async function resume() {
    setError("");
    setFetched(null);
    const key = secret || localStorage.getItem(`mrprof:${id}`) || "";
    const res = await fetch(`/api/assessments/${encodeURIComponent(id)}`, {
      headers: { Authorization: `Bearer ${key}` },
    });
    if (!res.ok) return setError(`resume failed: ${res.status}`);
    setFetched((await res.json()) as Fetched);
  }

  return (
    <main>
      <h1>MrProf — start or resume</h1>
      <section>
        <h2>New assessment</h2>
        <button onClick={start}>Start</button>
        {created && (
          <div>
            <p>Save your access secret now — it is shown once and cannot be recovered in this MVP.</p>
            <p>ID: <code>{created.assessment_id}</code></p>
            <p>Secret: <code>{created.access_secret}</code></p>
          </div>
        )}
      </section>
      <section>
        <h2>Resume</h2>
        <label>Assessment ID <input value={id} onChange={(e) => setId(e.target.value)} /></label>{" "}
        <label>Secret <input value={secret} onChange={(e) => setSecret(e.target.value)} type="password" /></label>{" "}
        <button onClick={resume}>Resume</button>
        {fetched && <p>Stage: {fetched.stage}, status: {fetched.status}, version: {fetched.version}</p>}
      </section>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
