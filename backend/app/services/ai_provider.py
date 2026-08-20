"""AIProvider abstraction."""
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
class TopicScopeAssessment:
    """A live AI judgment of a freely-typed (subject, topic) pair — used to
    gate AI Weekly Exam registration, which by definition has no existing
    question-bank history to score a formula against (see
    ai_exam_service.py::evaluate_ai_weekly_topic)."""
    difficulty_percent: int
    is_appropriate_scope: bool
    reason: str


@dataclass
class GeneratedMCQ:
    prompt: str
    options: list[tuple[str, bool]] = field(default_factory=list)
    # "single" (exactly one correct option, MCQ) | "multiple" (one or more
    # correct options, MSQ). Defaults to "single" so the existing
    # generate_questions() callers (ai_practice, the old weekly/monthly
    # contest slots) are unaffected.
    question_type: str = "single"


class AIGenerationError(Exception):
    """Raised when a provider cannot produce valid generated content."""


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def chat(
        self, messages: list[dict], *, system_prompt: str | None = None, image_data_url: str | None = None
    ) -> AIResponse:
        ...

    @abstractmethod
    async def generate_questions(self, subject: str, count: int) -> list[GeneratedMCQ]:
        ...

    @abstractmethod
    async def generate_mixed_questions(self, topic: str, single_count: int, multiple_count: int) -> list[GeneratedMCQ]:
        """single_count single-answer (MCQ) + multiple_count multi-answer
        (MSQ) questions on `topic`, e.g. the AI Weekly Exam's 40+10 set."""
        ...

    @abstractmethod
    async def evaluate_topic_scope(self, subject: str, topic: str) -> TopicScopeAssessment:
        """Judges whether `topic` is a real, well-scoped subtopic of
        `subject` — broad enough to support 50 distinct, non-repetitive
        exam questions — and how difficult such an exam would be."""
        ...


class MockAIProvider(AIProvider):
    name = "mock"

    async def chat(
        self, messages: list[dict], *, system_prompt: str | None = None, image_data_url: str | None = None
    ) -> AIResponse:
        start = time.perf_counter()
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        image_note = " I can see you attached an image — connect a real Sarvam AI key to have it actually analyzed." if image_data_url else ""
        content = (
            f"(Mock AI tutor) Here's a starting point on \"{last_user[:120]}\": break the problem into "
            "smaller steps, check the relevant lesson material, and try a practice question."
            f"{image_note} "
            "Connect a real Sarvam AI key and set AI_PROVIDER=sarvam to replace this with a live response."
        )
        return AIResponse(content=content, provider=self.name, tokens_used=len(content.split()),
                          latency_ms=int((time.perf_counter() - start) * 1000))

    async def generate_questions(self, subject: str, count: int) -> list[GeneratedMCQ]:
        questions: list[GeneratedMCQ] = []
        for i in range(1, count + 1):
            questions.append(GeneratedMCQ(
                prompt=f"(Mock AI) Practice question {i} on \"{subject}\": which of the following is correct?",
                options=[
                    (f"The correct concept #{i} in {subject}", True),
                    (f"A related but incorrect idea #{i} in {subject}", False),
                    (f"A common misconception about {subject} (#{i})", False),
                    (f"An unrelated distractor for {subject} (#{i})", False),
                ],
            ))
        return questions

    async def generate_mixed_questions(self, topic: str, single_count: int, multiple_count: int) -> list[GeneratedMCQ]:
        questions: list[GeneratedMCQ] = []
        for i in range(1, single_count + 1):
            questions.append(GeneratedMCQ(
                prompt=f"(Mock AI) Question {i} on \"{topic}\": which of the following is correct?",
                options=[(f"Correct concept #{i}", True), (f"Distractor A #{i}", False), (f"Distractor B #{i}", False), (f"Distractor C #{i}", False)],
                question_type="single",
            ))
        for i in range(1, multiple_count + 1):
            questions.append(GeneratedMCQ(
                prompt=f"(Mock AI) Multi-select question {i} on \"{topic}\": select ALL that apply.",
                options=[(f"Correct concept A #{i}", True), (f"Correct concept B #{i}", True), (f"Distractor #{i}", False), (f"Another distractor #{i}", False)],
                question_type="multiple",
            ))
        return questions

    async def evaluate_topic_scope(self, subject: str, topic: str) -> TopicScopeAssessment:
        subject_clean, topic_clean = subject.strip(), topic.strip()
        if not topic_clean or topic_clean.lower() == subject_clean.lower():
            return TopicScopeAssessment(
                difficulty_percent=0, is_appropriate_scope=False,
                reason="(Mock AI) The topic must be a real, specific subtopic of the subject — not blank or identical to the subject itself.",
            )
        # Deterministic stand-in for a real judgment call: a longer, more
        # specific topic description plausibly supports more/harder distinct
        # questions than a one- or two-word topic does. Real scoring comes
        # from SarvamAIProvider once AI_PROVIDER=sarvam is configured.
        score = min(96, max(35, len(topic_clean) * 3))
        appropriate = len(topic_clean.split()) >= 2 and len(topic_clean) >= 8
        reason = (
            f"(Mock AI) \"{topic_clean}\" under \"{subject_clean}\" scored {score}% difficulty based on topic length/specificity. "
            + ("Scope looks broad enough for a 50-question exam." if appropriate
               else "Too short or vague to reliably support 50 distinct questions — be more specific.")
            + " Connect a real Sarvam AI key and set AI_PROVIDER=sarvam for a real evaluation."
        )
        return TopicScopeAssessment(difficulty_percent=score, is_appropriate_scope=appropriate, reason=reason)


