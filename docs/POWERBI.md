# Power BI setup guide

This platform now ships **two** real, independent ways to get data into
Power BI: a REST API push-dataset integration (this document's primary
focus, as of this pass) and the direct-Postgres pull model documented
further below (still valid, still zero backend code changes, and a good
fallback if you'd rather not stand up an Azure AD app).

## What's real

- **Push-dataset REST API integration** (`app/services/powerbi_service.py`):
  a real service-principal (Azure AD app, client-credentials grant) OAuth2
  flow against `https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token`,
  followed by real Power BI REST API calls
  (`https://api.powerbi.com/v1.0/myorg/groups/{workspaceId}/datasets`) that
  create (if missing) a `SurvivalSchool Daily Engagement` push dataset and
  push one aggregate row per day into its `DailyEngagement` table. Wired
  into the daily background job (`app/workers/worker.py::run_powerbi_sync`,
  every 24h) and into an admin-only manual-trigger endpoint
  (`POST /api/v1/admin/powerbi/sync`) for on-demand testing. Covered by
  real tests in `backend/tests/test_powerbi.py` — Azure AD token requests,
  Power BI dataset-create/list/push calls, and the aggregation math are all
  asserted against seeded data, and the inert-when-unconfigured path is
  asserted to make zero HTTP calls.
- **Inert by default**: exactly like `app/services/push_service.py` (VAPID
  keys) and `app/services/n8n_service.py` (webhook URL) — if any of
  `POWERBI_TENANT_ID` / `POWERBI_CLIENT_ID` / `POWERBI_CLIENT_SECRET` /
  `POWERBI_WORKSPACE_ID` is unset, the sync is a logged no-op. No fabricated
  credentials are baked in anywhere; a real deployment sets its own via env
  vars.
- **Data pushed is aggregate-only, never per-student**: one row per
  calendar day — active student count, quiz attempts/pass rate/average
  score, daily challenge completions/correct rate, points awarded. No
  `user_id`, no email, no name — see the schema below. This mirrors the PII
  discipline already documented for the pull model further down this file.
- **Also still real**: `app/services/analytics_service.py::track_event()`
  writes every significant platform event to the append-only
  `analytics_events` table, which both the push-dataset aggregation and the
  pull-model approach below read from.

## Setup: push-dataset REST API integration

### 1. Register an Azure AD app (service principal)

In the [Azure Portal](https://portal.azure.com) → **Azure Active
Directory → App registrations → New registration**:

- Name it something like `survivalschool-powerbi-push`.
- Supported account types: single tenant is fine for this use case.
- No redirect URI needed (this is a client-credentials/daemon flow, not an
  interactive login).
- After creation, note the **Application (client) ID** and **Directory
  (tenant) ID** from the app's Overview page.

### 2. Create a client secret

App registration → **Certificates & secrets → New client secret**. Copy the
secret **value** immediately (Azure only shows it once) — this becomes
`POWERBI_CLIENT_SECRET`.

### 3. Enable service principal access in the Power BI tenant

Power BI Service → **Settings → Admin portal → Tenant settings →
Developer settings → "Allow service principals to use Power BI APIs"** —
enable it for your organization (or a security group containing this app).
This step is required or every API call will get a 403 regardless of the
next step.

### 4. Grant the app access to your workspace

In the Power BI Service, open the workspace you want this data pushed to
→ **Access → Add people or groups** → search for the app registration by
name → add it as **Contributor** or higher (Contributor can create/write
datasets; Admin is not required). Note the workspace's ID (from its URL,
`app.powerbi.com/groups/{workspaceId}/...`) — this becomes
`POWERBI_WORKSPACE_ID`.

### 5. Set the four environment variables

In `backend/.env` (see `backend/.env.example`):

```
POWERBI_TENANT_ID=<Directory (tenant) ID from step 1>
POWERBI_CLIENT_ID=<Application (client) ID from step 1>
POWERBI_CLIENT_SECRET=<client secret value from step 2>
POWERBI_WORKSPACE_ID=<workspace ID from step 4>
```

All four must be set for the integration to activate — a partially-set
group is treated as unconfigured (fails safe to inert, per
`powerbi_configured()` in `app/services/powerbi_service.py`).

### 6. Verify it

Restart the backend (or the worker), then as an admin user call:

```
POST /api/v1/admin/powerbi/sync
Authorization: Bearer <admin access token>
```

A `{"status": "synced", "date": "...", ...}` response means the dataset
was created (first run) or found, and yesterday's aggregate row was pushed.
A `{"status": "skipped", "reason": "powerbi_not_configured"}` response means
one of the four env vars is still missing.

In the Power BI Service, open the target workspace and you should see a new
dataset named **SurvivalSchool Daily Engagement**. Build a report against
its `DailyEngagement` table — it accumulates one row per day going forward
(the scheduled worker job runs this automatically every 24 hours; the admin
endpoint is for on-demand testing/backfill, not a substitute for it).

### 7. Dataset schema (`DailyEngagement` table)

| Column | Type | Meaning |
|---|---|---|
| `Date` | DateTime | Calendar day (UTC midnight) this row summarizes |
| `ActiveStudents` | Int64 | Distinct students with at least one tracked analytics event that day |
| `QuizAttempts` | Int64 | Quiz attempts submitted that day |
| `QuizPassRate` | Double | Fraction (0–1) of that day's submitted quiz attempts that passed |
| `AverageQuizScore` | Double | Mean `score_percent` across that day's submitted quiz attempts |
| `DailyChallengeCompletions` | Int64 | Daily-challenge attempts submitted that day |
| `DailyChallengeCorrectRate` | Double | Fraction (0–1) of that day's daily-challenge attempts answered correctly |
| `PointsAwarded` | Int64 | Sum of gamification points awarded that day |

No student-identifying column exists in this table by design (spec section
50: data minimization) — join to per-student detail is intentionally not
possible from this dataset; use the pull model below if you need
per-student drill-down.

## Alternative / complementary approach: Power BI Desktop → PostgreSQL connector (direct query)

Still fully supported, requires zero backend code changes, and is the
better choice if you want per-student drill-down (the push dataset above
is aggregate-only) or don't want to stand up an Azure AD app at all.

### 1. Create a read-only reporting database user

Run this once against your production Postgres (not as the application's
own `survivalschool` user — least privilege, and it stops a bad DAX query
from ever being able to write):

```sql
CREATE ROLE powerbi_reader WITH LOGIN PASSWORD 'choose-a-strong-password';
GRANT CONNECT ON DATABASE survivalschool TO powerbi_reader;
GRANT USAGE ON SCHEMA public TO powerbi_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO powerbi_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO powerbi_reader;
```

The last line matters: it makes future tables (from new Alembic migrations)
automatically readable by this role too, without re-running the grant.

### 2. Install the Npgsql / PostgreSQL driver Power BI needs

Power BI Desktop's built-in PostgreSQL connector needs the Npgsql driver
installed on the machine running Power BI Desktop. Get Data → PostgreSQL
database will prompt you to install it if it's missing, or download it
directly from the Npgsql project's releases page.

### 3. Connect

In Power BI Desktop: **Get Data → Database → PostgreSQL database**

- **Server**: your Postgres host (e.g. the RDS/Cloud SQL endpoint, or
  whatever host you deployed `postgres` to — see `docs/DEPLOYMENT.md`)
- **Database**: `survivalschool`
- **Data Connectivity mode**: `DirectQuery` if you want live dashboards, or
  `Import` if you want faster report interaction and are fine refreshing on
  a schedule (Import is the more common choice for this kind of platform)
- **Credentials**: the `powerbi_reader` user from step 1

### 4. Tables worth building reports on

| Table | What it gives you |
|---|---|
| `analytics_events` | Raw event stream — `event_type`, `user_id`, `occurred_at`, `metadata_json`. Best table for time-series/funnel analysis (registrations → enrollments → completions). |
| `enrollments` | Course enrollment + completion status, per student/course. |
| `quiz_attempts` / `exam_attempts` | Scores, pass/fail, timestamps — assessment performance dashboards. |
| `certificates` | Certificates issued, by course/date — completion-outcome reporting. |
| `points` | Append-only gamification ledger — engagement trends. |
| `audit_logs` | Admin/moderation activity — operational oversight dashboards. |
| `users` / `courses` | Dimension tables to join against for names instead of raw UUIDs (careful: `users` has `password_hash` — do not expose that column in any report; consider a Postgres view that excludes it, see below). |

### 5. Recommended: build a reporting view instead of exposing raw tables

Rather than pointing Power BI at `users` directly, create a view that
excludes sensitive columns, so there's no risk of a report accidentally
surfacing `password_hash` or other internal columns to a Power BI author:

```sql
CREATE VIEW reporting_users AS
SELECT id, email, full_name, is_active, is_email_verified, created_at
FROM users;

GRANT SELECT ON reporting_users TO powerbi_reader;
```

Do the same for any other table with columns you don't want a report author
to see, and only grant `powerbi_reader` access to the views, not the
underlying tables with sensitive columns, if you want to be strict about it
(the base `GRANT SELECT ON ALL TABLES` above is simpler but broader — choose
based on your organization's data-access policy).

### 6. Scheduled refresh (Power BI Service)

Once you publish the report to the Power BI Service, set up a scheduled
refresh under the dataset's settings, pointing at the same Postgres
credentials via an on-premises data gateway if your database isn't
publicly reachable, or directly if it is (with the connection properly
firewalled to Power BI's egress IP ranges — check Microsoft's published
IP list for your region before opening that up).
