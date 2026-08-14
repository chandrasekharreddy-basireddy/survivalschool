# Engagement: daily streaks + daily challenge

## Daily streaks

`app/models/gamification.py::Streak` (one row per student:
`current_streak_days`, `longest_streak_days`, `last_activity_date`) and
`app/services/gamification_service.py::record_daily_activity()` predate this
pass — completing a lesson already extended a student's streak. This pass
adds a second, independent way to build one: **answering today's daily
challenge** also calls `record_daily_activity()`, so a student who never
touches a course but answers every day's challenge still builds a real
streak, exactly like one who only completes lessons. `evaluate_and_award_badges()`
already had `week_streak`/`month_streak` badge rules keyed off
`current_streak_days` — those now trigger from either path too, with no
changes needed there.

## Daily challenge

One real question from the existing question bank (the same `Question`/
`QuestionOption` tables quizzes and exams use — no separate "trivia"
content), selected once per calendar day (UTC) and shared by **every**
student, the same day-one-puzzle-for-everyone mechanic real engagement
products use.

**Backend**

- **`app/models/challenge.py`**: `DailyChallenge` (one row per
  `challenge_date`, unique-constrained — `question_id` FK) and
  `DailyChallengeAttempt` (one row per `(student_id, challenge_id)`, also
  unique-constrained — a student cannot re-roll the same day's question for
  more points). Migration:
  `alembic/versions/a3d5e8f0c2b7_add_daily_challenges.py`.
- **`app/services/daily_challenge_service.py`**:
  - `get_or_create_todays_challenge()` — lazy creation on first request each
    day, not a cron job (there's nothing to precompute). Picks a random
    `single`/`true_false` question, preferring ones not used in the last 30
    days (falls back to allowing a repeat if the bank is too small to avoid
    one). The unique constraint on `challenge_date` is the real
    concurrency guard: if two requests race to create "today," the losing
    one's insert is caught (`IntegrityError` inside a `db.begin_nested()`
    SAVEPOINT — the same pattern `evaluate_and_award_badges` already used
    for badge-award races) and it just fetches the winner's row instead of
    erroring.
  - `submit_attempt()` — scores the submission server-side against the real
    `QuestionOption.is_correct` answer key (never trusts a client-submitted
    correctness flag, same principle as quiz/exam scoring), awards 15
    points on a correct answer, records the attempt (again SAVEPOINT-guarded
    against a double-submit race), and calls `record_daily_activity()`.
- **`app/api/v1/challenges.py`** (`/daily-challenge/*`):
  - `GET /today` — today's question (options only, no `is_correct` — same
    rule every quiz/exam/practice endpoint follows), whether this student
    has already answered, and their result (including the real correct
    answer) if they have.
  - `POST /today/attempt` — submit once; a second attempt the same day
    returns `422` (correctness of an answer is never guessable from a retry).
  - `GET /history` — a student's own past challenge results.

**Frontend**

- **`/daily-challenge`** — today's question, single-select options, submit,
  immediate server-verified feedback (correct answer highlighted in green,
  the student's own wrong pick in red if they missed it), current streak
  shown as a badge.
- **`/daily-challenge/history`** — a simple list of past days: correct/missed,
  points earned.
- **Dashboard widget** — "Daily challenge" card showing today's status
  (done / not done, points earned if done) with a button straight into the
  flow, so it's visible on login without hunting for a nav item.
- **Nav** — a top-level "Daily Challenge" link (desktop + mobile menu),
  alongside the existing Practice/Leaderboard links.

## Verification

`tests/test_daily_challenge.py` — 7 tests, all against the real API and a
real Postgres database, run in the same shared-database test session as
every other backend test (see `tests/conftest.py`'s session-scoped
`_setup_database` fixture) — which matters here specifically because
`DailyChallenge` is a real per-day *singleton*: whichever request reaches
`GET /daily-challenge/today` first for the day is the one that persists for
every other test (and every other student) for the rest of that run. The
tests are written to be correct under that constraint rather than fighting
it — they look up the real correct answer directly via
`AsyncSessionLocal`/`QuestionOption.is_correct` for whatever question
actually ended up being "today's," rather than assuming their own freshly
seeded question won the race. Covers: auth required; a real question with no
leaked answer key; the same challenge served to two different students;
correct answer → 15 points + streak increment (checked against
`/gamification/me` before/after, not just the response body); wrong answer →
0 points but streak still increments; a second submit attempt the same day
→ `422`; history reflects the attempt. All 7 pass; full backend suite passed
105/105 at the time this feature was added (106/106 as of the subsequent
peer-review pass — see docs/PEER_REVIEW.md — which added one more,
unrelated regression test).

A real browser end-to-end pass (Playwright + Chromium, against a live
gunicorn backend and a `next start` production frontend build) additionally
confirmed the full user-facing path works, not just the API: register →
verify → log in through the real login form → land on `/dashboard` and see
the real "Daily challenge" widget → click through the real nav link →
`/daily-challenge` renders the real question fetched from the backend →
select an option and submit → immediate correct/incorrect feedback renders
→ reloading the page shows the same already-answered state (proving the
result is server-persisted, not just React state) → `/daily-challenge/history`
shows the entry.
