from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import get_db
from ..models import Sheet, SheetMeta, User
from .auth import get_current_user

router = APIRouter(prefix="/sheets", tags=["sheets"])


@router.get("")
async def list_sheets(
    folder_id: int | None = None,
    filename: str | None = None,
    meta_key: str | None = None,
    meta_value: str | None = None,
    sort_by: str = "filename",
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Sheet)
        .where(Sheet.user_id == user.id)
        .options(selectinload(Sheet.metadata_entries))
    )

    if folder_id is not None:
        query = query.where(Sheet.library_folder_id == folder_id)

    if filename:
        query = query.where(Sheet.filename.ilike(f"%{filename}%"))

    if meta_key and meta_value:
        query = query.join(
            SheetMeta,
            (SheetMeta.sheet_id == Sheet.id)
            & (SheetMeta.key == meta_key)
            & (SheetMeta.value.ilike(f"%{meta_value}%")),
        )
    elif meta_key:
        query = query.join(
            SheetMeta,
            (SheetMeta.sheet_id == Sheet.id) & (SheetMeta.key == meta_key),
        )

    sort_col = Sheet.filename if sort_by == "filename" else Sheet.folder_path
    query = query.order_by(sort_col.asc() if sort_dir == "asc" else sort_col.desc())

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    query = query.offset((page - 1) * page_size).limit(page_size)
    sheets = (await db.execute(query)).scalars().all()

    return {
        "sheets": [
            {
                "id": s.id,
                "filename": s.filename,
                "folder_path": s.folder_path,
                "backend_type": s.backend_type,
                "library_folder_id": s.library_folder_id,
                "metadata": {m.key: m.value for m in s.metadata_entries},
            }
            for s in sheets
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{sheet_id}")
async def get_sheet(
    sheet_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Sheet)
        .where(Sheet.id == sheet_id, Sheet.user_id == user.id)
        .options(selectinload(Sheet.metadata_entries))
    )
    sheet = result.scalar_one_or_none()
    if not sheet:
        raise HTTPException(status_code=404, detail="Sheet not found")
    return {
        "id": sheet.id,
        "filename": sheet.filename,
        "folder_path": sheet.folder_path,
        "backend_type": sheet.backend_type,
        "library_folder_id": sheet.library_folder_id,
        "metadata": {m.key: m.value for m in sheet.metadata_entries},
    }


@router.patch("/{sheet_id}/metadata")
async def update_metadata(
    sheet_id: int,
    metadata: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # TODO: update metadata in PDF and index
    return {"id": sheet_id, "metadata": metadata, "updated": True}
