"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { loadSession } from "../lib/session";

/** Assessment ID banner rendered in the site header via the root layout. */
export default function AssessmentHeader() {
  const pathname = usePathname();
  const [code, setCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setCode(loadSession()?.code ?? null);
    setCopied(false);
  }, [pathname]);

  if (!code) return null;

  async function copy() {
    try {
      await navigator.clipboard.writeText(code as string);
      setCopied(true);
    } catch {
      // Clipboard unavailable; the code remains visible for manual copy.
    }
  }

  return (
    <p className="text-sm text-ink-soft">
      Assessment ID: <code className="rounded bg-cream px-1.5 py-0.5 font-mono text-[13px]">{code}</code>{" "}
      <button
        onClick={copy}
        className="rounded-full border border-line px-2.5 py-0.5 text-xs text-ink-soft hover:border-primary hover:text-primary"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </p>
  );
}
