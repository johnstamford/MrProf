"use client";

import { useRouter } from "next/navigation";

export default function InterviewPage() {
  const router = useRouter();
  return (
    <main>
      <h1>MrProf — interview</h1>
      <p>
        The adaptive interview is built in the next stage of this project. Your screening
        answers are saved and will carry forward — you will not need to repeat them.
      </p>
      <button onClick={() => router.push("/report")}>← Back to screening report</button>
    </main>
  );
}
