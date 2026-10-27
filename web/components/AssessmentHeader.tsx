"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { loadSession } from "../lib/session";

/** Assessment ID banner rendered on every screen via the root layout. */
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
    <header>
      <p>
        Assessment ID: <code>{code}</code>{" "}
        <button onClick={copy}>{copied ? "Copied" : "Copy"}</button>
      </p>
    </header>
  );
}
