"""In-memory job registry for background organize tasks."""

import uuid
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class OrganizeJob:
    job_id: str
    user_id: int
    total: int
    status: Literal["running", "complete", "error"] = "running"
    current_file: str = ""
    processed: int = 0
    moved_count: int = 0
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)
    error: str = ""


# Keyed by (user_id, job_id)
_jobs: dict[tuple[int, str], OrganizeJob] = {}

# One active organize job per user at a time
_active_user_job: dict[int, str] = {}


def get_job(user_id: int, job_id: str) -> OrganizeJob | None:
    return _jobs.get((user_id, job_id))


def get_active_job_id(user_id: int) -> str | None:
    return _active_user_job.get(user_id)


def start_job(user_id: int, total: int) -> OrganizeJob:
    job_id = str(uuid.uuid4())
    job = OrganizeJob(job_id=job_id, user_id=user_id, total=total)
    _jobs[(user_id, job_id)] = job
    _active_user_job[user_id] = job_id
    return job


def clear_active_job(user_id: int) -> None:
    _active_user_job.pop(user_id, None)
