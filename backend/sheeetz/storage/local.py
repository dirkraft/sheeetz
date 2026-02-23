import os
from pathlib import Path


def list_subfolders(parent_path: str) -> list[dict]:
    """List subdirectories of a local path.

    Returns list of {id, name} where id is the absolute path.
    """
    parent = Path(parent_path).resolve()
    if not parent.is_dir():
        return []

    folders = []
    try:
        for entry in sorted(parent.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                folders.append({
                    "id": str(entry),
                    "name": entry.name,
                })
    except PermissionError:
        pass

    return folders


def get_folder_info(folder_path: str) -> dict:
    """Get name and parent of a local folder."""
    p = Path(folder_path).resolve()
    return {
        "id": str(p),
        "name": p.name,
        "parent_id": str(p.parent) if p.parent != p else None,
    }


def get_default_root() -> str:
    """Return a sensible default root for browsing."""
    return str(Path.home())
