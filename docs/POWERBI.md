# Power BI setup guide

You asked to be given the connection steps rather than have this configured
for you, since it needs your actual Power BI tenant. Here's exactly how to
connect it. This document also states plainly what this codebase does and
does not provide toward that integration — read the "What's real vs. not
yet built" section before you start.

## What's real vs. not yet built

- **Real and populated**: `app/services/analytics_service.py::track_event()`
  writes every significant platform event (lesson completions, quiz/exam
  submissions, certificate issuances, etc.) to the `analytics_events` table
  — append-only, deliberately decoupled from the transactional tables so
  Power BI queries never touch hot OLTP paths. This table, plus
  `audit_logs`, `enrollments`, `quiz_attempts`, `exam_attempts`,
  `certificates`, and `points`, are all real Postgres tables with real data
  the moment the platform is used.
- **Not built**: `POWERBI_TENANT_ID` / `POWERBI_CLIENT_ID` /
  `POWERBI_CLIENT_SECRET` / `POWERBI_WORKSPACE_ID` exist as settings in
  `app/config.py` but **no code anywhere calls the Power BI REST API** — no
  push-dataset integration, no scheduled dataflow trigger, nothing. Those
  settings are there so a future integration has somewhere to read
  credentials from; they don't do anything yet. This document describes the
  path that works today (Power BI pulling from Postgres directly), not a
  feature that was built and is waiting for your credentials.

## Recommended approach: Power BI Desktop → PostgreSQL connector (direct query)

This works today, requires zero backend code changes, and is the standard
way Power BI connects to a Postgres-backed application.

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

## If you later want a real Power BI REST API push-dataset integration

That's a materially different (and larger) piece of work than the pull
model above: registering an Azure AD app, implementing OAuth2 client
credentials flow against `POWERBI_TENANT_ID`/`POWERBI_CLIENT_ID`/
`POWERBI_CLIENT_SECRET`, and a backend job that pushes rows to a Power BI
streaming/push dataset on a schedule. None of that exists in this codebase
yet — the settings are placeholders for exactly this future work. The
pull-model approach above is almost certainly what you want first: it needs
no backend code, works today, and is how most Power BI + Postgres
integrations are actually built in practice.
