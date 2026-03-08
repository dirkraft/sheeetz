"""Organize-files feature: preview and background job endpoints."""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .. import db as db_module
from ..db import get_db
from ..job_tasks import (
    OrganizeJob,
    clear_active_job,
    get_active_job_id,
    get_job,
    start_job,
)
from ..models import LibraryFolder, Sheet, User
from ..storage.organize import build_vars, move_drive_file, move_local_file, resolve_template
from .auth import get_current_user
from .folders import _refresh_and_get_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/organize", tags=["organize"])


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class PreviewRequest(BaseModel):
    sheet_ids: list[int]
    template: str


class SheetPreview(BaseModel):
    sheet_id: int
    filename: str
    from_path: str
    to_path: str | None
    can_move: bool
    warning: str | None = None


class PreviewResponse(BaseModel):
    previews: list[SheetPreview]


class OrganizeRequest(BaseModel):
    sheet_ids: list[int]
    template: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    total: int
    processed: int
    moved_count: int
    failed_count: int
    current_file: str
    errors: list[str]
    error: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_sheets_with_relations(
    sheet_ids: list[int], user_id: int, db
) -> list[Sheet]:
    result = await db.execute(
        select(Sheet)
        .where(Sheet.id.in_(sheet_ids), Sheet.user_id == user_id)
        .options(
            selectinload(Sheet.metadata_entries),
            selectinload(Sheet.library_folder),
        )
    )
    return list(result.scalars().all())


def _display_path(sheet: Sheet) -> str:
    """Human-readable current location of a sheet."""
    if sheet.backend_type == "local":
        return sheet.backend_file_id
    folder_path = sheet.folder_path or ""
    return f"{folder_path}/{sheet.filename}".lstrip("/")


def _job_response(job: OrganizeJob) -> dict:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "total": job.total,
        "processed": job.processed,
        "moved_count": job.moved_count,
        "failed_count": job.failed_count,
        "current_file": job.current_file,
        "errors": job.errors,
        "error": job.error,
    }


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _run_organize(
    user_id: int,
    job_id: str,
    sheet_ids: list[int],
    template: str,
    access_token: str | None,
) -> None:
    job = get_job(user_id, job_id)
    if not job:
        return

    try:
        async with db_module.background_session() as db:
            sheets = await _load_sheets_with_relations(sheet_ids, user_id, db)
            sheet_map = {s.id: s for s in sheets}

            for sid in sheet_ids:
                sheet = sheet_map.get(sid)
                if not sheet:
                    job.failed_count += 1
                    job.errors.append(f"Sheet {sid} not found")
                    job.processed += 1
                    continue

                job.current_file = sheet.filename
                vars = build_vars(sheet)
                rel_path, warnings = resolve_template(template, vars)

                if rel_path is None:
                    job.failed_count += 1
                    job.errors.append(f"{sheet.filename}: {warnings[0] if warnings else 'unresolvable'}")
                    job.processed += 1
                    continue

                try:
                    if sheet.backend_type == "local":
                        await move_local_file(sheet, rel_path, db)
                    else:
                        if not access_token:
                            raise RuntimeError("No Drive token available")
                        await move_drive_file(sheet, rel_path, access_token, db)
                    job.moved_count += 1
                except Exception as e:
                    logger.exception("Failed to move sheet %d", sid)
                    job.failed_count += 1
                    job.errors.append(f"{sheet.filename}: {e}")

                job.processed += 1

        job.status = "complete"
        job.current_file = ""

    except Exception as e:
        logger.exception("Organize job %s failed", job_id)
        job.status = "error"
        job.error = str(e)
    finally:
        clear_active_job(user_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/preview", response_model=PreviewResponse)
async def preview_organize(
    body: PreviewRequest,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    if not body.sheet_ids:
        raise HTTPException(status_code=400, detail="No sheets selected")
    if not body.template.strip():
        raise HTTPException(status_code=400, detail="Template is required")

    sheets = await _load_sheets_with_relations(body.sheet_ids, user.id, db)
    sheet_map = {s.id: s for s in sheets}

    previews = []
    for sid in body.sheet_ids:
        sheet = sheet_map.get(sid)
        if not sheet:
            continue

        vars = build_vars(sheet)
        rel_path, warnings = resolve_template(body.template, vars)
        from_path = _display_path(sheet)

        if rel_path is None:
            previews.append(SheetPreview(
                sheet_id=sid,
                filename=sheet.filename,
                from_path=from_path,
                to_path=None,
                can_move=False,
                warning=warnings[0] if warnings else "Cannot resolve template",
            ))
        else:
            if sheet.backend_type == "local" and sheet.library_folder:
                folder_root = sheet.library_folder.backend_folder_id
                to_path = str(Path(folder_root) / rel_path)
            else:
                to_path = rel_path
            previews.append(SheetPreview(
                sheet_id=sid,
                filename=sheet.filename,
                from_path=from_path,
                to_path=to_path,
                can_move=True,
            ))

    return PreviewResponse(previews=previews)


@router.post("")
async def start_organize(
    body: OrganizeRequest,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    if not body.sheet_ids:
        raise HTTPException(status_code=400, detail="No sheets selected")
    if not body.template.strip():
        raise HTTPException(status_code=400, detail="Template is required")

    # One organize job per user at a time
    active_id = get_active_job_id(user.id)
    if active_id:
        existing = get_job(user.id, active_id)
        if existing and existing.status == "running":
            raise HTTPException(
                status_code=409,
                detail="An organize job is already running. Wait for it to finish.",
            )

    # Check if any selected sheets use gdrive backend — need token upfront
    sheets_check = await _load_sheets_with_relations(body.sheet_ids, user.id, db)
    needs_drive = any(s.backend_type == "gdrive" for s in sheets_check)
    access_token = None
    if needs_drive:
        access_token = await _refresh_and_get_token(user, db)

    job = start_job(user.id, total=len(body.sheet_ids))

    asyncio.create_task(
        _run_organize(user.id, job.job_id, body.sheet_ids, body.template, access_token)
    )

    return _job_response(job)


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: str,
    user: User = Depends(get_current_user),
):
    job = get_job(user.id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_response(job)
