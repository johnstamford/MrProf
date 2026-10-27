"""Manual live-model smoke test. NOT part of the default suite.

Run on demand only (costs real model calls, needs real credentials):
  docker compose exec -e MRPROF_LIVE_SMOKE=1 api pytest tests/test_live_smoke.py -q

Asserts the real provider path end to end: questions are model-phrased
(not stub templates) and the two-turn answer loop persists correctly.
Fixtures are cleaned up afterwards.
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("MRPROF_LIVE_SMOKE") != "1",
    reason="manual live-model smoke only: set MRPROF_LIVE_SMOKE=1",
)

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.interview import PLAN_ORDER, fallback_question  # noqa: E402
from app.llm import load_config  # noqa: E402
from app.main import app  # noqa: E402


def _auth(password: str) -> dict:
    return {"Authorization": f"Bearer {password}"}


async def test_live_two_turn_smoke():
    cfg = load_config()
    if cfg.provider != "openai-compatible":
        pytest.skip(f"live smoke needs LLM_PROVIDER=openai-compatible, got {cfg.provider!r}")
    password = f"correct horse {uuid.uuid4().hex[:8]}"
    assessment_id = ""
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            created = (await c.post("/assessments", json={"password": password})).json()
            assessment_id = created["assessment_id"]
            headers = _auth(password)

            started = await c.post(
                f"/assessments/{assessment_id}/interview/start",
                json={"base_version": 1, "idempotency_key": f"live-{uuid.uuid4().hex[:8]}"},
                headers=headers,
            )
            assert started.status_code == 200, started.text
            q1 = started.json()["question"]
            assert q1["objective"] == PLAN_ORDER[0]
            assert q1["model_provider"] == "openai-compatible", q1
            # Model-phrased, not the deterministic stub template.
            assert q1["text"] != fallback_question(PLAN_ORDER[0])

            answered = await c.post(
                f"/assessments/{assessment_id}/interview/answer",
                json={
                    "answer_text": "I find it hard to start boring paperwork and often leave it for weeks",
                    "base_version": 2,
                    "idempotency_key": f"live-{uuid.uuid4().hex[:8]}",
                },
                headers=headers,
            )
            assert answered.status_code == 200, answered.text
            body = answered.json()
            assert body["question"]["objective"] == PLAN_ORDER[1]
            assert body["question"]["model_provider"] == "openai-compatible"
    finally:
        if assessment_id:
            from app.db import get_db

            await get_db()["assessments"].delete_one({"_id": assessment_id})
            await get_db()["reports"].delete_many({"assessment_id": assessment_id})
