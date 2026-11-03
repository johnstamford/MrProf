"use client";

export const RISK_SIGNPOST =
  "Support note — no one monitors your answers here. MrProf does not provide crisis support and no one reviews your answers in real time. If you feel unsafe or are thinking about harming yourself, please contact your local emergency number now (for example 112 in most of Europe, 911 in the US, 999 in the UK) or a local crisis helpline. You can also stop the interview at any time.";

export default function RiskNote() {
  return (
    <p className="mt-4 rounded-xl border border-line bg-card px-4 py-3 text-xs leading-relaxed text-ink-soft">
      {RISK_SIGNPOST}
    </p>
  );
}

/** Compact support link for the interview loop: one click reveals the full note. */
export function RiskLink() {
  return (
    <details className="mt-4 text-sm">
      <summary className="cursor-pointer font-medium text-primary hover:underline">
        Need support?
      </summary>
      <p className="mt-2 rounded-xl border border-line bg-card px-4 py-3 text-xs leading-relaxed text-ink-soft">
        {RISK_SIGNPOST}
      </p>
    </details>
  );
}
