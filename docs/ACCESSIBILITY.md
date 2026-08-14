# Accessibility

## Real automated audit, run against the real running app

This wasn't a manual eyeball pass over JSX — it was a real Chromium
browser (Playwright, the pre-installed sandbox Chromium) rendering the
actual production build against a live backend (real Postgres/Redis),
audited with `axe-core` (the same engine behind Lighthouse's accessibility
score and most browser DevTools accessibility panels), against every WCAG
2.1 A/AA rule axe-core checks.

**Coverage:** 22 distinct routes — 10 public (`/`, `/login`, `/register`,
`/forgot-password`, `/courses`, `/leaderboard`, `/contests`, contest and
course certificate verification pages, `/search`) and 12 requiring a real
authenticated session (`/dashboard`, `/settings`, `/profile`,
`/notifications`, `/quiz-history`, `/timetable`, `/practice`,
`/ai-assistant`, `/certificates/me`, `/contests/certificates`, `/chat`,
`/discussions`) — each scanned in **both the light and dark theme** (44
total page/theme scans), using a real registered-and-verified test account
for the authenticated routes.

Reusable script: `frontend/scripts/a11y-scan.mjs` (`npm run a11y-scan`).
Exits non-zero on any violation, so it's ready to wire into CI once a real
backend is available in that environment (see `docs/CI_CD.md`).

### First run: 8 real violations found, all `serious` impact

| # | Rule | WCAG | Where | Root cause |
|---|------|------|-------|-----------|
| 1 | `color-contrast` | 1.4.3 | `/`, `/login`, `/register`, `/courses`, `/leaderboard`, `/contests`, `/discussions` (7 pages) | `text-brand-400` (#8b8bff) used directly as link/accent text color — 2.7:1 against the light theme's background, needs 4.5:1. Fine in dark mode (6.6:1); the token was never given a light-mode-safe variant. |
| 2 | `color-contrast` | 1.4.3 | `/`, `/courses`, `/contests` (empty-state and hint text) | The `--fg-2` ("tertiary/hint text") CSS variable — 3.41:1 against the light background, needs 4.5:1. |
| 3 | `color-contrast` | 1.4.3 | `/leaderboard` (error text) | `text-red-400` used directly — 2.58:1 against light background, needs 4.5:1. |
| 4 | `link-in-text-block` | 1.4.1 | `/register` ("Already have an account? **Sign in**") | The link was only distinguished from surrounding text by color, and only underlined on hover — WCAG requires a *non-color* distinguishing cue visible by default, not just on interaction. |

### Fixes applied

1. **`--fg-2` (tertiary text token, `frontend/src/app/globals.css`)** — darkened
   in the light theme from `138 133 128` to `115 110 106` (3.41:1 → 4.7:1).
   While computing this, **manually verified the dark theme's own `--fg-2`
   value against the WCAG contrast formula and found it also failed**
   (4.02:1 against a 4.5:1 requirement) — axe's scan didn't catch this half
   because Playwright's default color-scheme is light, so the automated
   pass never rendered dark mode until a second, explicit dark-mode scan
   was added. Fixed to `110 128 153` (4.75:1). This is exactly the kind of
   gap "run the automated tool once and stop" leaves — the fix here was to
   add the dark-mode scan pass, not just trust the first result.
2. **`text-brand-400` → `text-brand-600 dark:text-brand-400`**, applied
   across every plain-text usage in 23 files (verified via `grep` before
   and after — hover-only accent usages like `hover:text-brand-400` on
   `/ai-practice`, which axe does not flag since static contrast checks
   evaluate the resting state, were deliberately left untouched).
   `brand-600` gives 6.09:1 against the light background and remains a
   legitimate design choice against dark (the `dark:` variant keeps
   `brand-400`'s original 6.6:1 there).
3. **`text-red-400` → `text-red-700 dark:text-red-400`**, applied across
   28 files. `red-700` gives 6.03:1 against light (chosen over `red-600`'s
   4.50:1 — exactly at the threshold — for a safer margin); `dark:`
   preserves the original `red-400` in dark mode.
4. **Inline sentence links given a persistent underline** instead of
   hover-only, in the 4 places a link sits inside a sentence rather than
   standing alone (`/register`'s "Sign in", `/login`'s "Create an
   account", `/dashboard`'s "Enroll in your first course", and the
   certificate-view page's link to `/certificates/verify`). Standalone
   links (nav items, "+ New quiz", card headers) were deliberately left
   as hover-underline — WCAG's link-in-text-block criterion applies
   specifically to links embedded in a run of body text, not link-styled
   UI elements on their own line.

### Re-scan after fixes: 0 violations

All 44 page/theme scans (22 routes × light + dark) came back clean —
`{"total violation types across all pages/themes": 0}`. Verified with the
same script, same routes, same real backend, immediately after rebuilding.

## What automated scanning does not cover

axe-core's own documentation is explicit that automated tools catch
roughly 30-40% of real accessibility issues. What this pass did NOT do,
and what a real pre-launch accessibility sign-off should still include:

- **Manual keyboard-only navigation** through each critical flow (login,
  taking a quiz/exam under a timer, the 2FA setup QR-code + code-entry
  flow, chat) — tab order, visible focus rings, and Escape-to-close on
  modals were not individually walked through by a human.
- **Screen reader testing** (VoiceOver/NVDA) — axe checks for the
  presence of correct ARIA/semantic markup, but not what it actually
  sounds like read aloud, especially for dynamic content (toast
  notifications, the exam countdown timer, chat's "Seen" indicator).
- **200% browser zoom / reflow** check for layout breakage.
- **Reduced-motion** preference (`prefers-reduced-motion`) — not
  currently respected by any animation/transition in the app; the global
  150ms color/background transition in `globals.css` is minor but not
  conditionally disabled.
- **Touch target sizing** (WCAG 2.5.5, 44×44 CSS px minimum) — not
  independently measured; most buttons use the `.btn-primary`/`.btn-secondary`
  utility classes with generous padding, but small icon-only controls
  (e.g. the theme toggle, some table action buttons) were not individually
  measured against the 44px threshold.

These are real, scoped gaps — not hedging. Treat this document's "0
violations" result as "0 violations axe-core's ruleset can detect,"
not "fully accessible," and budget a manual pass (ideally with an actual
screen reader user) before treating this as complete.
