"use client";

/** WS2-A: compact 4-area progress rail for the interview loop. Derived
 * deterministically from answered objectives (fixed round-1 order); no
 * total-question countdown, because the count genuinely branches. */

const PLAN_ORDER = [
  "background-goals",
  "attention-focus",
  "organization",
  "task-completion",
  "forgetfulness",
  "restlessness",
  "impulsivity",
  "childhood-onset",
  "persistence-course",
  "settings",
  "impact-work",
  "impact-relationships",
  "context-factors",
  "strategies",
];

const TASTER_OBJECTIVES = [
  "attention-focus",
  "organization",
  "task-completion",
  "forgetfulness",
  "restlessness",
  "impulsivity",
];

const AREAS: { key: string; title: string; members: string[] }[] = [
  {
    key: "functioning",
    title: "Daily functioning",
    members: TASTER_OBJECTIVES,
  },
  { key: "course", title: "History and course", members: ["childhood-onset", "persistence-course"] },
  { key: "impact", title: "Settings and impact", members: ["settings", "impact-work", "impact-relationships"] },
  {
    key: "context",
    title: "Context and background",
    members: ["background-goals", "context-factors", "strategies"],
  },
];

export default function ProgressRail({
  mode,
  turnsAnswered,
  currentObjective,
}: {
  mode: "full" | "taster";
  turnsAnswered: number;
  currentObjective: string | null;
}) {
  const round1 = mode === "taster" ? TASTER_OBJECTIVES : PLAN_ORDER;
  return (
    <nav aria-label="Interview progress by area" className="mt-4">
      <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {AREAS.map((a) => {
          const inScope = a.members.some((m) => round1.includes(m));
          const done =
            inScope && a.members.filter((m) => round1.includes(m)).every((m) => round1.indexOf(m) < turnsAnswered);
          const current =
            inScope && !done && currentObjective != null && a.members.includes(currentObjective);
          const state = !inScope ? "gap" : done ? "done" : current ? "current" : "upcoming";
          const label =
            state === "done"
              ? `${a.title}: covered`
              : state === "current"
                ? `${a.title}: current area`
                : state === "gap"
                  ? `${a.title}: not in the short taster`
                  : `${a.title}: upcoming`;
          return (
            <li
              key={a.key}
              aria-label={label}
              title={label}
              className={`rounded-xl border px-3 py-2 text-xs font-medium leading-snug ${
                state === "done"
                  ? "border-primary/40 bg-primary-tint text-primary-deep"
                  : state === "current"
                    ? "border-primary bg-card text-ink shadow-[0_0_0_1px_var(--color-primary)]"
                    : state === "gap"
                      ? "border-dashed border-line bg-paper text-ink-faint"
                      : "border-line bg-card text-ink-soft"
              }`}
            >
              <span aria-hidden>{state === "done" ? "● " : state === "current" ? "◐ " : "○ "}</span>
              {a.title}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
