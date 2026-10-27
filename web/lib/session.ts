"use client";

export const SESSION_CODE_KEY = "mrprof.assessment_code";
export const SESSION_PASSWORD_KEY = "mrprof.assessment_password";

export function saveSession(code: string, password: string) {
  try {
    sessionStorage.setItem(SESSION_CODE_KEY, code.toUpperCase());
    sessionStorage.setItem(SESSION_PASSWORD_KEY, password);
  } catch {
    // Private-mode storage may throw; manual entry remains as fallback.
  }
}

export function loadSession(): { code: string; password: string } | null {
  try {
    const code = sessionStorage.getItem(SESSION_CODE_KEY) ?? "";
    const password = sessionStorage.getItem(SESSION_PASSWORD_KEY) ?? "";
    return code && password ? { code, password } : null;
  } catch {
    return null;
  }
}
