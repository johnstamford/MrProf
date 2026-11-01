"""F10a slice 1: deterministic question validation + bounded regen."""

import app.routes.interview as ir
from app.interview import PLAN_ORDER, fallback_question, load_topics
from app.llm import LLMQuestion
from app.question_validation import QUESTION_MAX_CHARS, validate_question


def _fallbacks():
    return {t.get("opener", "") for t in load_topics().values()}


def test_ok_and_fallback_exempt():
    fb = fallback_question("forgetfulness")  # two-sentence house style, must pass
    assert "?" in fb
    assert validate_question(fb, "forgetfulness", "forgetfulness", [], [], _fallbacks()) == "ok"
    assert validate_question(
        "What is it like to stay focused on one thing?", "attention-focus", "attention-focus",
        [], [], _fallbacks(),
    ) == "ok"


def test_off_objective_and_already_answered():
    assert validate_question("Q?", "organization", "attention-focus", [], []) == "off_objective"
    assert validate_question(
        "Q?", "organization", "attention-focus", [],
        ["attention-focus", "organization"], _fallbacks(),
    ) == "already_answered"


def test_repeated_leading_compound_toolong():
    assert validate_question("Hello there?", "attention-focus", "attention-focus", ["Hello there?"], []) == "repeated"
    assert validate_question(
        "You struggle to focus, don't you?", "attention-focus", "attention-focus", [], [],
    ) == "leading"
    assert validate_question(
        "Your ADHD symptoms make this hard, right?", "attention-focus", "attention-focus", [], [],
    ) == "leading"
    assert validate_question("One? Two? Three?", "attention-focus", "attention-focus", [], []) == "compound"
    assert validate_question(
        "How is work and how is home?", "settings", "settings", [], [],
    ) == "compound"
    long_q = "What is it like? " + "x" * QUESTION_MAX_CHARS
    assert validate_question(long_q, "attention-focus", "attention-focus", [], []) == "too_long"
    # Single-question openers with "and" inside one clause are fine.
    assert validate_question(
        "What brings you here now?", "background-goals", "background-goals", [], [],
    ) == "ok"


async def _run_generate(monkeypatch, texts: list[str], objective="attention-focus"):
    calls = {"n": 0}

    async def fake_gen(**kwargs):
        idx = min(calls["n"], len(texts) - 1)
        calls["n"] += 1
        return (
            LLMQuestion(question_text=texts[idx], objective=kwargs.get("objective", objective), reason="why now"),
            {"provider": "dummy", "model": "t"},
            {"session_id": "s"},
        )

    monkeypatch.setattr(ir, "generate_next_question", fake_gen)
    q, info, _, _, _ = await ir._generate("aid", objective, "r", [], None)
    return q, info, calls["n"]


def test_regen_repairs_leading_then_asks(monkeypatch):
    import asyncio

    q, info, n = asyncio.run(_run_generate(
        monkeypatch,
        ["You struggle to focus, don't you?", "What is it like to stay focused?"],
    ))
    assert n == 2
    assert q.question_text == "What is it like to stay focused?"


def test_persistent_failure_falls_back_bounded(monkeypatch):
    import asyncio

    q, info, n = asyncio.run(_run_generate(
        monkeypatch,
        ["You struggle, don't you?"] * 5,
    ))
    # 1 initial + 2 regens, then pre-approved fallback.
    assert n == 3
    assert q.question_text == fallback_question("attention-focus")
    assert info.get("validation_fallback") == "leading"
