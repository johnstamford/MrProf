"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { loadSession } from "../../lib/session";

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

export default function ScreeningPage() {
  const router = useRouter();
  const [version, setVersion] = useState<number | null>(null);
  const [answers, setAnswers] = useState<string[]>(Array(6).fill(""));
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const advanceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const session = loadSession();
    if (!session) {
      router.replace("/start");
      return;
    }
    void (async () => {
      const res = await fetch(`/api/assessments/${encodeURIComponent(session.code)}`, {
        headers: { Authorization: `Bearer ${session.password}` },
      });
      if (!res.ok) {
        setError("could not load your assessment — please start again");
        return;
      }
      const body = await res.json();
      setVersion(body.version as number);
      const s = await fetch(
        `/api/assessments/${encodeURIComponent(session.code)}/screening`,
        { headers: { Authorization: `Bearer ${session.password}` } },
      );
      if (s.ok) {
        const saved = (await s.json()).answers as string[];
        setAnswers(saved);
        const firstUnanswered = saved.findIndex((a) => !a);
        setStep(firstUnanswered === -1 ? 5 : firstUnanswered);
      }
    })();
    return () => {
      if (advanceTimer.current) clearTimeout(advanceTimer.current);
    };
  }, [router]);

  function choose(key: string) {
    setAnswers((prev) => prev.map((v, j) => (j === step ? key : v)));
    setError("");
    // Auto-advance so each question gets its own calm moment; the last
    // question stays put so the user explicitly saves.
    if (advanceTimer.current) clearTimeout(advanceTimer.current);
    if (step < QUESTIONS.length - 1) {
      advanceTimer.current = setTimeout(() => setStep((s) => Math.min(s + 1, QUESTIONS.length - 1)), 280);
    }
  }

  async function next() {
    setError("");
    if (answers.some((a) => !a)) return setError("please answer all six questions");
    const session = loadSession();
    if (!session || version === null) return setError("session lost — please start again");
    setSaving(true);
    try {
      const key =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `key-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      let res = await fetch(`/api/assessments/${encodeURIComponent(session.code)}/screening`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.password}` },
        body: JSON.stringify({ answers, base_version: version, idempotency_key: key }),
      });
      if (res.status === 409) {
        // State moved on underneath us — reload the version and retry once.
        const fresh = await fetch(`/api/assessments/${encodeURIComponent(session.code)}`, {
          headers: { Authorization: `Bearer ${session.password}` },
        });
        if (!fresh.ok) return setError("could not save — please try again");
        const body = await fresh.json();
        setVersion(body.version as number);
        res = await fetch(`/api/assessments/${encodeURIComponent(session.code)}/screening`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.password}` },
          body: JSON.stringify({
            answers,
            base_version: body.version,
            idempotency_key: `key-${Date.now()}-${Math.random().toString(36).slice(2)}`,
          }),
        });
      }
      if (res.status === 422) return setError("please answer all six questions");
      if (!res.ok) return setError("could not save — please try again");
      router.push("/report");
    } finally {
      setSaving(false);
    }
  }

  const answered = answers.filter(Boolean).length;

  return (
    <div className="mx-auto max-w-2xl pt-10 sm:pt-14">
      <h1 className="font-serif text-3xl font-semibold tracking-tight">Screening questions</h1>
      <p className="mt-3 text-sm leading-relaxed text-ink-soft sm:text-base">{INSTRUCTIONS}</p>

      {/* Progress: counts only, never percentages */}
      <div className="mt-6" role="status" aria-label={`Question ${step + 1} of 6, ${answered} of 6 answered`}>
        <div className="flex items-center justify-between text-sm">
          <span className="font-semibold">
            {step + 1} of 6
          </span>
          <span className="text-ink-faint">{answered} of 6 answered</span>
        </div>
        <div className="mt-2 flex gap-1.5" aria-hidden>
          {QUESTIONS.map((_, i) => (
            <span
              key={i}
              className={`h-2 flex-1 rounded-full ${i < step || (i === step && answers[i]) ? "bg-primary" : i === step ? "bg-primary/40" : "bg-line"}`}
            />
          ))}
        </div>
      </div>

      <section aria-label={`Question ${step + 1}`} className="mt-6 rounded-2xl border border-line bg-card p-5 sm:p-8" key={step}>
        <fieldset>
          <legend className="font-serif text-xl font-semibold leading-snug sm:text-2xl">
            {QUESTIONS[step]}
          </legend>
          <div className="mt-5 space-y-2.5" role="radiogroup" aria-label={`Answers for question ${step + 1}`}>
            {RESPONSES.map((r) => {
              const selected = answers[step] === r.key;
              return (
                <label
                  key={r.key}
                  className={`flex cursor-pointer items-center gap-3 rounded-2xl border-2 px-4 py-3.5 text-base font-medium transition-colors ${
                    selected
                      ? "border-primary bg-primary-tint text-ink"
                      : "border-line bg-paper text-ink-soft hover:border-primary/60"
                  }`}
                >
                  <input
                    type="radio"
                    name={`q${step}`}
                    value={r.key}
                    checked={selected}
                    onChange={() => choose(r.key)}
                    className="h-5 w-5 shrink-0 accent-[#0E7C6B]"
                  />
                  <span className="flex-1">{r.label}</span>
                  {selected && <Check className="h-5 w-5 shrink-0 text-primary" aria-hidden />}
                </label>
              );
            })}
          </div>
        </fieldset>

        <div className="mt-6 flex items-center justify-between gap-3">
          <button
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
            className="inline-flex items-center gap-1.5 rounded-full px-4 py-2.5 text-sm font-semibold text-ink-soft hover:text-ink disabled:opacity-30"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden /> Back
          </button>
          {step < QUESTIONS.length - 1 ? (
            <button
              onClick={() => setStep((s) => Math.min(s + 1, QUESTIONS.length - 1))}
              className="inline-flex items-center gap-1.5 rounded-full border border-primary px-5 py-2.5 text-sm font-semibold text-primary hover:bg-primary-tint"
            >
              Skip for now <ArrowRight className="h-4 w-4" aria-hidden />
            </button>
          ) : (
            <button
              onClick={next}
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-full bg-primary px-6 py-2.5 text-sm font-semibold text-white hover:bg-primary-deep disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save and see my report"} <ArrowRight className="h-4 w-4" aria-hidden />
            </button>
          )}
        </div>
      </section>

      {error && <p role="alert" className="mt-4 rounded-xl border border-tension/40 bg-tension-tint px-4 py-3 text-sm font-medium">{error}</p>}

      <footer className="mt-8 border-t border-line pt-4">
        <p className="text-xs leading-relaxed text-ink-faint"><small>{ATTRIBUTION}</small></p>
      </footer>
    </div>
  );
}
