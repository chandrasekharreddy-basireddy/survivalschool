# Changelog

All notable changes to Survival School are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/); versioning is
[SemVer](https://semver.org/).

## [1.0.0] — 2026-08-14

First production-ready release. This version closes out a dedicated
hardening pass across performance, security, reliability, accessibility,
mobile/PWA, and engagement — the last mile between "the features work" and
"this is safe and pleasant to actually run in production." Every item below
is backed by a real passing test, a real migration applied against a live
database, or a real measurement — see the linked doc for the specific
evidence; nothing here is aspirational. `docs/PEER_REVIEW.md` documents an
independent four-agent adversarial review of this release's own new code,
including one critical bug it caught and fixed before release (see below).

### Added

- **Performance**: Redis caching for hot read endpoints (courses, contests,
  leaderboard), a DB index audit + migration for previously-missing
  indexes, and a real load test with measured numbers (~4.4x throughput /
  ~3.2x median-latency improvement from caching; login rate-limiter
  validated under real concurrent load). See `docs/PERFORMANCE.md`.
- **Security**: TOTP-based two-factor authentication (RFC 6238, no
  third-party SMS account needed) with hashed, rate-limited backup codes;
  GDPR-style data export (Art. 15/20) and real hard account deletion (Art.
  17); continuous scheduled dependency scanning (`pip-audit`, `npm audit`)
  plus Dependabot, distinct from the existing push/PR-triggered CI scan.
  See `docs/SECURITY.md`, `docs/PEER_REVIEW.md`.
- **Reliability**: a materially more rigorous backup-restore drill (byte-
  identical row verification, migration-revision match, and booting the
  real app against the restored database to serve a real request) and
  production error tracking via Sentry — genuinely inert with no DSN
  configured, genuinely functional once one is. See `docs/DATABASE.md`,
  `docs/OBSERVABILITY.md`.
- **Accessibility**: a real automated WCAG 2.1 AA audit (Chromium +
  axe-core, both themes, 22 routes) that found and fixed 8 violations, plus
  a follow-up peer-review pass that found and fixed 8 more
  previously-undetected contrast violations the first scan's route/state
  coverage had missed. See `docs/ACCESSIBILITY.md`, `docs/PEER_REVIEW.md`.
- **Mobile/PWA**: a real, build-generated service worker (Serwist) —
  offline app-shell caching, a real offline fallback page, `/api/*` never
  cached. See `docs/PWA.md`.
- **Web Push notifications**: real Web Push (RFC 8030) via a self-generated
  VAPID keypair (RFC 8292) — no Firebase/APNs/OneSignal account. Real
  encrypted payload delivery via `pywebpush`, subscription management,
  dead-subscription pruning, and a self-service "send me a test
  notification" button. See `docs/PUSH_NOTIFICATIONS.md`.
- **Engagement**: a daily challenge (one real question from the existing
  bank, shared by every student, once per day) wired into the existing
  streak system, plus a dashboard widget, dedicated page, and history view.
  See `docs/ENGAGEMENT.md`.

### Fixed

- **Critical**: GDPR account deletion crashed (and silently did NOT delete
  the account) for any user who had ever loaded their profile, due to a
  missing `passive_deletes=True` on the `User.profile` relationship. Caught
  by this release's own peer-review pass before shipping; fixed with a
  permanent regression test. See `docs/PEER_REVIEW.md`.
- TOTP backup codes strengthened from 32 to 64 bits of entropy (defense
  against offline brute-force of a leaked database, not the online path,
  which was already rate-limited).
- A daily-streak read-modify-write race that could under-count a student's
  streak under concurrent activity, now row-locked.
- A dashboard widget that could get stuck on an infinite "Loading…" state
  for unverified users; a push-subscribe flow that could hang forever with
  no error if no service worker was active; a stale-UI race on a
  double-submitted daily challenge answer.

### Changed

- `SERVICE_VERSION` bumped from `0.1.0` to `1.0.0` across backend config
  and frontend `package.json`.

---

## [0.1.0] and earlier — initial build through feature-complete

Everything before this release: the initial monorepo scaffold, auth/RBAC,
course + lesson engine, quiz/exam engine with server-side scoring,
gamification + certificates, real-time chat, AI assistant/mock-practice,
notifications, analytics/audit logging, admin console, the full frontend
design system, contests with auto-scheduling, bulk question import, exam
integrity monitoring, timetable/attendance, discussions, practice mode,
Docker Compose + CI/CD + Kubernetes manifests, and a full documentation
set. See `docs/STATUS.md` for the complete, dated pass-by-pass history —
this changelog starts detailed tracking at the 1.0.0 hardening pass above;
everything prior is summarized there rather than re-dated here to avoid
guessing at timestamps this file doesn't have first-hand.
