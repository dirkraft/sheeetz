"""In-memory cleanup task registry for tracking background empty-folder cleanup jobs."""

from dataclasses import dataclass

from .bg_tasks import BackgroundJob


@dataclass
class CleanupTask(BackgroundJob):
    folder_id: int = 0
    removed: int = 0


# Keyed by (user_id, folder_id) to isolate per-user state
_tasks: dict[tuple[int, int], CleanupTask] = {}


def get_task(user_id: int, folder_id: int) -> CleanupTask | None:
    return _tasks.get((user_id, folder_id))


def start_task(user_id: int, folder_id: int) -> CleanupTask:
    task = CleanupTask(folder_id=folder_id)
    _tasks[(user_id, folder_id)] = task
    return task


def remove_task(user_id: int, folder_id: int) -> None:
    _tasks.pop((user_id, folder_id), None)
