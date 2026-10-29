"""Feature 5: server-side model connection via Microsoft Agent Framework.

One InterviewAgent phrases questions. The deterministic planner in
`interview.py` selects objectives in code — the LLM never plans, scores,
or diagnoses.

Provider model (env, server-side only — never exposed to the frontend):
  LLM_PROVIDER=openai-compatible   Real path via Agent Framework +
                                   OpenAI-compatible chat completions
                                   (Claude via an OpenAI-compatible
                                   base URL, OpenRouter, or local).
  LLM_PROVIDER=dummy (default)     No network. Deterministic stub
                                   templates for the food/hobbies flow test.
  LLM_MODEL / LLM_BASE_URL / LLM_API_KEY configure the real path.
  LLM_TIMEOUT_S (default 30), LLM_MAX_TOKENS (default 300) bound cost/time.
  LLM_REASONING_EFFORT (default minimal): the interviewer asks for bounded
  reasoning on the critical path (measured ~2x faster than the default
  ~1000 thinking tokens, valid JSON preserved). "off" omits the hint for
  endpoints that reject it. The background extractor keeps full reasoning
  for evidence quality.
  LLM_EXTRACT_TIMEOUT_S (default 60) bounds the background evidence
  extractor separately — it emits long JSON off the critical path.
  NOTE: max_tokens is intentionally NOT passed as a ChatOptions hint — the
  current OpenAI-compatible endpoint returns empty text when any max_tokens
  hint is sent (verified live Oct 2026). Tokens are bounded in practice by
  the short-question contract (max 200 chars) plus strict JSON validation.
  LLM_JSON_MODE (default json_object): pass response_format json_object so
  the endpoint emits JSON directly; "off" disables the hint. Strict
  JSON+Pydantic validation stays on either way — the hint only cuts the
  malformed-regen path, it never relaxes validation.

Structured output is enforced by strict JSON parsing + Pydantic
validation. Malformed output triggers one regeneration retry, then an
actionable 502 — never silent malformed data.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from pydantic import BaseModel, Field

log = logging.getLogger("mrprof")

SUPPORTED_PROVIDERS = ("dummy", "openai-compatible")
DEFAULT_TIMEOUT_S = 30
DEFAULT_EXTRACT_TIMEOUT_S = 60
DEFAULT_MAX_TOKENS = 300


class LLMConfig(BaseModel):
    provider: str = "dummy"
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    timeout_s: int = DEFAULT_TIMEOUT_S
    max_tokens: int = DEFAULT_MAX_TOKENS
    json_mode: str = "json_object"
    reasoning_effort: str = "minimal"
    # Extraction emits long JSON and runs off the critical path
    # (BackgroundTasks), so it gets its own generous bound.
    extractor_timeout_s: int = DEFAULT_EXTRACT_TIMEOUT_S


class LLMQuestion(BaseModel):
    question_text: str = Field(min_length=3, max_length=500)
    objective: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=3, max_length=500)


class LLMError(Exception):
    """Actionable model failure. `code` is machine-readable; `message` is
    safe to return (never contains keys or answer text)."""

    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def load_config() -> LLMConfig:
    def _int(name: str, default: int) -> int:
        try:
            return max(1, int(os.environ.get(name, str(default))))
        except ValueError:
            return default

    return LLMConfig(
        provider=(os.environ.get("LLM_PROVIDER", "dummy") or "dummy").strip().lower(),
        model=(os.environ.get("LLM_MODEL", "") or "").strip(),
        base_url=(os.environ.get("LLM_BASE_URL", "") or "").strip().rstrip("/"),
        api_key=(os.environ.get("LLM_API_KEY", "") or "").strip(),
        timeout_s=_int("LLM_TIMEOUT_S", DEFAULT_TIMEOUT_S),
        max_tokens=_int("LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS),
        json_mode=(os.environ.get("LLM_JSON_MODE", "json_object") or "json_object").strip().lower(),
        reasoning_effort=(os.environ.get("LLM_REASONING_EFFORT", "minimal") or "minimal").strip().lower(),
        extractor_timeout_s=_int("LLM_EXTRACT_TIMEOUT_S", DEFAULT_EXTRACT_TIMEOUT_S),
    )


def is_dummy(cfg: LLMConfig) -> bool:
    """True only when explicitly configured for the stub path."""
    return cfg.provider == "dummy"


def require_effective_provider(cfg: LLMConfig) -> str:
    """Resolve the execution path, failing loudly on misconfiguration.

    Unknown providers and incomplete credentials raise actionable
    LLMError instead of silently falling back to the stub.
    """
    if cfg.provider == "dummy":
        return "dummy"
    if cfg.provider not in SUPPORTED_PROVIDERS:
        raise LLMError(
            "provider_unsupported",
            f"LLM_PROVIDER={cfg.provider!r} is not supported. "
            f"Supported: {list(SUPPORTED_PROVIDERS)}.",
            status=500,
        )
    if not (cfg.model and cfg.base_url and cfg.api_key):
        raise LLMError(
            "provider_misconfigured",
            f"LLM_PROVIDER={cfg.provider!r} needs LLM_MODEL, LLM_BASE_URL, "
            "and LLM_API_KEY all set. No state was changed.",
            status=500,
        )
    return cfg.provider


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def chat_options(cfg: LLMConfig, effort: str | None) -> dict:
    """Build the ChatOptions hint dict. Validation is unchanged either way.

    effort "off"/"" omits the reasoning hint (for endpoints that reject it);
    None means full default reasoning (background extraction).
    """
    options: dict = (
        {"response_format": {"type": "json_object"}} if cfg.json_mode == "json_object" else {}
    )
    if effort and effort != "off":
        options["reasoning"] = {"effort": effort}
    return options


def parse_llm_json(text: str, objective: str) -> LLMQuestion:
    """Strict-parse model output. Raises LLMError (malformed) on any deviation."""
    try:
        data = json.loads(_strip_fences(text))
    except (json.JSONDecodeError, ValueError):
        raise LLMError(
            "malformed_output",
            "Model did not return valid JSON. Check that the configured model "
            "follows JSON-only instructions or use LLM_PROVIDER=dummy.",
        )
    if not isinstance(data, dict):
        raise LLMError(
            "malformed_output",
            "Model returned a JSON value that is not an object. Check the model "
            "configuration or use LLM_PROVIDER=dummy.",
        )
    data.setdefault("objective", objective)
    try:
        return LLMQuestion.model_validate(data)
    except ValueError as exc:
        raise LLMError(
            "malformed_output",
            "Model output failed validation (one question + objective + reason "
            f"required): {exc}. Check the model or use LLM_PROVIDER=dummy.",
        )


async def generate_next_question(
    *,
    cfg: LLMConfig,
    instructions: str,
    prompt: str,
    objective: str,
    reason: str,
    fallback_question: str,
    session_id: str,
) -> tuple[LLMQuestion, dict, dict]:
    """Run one InterviewAgent turn. Returns (question, model_info, session_blob).

    Dummy path returns the deterministic fallback with no network.
    Real path uses Agent Framework (Agent + OpenAI-compatible chat client),
    one regen retry on malformed output, bounded by LLM_TIMEOUT_S.
    """
    model_info = {
        "provider": cfg.provider,
        "model": cfg.model or "dummy-stub",
    }
    session_blob = {"session_id": session_id}
    if require_effective_provider(cfg) == "dummy":
        return (
            LLMQuestion(question_text=fallback_question, objective=objective, reason=reason),
            model_info,
            session_blob,
        )
    agent, session = build_agent(cfg, instructions, session_id)
    last_error: LLMError | None = None
    current_prompt = prompt
    # Bounded attempts: one transient retry (timeout/provider blip, same prompt)
    # plus one malformed-output regen (repair prompt). Worst case: 3 calls.
    for attempt in (1, 2, 3):
        try:
            text, model_info, session_blob = await run_agent_text(
                cfg, agent, session, current_prompt, model_info, session_id,
                effort=cfg.reasoning_effort,
            )
        except LLMError as exc:
            if exc.code in ("timeout", "provider_error") and attempt == 1:
                log.warning("transient model failure, retrying once: %s", exc.code)
                continue
            raise
        try:
            return parse_llm_json(text, objective), model_info, session_blob
        except LLMError as exc:
            last_error = exc
            if attempt == 3:
                break
            # prompt may be a single string or a list of lines (build_prompt);
            # the repair instruction needs a string either way.
            base = prompt if isinstance(prompt, str) else "\n".join(prompt)
            current_prompt = (
                "Your previous reply was not valid JSON with keys "
                "question_text/objective/reason. Reply with JSON ONLY, no other text.\n\n"
                + base
            )
            log.warning("malformed model output (attempt %d), retrying", attempt)
    assert last_error is not None
    raise last_error


def build_agent(cfg: LLMConfig, instructions: str, session_id: str) -> tuple:
    """Build (agent, session). Raises actionable LLMError on any setup failure."""
    try:
        from agent_framework import Agent, AgentSession
        from agent_framework.openai import OpenAIChatClient
    except ImportError as exc:
        raise LLMError(
            "framework_unavailable",
            "Microsoft Agent Framework client is not installed. "
            "Install agent-framework with the OpenAI client or use "
            f"LLM_PROVIDER=dummy. ({type(exc).__name__})",
            status=500,
        )
    try:
        client = OpenAIChatClient(model=cfg.model, api_key=cfg.api_key, base_url=cfg.base_url)
        agent = Agent(client=client, instructions=instructions)
        session = AgentSession(session_id=session_id)
    except Exception as exc:
        raise LLMError(
            "provider_misconfigured",
            "Could not configure the model client. Check LLM_MODEL, "
            f"LLM_BASE_URL, and credentials. ({type(exc).__name__})",
            status=500,
        )
    return agent, session


async def run_agent_text(
    cfg: LLMConfig,
    agent,
    session,
    prompt: str,
    model_info: dict,
    session_id: str,
    timeout_s: int | None = None,
    effort: str | None = None,
) -> tuple[str, dict, dict]:
    """One bounded agent call. Returns (text, model_info, session_blob).

    Raises LLMError (timeout / provider_error); never leaks keys or answers.
    timeout_s overrides cfg.timeout_s for callers (like extraction) that
    need a different bound. effort sets the reasoning hint via chat_options;
    None keeps full default reasoning. When cfg.json_mode is "json_object",
    response_format is passed as a ChatOptions hint; validation is
    unchanged — the hint only avoids the malformed-regen retry.
    """
    import time

    bound = timeout_s or cfg.timeout_s
    started = time.monotonic()
    options = chat_options(cfg, effort)
    try:
        response = await asyncio.wait_for(
            agent.run(prompt, session=session, options=options), timeout=bound
        )
    except (asyncio.TimeoutError, TimeoutError):
        raise LLMError(
            "timeout",
            f"Model request timed out after {bound}s. "
            "No state was changed; retry with the same idempotency key.",
            status=502,
        )
    except Exception as exc:
        # Never leak keys/answers: exception text is not forwarded.
        log.warning("model call failed: %s", type(exc).__name__)
        raise LLMError(
            "provider_error",
            "Model request failed before any state was saved. Check "
            "LLM_BASE_URL/LLM_MODEL/credentials and retry with the same "
            f"idempotency key. ({type(exc).__name__})",
            status=502,
        )
    try:
        session_blob = session.to_dict()
    except Exception:  # noqa: BLE001 - blob is best-effort diagnostics
        session_blob = {"session_id": session_id}
    usage = getattr(response, "usage_details", None)
    if usage is not None:
        model_info["usage"] = str(usage)[:500]
    log.info("model call ok in %.1fs", time.monotonic() - started)
    return (response.text or "").strip(), model_info, session_blob
