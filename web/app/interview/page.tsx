"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { loadSession } from "../../lib/session";
import BriefingView, { type Briefing } from "../../components/briefing";
import ProgressRail from "../../components/progress-rail";
import { RiskLink } from "../../components/risk-note";

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

type ReviewObservation = {
  turn: number;
  obs_index: number;
  assertion: string;
  quote: string;
  segment_id: string;
  line: number | null;
  note: string;
  user_correction: string;
};

type ReviewTopic = {
  objective: string;
  title: string;
  status: string;
  label: string;
  note: string;
  observations: ReviewObservation[];
};

type ReviewState = {
  version: number;
  status: string;
  mode: string;
  turns_answered: number;
  topics: ReviewTopic[];
};

type Topup = { objective: string; title: string; question: string; dimension: string };

function draftKey(code: string, turn: number) {
  return `mrprof.draft.${code}.${turn}`;
}

export default function InterviewPage() {
  const router = useRouter();
  const [phase, setPhase] = useState<"loading" | "ready" | "assessing" | "review" | "done">("loading");
  const [review, setReview] = useState<ReviewState | null>(null);
  const [topups, setTopups] = useState<Topup[]>([]);
  const [topupAnswers, setTopupAnswers] = useState<Record<string, string>>({});
  const [addOpen, setAddOpen] = useState<Record<string, boolean>>({});
  const [addText, setAddText] = useState<Record<string, string>>({});
  const [correctOpen, setCorrectOpen] = useState<Record<string, boolean>>({});
  const [correctText, setCorrectText] = useState<Record<string, string>>({});
  const [reviewMsg, setReviewMsg] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [version, setVersion] = useState<number | null>(null);
  const [question, setQuestion] = useState<Question | null>(null);
  const [turnsAnswered, setTurnsAnswered] = useState(0);
  const [answer, setAnswer] = useState("");
  const [correcting, setCorrecting] = useState(false);
  const [correction, setCorrection] = useState("");
  const [correctMsg, setCorrectMsg] = useState("");
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [stage, setStage] = useState(0);
  const [mode, setMode] = useState<"full" | "taster">("full");
  const [assessProgress, setAssessProgress] = useState<{ done: number; total: number } | null>(null);
  const [reviewingKey, setReviewingKey] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  // Reviewer controls live only in explicit reviewer mode (?review=1); the
  // patient's own briefing never shows Accept/Amend/Reject machinery.
  const [reviewerMode, setReviewerMode] = useState(false);
  useEffect(() => {
    try {
      setReviewerMode(new URLSearchParams(window.location.search).get("review") === "1");
    } catch {
      setReviewerMode(false);
    }
  }, []);

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

  const newKey = () =>
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `key-${Date.now()}-${Math.random().toString(36).slice(2)}`;

  const loadReview = useCallback(async (): Promise<boolean> => {
    const auth = authHeaders();
    if (!auth) {
      router.replace("/start");
      return false;
    }
    const { session, headers } = auth;
    const base = `/api/assessments/${encodeURIComponent(session.code)}`;
    const res = await fetch(`${base}/interview/review`, { headers });
    if (res.status === 404) return false;
    if (!res.ok) {
      setError("could not load the review step — please try again");
      return false;
    }
    const body = (await res.json()) as ReviewState;
    setMode(body.mode === "taster" ? "taster" : "full");
    setVersion(body.version);
    setTurnsAnswered(body.turns_answered);
    setReview(body);
    setTopups([]);
    setReviewMsg("");
    setAssessProgress(null);
    setPhase("review");
    return true;
  }, [authHeaders, router]);

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
    if (state.status === "review") {
      // WS1: gathering done, briefing deferred until the user confirms.
      await loadReview();
      return;
    }
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
  }, [authHeaders, router, loadReview]);

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
      if (body.status === "review") {
        // WS1: gathering done — the user checks the review step before any
        // briefing is generated.
        await loadReview();
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
  }, [authHeaders, router, loadReview]);

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

  async function submitCorrection() {
    const auth = authHeaders();
    if (!auth || version === null || turnsAnswered < 1) return;
    const text = correction.trim();
    if (!text) {
      setError("please write your correction before saving");
      return;
    }
    setError("");
    setCorrectMsg("");
    try {
      const { session, headers } = auth;
      const base = `/api/assessments/${encodeURIComponent(session.code)}`;
      const key =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `key-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const res = await fetch(`${base}/interview/correct`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({
          corrects_turn: turnsAnswered,
          answer_text: text,
          base_version: version,
          idempotency_key: key,
        }),
      });
      if (res.status === 409) {
        setError("already saved — please reload to see the latest state");
        return;
      }
      if (!res.ok) {
        setError("could not save the correction — please try again");
        return;
      }
      const body = (await res.json()) as { version: number };
      setVersion(body.version);
      setCorrecting(false);
      setCorrection("");
      setCorrectMsg("Correction saved — your original answer is kept, and the correction will appear with your briefing.");
    } catch {
      setError("could not save the correction — please try again");
    }
  }

  async function submitReviewAdd(objective: string, text: string) {
    const auth = authHeaders();
    if (!auth || version === null) return;
    const clean = text.trim();
    if (!clean) {
      setError("please write your addition before saving");
      return;
    }
    setError("");
    setReviewMsg("");
    try {
      const { session, headers } = auth;
      const base = `/api/assessments/${encodeURIComponent(session.code)}`;
      const res = await fetch(`${base}/interview/review/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ objective, answer_text: clean, base_version: version, idempotency_key: newKey() }),
      });
      if (res.status === 409) {
        setError("already saved — reloading the review step");
        await loadReview();
        return;
      }
      if (!res.ok) {
        setError("could not save your addition — please try again");
        return;
      }
      setAddText((m) => ({ ...m, [objective]: "" }));
      setAddOpen((m) => ({ ...m, [objective]: false }));
      setTopupAnswers((m) => {
        const c = { ...m };
        delete c[objective];
        return c;
      });
      setReviewMsg("Saved — your addition will appear as cited evidence in your briefing.");
      await loadReview();
    } catch {
      setError("could not save your addition — please try again");
    }
  }

  async function submitReviewCorrect(turn: number, obsIndex: number, text: string) {
    const auth = authHeaders();
    if (!auth || version === null) return;
    const clean = text.trim();
    if (!clean) {
      setError("please write your correction before saving");
      return;
    }
    const key = `${turn}:${obsIndex}`;
    setError("");
    setReviewMsg("");
    try {
      const { session, headers } = auth;
      const base = `/api/assessments/${encodeURIComponent(session.code)}`;
      const res = await fetch(`${base}/interview/review/correct`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ turn, obs_index: obsIndex, answer_text: clean, base_version: version, idempotency_key: newKey() }),
      });
      if (res.status === 409) {
        setError("already saved — reloading the review step");
        await loadReview();
        return;
      }
      if (!res.ok) {
        setError("could not save your correction — please try again");
        return;
      }
      setCorrectText((m) => ({ ...m, [key]: "" }));
      setCorrectOpen((m) => ({ ...m, [key]: false }));
      setReviewMsg("Saved — your correction will appear alongside the original note.");
      await loadReview();
    } catch {
      setError("could not save your correction — please try again");
    }
  }

  async function loadTopups() {
    const auth = authHeaders();
    if (!auth || topups.length > 0) return;
    setError("");
    try {
      const { session, headers } = auth;
      const base = `/api/assessments/${encodeURIComponent(session.code)}`;
      const res = await fetch(`${base}/interview/review/topups`, { method: "POST", headers });
      if (!res.ok) {
        setError("could not load follow-ups — you can still confirm below");
        return;
      }
      setTopups(((await res.json()) as { topups: Topup[] }).topups ?? []);
    } catch {
      setError("could not load follow-ups — you can still confirm below");
    }
  }

  async function submitConfirm() {
    const auth = authHeaders();
    if (!auth || version === null) return;
    setError("");
    setConfirming(true);
    try {
      const { session, headers } = auth;
      const base = `/api/assessments/${encodeURIComponent(session.code)}`;
      const res = await fetch(`${base}/interview/review/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ base_version: version, idempotency_key: newKey() }),
      });
      if (res.status === 409) {
        setConfirming(false);
        setError("already confirmed — reloading");
        await load();
        return;
      }
      if (!res.ok) {
        setConfirming(false);
        setError("could not build your briefing — please try again");
        return;
      }
      const rep = await fetch(`${base}/interview/report`, { headers });
      if (!rep.ok) {
        setConfirming(false);
        setError("confirmed, but the briefing is missing — please reload");
        return;
      }
      setBriefing((await rep.json()) as Briefing);
      setReview(null);
      setConfirming(false);
      setPhase("done");
    } catch {
      setConfirming(false);
      setError("could not build your briefing — please try again");
    }
  }

  async function continueToFull() {
    const auth = authHeaders();
    if (!auth) return;
    setError("");
    try {
      const { session, headers } = auth;
      const base = `/api/assessments/${encodeURIComponent(session.code)}`;
      const nxt = await fetch(`${base}/interview/next`, { headers });
      if (!nxt.ok) {
        setError("could not continue — please reload");
        return;
      }
      const state = (await nxt.json()) as NextState;
      const res = await fetch(`${base}/interview/continue`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ base_version: state.version, idempotency_key: newKey() }),
      });
      if (!res.ok) {
        setError("could not continue — please try again");
        return;
      }
      const body = (await res.json()) as { version: number; question: Question | null; mode: string };
      setMode(body.mode === "taster" ? "taster" : "full");
      setVersion(body.version);
      setQuestion(body.question);
      setTurnsAnswered(0);
      setBriefing(null);
      setPhase("ready");
    } catch {
      setError("could not continue — please try again");
    }
  }

  async function submit(preset?: string) {
    const auth = authHeaders();
    if (!auth || !question || version === null) {
      setError("session lost — please start again");
      return;
    }
    const text = (preset ?? answer).trim();
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
    const glance = (() => {
      const groups: Record<string, string[]> = {};
      for (const t of briefing.topics ?? []) {
        const key = (t.label || t.status || "").toLowerCase();
        (groups[key] ??= []).push(t.title);
      }
      return groups;
    })();
    return (
      <div className="pt-8 sm:pt-12">
        <h1 className="font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
          Your interview briefing
        </h1>
        {!reviewerMode && (
          <section aria-label="Your account at a glance" className="no-print mt-4 max-w-3xl rounded-2xl border border-line bg-card p-5">
            <h2 className="font-serif text-lg font-semibold">Your account at a glance</h2>
            <p className="mt-1 text-sm text-ink-faint">
              A plain recap of what you reported — no interpretation. The full
              evidence is below.
            </p>
            {briefing.screening != null && briefing.screening.score != null && (
              <p className="mt-2 text-sm leading-relaxed">
                <span className="font-medium">Screening: </span>
                {briefing.screening.score}/6 ({briefing.screening.scoring_method}
                {briefing.screening.positive == null
                  ? ""
                  : briefing.screening.positive
                    ? ", above threshold — further assessment may be useful"
                    : ", below threshold — does not exclude ADHD or other conditions"}
                ).
              </p>
            )}
            {(glance["reported"] ?? []).length > 0 && (
              <p className="mt-2 text-sm leading-relaxed">
                <span className="font-medium">You described experiences with: </span>
                {(glance["reported"] ?? []).join("; ")}.
              </p>
            )}
            {(glance["explicitly denied"] ?? []).length > 0 && (
              <p className="mt-2 text-sm leading-relaxed">
                <span className="font-medium">You said {(glance["explicitly denied"] ?? []).length === 1 ? "this was" : "these were"} not an issue for you: </span>
                {(glance["explicitly denied"] ?? []).join("; ")}.
              </p>
            )}
            {(glance["uncertain"] ?? []).length > 0 && (
              <p className="mt-2 text-sm leading-relaxed">
                <span className="font-medium">You weren&apos;t sure about: </span>
                {(glance["uncertain"] ?? []).join("; ")}.
              </p>
            )}
            {((glance["limited"] ?? []).length > 0 || (glance["not covered"] ?? []).length > 0) && (
              <p className="mt-2 text-sm leading-relaxed">
                <span className="font-medium">Limited or not covered: </span>
                {[...(glance["limited"] ?? []), ...(glance["not covered"] ?? [])].join("; ")}.
              </p>
            )}
            <p className="mt-3 text-sm leading-relaxed text-ink-soft">
              Take both reports to your appointment — every point links to your
              line-numbered transcript so a clinician can check it.
            </p>
          </section>
        )}
        {reviewerMode && (
          <p role="note" className="mt-2 max-w-3xl rounded-xl border border-line bg-cream px-4 py-2.5 text-sm">
            Reviewer mode — Accept / Amend / Reject controls are enabled. They write
            only to evidence review state, never to the transcript or screening answers.
          </p>
        )}
        {briefing.mode === "taster" && !reviewerMode && (
          <div role="note" className="no-print mt-4 max-w-3xl rounded-2xl border border-primary/30 bg-primary-tint px-4 py-3.5">
            <p className="text-sm font-semibold text-primary-deep">This was the short taster — 8 topics were not reached.</p>
            <p className="mt-1 text-sm text-primary-deep">
              Continue to the full interview on the same assessment: your answers carry
              over, and you will check a fresh review before briefing v2.
            </p>
            <button
              onClick={continueToFull}
              className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-white hover:bg-primary-deep"
            >
              Continue to the full interview <ArrowRight className="h-4 w-4" aria-hidden />
            </button>
          </div>
        )}
        <div className="mt-4">
          <BriefingView
            briefing={briefing}
            reviewingKey={reviewingKey}
            reviewError={reviewError}
            onReview={reviewerMode ? async (turn, obsIndex, action, note) => {
              const auth = authHeaders();
              if (!auth) return;
              const key = `${turn}:${obsIndex}`;
              setReviewingKey(key);
              setReviewError(null);
              try {
                const { session, headers } = auth;
                const base = `/api/assessments/${encodeURIComponent(session.code)}`;
                const ev = await fetch(`${base}/interview/evidence`, { headers });
                if (!ev.ok) throw new Error(`could not load evidence (${ev.status})`);
                const turns = ((await ev.json()) as { turns: { turn: number; version: number }[] }).turns;
                const match = turns.find((t) => t.turn === turn);
                if (!match) throw new Error("evidence for this answer is missing");
                const res = await fetch(`${base}/interview/evidence/${turn}/observations/${obsIndex}`, {
                  method: "PATCH",
                  headers: { "Content-Type": "application/json", ...headers },
                  body: JSON.stringify({ action, note, expected_version: match.version }),
                });
                if (res.status === 409) throw new Error("changed underneath — reloading the briefing");
                if (!res.ok) throw new Error(`review failed (${res.status})`);
                const rep = await fetch(`${base}/interview/report`, { headers });
                if (rep.ok) setBriefing((await rep.json()) as Briefing);
              } catch (e) {
                setReviewError(e instanceof Error ? e.message : "review failed — please try again");
              } finally {
                setReviewingKey(null);
              }
            } : undefined}
          />
        </div>
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

  if (phase === "review" && review) {
    return (
      <div className="mx-auto max-w-2xl pt-10 sm:pt-14">
        <p className="inline-block rounded-full bg-primary-tint px-3 py-1 text-xs font-bold uppercase tracking-wider text-primary-deep">
          Review step — nothing is final yet
        </p>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
          Before we write your briefing
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft sm:text-base">
          Check that this looks like you. Every point links to your exact words.
          Add anything we missed, or correct anything we misread — then build your briefing.
        </p>

        <div className="mt-6 space-y-4">
          {review.topics.map((t) => (
            <section key={t.objective} aria-label={t.title} className="rounded-2xl border border-line bg-card p-5">
              <h2 className="flex flex-wrap items-center gap-2 font-serif text-lg font-semibold">
                {t.title}
                <span className="rounded-full bg-cream px-2.5 py-0.5 text-xs font-medium text-ink-soft">
                  {t.label || t.status}
                </span>
              </h2>
              {t.observations.length === 0 ? (
                <p className="mt-2 text-sm text-ink-soft">{t.note || "Nothing recorded here yet."}</p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {t.observations.map((o) => {
                    const key = `${o.turn}:${o.obs_index}`;
                    return (
                      <li key={key} className="rounded-xl bg-paper px-4 py-3">
                        <blockquote className="font-serif text-[16px] leading-relaxed text-ink">
                          &ldquo;{o.quote}&rdquo;
                        </blockquote>
                        {o.note && <p className="mt-1.5 text-sm text-ink-soft">{o.note}</p>}
                        <p className="mt-1.5 text-xs text-ink-faint">
                          turn {o.turn}
                          {o.line != null ? ` · line ${o.line}` : ""} · segment {o.segment_id}
                        </p>
                        {o.user_correction && (
                          <p className="mt-1.5 rounded-lg bg-primary-tint px-3 py-2 text-sm">
                            <span className="font-medium text-primary-deep">Your correction: </span>
                            {o.user_correction}
                          </p>
                        )}
                        {!correctOpen[key] ? (
                          <button
                            onClick={() => setCorrectOpen((m) => ({ ...m, [key]: true }))}
                            className="mt-2 text-sm font-medium text-primary hover:underline"
                          >
                            This isn&apos;t what I meant
                          </button>
                        ) : (
                          <div className="mt-2">
                            <label className="block text-sm font-medium">
                              What did you mean?
                              <textarea
                                value={correctText[key] ?? ""}
                                onChange={(e) => setCorrectText((m) => ({ ...m, [key]: e.target.value }))}
                                rows={2}
                                className="mt-1.5 w-full rounded-xl border border-line bg-card px-3 py-2 text-sm"
                                placeholder="Say it in your own words"
                              />
                            </label>
                            <div className="mt-2 flex flex-wrap gap-2">
                              <button
                                onClick={() => submitReviewCorrect(o.turn, o.obs_index, correctText[key] ?? "")}
                                className="rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-white hover:bg-primary-deep"
                              >
                                Save correction
                              </button>
                              <button
                                onClick={() => setCorrectOpen((m) => ({ ...m, [key]: false }))}
                                className="rounded-full border border-line px-4 py-1.5 text-xs font-medium text-ink-soft"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
              {!addOpen[t.objective] ? (
                <button
                  onClick={() => setAddOpen((m) => ({ ...m, [t.objective]: true }))}
                  className="mt-3 text-sm font-medium text-primary hover:underline"
                >
                  Add something
                </button>
              ) : (
                <div className="mt-3 rounded-xl bg-paper p-4">
                  <label className="block text-sm font-medium">
                    Add to {t.title.toLowerCase()}
                    <textarea
                      value={addText[t.objective] ?? ""}
                      onChange={(e) => setAddText((m) => ({ ...m, [t.objective]: e.target.value }))}
                      rows={3}
                      className="mt-1.5 w-full rounded-xl border border-line bg-card px-3 py-2 text-sm"
                      placeholder="Anything important we missed on this topic?"
                    />
                  </label>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      onClick={() => submitReviewAdd(t.objective, addText[t.objective] ?? "")}
                      className="rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-white hover:bg-primary-deep"
                    >
                      Save addition
                    </button>
                    <button
                      onClick={() => setAddOpen((m) => ({ ...m, [t.objective]: false }))}
                      className="rounded-full border border-line px-4 py-1.5 text-xs font-medium text-ink-soft"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </section>
          ))}
        </div>

        <section aria-label="Anything else" className="mt-4 rounded-2xl border border-line bg-card p-5">
          <h2 className="font-serif text-lg font-semibold">Anything important we didn&apos;t ask about?</h2>
          <textarea
            value={addText["__global"] ?? ""}
            onChange={(e) => setAddText((m) => ({ ...m, ["__global"]: e.target.value }))}
            rows={3}
            className="mt-2 w-full rounded-xl border border-line bg-paper px-3 py-2 text-sm"
            placeholder="Anything else your clinician should understand?"
          />
          <button
            onClick={() => submitReviewAdd("background-goals", addText["__global"] ?? "")}
            className="mt-2 rounded-full border border-primary px-4 py-1.5 text-xs font-semibold text-primary hover:bg-primary-tint"
          >
            Save as background and goals
          </button>
        </section>

        <section aria-label="Follow-ups" className="mt-4 rounded-2xl border border-line bg-card p-5">
          <h2 className="font-serif text-lg font-semibold">Fill the thinnest areas</h2>
          {topups.length === 0 ? (
            <>
              <p className="mt-1.5 text-sm text-ink-soft">
                Answer 1–3 quick follow-ups for the thinnest areas — or skip straight to confirm.
              </p>
              <button
                onClick={loadTopups}
                className="mt-2 rounded-full border border-primary px-4 py-1.5 text-xs font-semibold text-primary hover:bg-primary-tint"
              >
                Show follow-ups
              </button>
            </>
          ) : (
            <ul className="mt-2 space-y-3">
              {topups.map((tp) => (
                <li key={tp.objective} className="rounded-xl bg-paper px-4 py-3">
                  <p className="font-medium">{tp.question}</p>
                  <p className="mt-0.5 text-xs text-ink-faint">{tp.title}</p>
                  <textarea
                    value={topupAnswers[tp.objective] ?? ""}
                    onChange={(e) => setTopupAnswers((m) => ({ ...m, [tp.objective]: e.target.value }))}
                    rows={2}
                    className="mt-2 w-full rounded-xl border border-line bg-card px-3 py-2 text-sm"
                    placeholder="Your answer"
                  />
                  <button
                    onClick={() => submitReviewAdd(tp.objective, topupAnswers[tp.objective] ?? "")}
                    className="mt-2 rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-white hover:bg-primary-deep"
                  >
                    Save answer
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {reviewMsg && <p role="status" className="mt-4 text-sm font-medium text-primary-deep">{reviewMsg}</p>}
        {error && <p role="alert" className="mt-4 rounded-xl border border-tension/40 bg-tension-tint px-4 py-3 text-sm font-medium">{error}</p>}
        {confirming ? (
          <div role="status" aria-live="polite" className="mt-6 rounded-2xl border border-line bg-card p-6 text-center">
            <div className="mrprof-spinner mx-auto" aria-hidden />
            <p className="mt-4 font-semibold">Building your briefing…</p>
            <p className="mt-2 text-sm text-ink-soft">
              Gathering the last details into your report — this can take up to
              a minute. Your answers are safe; please keep this tab open.
            </p>
          </div>
        ) : (
          <button
            onClick={submitConfirm}
            className="mt-6 inline-flex w-full items-center justify-center gap-1.5 rounded-full bg-primary px-6 py-3.5 text-base font-semibold text-white hover:bg-primary-deep"
          >
            Looks right — build my briefing <ArrowRight className="h-4 w-4" aria-hidden />
          </button>
        )}
        <p className="mt-2 pb-10 text-center text-xs text-ink-faint">
          Your briefing is only generated after you confirm. Closing the browser here resumes at this step.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl pt-10 sm:pt-14">
      <h1 className="font-serif text-3xl font-semibold tracking-tight">Interview</h1>
      <p className="mt-3 text-sm leading-relaxed text-ink-soft sm:text-base">
        One question at a time — there is no time limit. Short answers are accepted:
        a plain no, or “I can’t remember”, is a valid answer.
      </p>
      {mode === "taster" && (
        <p role="note" className="mt-3 rounded-xl border border-primary/30 bg-primary-tint px-4 py-2.5 text-sm font-medium text-primary-deep">
          Short taster — about 6 questions. Anything not covered is marked as a gap in your briefing.
        </p>
      )}
      <RiskLink />
      <ProgressRail mode={mode} turnsAnswered={turnsAnswered} currentObjective={question?.objective ?? null} />
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
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              onClick={() => submit()}
              className="inline-flex items-center gap-1.5 rounded-full bg-primary px-6 py-3 text-sm font-semibold text-white hover:bg-primary-deep"
            >
              Save and continue <ArrowRight className="h-4 w-4" aria-hidden />
            </button>
            <button
              onClick={() => submit("I can't remember.")}
              className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card px-5 py-2.5 text-sm font-medium text-ink-soft hover:border-primary hover:text-primary"
            >
              I can&apos;t remember
            </button>
            <button
              onClick={() => submit("I'd rather skip this one.")}
              className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card px-5 py-2.5 text-sm font-medium text-ink-soft hover:border-primary hover:text-primary"
            >
              Skip this one
            </button>
          </div>
          <p className="mt-2 text-xs text-ink-faint">
            Skipping or not remembering is a complete answer — the topic closes and is never probed.
          </p>
          {turnsAnswered >= 1 && (
            <div className="mt-3">
              {!correcting ? (
                <button
                  onClick={() => { setCorrecting(true); setCorrectMsg(""); }}
                  className="text-sm font-medium text-primary hover:underline"
                >
                  Fix my last answer
                </button>
              ) : (
                <div className="rounded-2xl border border-line bg-paper p-4">
                  <label className="block text-sm font-semibold">
                    Correct your last answer (the original is kept)
                    <textarea
                      value={correction}
                      onChange={(e) => setCorrection(e.target.value)}
                      rows={3}
                      className="mt-2 w-full rounded-2xl border border-line bg-card px-4 py-3 text-base leading-relaxed"
                      placeholder="What did you mean instead?"
                    />
                  </label>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      onClick={submitCorrection}
                      className="inline-flex items-center gap-1.5 rounded-full bg-primary px-5 py-2 text-sm font-semibold text-white hover:bg-primary-deep"
                    >
                      Save correction
                    </button>
                    <button
                      onClick={() => { setCorrecting(false); setCorrection(""); }}
                      className="inline-flex items-center gap-1.5 rounded-full border border-line bg-card px-5 py-2 text-sm font-medium text-ink-soft hover:border-primary hover:text-primary"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
              {correctMsg && <p role="status" className="mt-2 text-sm text-primary-deep">{correctMsg}</p>}
            </div>
          )}
        </section>
      )
      )}
      {error && <p role="alert" className="mt-4 rounded-xl border border-tension/40 bg-tension-tint px-4 py-3 text-sm font-medium">{error}</p>}
    </div>
  );
}
