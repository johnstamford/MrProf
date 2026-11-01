"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { loadSession } from "../../lib/session";
import BriefingView, { type Briefing } from "../../components/briefing";
import RiskNote from "../../components/risk-note";

type Question = {
  turn: number;
  objective: string;
  reason: string;
  text: string;
  model_provider: string;
  model_name: string;
  skill_version: string;
  topic_version: string;
  effort_nudge?: boolean;
};

type NextState = {
  version: number;
  status: string;
  turns_answered: number;
  question: Question | null;
  completed: boolean;
};

function draftKey(code: string, turn: number) {
  return `mrprof.draft.${code}.${turn}`;
}

export default function InterviewPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<"loading" | "ready" | "assessing" | "done">("loading");
  const [version, setVersion] = useState<number | null>(null);
  const [question, setQuestion] = useState<Question | null>(null);
  const [turnsAnswered, setTurnsAnswered] = useState(0);
  const [answer, setAnswer] = useState("");
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [stage, setStage] = useState(0);
  const [mode, setMode] = useState<"full" | "taster">("full");
  const [assessProgress, setAssessProgress] = useState<{ done: number; total: number } | null>(null);

  const STAGES = ["Saving your answer…", "Thinking…", "Preparing the next question…"];

  // Advance the thinking-panel copy on a timer so the screen feels alive
  // even when the proxy buffers the SSE stream and all events arrive at once.
  // Stream events (when they arrive incrementally) jump the stage forward.
  useEffect(() => {
    if (!saving) return;
    const id = setInterval(() => setStage((s) => Math.min(s + 1, STAGES.length - 1)), 5000);
    return () => clearInterval(id);
  }, [saving]);

  type StreamDone = {
    version: number;
    turn_answered: number;
    status: string;
    question: Question | null;
    completed: boolean;
    replayed?: boolean;
    mode?: string;
  };

  function parseSseBuffer(buf: string): { events: { name: string; data: string }[]; rest: string } {
    const events: { name: string; data: string }[] = [];
    const parts = buf.split("\n\n");
    const rest = parts.pop() ?? "";
    for (const part of parts) {
      const lines = part.split("\n");
      let name = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length) events.push({ name, data: dataLines.join("\n") });
    }
    return { events, rest };
  }

  async function postStream(
    base: string,
    headers: Record<string, string>,
    text: string,
    v: number,
    key: string,
    onStage: (stage: string) => void,
  ): Promise<StreamDone> {
    const res = await fetch(`${base}/interview/answer/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...headers },
      body: JSON.stringify({ answer_text: text, base_version: v, idempotency_key: key }),
    });
    const ctype = res.headers.get("content-type") ?? "";
    if (!res.ok || !res.body || !ctype.includes("text/event-stream")) {
      throw new Error(`stream-unavailable:${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const { events, rest } = parseSseBuffer(buf);
      buf = rest;
      for (const ev of events) {
        if (ev.name === "received") onStage("saved");
        else if (ev.name === "phrasing") onStage("phrasing");
        else if (ev.name === "assessing") onStage("assessing");
        else if (ev.name === "done") return JSON.parse(ev.data) as StreamDone;
        else if (ev.name === "error") throw new Error(`stream-error:${ev.data}`);
      }
    }
    const { events } = parseSseBuffer(buf + "\n\n");
    for (const ev of events) {
      if (ev.name === "done") return JSON.parse(ev.data) as StreamDone;
      if (ev.name === "error") throw new Error(`stream-error:${ev.data}`);
    }
    throw new Error("stream-incomplete");
  }

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
      const wantTaster =
        typeof window !== "undefined" &&
        new URLSearchParams(window.location.search).get("mode") === "taster";
      const key =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `key-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const started = await fetch(`${base}/interview/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ base_version: assessed.version, idempotency_key: key, mode: wantTaster ? "taster" : "full" }),
      });
      if (started.status === 409) {
        if (depth < 2) return load(depth + 1);
        setError("the interview changed while loading — please try again");
        return;
      }
      if (started.status === 422) {
        setError("could not start the interview — please try again");
        return;
      }
      if (!started.ok) {
        setError(await failureMessage(started, "could not start the interview"));
        return;
      }
      const body = await started.json();
      setMode(body.mode === "taster" ? "taster" : "full");
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
    const state = (await nextRes.json()) as NextState & { mode?: string };
    setMode(state.mode === "taster" ? "taster" : "full");
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

  const pollAssessment = useCallback(async (): Promise<boolean> => {
    const auth = authHeaders();
    if (!auth) {
      router.replace("/start");
      return false;
    }
    const { session, headers } = auth;
    const base = `/api/assessments/${encodeURIComponent(session.code)}`;
    for (let i = 0; i < 40; i++) {
      const res = await fetch(`${base}/interview/assessment`, { headers });
      if (!res.ok) {
        setError("could not check the assessment — please try again");
        return false;
      }
      const body = await res.json();
      if (body.status === "followup" && body.question) {
        const next = await fetch(`${base}/interview/next`, { headers });
        if (!next.ok) {
          setError("could not load the follow-up question — please try again");
          return false;
        }
        const state = (await next.json()) as NextState;
        setVersion(state.version);
        setTurnsAnswered(state.turns_answered);
        setQuestion(state.question);
        setAssessProgress(null);
        setPhase("ready");
        return true;
      }
      if (body.status === "complete") {
        const rep = await fetch(`${base}/interview/report`, { headers });
        if (!rep.ok) {
          setError("interview finished but the briefing is missing — please reload");
          return false;
        }
        setBriefing((await rep.json()) as Briefing);
        setAssessProgress(null);
        setPhase("done");
        return true;
      }
      if (body.status !== "assessing" && body.status !== "processing") {
        setError(`unexpected interview status (${body.status}) — please reload`);
        return false;
      }
      if (typeof body.extract_total === "number" && body.extract_total > 0) {
        setAssessProgress({ done: body.extracted ?? 0, total: body.extract_total });
      }
      await new Promise((r) => setTimeout(r, 3000));
    }
    setError("the assessment is taking too long — please reload to check again");
    return false;
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
    setStage(0);
    const stageFor: Record<string, number> = { saved: 0, phrasing: 1, assessing: 2 };
    try {
      const { session, headers } = auth;
      const base = `/api/assessments/${encodeURIComponent(session.code)}`;
      const post = (v: number, key: string) =>
        fetch(`${base}/interview/answer`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...headers },
          body: JSON.stringify({ answer_text: text, base_version: v, idempotency_key: key }),
        });
      const newKey = () =>
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `key-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const applyDone = async (body: StreamDone) => {
        clearDraft(question.turn);
        setAnswer("");
        if (body.mode === "taster" || body.mode === "full") setMode(body.mode);
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
        if (body.question) {
          setQuestion(body.question as Question);
          // Best-effort: have the server phrase the following question while
          // the user reads this one. Failures fall back to the live path.
          void fetch(`${base}/interview/prefetch`, { method: "POST", headers }).catch(() => {});
          return;
        }
        // No question yet: the batch assessment is running. Poll for the
        // follow-up round or the final briefing.
        setPhase("assessing");
        setSaving(false);
        await pollAssessment();
      };

      // Stream first for staged progress; fall back to the sync endpoint.
      const streamKey = newKey();
      try {
        const done = await postStream(base, headers, text, version, streamKey, (s) => {
          const n = stageFor[s];
          if (n !== undefined) setStage((cur) => Math.max(cur, n));
        });
        await applyDone(done);
        return;
      } catch (e) {
        const msg = e instanceof Error ? e.message : "";
        if (msg.startsWith("stream-error:")) {
          try {
            const payload = JSON.parse(msg.slice("stream-error:".length)) as {
              error?: string;
              current_version?: number;
            };
            if (payload.error === "version_conflict") {
              await load();
              const fresh = loadSession();
              if (!fresh) return;
              const retryVersion = (
                (await (await fetch(base, { headers })).json()) as { version: number }
              ).version;
              const res = await post(retryVersion, newKey());
              if (!res.ok) {
                setError("could not save — please try again");
                return;
              }
              await applyDone((await res.json()) as StreamDone);
              return;
            }
            setError("could not save — please try again");
            return;
          } catch {
            // Malformed error payload: fall through to sync fallback.
          }
        }
        // stream-unavailable / stream-incomplete / network: sync fallback below.
      }

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
      const body = (await res.json()) as StreamDone;
      await applyDone(body);
      return;
    } finally {
      setSaving(false);
    }
  }

  if (phase === "loading") {
    return (
      <div className="mx-auto max-w-2xl pt-10">
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Interview</h1>
        <div className="mt-6 rounded-2xl border border-line bg-card p-6 text-center">
          <div className="mrprof-spinner mx-auto" role="status" aria-label="Starting your interview" />
          <p role="status" className="mt-4 text-ink-soft">Starting your interview — this can take a few seconds…</p>
          {error && (
            <div className="mt-4">
              <p role="alert" className="text-sm font-medium text-tension">{error}</p>
              <button
                onClick={() => { setError(""); void load(); }}
                className="mt-3 rounded-full border border-primary px-5 py-2 text-sm font-semibold text-primary hover:bg-primary-tint"
              >
                Try again
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (phase === "assessing") {
    const p = assessProgress;
    const msg =
      p && p.total > 0 && p.done < p.total
        ? `Reviewing your answers… (${p.done} of ${p.total} checked)`
        : p && p.total > 0
          ? "Deciding what to ask next…"
          : "Reviewing your answers to decide what to ask next…";
    return (
      <div className="mx-auto max-w-2xl pt-10">
        <h1 className="font-serif text-3xl font-semibold tracking-tight">Interview</h1>
        <div className="mt-6 rounded-2xl border border-line bg-card p-6 text-center">
          <div className="mrprof-spinner mx-auto" role="status" aria-label={msg} />
          <p role="status" className="mt-4 font-semibold">{msg}</p>
          <p className="mt-2 text-sm text-ink-soft">Your answers are saved — this usually takes under a minute…</p>
          <div className="mt-4 text-left"><RiskNote /></div>
          {error && (
            <div className="mt-4">
              <p role="alert" className="text-sm font-medium text-tension">{error}</p>
              <button
                onClick={() => { setError(""); setAssessProgress(null); void pollAssessment(); }}
                className="mt-3 rounded-full border border-primary px-5 py-2 text-sm font-semibold text-primary hover:bg-primary-tint"
              >
                Check again
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (phase === "done" && briefing) {
    return (
      <div className="pt-8 sm:pt-12">
        <h1 className="font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
          Your interview briefing
        </h1>
        <div className="mt-4">
          <BriefingView briefing={briefing} />
        </div>
        <div className="no-print mt-4"><RiskNote /></div>
        <p className="no-print mt-8 flex flex-wrap gap-3 border-t border-line pt-6">
          <button
            onClick={() => router.push("/report")}
            className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card px-5 py-2.5 text-sm font-semibold text-ink-soft hover:border-primary hover:text-primary"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden /> Back to screening report
          </button>
          <button
            onClick={() => router.push("/start")}
            className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card px-5 py-2.5 text-sm font-semibold text-ink-soft hover:border-primary hover:text-primary"
          >
            Start / resume page <ArrowRight className="h-4 w-4" aria-hidden />
          </button>
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl pt-10 sm:pt-14">
      <h1 className="font-serif text-3xl font-semibold tracking-tight">Interview</h1>
      <p className="mt-3 text-sm leading-relaxed text-ink-soft sm:text-base">
        One question at a time — there is no time limit, and topics are a first draft,
        not a clinical assessment. Short answers are accepted: a plain no, or
        “I can’t remember”, is a valid answer.
      </p>
      {mode === "taster" && (
        <p role="note" className="mt-3 rounded-xl border border-primary/30 bg-primary-tint px-4 py-2.5 text-sm font-medium text-primary-deep">
          Short taster — about 6 questions. Anything not covered is marked as a gap in your briefing.
        </p>
      )}
      <RiskNote />
      <p className="mt-4 text-sm font-medium text-ink-soft" role="status">
        Question {question ? question.turn : "…"} · {turnsAnswered} answered so far
      </p>
      {saving ? (
        <section aria-live="polite" className="mt-4 rounded-2xl border border-line bg-card p-6 text-center">
          <div className="mrprof-spinner mx-auto" role="status" aria-label={STAGES[stage]} />
          <p role="status" className="mt-4 font-semibold">{STAGES[stage]}</p>
          <p className="mt-2 text-primary" aria-hidden>
            {[0, 1, 2].map((i) => (
              <span key={i}>{i <= stage ? "● " : "○ "}</span>
            ))}
          </p>
          <p className="mt-2 text-sm text-ink-soft">Your answer is safe — you can wait, this usually takes a few seconds…</p>
        </section>
      ) : (
      question && (
        <section aria-label={`Question ${question.turn}`} className="mt-4 rounded-2xl border border-line bg-card p-5 sm:p-8">
          {question.effort_nudge && (
            <p role="note" className="mb-4 rounded-xl border border-uncertain/40 bg-uncertain-tint px-4 py-3 text-sm leading-relaxed">
              <strong>A quick note before this one:</strong> to get the most out of
              your briefing, concrete detail helps a lot — one example of when this
              happened and what followed. Short answers are still accepted, and
              “I can’t remember” is always a valid answer.
            </p>
          )}
          <p className="font-serif text-xl font-semibold leading-snug sm:text-2xl">{question.text}</p>
          <label className="mt-5 block">
            <span className="text-sm font-semibold">Your answer</span>
            <textarea
              value={answer}
              onChange={(e) => onType(e.target.value)}
              rows={4}
              cols={60}
              className="autogrow mt-2 w-full rounded-2xl border border-line bg-paper px-4 py-3 text-base leading-relaxed"
              placeholder="A few sentences with an example make for a much better briefing than a few words."
            />
          </label>
          <div className="mt-4">
            <button
              onClick={submit}
              className="inline-flex items-center gap-1.5 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-white hover:bg-primary-deep"
            >
              Save and continue <ArrowRight className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </section>
      )
      )}
      {error && <p role="alert" className="mt-4 rounded-xl border border-tension/40 bg-tension-tint px-4 py-3 text-sm font-medium">{error}</p>}
    </div>
  );
}
