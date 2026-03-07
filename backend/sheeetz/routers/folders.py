import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import db as db_module
from ..db import get_db
from ..models import LibraryFolder, User
from ..scan_tasks import ScanTask, get_task, remove_task, start_task
from ..storage.drive_api import (
    DriveTokenError,
    build_folder_path,
    get_folder_info as drive_get_folder_info,
    get_valid_token,
    list_folders as drive_list_folders,
)
from ..storage.local import (
    get_default_root,
    get_folder_info as local_get_folder_info,
    list_subfolders,
)
from ..config import settings
from .auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/folders", tags=["folders"])


def _check_backend(backend: str):
    if backend == "local" and not settings.enable_local_backend:
        raise HTTPException(status_code=403, detail="Local backend is disabled")
    if backend not in ("local", "gdrive"):
        raise HTTPException(status_code=400, detail=f"Invalid backend: {backend}")


async def _refresh_and_get_token(user: User, db: AsyncSession) -> str:
    try:
        access_token, updated_json = await get_valid_token(user)
    except DriveTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))
    if updated_json != user.drive_token_json:
        user.drive_token_json = updated_json
        await db.commit()
    return access_token


def _task_response(task: ScanTask) -> dict:
    resp: dict = {
        "folder_id": task.folder_id,
        "status": task.status,
        "current_file": task.current_file,
        "processed": task.processed,
        "new_count": task.new_count,
        "skipped_count": task.skipped_count,
    }
    if task.total_count is not None:
        resp["total_count"] = task.total_count
    if task.error:
        resp["error"] = task.error
    return resp


async def _run_scan(user_id: int, folder_id: int, backend_type: str,
                    backend_folder_id: str, access_token: str | None) -> None:
    """Run a folder scan in the background, updating the in-memory task."""
    task = get_task(user_id, folder_id)
    if not task:
        return

    try:
        async with db_module.background_session() as db:
            # Re-fetch the folder in this session
            result = await db.execute(
                select(LibraryFolder).where(LibraryFolder.id == folder_id)
            )
            folder = result.scalar_one_or_none()
            if not folder:
                task.status = "error"
                task.error = "Folder not found"
                return

            def on_progress(filename: str, processed: int, total: int | None) -> None:
                task.current_file = filename
                task.processed = processed
                if total is not None:
                    task.total_count = total

            if backend_type == "local":
                from ..storage.scanner import scan_local_folder
                scan_result = await scan_local_folder(folder, db, on_progress)
            else:
                from ..storage.scanner import scan_gdrive_folder
                scan_result = await scan_gdrive_folder(
                    folder, access_token, db, on_progress
                )

            task.status = "complete"
            task.current_file = ""
            task.new_count = scan_result.new_count
            task.total_count = scan_result.total_count
            task.skipped_count = scan_result.skipped_count
            task.processed = scan_result.total_count

    except Exception as e:
        logger.exception("Scan failed for folder %d", folder_id)
        task.status = "error"
        task.error = str(e)


@router.get("/browse")
async def browse_folders(
    backend: str = "local",
    parent_id: str = "",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_backend(backend)

    if backend == "local":
        root = parent_id or get_default_root()
        folders = list_subfolders(root)
        parent_info = local_get_folder_info(root)
        return {"folders": folders, "parent": parent_info}

    # gdrive
    if not parent_id:
        parent_id = "root"
    token = await _refresh_and_get_token(user, db)
    folders = await drive_list_folders(token, parent_id)

    parent_info = None
    if parent_id != "root":
        info = await drive_get_folder_info(token, parent_id)
        parent_info = {
            "id": info["id"],
            "name": info["name"],
            "parent_id": (info.get("parents") or [None])[0],
        }

    return {"folders": folders, "parent": parent_info}


class FolderSelectRequest(BaseModel):
    backend_type: str
    backend_folder_id: str
    folder_name: str


@router.get("")
async def list_selected_folders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LibraryFolder).where(LibraryFolder.user_id == user.id)
    )
    folders = result.scalars().all()
    return {
        "folders": [
            {
                "id": f.id,
                "backend_type": f.backend_type,
                "backend_folder_id": f.backend_folder_id,
                "folder_name": f.folder_name,
                "folder_path": f.folder_path,
            }
            for f in folders
        ]
    }


@router.post("", status_code=201)
async def add_folder(
    body: FolderSelectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_backend(body.backend_type)

    existing = await db.execute(
        select(LibraryFolder).where(
            LibraryFolder.user_id == user.id,
            LibraryFolder.backend_type == body.backend_type,
            LibraryFolder.backend_folder_id == body.backend_folder_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Folder already selected")

    # Build display path
    if body.backend_type == "local":
        path = body.backend_folder_id  # already an absolute path
    else:
        token = await _refresh_and_get_token(user, db)
        path = await build_folder_path(token, body.backend_folder_id)

    folder = LibraryFolder(
        user_id=user.id,
        backend_type=body.backend_type,
        backend_folder_id=body.backend_folder_id,
        folder_name=body.folder_name,
        folder_path=path,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)

    return {
        "id": folder.id,
        "backend_type": folder.backend_type,
        "backend_folder_id": folder.backend_folder_id,
        "folder_name": folder.folder_name,
        "folder_path": folder.folder_path,
    }


@router.post("/{folder_id}/scan")
async def scan_folder(
    folder_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LibraryFolder).where(
            LibraryFolder.id == folder_id,
            LibraryFolder.user_id == user.id,
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    _check_backend(folder.backend_type)

    # Check if already scanning
    existing_task = get_task(user.id, folder_id)
    if existing_task and existing_task.status == "scanning":
        return _task_response(existing_task)

    # Get Drive token before launching background task (needs request context)
    access_token = None
    if folder.backend_type == "gdrive":
        access_token = await _refresh_and_get_token(user, db)

    task = start_task(user.id, folder_id)

    asyncio.create_task(
        _run_scan(user.id, folder_id, folder.backend_type,
                  folder.backend_folder_id, access_token)
    )

    return _task_response(task)


@router.get("/{folder_id}/scan-status")
async def scan_status(
    folder_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = get_task(user.id, folder_id)
    if not task:
        return {"folder_id": folder_id, "status": "idle"}
    return _task_response(task)


@router.delete("/{folder_id}", status_code=204)
async def remove_folder(
    folder_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LibraryFolder).where(
            LibraryFolder.id == folder_id,
            LibraryFolder.user_id == user.id,
        )
    )
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    remove_task(user.id, folder_id)
    await db.delete(folder)
    await db.commit()
