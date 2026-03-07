"""In-memory scan task registry for tracking background folder scans."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ScanTask:
    folder_id: int
    status: Literal["scanning", "complete", "error"] = "scanning"
    current_file: str = ""
    processed: int = 0
    new_count: int = 0
    skipped_count: int = 0
    total_count: int | None = None
    error: str = ""


# Keyed by (user_id, folder_id) to isolate per-user state
_tasks: dict[tuple[int, int], ScanTask] = {}


def get_task(user_id: int, folder_id: int) -> ScanTask | None:
    return _tasks.get((user_id, folder_id))


def start_task(user_id: int, folder_id: int) -> ScanTask:
    task = ScanTask(folder_id=folder_id)
    _tasks[(user_id, folder_id)] = task
    return task


def remove_task(user_id: int, folder_id: int) -> None:
    _tasks.pop((user_id, folder_id), None)
