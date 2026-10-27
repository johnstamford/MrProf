import { getReadiness } from "../lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  const { status, body } = await getReadiness();
  const apiOk = status === 200 && body?.ok === true;
  return (
    <main>
      <h1>MrProf</h1>
      <p>Feature 1 stack placeholder. Assessment UI lands in Feature 2+.</p>
      <ul>
        <li>API reachable: {apiOk ? "yes" : "no"}</li>
        <li>MongoDB reachable via API: {body?.mongo ?? "unknown"}</li>
      </ul>
      <p>
        <a href="/api/health">Backend /api/health through the intended route</a>
      </p>
    </main>
  );
}
