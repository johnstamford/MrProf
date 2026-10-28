"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { loadSession } from "../../lib/session";

type Question = {
  turn: number;
  objective: string;
  reason: string;
  text: string;
  model_provider: string;
  model_name: string;
  skill_version: string;
  topic_version: string;
};

type NextState = {
  version: number;
  status: string;
  turns_answered: number;
  question: Question | null;
  completed: boolean;
};

type BriefingGap = { area: string; status: string };
type BriefingCoverage = { objective: string; title: string; status: string; turns: number[]; note: string };
type BriefingContradiction = { family: string; areas: string[]; present_turn: number; denial_turn: number; clarified: boolean; note: string };

type Briefing = {
  report_version: number;
  banner: string;
  completion_note: string;
  turns_answered: number;
  statements: { turn: number; question: string; answer: string }[];
  system_notes: { turn: number; objective: string; reason: string }[];
  coverage: BriefingCoverage[];
  contradictions: BriefingContradiction[];
  gaps: BriefingGap[];
};

function draftKey(code: string, turn: number) {
  return `mrprof.draft.${code}.${turn}`;
}

export default function InterviewPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<"loading" | "ready" | "done">("loading");
  const [version, setVersion] = useState<number | null>(null);
  const [question, setQuestion] = useState<Question | null>(null);
  const [turnsAnswered, setTurnsAnswered] = useState(0);
  const [answer, setAnswer] = useState("");
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const authHeaders = useCallback(() => {
    const session = loadSession();
    return session ? { session, headers: { Authorization: `Bearer ${session.password}` } } : null;
  }, []);

  function failureMessage(res: Response, fallback: string): Promise<string> {
    return (async () => {
      try {
        const body = await res.json();
        const detail = (body as { detail?: string | { message?: string } }).detail;
        if (typeof detail === "string") return detail;
        if (detail?.message) return detail.message;
      } catch {
        // Non-JSON error body; fall through to the generic message.
      }
      return `${fallback} (status ${res.status})`;
    })();
  }

  const load = useCallback(
    async (depth = 0) => {
      const auth = authHeaders();
      if (!auth) {
        router.replace("/start");
        return;
      }
    const { session, headers } = auth;
    const base = `/api/assessments/${encodeURIComponent(session.code)}`;
    setError("");
    const me = await fetch(base, { headers });
    if (me.status === 401) {
      setError("wrong assessment code or password — please start again");
      setPhase("loading");
      return;
    }
    if (!me.ok) {
      setError("could not load your assessment — please try again");
      return;
    }
    const nextRes = await fetch(`${base}/interview/next`, { headers });
    if (nextRes.status === 404) {
      // Interview never started: begin it, then show Q1.
      const assessed = await me.json();
      const key =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `key-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const started = await fetch(`${base}/interview/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ base_version: assessed.version, idempotency_key: key }),
      });
      if (started.status === 409) {
        if (depth < 2) return load(depth + 1);
        setError("the interview changed while loading — please try again");
        return;
      }
      if (!started.ok) {
        setError(await failureMessage(started, "could not start the interview"));
        return;
      }
      const body = await started.json();
      setVersion(body.version as number);
      setQuestion(body.question as Question);
      setTurnsAnswered(0);
      setPhase("ready");
      return;
    }
    if (!nextRes.ok) {
      setError("could not load the interview — please try again");
      return;
    }
    const state = (await nextRes.json()) as NextState;
    setVersion(state.version);
    setTurnsAnswered(state.turns_answered);
    if (state.completed || !state.question) {
      const rep = await fetch(`${base}/interview/report`, { headers });
      if (!rep.ok) {
        setError("interview finished but the briefing is missing — please try again");
        return;
      }
      setBriefing((await rep.json()) as Briefing);
      setPhase("done");
      return;
    }
    setQuestion(state.question);
    setPhase("ready");
  }, [authHeaders, router]);

  useEffect(() => {
    void load();
  }, [load]);

  // Restore an unsent draft for this turn (refresh-safe typing).
  useEffect(() => {
    const session = loadSession();
    if (!session || !question) return;
    try {
      setAnswer(sessionStorage.getItem(draftKey(session.code, question.turn)) ?? "");
    } catch {
      // Storage unavailable; start with an empty box.
    }
  }, [question?.turn]);

  function onType(value: string) {
    setAnswer(value);
    const session = loadSession();
    if (!session || !question) return;
    try {
      sessionStorage.setItem(draftKey(session.code, question.turn), value);
    } catch {
      // Draft persistence is best-effort.
    }
  }

  function clearDraft(turn: number) {
    const session = loadSession();
    if (!session) return;
    try {
      sessionStorage.removeItem(draftKey(session.code, turn));
    } catch {
      // Ignore.
    }
  }

  async function submit() {
    const auth = authHeaders();
    if (!auth || !question || version === null) {
      setError("session lost — please start again");
      return;
    }
    const text = answer.trim();
    if (!text) {
      setError("please write an answer before continuing");
      return;
    }
    setError("");
    setSaving(true);
    try {
      const { session, headers } = auth;
      const base = `/api/assessments/${encodeURIComponent(session.code)}`;
      const post = async (v: number, key: string) =>
        fetch(`${base}/interview/answer`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...headers },
          body: JSON.stringify({ answer_text: text, base_version: v, idempotency_key: key }),
        });
      const newKey = () =>
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `key-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      let res = await post(version, newKey());
      if (res.status === 409) {
        // State moved on underneath us — reload and retry once.
        await load();
        const fresh = loadSession();
        if (!fresh) return;
        const retryVersion = (
          (await (await fetch(base, { headers })).json()) as { version: number }
        ).version;
        res = await post(retryVersion, newKey());
      }
      if (!res.ok) {
        setError("could not save — please try again");
        return;
      }
      const body = await res.json();
      clearDraft(question.turn);
      setAnswer("");
      setVersion(body.version as number);
      setTurnsAnswered(body.turn_answered as number);
      if (body.completed) {
        const rep = await fetch(`${base}/interview/report`, { headers });
        if (!rep.ok) {
          setError("saved, but the briefing is missing — please reload");
          return;
        }
        setBriefing((await rep.json()) as Briefing);
        setPhase("done");
        return;
      }
      setQuestion(body.question as Question);
    } finally {
      setSaving(false);
    }
  }

  if (phase === "loading") {
    return (
      <main>
        <h1>MrProf — interview</h1>
        <p role="status">Starting your interview — this can take a few seconds…</p>
        {error && (
          <div>
            <p role="alert">{error}</p>
            <button onClick={() => { setError(""); void load(); }}>Try again</button>
          </div>
        )}
      </main>
    );
  }

  if (phase === "done" && briefing) {
    return (
      <main>
        <h1>MrProf — interview briefing</h1>
        <p>{briefing.banner}</p>
        <section>
          <h2>What you reported</h2>
          <ol>
            {briefing.statements.map((s) => (
              <li key={s.turn}>
                <p>Q{s.turn}: {s.question}</p>
                <p>A{s.turn}: {s.answer}</p>
              </li>
            ))}
          </ol>
        </section>
        <section>
          <h2>How each question was chosen (system notes — not what you said)</h2>
          <ul>
            {briefing.system_notes.map((n) => (
              <li key={n.turn}>
                Q{n.turn}: topic <code>{n.objective}</code> — {n.reason}
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h2>Coverage — what was explored</h2>
          <ul>
            {(briefing.coverage ?? []).map((c) => (
              <li key={c.objective}>{c.title} — {c.status} ({c.note}{c.turns.length ? `, turns ${c.turns.join(", ")}` : ""})</li>
            ))}
          </ul>
        </section>
        {(briefing.contradictions ?? []).length > 0 && (
          <section>
            <h2>Accounts in tension (both retained)</h2>
            <ul>
              {briefing.contradictions.map((c) => (
                <li key={c.family}>
                  {c.areas.join(" / ")}: turn {c.denial_turn} reported no difficulty, turn {c.present_turn} described difficulty — {c.note}
                </li>
              ))}
            </ul>
          </section>
        )}
        <section>
          <h2>Not covered in this interview</h2>
          <p>{briefing.completion_note}</p>
          <ul>
            {briefing.gaps.map((g) => (
              <li key={g.area}>{g.area} — {g.status}</li>
            ))}
          </ul>
        </section>
        <p>
          <button onClick={() => router.push("/report")}>← Back to screening report</button>{" "}
          <button onClick={() => router.push("/start")}>Start / resume page</button>
        </p>
      </main>
    );
  }

  return (
    <main>
      <h1>MrProf — interview</h1>
      <p>Draft interview, one question at a time — there is no time limit. Topics are a first draft, not a clinical assessment.</p>
      <p>The more detail you give — a few sentences with a concrete example — the better your briefing will be. Short answers are still accepted: a plain no, or “I can’t remember”, is a valid answer.</p>
      <p>Question {question ? question.turn : "…"} · {turnsAnswered} answered so far</p>
      {question && (
        <section>
          <p><strong>{question.text}</strong></p>
          <label>
            Your answer{" "}
            <textarea value={answer} onChange={(e) => onType(e.target.value)} rows={4} cols={60} disabled={saving} />
          </label>
          <p>A few sentences with an example make for a much better briefing than a few words.</p>
          <div>
            <button onClick={submit} disabled={saving}>{saving ? "Thinking…" : "Save and continue →"}</button>
          </div>
          {saving && <p role="status">Waiting for the next question — usually a few seconds…</p>}
        </section>
      )}
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
