"""Process-level runtime state that has nowhere else to live.

Currently just the process start time, used by GET /admin/system-health to
report uptime. Deliberately a plain module attribute set at import time
(effectively "when this worker process was created") rather than something
set explicitly in main.py's lifespan — with multiple gunicorn workers, each
worker imports this module once when it forks/starts, which is exactly the
per-worker uptime we want to report, not a single shared "server" uptime.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Coroutine
from typing import Any

PROCESS_STARTED_AT = time.time()

# asyncio.create_task() only holds a WEAK reference to the task it returns —
# per the stdlib docs, a task with no other strong reference "can disappear
# mid-execution" if the event loop decides to garbage-collect it. Fire-and-
# forget background work (e.g. AI question generation kicked off from a
# request handler that returns immediately) has no natural owner to hold
# that reference, so it goes here instead. The done-callback removes each
# task from the set once it finishes, so this never grows unbounded.
_background_tasks: set[asyncio.Task] = set()


def spawn_background_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """asyncio.create_task() with a kept strong reference — use this instead
    of calling asyncio.create_task() directly for any detached task that
    isn't awaited or otherwise referenced by its caller."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
