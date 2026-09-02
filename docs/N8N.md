# n8n automation integration

## What exists

A real, published workflow in the user's actual n8n Cloud instance:

- **Name**: "Survival School — Event Router"
- **Workflow ID**: `y96SeFRWA6e594bS`
- **Status**: `active: true` (confirmed live via a direct n8n API query during
  this documentation pass — not an assumption from earlier in the build)
- **Trigger**: Webhook, `POST`
  `https://vishalreddy18.app.n8n.cloud/webhook/survivalschool/events`
  (production URL) / `https://vishalreddy18.app.n8n.cloud/webhook-test/survivalschool/events`
  (test URL), no additional webhook credentials required (auth happens via
  the `x-n8n-webhook-secret` header the backend sends, checked inside the
  workflow, not via n8n's own credential system)
- **9 nodes**, single trigger, response mode "Respond to Webhook"
- A reference copy of the workflow's source lives at
  `infra/n8n/event-router.workflow.js` in this repository for version
  control / disaster recovery, since the canonical copy lives in n8n Cloud,
  outside this git repo.

## What it does

Receives lifecycle events from the backend and builds notification content
for each.

**Correction (post-pivot):** the table below previously listed
`course.enrolled`, `quiz.completed`, `exam.completed`, and
`certificate.issued` from `api/v1/courses.py` / `quizzes.py` / `exams.py` /
`lessons.py` — none of those routers exist anymore (see the
courses/LMS-removal migration; this platform pivoted to a contest/practice
model). That table was stale, describing a pre-pivot version of this
integration. Here is every event type the *current* codebase actually
emits, found by grepping every `emit_event(...)` call site:

| Event type | Emitted from | Purpose |
|---|---|---|
| `student.registered` | `api/v1/auth.py`, after successful registration | Welcome notification |
| `instructor.application_approved` | `api/v1/admin.py`, after an admin approves an instructor application | Tell the applicant they're approved |
| `campus_timetable.changed` | `app/services/campus_timetable_service.py::apply_campus_rows`, whenever a sync (manual upload or live-sync poll) produces a room change, time change, or cancellation | Change-detection alert — see note below |

**`campus_timetable.changed` payload** is `{"source": "upload"|"live_sync",
"change_count": int, "changes": [{"section", "course", "date", "old_room",
"new_room", "old_time", "new_time", "was_cancelled"}, ...]}` (capped to the
first 50 changes). Change detection itself — including de-duplication, via
a content hash on each row so re-uploading identical data never re-fires —
is real, tested backend logic, not a stub. What it does NOT include is
which students are affected (no email addresses, no resolved recipient
list) — an n8n workflow handling this event would need to resolve
"students whose profile.section matches this change's section" itself
(the backend has no callback endpoint for that today), or the payload
would need to be enriched with resolved recipients before this is
genuinely actionable as a real email trigger.

**Whether the *live* n8n workflow currently routes and builds content for
`instructor.application_approved` and `campus_timetable.changed`
specifically has not been re-verified** since this correction — the
original documentation pass (below) only confirmed the workflow was active
and correct for the (now-stale) event list above. Re-run the verification
steps in this file against the current event names before relying on it.

The workflow's own description (visible via the n8n API, as of the
original documentation pass) was explicit about its own limits: *"Email/Slack
delivery nodes are not yet wired to real credentials"* — i.e. even for
events it does recognize, the workflow receives, routes, and builds
content, but does not send a real email or Slack message anywhere. Wiring
an actual SMTP/Slack credential into the existing delivery nodes — and,
for `campus_timetable.changed`, adding recipient-resolution — is n8n
Cloud workflow configuration, owned by whoever holds that n8n account; it
is not a backend code change and cannot be done from this repository.

## Backend integration point

`app/services/n8n_service.py::emit_event(event_type, payload)`:

```python
POST {N8N_WEBHOOK_BASE_URL}/webhook/survivalschool/events
headers: {"x-n8n-webhook-secret": N8N_WEBHOOK_SECRET}
body: {"event_type": event_type, **payload}
```

Called with `await` but never allowed to affect the request that triggered
it — wrapped in try/except, failures are logged
(`logger.warning("n8n_event_failed", ...)`) and swallowed. If
`N8N_WEBHOOK_BASE_URL` isn't configured, the function no-ops with a debug
log rather than raising. This matches the spec requirement that automation
outages never affect core application behavior (registration, enrollment,
grading, certificate issuance all commit to Postgres regardless of whether
the n8n call that follows succeeds).

## Current status: workflow TESTED, backend→n8n network hop NOT TESTED from this sandbox

Two separable claims:

1. **The workflow itself is correct.** It was created, its trigger
   configuration was validated, and — critically — it was actually executed
   with real payloads through the n8n platform's own tools during this
   build, producing real execution output. This is not a claim based on
   reading the workflow definition; it was run.
2. **The backend's HTTP call to that webhook has not been exercised from
   this sandbox.** A direct connectivity test from this environment to
   `vishalreddy18.app.n8n.cloud` returned a 403 from the sandbox's own
   network proxy — the same class of egress restriction documented for
   Sarvam AI in `docs/AI.md`, not an error from n8n or the workflow itself.

Net effect: the moment `emit_event()` runs from a host with real network
access to that n8n instance, it will work — the webhook is live, active, and
already proven to accept and correctly route this exact payload shape. What
hasn't happened yet is running the backend itself somewhere with that
network access and watching the HTTP call succeed end-to-end.

## How to verify the live hop once deployed somewhere with real egress

```bash
curl -X POST https://vishalreddy18.app.n8n.cloud/webhook/survivalschool/events \
  -H "content-type: application/json" \
  -H "x-n8n-webhook-secret: <your N8N_WEBHOOK_SECRET>" \
  -d '{"event_type": "student.registered", "email": "test@example.com", "full_name": "Test User"}'
```

A 200 response confirms the full path (backend network egress → n8n webhook
→ workflow execution) works, not just the workflow in isolation.
