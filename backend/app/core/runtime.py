"""Process-level runtime state that has nowhere else to live.

Currently just the process start time, used by GET /admin/system-health to
report uptime. Deliberately a plain module attribute set at import time
(effectively "when this worker process was created") rather than something
set explicitly in main.py's lifespan — with multiple gunicorn workers, each
worker imports this module once when it forks/starts, which is exactly the
per-worker uptime we want to report, not a single shared "server" uptime.
"""
from __future__ import annotations

import time

PROCESS_STARTED_AT = time.time()
