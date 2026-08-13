"""AIProvider abstraction (spec section 18).

The rest of the application talks only to `AIProvider` — never to a specific
vendor SDK — so a new provider can be dropped in by implementing this
interface and flipping the `AI_PROVIDER` env var. Credentials never leave the
backend; the frontend only ever calls our own `/api/v1/ai/*` endpoints.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

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


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def chat(self, messages: list[dict], *, system_prompt: str | None = None) -> AIResponse:
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


def get_ai_provider() -> AIProvider:
    settings = get_settings()
    if settings.AI_PROVIDER == "sarvam":
        return SarvamAIProvider()
    return MockAIProvider()
