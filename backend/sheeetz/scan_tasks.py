"""In-memory scan task registry for tracking background folder scans."""

from dataclasses import dataclass

from .bg_tasks import BackgroundJob


@dataclass
class ScanTask(BackgroundJob):
    folder_id: int = 0
    current_file: str = ""
    processed: int = 0
    new_count: int = 0
    skipped_count: int = 0
    total_count: int | None = None


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
