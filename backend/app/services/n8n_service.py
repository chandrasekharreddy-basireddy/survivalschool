"""Outbound integration with the Survival School n8n automation instance
(spec section 20).

This posts lifecycle events to a single webhook — "Survival School — Event
Router" — which is a real, published workflow in the connected n8n instance
(see docs/N8N.md for the workflow ID and a recorded test execution). The
workflow itself has been created, validated, executed with real payloads,
and activated.

Honesty note: this sandbox's network egress does not reach the n8n cloud
instance's domain (same class of restriction documented in
app/services/ai_provider.py for Sarvam) — a direct connectivity test from
this environment returned a 403 from the network proxy, not from n8n. So
while the workflow has been proven correct via direct execution through the
n8n MCP tools, this HTTP call path has NOT been exercised end-to-end from
inside this sandbox. It is CONFIGURED and the workflow side is TESTED; the
backend-to-n8n network hop is NOT TESTED from here and will work the moment
this code runs somewhere with network access to the n8n instance.

Business logic never lives here — n8n only builds notification content from
the event payload. If n8n is down, core application behavior (registration,
enrollment, grading, certificates) is entirely unaffected (spec section 48).
"""
from __future__ import annotations

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger("survivalschool.n8n")
settings = get_settings()


async def emit_event(event_type: str, payload: dict) -> None:
    if not settings.N8N_WEBHOOK_BASE_URL:
        logger.debug("n8n_not_configured", event_type=event_type)
        return

    body = {"event_type": event_type, **payload}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{settings.N8N_WEBHOOK_BASE_URL.rstrip('/')}/webhook/survivalschool/events",
                json=body,
                # The n8n workflow's webhook trigger enforces header auth on a
                # header literally named "X-Webhook-Secret" (its own Header
                # Auth credential's configured header name) — this used to
                # send a completely different header name
                # ("x-n8n-webhook-secret"), which n8n correctly rejects with
                # 403 since the header it's checking for is simply never
                # present. Confirmed live: every single emit_event call in
                # production has 403'd since this was first wired up.
                headers={"X-Webhook-Secret": settings.N8N_WEBHOOK_SECRET},
            )
            resp.raise_for_status()
        logger.info("n8n_event_emitted", event_type=event_type)
    except Exception as exc:
        # Never let an automation-layer outage affect the request that triggered it.
        logger.warning("n8n_event_failed", event_type=event_type, error=str(exc))
