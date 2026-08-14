"""AIProvider abstraction (spec section 18).

The rest of the application talks only to `AIProvider` — never to a specific
vendor SDK — so a new provider can be dropped in by implementing this
interface and flipping the `AI_PROVIDER` env var. Credentials never leave the
backend; the frontend only ever calls our own `/api/v1/ai/*` endpoints.
"""
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger("survivalschool.ai")


@dataclass
class AIResponse:
    content: str
    provider: str
    tokens_used: int | None
    latency_ms: int
    error: str | None = None


@dataclass
class GeneratedMCQ:
    """One AI-generated multiple-choice question. Exactly one option must be
    marked correct — enforced by AIGenerationError below at the point of
    generation, not left for a caller to discover later."""
    prompt: str
    options: list[tuple[str, bool]] = field(default_factory=list)


class AIGenerationError(Exception):
    """Raised when an AI provider fails to produce well-formed questions —
    e.g. Sarvam returns text that isn't valid JSON, or the shape doesn't
    match (missing options, more/less than one correct answer). The caller
    must surface this as a real error to the student rather than silently
    falling back to fabricated content."""


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def chat(self, messages: list[dict], *, system_prompt: str | None = None) -> AIResponse:
        ...

    @abstractmethod
    async def generate_questions(self, subject: str, count: int) -> list[GeneratedMCQ]:
        ...


class MockAIProvider(AIProvider):
    """Deterministic, zero-cost provider used by default and in tests/CI.
    Produces plausible tutoring-style responses without calling any external
    service — never presented to the user as a real Sarvam response."""

    name = "mock"

    async def chat(self, messages: list[dict], *, system_prompt: str | None = None) -> AIResponse:
        start = time.perf_counter()
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        content = (
            f"(Mock AI tutor) Here's a starting point on \"{last_user[:120]}\": break the problem into "
            "smaller steps, check the relevant lesson material, and try a practice question. "
            "Connect a real Sarvam AI key and set AI_PROVIDER=sarvam to replace this with a live response."
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        return AIResponse(content=content, provider=self.name, tokens_used=len(content.split()), latency_ms=latency_ms)

    async def generate_questions(self, subject: str, count: int) -> list[GeneratedMCQ]:
        """Deterministic, zero-cost, template-based question generation —
        same honesty contract as MockAIProvider.chat(): real, working code
        that produces genuinely internally-consistent MCQs (one clearly
        marked correct answer among four options), openly a mock/dev
        stand-in rather than a real Sarvam call. Connect a real Sarvam key
        and set AI_PROVIDER=sarvam for live AI-authored questions."""
        questions: list[GeneratedMCQ] = []
        for i in range(1, count + 1):
            options = [
                (f"The correct concept #{i} in {subject}", True),
                (f"A related but incorrect idea #{i} in {subject}", False),
                (f"A common misconception about {subject} (#{i})", False),
                (f"An unrelated distractor for {subject} (#{i})", False),
            ]
            questions.append(GeneratedMCQ(
                prompt=f"(Mock AI) Practice question {i} on \"{subject}\": which of the following is correct?",
                options=options,
            ))
        return questions


class SarvamAIProvider(AIProvider):
    """Real integration against Sarvam AI's chat completions API.

    IMPORTANT — honesty note (see docs/AI.md): this implementation is written
    against Sarvam's publicly documented REST contract and a real API key is
    configured, but this sandbox's network egress does not reach api.sarvam.ai
    (confirmed via a direct connectivity test), so this code path has NOT been
    exercised with a live call from this environment. It will execute for real
    the moment it runs somewhere with network access to Sarvam — status is
    CONFIGURED, NOT TESTED, not "working."
    """

    name = "sarvam"

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.SARVAM_API_KEY
        self.base_url = settings.SARVAM_BASE_URL
        self.model = settings.SARVAM_CHAT_MODEL
        self.timeout = settings.AI_REQUEST_TIMEOUT_SECONDS

    async def chat(self, messages: list[dict], *, system_prompt: str | None = None) -> AIResponse:
        if not self.api_key:
            return AIResponse(content="", provider=self.name, tokens_used=None, latency_ms=0,
                               error="SARVAM_API_KEY is not configured.")

        payload_messages = messages
        if system_prompt:
            payload_messages = [{"role": "system", "content": system_prompt}, *messages]

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers={"api-subscription-key": self.api_key, "Content-Type": "application/json"},
                    json={"model": self.model, "messages": payload_messages},
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                tokens = data.get("usage", {}).get("total_tokens")
        except Exception as exc:
            logger.error("sarvam_call_failed", error=str(exc))
            return AIResponse(content="", provider=self.name, tokens_used=None,
                               latency_ms=int((time.perf_counter() - start) * 1000), error=str(exc))

        return AIResponse(content=content, provider=self.name, tokens_used=tokens,
                           latency_ms=int((time.perf_counter() - start) * 1000))

    async def generate_questions(self, subject: str, count: int) -> list[GeneratedMCQ]:
        """Asks Sarvam for strict JSON and parses it defensively. Never
        fabricates a fallback question set on failure — a malformed or
        missing response raises AIGenerationError, which the API layer turns
        into a clear error for the student rather than silently serving
        something that looks generated but isn't real. Same untested-from-
        this-sandbox caveat as chat() above."""
        system_prompt = (
            "You are a question-generation engine for a university practice tool. "
            "Output ONLY valid JSON, no prose, no markdown fences. The JSON must be a list of objects, "
            "each shaped exactly as: "
            '{"prompt": "...", "options": [{"text": "...", "is_correct": true}, '
            '{"text": "...", "is_correct": false}, {"text": "...", "is_correct": false}, '
            '{"text": "...", "is_correct": false}]}. '
            "Exactly one option per question must have is_correct true. Do not include any other keys or text."
        )
        user_prompt = f"Generate exactly {count} multiple-choice practice questions about: {subject}"
        response = await self.chat([{"role": "user", "content": user_prompt}], system_prompt=system_prompt)
        if response.error:
            raise AIGenerationError(f"Sarvam AI request failed: {response.error}")

        raw = response.content.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIGenerationError("Sarvam AI did not return valid JSON.") from exc

        if not isinstance(data, list) or not data:
            raise AIGenerationError("Sarvam AI returned an empty or malformed question list.")

        questions: list[GeneratedMCQ] = []
        for item in data:
            if not isinstance(item, dict) or "prompt" not in item or "options" not in item:
                raise AIGenerationError("Sarvam AI returned a question missing required fields.")
            options = item["options"]
            if not isinstance(options, list) or len(options) < 2:
                raise AIGenerationError("Sarvam AI returned a question with fewer than 2 options.")
            correct_count = sum(1 for o in options if isinstance(o, dict) and o.get("is_correct") is True)
            if correct_count != 1:
                raise AIGenerationError("Sarvam AI returned a question without exactly one correct option.")
            questions.append(GeneratedMCQ(
                prompt=str(item["prompt"]),
                options=[(str(o["text"]), bool(o.get("is_correct", False))) for o in options],
            ))
        return questions


def get_ai_provider() -> AIProvider:
    settings = get_settings()
    if settings.AI_PROVIDER == "sarvam":
        return SarvamAIProvider()
    return MockAIProvider()