class SarvamAIProvider(AIProvider):
    name = "sarvam"

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.SARVAM_API_KEY
        self.base_url = settings.SARVAM_BASE_URL
        self.model = settings.SARVAM_CHAT_MODEL
        self.vision_model = settings.SARVAM_VISION_MODEL
        self.timeout = settings.AI_REQUEST_TIMEOUT_SECONDS

    async def chat(
        self, messages: list[dict], *, system_prompt: str | None = None, image_data_url: str | None = None
    ) -> AIResponse:
        if not self.api_key:
            return AIResponse(content="", provider=self.name, tokens_used=None, latency_ms=0,
                               error="SARVAM_API_KEY is not configured.")

        payload_messages = [{"role": "system", "content": system_prompt}, *messages] if system_prompt else list(messages)

        # Image input is only documented on /v2/chat/completions with the
        # gemma4 model (see SARVAM_VISION_MODEL's comment in config.py) — the
        # flagship v1 model used for every other request has no documented
        # vision support. Only the LAST message gets the multimodal content
        # array; earlier turns stay plain text, matching how the rest of the
        # conversation history is already plain strings.
        endpoint = "/v1/chat/completions"
        model = self.model
        if image_data_url and payload_messages and payload_messages[-1]["role"] == "user":
            endpoint = "/v2/chat/completions"
            model = self.vision_model
            last = payload_messages[-1]
            payload_messages[-1] = {
                "role": "user",
                "content": [
                    {"type": "text", "text": last["content"]},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }

        headers = {"api-subscription-key": self.api_key, "Content-Type": "application/json"}
        if endpoint == "/v2/chat/completions":
            # v2 documents both api-subscription-key and a bearer
            # Authorization header as required; v1 only ever needed the
            # former, so this is added only on the v2 path rather than
            # changed globally.
            headers["Authorization"] = f"Bearer {self.api_key}"

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}{endpoint}",
                    headers=headers,
                    json={"model": model, "messages": payload_messages, "max_tokens": 2048},
                )
                if resp.status_code >= 400:
                    body = resp.text[:500]
                    logger.error("sarvam_call_failed", status=resp.status_code, model=model, body=body)
                    return AIResponse(content="", provider=self.name, tokens_used=None,
                                       latency_ms=int((time.perf_counter() - start) * 1000),
                                       error=f"Sarvam {resp.status_code}: {body}")
                data = resp.json()
                try:
                    content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as exc:
                    logger.error("sarvam_invalid_response", model=model, error=type(exc).__name__)
                    return AIResponse(content="", provider=self.name, tokens_used=None,
                                       latency_ms=int((time.perf_counter() - start) * 1000),
                                       error="Sarvam returned a response without message content.")
                if not isinstance(content, str) or not content.strip():
                    logger.error("sarvam_empty_response", model=model)
                    return AIResponse(content="", provider=self.name, tokens_used=None,
                                       latency_ms=int((time.perf_counter() - start) * 1000),
                                       error="Sarvam returned empty message content.")
                tokens = data.get("usage", {}).get("total_tokens")
        except Exception as exc:
            logger.error("sarvam_call_failed", model=model, error=str(exc))
            return AIResponse(content="", provider=self.name, tokens_used=None,
                               latency_ms=int((time.perf_counter() - start) * 1000), error=str(exc))

        return AIResponse(content=content, provider=self.name, tokens_used=tokens,
                          latency_ms=int((time.perf_counter() - start) * 1000))

    async def generate_questions(self, subject: str, count: int) -> list[GeneratedMCQ]:
        system_prompt = (
            "You are a question-generation engine for a university practice tool. "
            "Output ONLY valid JSON, no prose, no markdown fences. The JSON must be a list of objects, "
            "each shaped exactly as: "
            '{"prompt": "...", "options": [{"text": "...", "is_correct": true}, '
            '{"text": "...", "is_correct": false}, {"text": "...", "is_correct": false}, '
            '{"text": "...", "is_correct": false}]}. '
            "Exactly one option per question must have is_correct true. Do not include any other keys or text."
        )
        response = await self.chat(
            [{"role": "user", "content": f"Generate exactly {count} multiple-choice practice questions about: {subject}"}],
            system_prompt=system_prompt,
        )
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
            if sum(1 for o in options if isinstance(o, dict) and o.get("is_correct") is True) != 1:
                raise AIGenerationError("Sarvam AI returned a question without exactly one correct option.")
            questions.append(GeneratedMCQ(
                prompt=str(item["prompt"]),
                options=[(str(o["text"]), bool(o.get("is_correct", False))) for o in options],
            ))
        return questions

    async def generate_mixed_questions(self, topic: str, single_count: int, multiple_count: int) -> list[GeneratedMCQ]:
        system_prompt = (
            "You are a question-generation engine for a university competitive exam. "
            "Output ONLY valid JSON, no prose, no markdown fences. The JSON must be a list of objects, "
            "each shaped exactly as: "
            '{"prompt": "...", "question_type": "single"|"multiple", "options": '
            '[{"text": "...", "is_correct": true|false}, ...]}. '
            "For question_type \"single\", exactly one option must have is_correct true (this is a standard "
            "multiple-choice question). For question_type \"multiple\", one or more options must have "
            "is_correct true, and at least one option must have is_correct false (this is a select-all-that-apply "
            "question, so it must have at least one wrong option to be a real question). Every question needs "
            "2-6 options. Do not include any other keys or text."
        )
        response = await self.chat(
            [{"role": "user", "content": (
                f"Generate exactly {single_count} single-answer multiple-choice questions and exactly "
                f"{multiple_count} multi-select questions about: {topic}. Total {single_count + multiple_count} questions."
            )}],
            system_prompt=system_prompt,
        )
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
            qtype = item.get("question_type")
            if qtype not in ("single", "multiple"):
                raise AIGenerationError(f"Sarvam AI returned an invalid question_type: {qtype!r}.")
            options = item["options"]
            if not isinstance(options, list) or len(options) < 2:
                raise AIGenerationError("Sarvam AI returned a question with fewer than 2 options.")
            correct_count = sum(1 for o in options if isinstance(o, dict) and o.get("is_correct") is True)
            if qtype == "single" and correct_count != 1:
                raise AIGenerationError("Sarvam AI returned a 'single' question without exactly one correct option.")
            if qtype == "multiple" and (correct_count < 1 or correct_count >= len(options)):
                raise AIGenerationError("Sarvam AI returned a 'multiple' question without a valid mix of correct/incorrect options.")
            questions.append(GeneratedMCQ(
                prompt=str(item["prompt"]), question_type=qtype,
                options=[(str(o["text"]), bool(o.get("is_correct", False))) for o in options],
            ))
        return questions

    async def evaluate_topic_scope(self, subject: str, topic: str) -> TopicScopeAssessment:
        system_prompt = (
            "You evaluate whether a topic is well-scoped for a rigorous university competitive exam. "
            "Output ONLY valid JSON, no prose, no markdown fences, shaped exactly as: "
            '{"difficulty_percent": <integer 0-100>, "is_appropriate_scope": true|false, "reason": "..."}. '
            "difficulty_percent is how hard a rigorous 50-question mixed multiple-choice/multi-select exam on "
            "this exact topic would be for a well-prepared student — 0 is trivial, 100 is expert-level. "
            "is_appropriate_scope is true only if the topic is a real, specific, well-defined subtopic of the "
            "given subject that is broad enough to support 50 distinct, non-repetitive questions without padding "
            "— false if the topic is blank, nonsensical, unrelated to the subject, or too narrow/trivial to "
            "support that many distinct questions. reason is a short 1-2 sentence explanation covering both judgments."
        )
        response = await self.chat(
            [{"role": "user", "content": f"Subject: {subject}\nTopic: {topic}"}],
            system_prompt=system_prompt,
        )
        if response.error:
            raise AIGenerationError(f"Sarvam AI request failed: {response.error}")

        raw = response.content.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AIGenerationError("Sarvam AI did not return valid JSON.") from exc
        if not isinstance(data, dict) or "difficulty_percent" not in data or "is_appropriate_scope" not in data:
            raise AIGenerationError("Sarvam AI returned a malformed topic-scope evaluation.")
        try:
            difficulty = int(data["difficulty_percent"])
        except (TypeError, ValueError) as exc:
            raise AIGenerationError("Sarvam AI returned a non-numeric difficulty_percent.") from exc
        difficulty = max(0, min(100, difficulty))
        return TopicScopeAssessment(
            difficulty_percent=difficulty,
            is_appropriate_scope=bool(data["is_appropriate_scope"]),
            reason=str(data.get("reason", "")).strip() or "No reason provided.",
        )


def get_ai_provider() -> AIProvider:
    return SarvamAIProvider() if get_settings().AI_PROVIDER == "sarvam" else MockAIProvider()
