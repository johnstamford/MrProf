"""Feature 8: simulated patients.

DummyPatient answers from the persona script (hermetic, no network).
ModelPatient roleplays the persona through the configured model path
(same provider config as the interviewer). Both expose .answer(question,
turn) -> str. The driver only ever forwards the returned answer text.
"""

from __future__ import annotations


class DummyPatient:
    def __init__(self, persona: dict):
        self._persona = persona
        self.calls = 0

    @property
    def kind(self) -> str:
        return "dummy"

    def answer(self, question: str, turn: int, objective: str) -> str:  # noqa: ARG002
        self.calls += 1
        return self._persona["script"][objective]["answer"]


class ModelPatient:
    """LLM roleplayer. Ground truth lives only in this object's prompts."""

    def __init__(self, persona: dict, session_id: str):
        self._persona = persona
        self._session_id = session_id
        self.calls = 0

    @property
    def kind(self) -> str:
        return "model"

    def _instructions(self) -> str:
        p = self._persona
        known = "\n".join(f"- {f}" for f in p["facts"])
        unknown = "\n".join(f"- {u}" for u in p["uncertain"]) or "- (none)"
        return (
            f"{p['brief']}\nFacts you know:\n{known}\n"
            f"Things you do NOT know (never invent these):\n{unknown}\n"
            "Reply with your answer text only — no JSON, no preamble."
        )

    async def answer(self, question: str, turn: int, objective: str) -> str:  # noqa: ARG002
        from app.llm import build_agent, load_config, run_agent_text

        cfg = load_config()
        agent, session = build_agent(cfg, self._instructions(), f"{self._session_id}-patient")
        text, _, _ = await run_agent_text(
            cfg, agent, session, f"Interviewer asks: {question}", {"provider": cfg.provider}, self._session_id
        )
        self.calls += 1
        return text.strip()[:2000] or "(no answer given)"
