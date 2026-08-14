# Multi-agent peer review — 2026-08-14

Four independent review agents ran in parallel against the current state of
the repository, each scoped to a different slice, each explicitly instructed
to report real bugs only (not style nitpicks) and to say so plainly when a
subsystem was clean rather than inventing findings. This is what they found
and what was actually fixed afterward — verified, not just claimed.

## Agent 1 — Backend security & correctness (new subsystems: 2FA, GDPR, push, daily challenge, Sentry)

**Critical, reproduced live: GDPR account deletion crashed for any user who
had ever loaded their profile.** `User.profile` was a plain SQLAlchemy
relationship with no `passive_deletes=True`; deleting a `User` with a
loaded `profile` made the ORM emit `UPDATE profiles SET user_id = NULL ...`
before the `DELETE`, which failed outright since `profiles.user_id` is
`NOT NULL` — the whole delete-account request 500'd and the account was
**not** actually deleted, silently breaking the GDPR Art. 17 erasure
endpoint. Root cause: the DB's own `ON DELETE CASCADE` on `profiles.user_id`
was already correct (verified against live `pg_constraint`, same as every
other FK to `users.id`) — the ORM just wasn't told to trust it for this one
relationship.

**Fixed**: added `passive_deletes=True` to `User.profile`
(`app/models/user.py`), with a comment explaining exactly why. Added a
permanent regression test,
`test_delete_account_succeeds_even_after_profile_was_created`
(`tests/test_gdpr.py`), that loads the profile before deleting — exactly
what a real settings page does — to make sure this can't silently regress.

**Medium, fixed**: TOTP backup codes were 32 bits of entropy
(`secrets.token_hex(4)`) — fine against the real online rate limit (10
attempts/5min, both per-IP and per-user), but crackable in well under an
hour offline against the stored SHA-256 hashes if the database were ever
exfiltrated. Bumped to 64 bits (`secrets.token_hex(8)`) in
`app/services/totp_service.py`; widened `TwoFactorLoginVerify.code`'s
`max_length` in `app/schemas/auth.py` to fit. All 15 `test_2fa.py` tests
still pass.

**Low/medium, fixed**: `record_daily_activity` (streak update) did a plain
read-modify-write on the `Streak` row with no locking — a pre-existing gap
that the new daily-challenge feature made more likely to actually trigger,
since it added a second real caller. Two near-simultaneous activities for
the same student could race and lose an update. Fixed with
`SELECT ... FOR UPDATE` row locking plus the same SAVEPOINT-then-catch
pattern already used for badge-award races, in
`app/services/gamification_service.py`.

**Not fixed (accepted tradeoff, noted for the record)**: `totp_secret` is
stored as plaintext base32 (needed for verification) with no
application-level encryption at rest — standard practice for TOTP
implementations, not treated as a defect.

Everything else in scope (2FA control-flow, GDPR export scoping, push
subscription CRUD scoping, Sentry PII scrubbing, the two daily-challenge
SAVEPOINT races) was reviewed and found correct — no changes needed.

## Agent 2 — Frontend correctness & accessibility (new UI: push settings, GDPR settings, 2FA settings, daily challenge, dashboard widget, service worker push handlers)

