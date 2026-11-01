"use client";

import { useEffect, useState } from "react";

type Consent = {
  version: string;
  provider: string;
  model: string;
  model_note: string;
  sections: { heading: string; body: string }[];
};

export default function ConsentPage() {
  const [consent, setConsent] = useState<Consent | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      const res = await fetch("/api/consent");
      if (!res.ok) return setError(`could not load consent details (${res.status})`);
      setConsent((await res.json()) as Consent);
    })();
  }, []);

  return (
    <div className="mx-auto max-w-2xl pt-10 sm:pt-14">
      <h1 className="font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
        Consent to take part
      </h1>
      <p className="mt-3 text-sm leading-relaxed text-ink-soft sm:text-base">
        MrProf is a draft research prototype. Please read this before you start —
        starting an assessment records that you accept version{" "}
        {consent ? <code className="rounded bg-card px-1 font-mono text-[13px]">{consent.version}</code> : "…"}.
      </p>
      {error && (
        <p role="alert" className="mt-4 rounded-xl border border-tension/40 bg-tension-tint px-4 py-3 text-sm font-medium">
          {error}
        </p>
      )}
      {!consent && !error && (
        <p role="status" className="mt-4 text-ink-soft">
          Loading…
        </p>
      )}
      {consent && (
        <>
          <section aria-label="Model handling" className="mt-5 rounded-2xl border border-line bg-card p-5 sm:p-6">
            <h2 className="font-serif text-xl font-semibold">How your answers are processed</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-soft sm:text-base">
              Interview questions are phrased by model{" "}
              <code className="rounded bg-cream px-1 font-mono text-[13px]">{consent.model}</code> (provider{" "}
              <code className="rounded bg-cream px-1 font-mono text-[13px]">{consent.provider}</code>).{" "}
              {consent.model_note}
            </p>
          </section>
          {consent.sections.map((s) => (
            <section key={s.heading} aria-label={s.heading} className="mt-4 rounded-2xl border border-line bg-card p-5 sm:p-6">
              <h2 className="font-serif text-xl font-semibold">{s.heading}</h2>
              <p className="mt-2 text-sm leading-relaxed text-ink-soft sm:text-base">{s.body}</p>
            </section>
          ))}
        </>
      )}
    </div>
  );
}
