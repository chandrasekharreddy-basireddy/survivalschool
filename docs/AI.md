# AI assistant (Sarvam AI integration)

## Design: provider abstraction, not a vendor lock-in

`app/services/ai_provider.py` defines an `AIProvider` interface with a single
method, `chat(messages, system_prompt=None) -> AIResponse`. Two
implementations exist:

- **`MockAIProvider`** (`name = "mock"`) — deterministic, zero-cost, used by
  default and by the entire automated test suite / CI pipeline. It never
  calls any external service and its responses are explicitly labeled as
  mock in their own content ("Connect a real Sarvam AI key... to replace
  this with a live response").
- **`SarvamAIProvider`** (`name = "sarvam"`) — a real `httpx` client posting
  to `{SARVAM_BASE_URL}/v1/chat/completions` with the
  `api-subscription-key` header, using `SARVAM_CHAT_MODEL` (default
  `sarvam-m`), matching Sarvam's publicly documented chat-completions
  contract.

`get_ai_provider()` selects between them based on the `AI_PROVIDER` setting
(`mock` or `sarvam`) — nothing else in the codebase imports `httpx` or
Sarvam-specific types directly, so swapping to a different vendor (or adding
a second one) means implementing the same four-method interface, not
touching route handlers or business logic.

## Current status: CONFIGURED, NOT LIVE-TESTED

The user-supplied Sarvam API key is present in `backend/.env`
(`SARVAM_API_KEY`, gitignored, `chmod 600`), `AI_PROVIDER=sarvam` is set, and
the HTTP call code is written against Sarvam's real REST contract.

**What was verified in this session:** the code compiles, passes lint, and
was exercised through its `MockAIProvider` path in integration tests (the AI
conversation endpoints — create conversation, send message, read history —
work end-to-end against the mock provider, which is what CI and the default
local/test environment use).

**What was NOT verified in this session:** an actual live HTTP call to
`api.sarvam.ai`. A direct connectivity test from this sandbox to that domain
was blocked by the sandbox's own network egress allowlist (confirmed: the
failure is a proxy-level 403, not an application error or an invalid key).
This is a constraint of the development sandbox, not of the code — the same
`SarvamAIProvider` code path will execute for real the moment it runs
somewhere with unrestricted network access to `api.sarvam.ai` (a real server,
a CI runner, or the user's own machine).

The `SarvamAIProvider` class docstring states this in the code itself, so
the honesty note travels with the implementation, not just this document:

> "this implementation is written against Sarvam's publicly documented REST
> contract and a real API key is configured, but this sandbox's network
> egress does not reach api.sarvam.ai... status is CONFIGURED, NOT TESTED,
> not 'working.'"

## How to actually verify the live integration

From an environment with real network access:

```bash
cd backend
source .venv/bin/activate  # or your environment
python -c "
import asyncio
from app.services.ai_provider import SarvamAIProvider

async def main():
    provider = SarvamAIProvider()
    resp = await provider.chat([{'role': 'user', 'content': 'What is a variable in Python?'}])
    print('error:', resp.error)
    print('content:', resp.content)

asyncio.run(main())
"
```

If `resp.error` is `None` and `resp.content` is non-empty, the live
integration works. If you see a connection error, check `SARVAM_API_KEY` and
`SARVAM_BASE_URL` in your `.env`, and confirm outbound HTTPS to
`api.sarvam.ai` is actually reachable from that host.

## Failure handling

If the Sarvam call fails for any reason (network error, bad key, non-2xx
response, malformed response body), `SarvamAIProvider.chat()` catches the
exception, logs it via structlog (`sarvam_call_failed`), and returns an
`AIResponse` with `error` set rather than raising — the `/ai/conversations/*`
route handlers surface that error to the client as a normal API error
response rather than a 500, so a Sarvam outage degrades gracefully instead of
breaking the endpoint.

## Rate limiting

`AI_DAILY_MESSAGE_LIMIT` (default 100) caps AI messages per user per day —
enforced in the conversation message endpoint, independent of the general
Redis-backed rate limiter used for auth endpoints.
