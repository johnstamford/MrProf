"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export const SESSION_CODE_KEY = "mrprof.assessment_code";
export const SESSION_PASSWORD_KEY = "mrprof.assessment_password";

export function saveSession(code: string, password: string) {
  try {
    sessionStorage.setItem(SESSION_CODE_KEY, code.toUpperCase());
    sessionStorage.setItem(SESSION_PASSWORD_KEY, password);
  } catch {
    // Private-mode storage may throw; manual entry remains as fallback.
  }
}

export function loadSession(): { code: string; password: string } | null {
  try {
    const code = sessionStorage.getItem(SESSION_CODE_KEY) ?? "";
    const password = sessionStorage.getItem(SESSION_PASSWORD_KEY) ?? "";
    return code && password ? { code, password } : null;
  } catch {
    return null;
  }
}

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
    goToScreening(body.assessment_id, newPassword);
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
    goToScreening(code, password);
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
            <p>Taking you to the screening questions…</p>
          </div>
        )}
      </section>
      <section>
        <h2>Resume</h2>
        <label>Assessment code <input value={id} onChange={(e) => setId(e.target.value)} /></label>{" "}
        <label>Password <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" /></label>{" "}
        <button onClick={resume}>Resume</button>
        {fetched && <p>Stage: {fetched.stage}, status: {fetched.status}, version: {fetched.version}. Taking you on…</p>}
      </section>
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