**Fixed**: the dashboard's "Daily challenge" widget got permanently stuck on
"Loading…" for any unverified user, because `/daily-challenge/today`
requires a verified email and the widget's error handler set the same
`null` state used for "hasn't loaded yet" — the two were indistinguishable.
Added a distinct `challengeUnavailable` state
(`src/app/dashboard/page.tsx`) with a real message ("Verify your email to
unlock the daily challenge.") instead of an infinite spinner.

**Fixed**: a real, previously-undetected contrast gap — `text-emerald-400`
and `text-amber-400` used unpaired (no light-mode-safe variant) across 16
files, most of them pre-existing from earlier work sessions, not caught by
the original WCAG audit because the axe-core scan (`docs/ACCESSIBILITY.md`)
only exercised the specific "success"/"open"/"connected" UI states in
routes and data conditions the scan script happened to reach (e.g. a valid
certificate result, a live contest, a connected chat session) — states the
automated scan's fixed route list and seeded test data didn't put it into.
Computed real WCAG contrast ratios against this app's actual background
colors (not textbook white/black) before picking a fix:
`emerald-400`/`amber-400` land at 1.6–1.8:1 against the light background
(need 4.5:1) — essentially invisible; `emerald-700`/`amber-700` land at
4.68–5.11:1, clearing the bar, while `-400` stays correct for dark mode
(9.9–11.5:1). Applied the same `-700 light / -400 dark` split already
established for `red-400`/`brand-400` in the prior audit, across all 16
files. Also fixed the same pattern in the three brand-new daily-challenge
files directly (`text-emerald-500`/`text-red-500` → the paired variants).

**Fixed**: `subscribeToPush()`/`unsubscribeFromPush()`
(`src/lib/push.ts`) awaited `navigator.serviceWorker.ready`, a promise that
never resolves at all if no service worker ever registers (silent
registration failure, or dev mode where Serwist is disabled) — a user
clicking "Enable" would see a spinner that never finished and no error.
Added an 8-second timeout race with a real error message.

**Fixed**: a losing double-submit race on the daily challenge (e.g. a
double-click, or two tabs) left the pre-attempt UI stuck showing an
answerable question after the server had already recorded someone else's
attempt as the real one. `daily-challenge/page.tsx`'s submit error handler
now refetches `/daily-challenge/today` on a 422 specifically, so the UI
converges to real server state instead of staying stale.

**Not fixed (accepted, self-correcting)**: `isSubscribedToPush()` trusts
only local `PushManager.getSubscription()` state rather than confirming
against the backend — lowest-priority; the "Send test notification" button
surfaces a mismatch immediately if one ever exists.

Everything else in scope (response-shape/schema alignment against the real
backend, XSS surface, the correct-answer-reveal logic matching the backend
contract, keyboard interaction on the daily-challenge option buttons, the
already-fixed brand-400/red-400 classes not regressing) was reviewed and
found correct.

## Agent 3 — Docs-vs-code fabrication check

Read all seven recently-written/updated docs (`PWA.md`,
`PUSH_NOTIFICATIONS.md`, `ENGAGEMENT.md`, `PERFORMANCE.md`,
`OBSERVABILITY.md`, `ACCESSIBILITY.md`, `ENVIRONMENT.md`) and cross-checked
every concrete claim — file paths, function/class names, config field
names and defaults, described behaviors, and numeric claims — against the
real source. **Verdict: no fabrication found.** Every file, function, and
config field named in these docs exists exactly as described; the one
numeric claim that didn't immediately reproduce (`ENGAGEMENT.md`'s
"105/105 passing") was traced to a stray orphaned `pytest` process from an
earlier interrupted run corrupting a later concurrent run against the same
test database — a session-hygiene artifact in the reviewing agent's own
process, not a defect in this codebase; a clean isolated rerun reproduced
105/105 exactly (in this final pass, 106/106 after this review's own GDPR
regression test was added). The load-test throughput numbers in
`PERFORMANCE.md` were correctly flagged as "unverifiable but plausible,
documented honestly" — internally consistent, with reproduction commands
given, but not independently re-run by the reviewing agent, exactly the
kind of honest sandbox-limitation framing the standing project rule asks
for rather than a fabricated re-confirmation.

## Agent 4 — Migration/model consistency & test coverage

**No drift found**: all four recently-added Alembic migrations
(`f2a7c9e1b4d6` push subscriptions, `a3d5e8f0c2b7` daily challenges,
`d18e6b4a3f57` TOTP fields, `c4a91f7d0e2b` performance indexes) match their
corresponding SQLAlchemy models field-for-field — types, nullability,
defaults, foreign keys, indexes, and unique constraints all verified by
direct comparison. `alembic heads` confirms a single linear head with no
branching; `alembic upgrade head` applies cleanly.

**No coverage gaps found**: every endpoint added in this work (all of
`challenges.py`, the `/push/*` routes in `notifications.py`, `/users/me/export`
and `/users/me/delete-account`, all `/2fa/*` routes) has real tests that
assert on response-body content, not just status codes.

**Pytest result reported by this agent**: 105/105 (before this review's own
additional GDPR regression test was added — 106/106 after).

## Net result of this review pass

- 1 critical bug fixed (GDPR account deletion, previously silently broken
  for any user with a profile — now has a permanent regression test).
- 2 medium-severity fixes (backup code entropy, streak update race).
- 4 real frontend bugs fixed (stuck-loading state, a genuine
  previously-undetected WCAG contrast gap spanning 16 files well beyond
  what this session's own new code touched, a hung-forever push-subscribe
  flow, a stale-UI race on double-submit).
- 0 fabrication found in any of the documentation written this session.
- 0 migration/model drift, 0 test-coverage gaps in the newly added
  subsystems.
- Full backend suite: **106/106 passing**. Frontend: `tsc --noEmit`,
  `next lint`, `next build` all clean.
