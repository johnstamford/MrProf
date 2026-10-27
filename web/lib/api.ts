export type Ready = { ok: boolean; mongo?: string };

export async function getReadiness(): Promise<{ status: number; body: Ready | null }> {
  const base = process.env.API_INTERNAL_URL ?? "http://api:8000";
  try {
    const res = await fetch(`${base}/ready`, { cache: "no-store" });
    const body = (await res.json()) as Ready;
    return { status: res.status, body };
  } catch {
    return { status: 0, body: null };
  }
}
