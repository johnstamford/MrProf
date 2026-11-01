"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight, KeyRound, PlusCircle } from "lucide-react";
import { saveSession } from "../../lib/session";
import RiskNote from "../../components/risk-note";

type Created = { assessment_id: string; version: number; stage: string };
type Fetched = { assessment_id: string; version: number; stage: string; status: string };

export default function StartPage() {
  const router = useRouter();
  const [newPassword, setNewPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [consentChecked, setConsentChecked] = useState(false);
  const [consentVersion, setConsentVersion] = useState("");
  const [inviteRequired, setInviteRequired] = useState(false);
  const [created, setCreated] = useState<Created | null>(null);
  const [id, setId] = useState("");
  const [password, setPassword] = useState("");
  const [fetched, setFetched] = useState<Fetched | null>(null);
  const [resumeTarget, setResumeTarget] = useState("/screening");
  const [resumeNote, setResumeNote] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch("/api/config");
        if (!res.ok) return;
        const cfg = (await res.json()) as {
          invite_required: boolean;
          consent_version: string;
        };
        setInviteRequired(!!cfg.invite_required);
        setConsentVersion(cfg.consent_version ?? "");
      } catch {
        // Config is best-effort; the server still enforces its gates.
      }
    })();
  }, []);

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
    if (!consentChecked) {
      setError("please read the consent details and tick the box before starting");
      return;
    }
    const res = await fetch("/api/assessments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        password: newPassword,
        invite_code: inviteCode,
        consent_accepted: consentChecked,
        consent_version: consentVersion,
      }),
    });
    if (res.status === 422)
      return setError(
        "please use a password of at least 10 characters and accept the current consent version",
      );
    if (res.status === 403) return setError("this opening needs an invite code — check your invite link");
    if (!res.ok) return setError(`start failed: ${res.status}`);
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
    <div className="mx-auto max-w-2xl pt-10 sm:pt-14">
      <h1 className="font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
        ADHD screening and evidence briefing
      </h1>
      <section aria-label="What is this" className="mt-5 rounded-2xl border border-line bg-card p-5 sm:p-6">
        <h2 className="font-serif text-xl font-semibold">What is this?</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft sm:text-base">
          MrProf helps you complete a 6-question ADHD screening questionnaire and,
          if you choose, answer follow-up questions about your experiences. You keep
          two reports: a screening summary and an evidence briefing with exact quotes
          from your answers.
        </p>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft sm:text-base">
          This is a draft research prototype — it organizes what you report so a
          clinician can review it. A result below the screening threshold does not
          rule anything out. Only a qualified clinician can determine what explains
          your experiences.
        </p>
      </section>

      <section aria-label="How it works" className="mt-4 rounded-2xl border border-line bg-card p-5 sm:p-6">
        <h2 className="font-serif text-xl font-semibold">How it works</h2>
        <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm leading-relaxed text-ink-soft sm:text-base">
          <li>Answer 6 screening questions (a few minutes).</li>
          <li>Get your screening report immediately — either result can continue.</li>
          <li>Optionally continue to the interview: one question at a time, in your own words.</li>
          <li>Get your evidence briefing with supporting quotes.</li>
        </ol>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">Both stages together take most people around 20–30 minutes. There is no time limit, and you can close the browser and resume later with your code and password.</p>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">Short on time? After the screening report you can try the short taster — about 6 questions — instead of the full interview.</p>
      </section>

      <div className="mt-4"><RiskNote /></div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <section aria-label="New assessment" className="rounded-2xl border border-line bg-card p-5">
          <h2 className="flex items-center gap-2 font-serif text-lg font-semibold">
            <PlusCircle className="h-5 w-5 text-primary" aria-hidden /> New assessment
          </h2>
          <label className="mt-3 block text-sm font-medium">
            Choose a password (min 10 characters)
            <input
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              type="password"
              autoComplete="new-password"
              className="mt-1.5 w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-base"
            />
          </label>
          {inviteRequired && (
            <label className="mt-3 block text-sm font-medium">
              Invite code
              <input
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
                autoComplete="off"
                className="mt-1.5 w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-base"
              />
            </label>
          )}
          <label className="mt-3 flex items-start gap-2.5 text-sm leading-relaxed text-ink-soft">
            <input
              type="checkbox"
              checked={consentChecked}
              onChange={(e) => setConsentChecked(e.target.checked)}
              className="mt-1 h-4 w-4 shrink-0"
            />
            <span>
              I have read the{" "}
              <a href="/consent" className="font-medium text-primary underline">
                consent details
              </a>{" "}
              and I agree to take part in this draft research prototype.
            </span>
          </label>
          <button
            onClick={start}
            className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-white hover:bg-primary-deep"
          >
            Start
          </button>
          {created && (
            <div className="mt-4 rounded-xl bg-cream p-4">
              <h3 className="font-semibold">Save your assessment details</h3>
              <p className="mt-1 text-sm">Assessment code: <code className="rounded bg-card px-1.5 py-0.5 font-mono">{created.assessment_id}</code></p>
              <p role="alert" className="mt-2 text-sm leading-relaxed">
                Write down your assessment code and password somewhere safe.
                You need both to get back to your assessment — without them it
                cannot be retrieved, and there is no password reset.
              </p>
              <button
                onClick={() => goToScreening(created.assessment_id, newPassword)}
                className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-deep"
              >
                I have saved my code and password — continue <ArrowRight className="h-4 w-4" aria-hidden />
              </button>
            </div>
          )}
        </section>

        <section aria-label="Resume" className="rounded-2xl border border-line bg-card p-5">
          <h2 className="flex items-center gap-2 font-serif text-lg font-semibold">
            <KeyRound className="h-5 w-5 text-primary" aria-hidden /> Resume
          </h2>
          <label className="mt-3 block text-sm font-medium">
            Assessment code
            <input
              value={id}
              onChange={(e) => setId(e.target.value)}
              autoComplete="off"
              className="mt-1.5 w-full rounded-xl border border-line bg-paper px-3 py-2.5 font-mono text-base uppercase"
            />
          </label>
          <label className="mt-3 block text-sm font-medium">
            Password
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              autoComplete="current-password"
              className="mt-1.5 w-full rounded-xl border border-line bg-paper px-3 py-2.5 text-base"
            />
          </label>
          <button
            onClick={resume}
            className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-full border border-primary px-5 py-2.5 text-sm font-semibold text-primary hover:bg-primary-tint"
          >
            Resume
          </button>
          {fetched && (
            <div className="mt-4 rounded-xl bg-cream p-4">
              <h3 className="font-semibold">Assessment found</h3>
              <p className="mt-1 text-sm">{resumeNote || "Assessment found."}</p>
              <p role="alert" className="mt-2 text-sm leading-relaxed">
                Keep your assessment code and password somewhere safe.
                You need both to get back to your assessment — without them it
                cannot be retrieved, and there is no password reset.
              </p>
              <button
                onClick={() => goTo(fetched.assessment_id, password, resumeTarget)}
                className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-deep"
              >
                Continue to {resumeTarget === "/interview" ? "interview" : "screening"} <ArrowRight className="h-4 w-4" aria-hidden />
              </button>
            </div>
          )}
        </section>
      </div>
      {error && <p role="alert" className="mt-4 rounded-xl border border-tension/40 bg-tension-tint px-4 py-3 text-sm font-medium">{error}</p>}
    </div>
  );
}
