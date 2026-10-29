import type { ReactNode } from "react";
import Link from "next/link";
import AssessmentHeader from "../components/AssessmentHeader";
import "./globals.css";

export const metadata = {
  title: "MrProf — prepare for your ADHD assessment",
  description:
    "Complete a screening questionnaire and prepare a traceable account of your experiences, with exact quotes, for clinician review.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen">
          <header className="no-print border-b border-line bg-card">
            <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
              <Link
                href="/"
                className="font-serif text-xl font-semibold tracking-tight text-ink"
              >
                MrProf
              </Link>
              <nav aria-label="Primary" className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                <Link className="text-ink-soft underline-offset-4 hover:underline" href="/start">
                  Start / resume
                </Link>
                <Link className="text-ink-soft underline-offset-4 hover:underline" href="/demo">
                  Example reports
                </Link>
              </nav>
              <div className="ml-auto">
                <AssessmentHeader />
              </div>
            </div>
          </header>
          <main className="mx-auto w-full max-w-5xl px-4 pb-20 sm:px-6">
            {children}
          </main>
          <footer className="no-print border-t border-line">
            <div className="mx-auto max-w-5xl px-4 py-6 text-sm text-ink-faint sm:px-6">
              <p>
                Draft research prototype. Nothing here is a clinical assessment —
                only a qualified clinician can determine what explains your
                experiences.
              </p>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
