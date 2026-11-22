"""Background job runner.

Jobs run on a bounded thread pool. Each job has an ID, a stage, a progress fraction, a message,
cooperative cancellation and an optional checkpoint, all persisted in the `jobs` table so the UI
can poll progress and long runs survive a browser refresh. (A process restart marks running
jobs as failed with an explanatory message; they can be retried and resume from checkpoint.)
"""
from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .. import db
from ..config import settings

STAGES = ["Uploading", "Extracting", "Validating", "Preparing data", "Running analysis",
          "Verifying evidence", "Generating visualisations", "Generating report", "Completed", "Failed"]

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()
_registry: dict[str, Callable[..., Any]] = {}


class JobCancelled(Exception):
    pass


def register(kind: str):
    def deco(fn):
        _registry[kind] = fn
        return fn
    return deco


def _pool() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=max(1, settings().job_workers), thread_name_prefix="lucerna-job")
        return _executor


class JobContext:
    def __init__(self, job_id: str):
        self.job_id = job_id

    def update(self, stage: str | None = None, progress: float | None = None, message: str | None = None) -> None:
        sets, vals = [], []
        if stage is not None:
            sets.append("stage=?"); vals.append(stage)
        if progress is not None:
            sets.append("progress=?"); vals.append(max(0.0, min(1.0, float(progress))))
        if message is not None:
            sets.append("message=?"); vals.append(message[:1000])
        if sets:
            db.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", (*vals, self.job_id))
        self.check_cancel()

    def check_cancel(self) -> None:
        r = db.query_one("SELECT cancel_requested FROM jobs WHERE id=?", (self.job_id,))
        if r and r["cancel_requested"]:
            raise JobCancelled()

    def save_checkpoint(self, data: Any) -> None:
        db.execute("UPDATE jobs SET checkpoint_json=? WHERE id=?", (db.dumps(data), self.job_id))

    def load_checkpoint(self, default: Any = None) -> Any:
        r = db.query_one("SELECT checkpoint_json FROM jobs WHERE id=?", (self.job_id,))
        return db.loads(r["checkpoint_json"] if r else None, default)


def _run(job_id: str, kind: str, params: dict) -> None:
    ctx = JobContext(job_id)
    db.execute("UPDATE jobs SET status='running', started_at=? WHERE id=?", (db.now(), job_id))
    try:
        fn = _registry[kind]
        result = fn(ctx, **params)
        db.execute("UPDATE jobs SET status='completed', stage='Completed', progress=1, result_json=?, finished_at=? WHERE id=?",
                   (db.dumps(result), db.now(), job_id))
    except JobCancelled:
        db.execute("UPDATE jobs SET status='cancelled', message='Cancelled by user', finished_at=? WHERE id=?", (db.now(), job_id))
    except Exception as exc:  # recorded, never hidden
        db.execute("UPDATE jobs SET status='failed', stage='Failed', error=?, finished_at=? WHERE id=?",
                   (f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}"[:4000], db.now(), job_id))


def submit(kind: str, params: dict, *, project_id: int | None, user_id: int | None, run_inline: bool = False,
           resume_from: str | None = None) -> str:
    if kind not in _registry:
        raise KeyError(f"Unknown job kind {kind}")
    job_id = uuid.uuid4().hex[:16]
    checkpoint = None
    if resume_from:
        prev = db.query_one("SELECT checkpoint_json FROM jobs WHERE id=?", (resume_from,))
        checkpoint = prev["checkpoint_json"] if prev else None
    db.execute("INSERT INTO jobs(id, project_id, kind, status, stage, progress, params_json, created_by, created_at, checkpoint_json)"
               " VALUES(?,?,?,?,?,?,?,?,?,?)",
               (job_id, project_id, kind, "queued", "Queued", 0.0, db.dumps(params), user_id, db.now(), checkpoint))
    if run_inline:
        _run(job_id, kind, params)
    else:
        _pool().submit(_run, job_id, kind, params)
    return job_id


def get(job_id: str) -> dict | None:
    j = db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if j:
        j["params"] = db.loads(j.get("params_json"), {})
        j["result"] = db.loads(j.get("result_json"), None)
    return j


def cancel(job_id: str) -> None:
    db.execute("UPDATE jobs SET cancel_requested=1 WHERE id=? AND status IN ('queued','running')", (job_id,))


def list_for_project(project_id: int, limit: int = 30) -> list[dict]:
    return db.query("SELECT id, kind, status, stage, progress, message, error, created_at, finished_at FROM jobs"
                    " WHERE project_id=? ORDER BY created_at DESC LIMIT ?", (project_id, limit))


def mark_orphans_failed() -> None:
    """Called at start-up: jobs that were running when the process stopped cannot still be running."""
    db.execute("UPDATE jobs SET status='failed', stage='Failed', error='Interrupted: the application stopped while this job was running. Retry to resume from the last checkpoint.', finished_at=?"
               " WHERE status IN ('queued','running')", (db.now(),))
