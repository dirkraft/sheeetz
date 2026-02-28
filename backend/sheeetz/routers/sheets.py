import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from ..db import get_db
from ..models import Sheet, SheetMeta, User
from ..storage.drive_api import (
    DriveTokenError,
    download_file,
    get_valid_token,
    upload_file_content,
)
from ..storage.metadata import (
    EDITABLE_CORE_KEYS,
    extract_pdf_metadata,
    map_raw_to_core,
    write_pdf_metadata,
)
from .auth import get_current_user

router = APIRouter(prefix="/sheets", tags=["sheets"])


@router.get("/metadata/distinct")
async def distinct_metadata_values(
    key: str = Query(..., description="Metadata key to get distinct values for"),
    q: str | None = Query(None, description="Substring filter (case-insensitive)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return distinct values for a given metadata key, scoped to the current user."""
    query = (
        select(SheetMeta.value)
        .join(Sheet, SheetMeta.sheet_id == Sheet.id)
        .where(Sheet.user_id == user.id, SheetMeta.key == key)
        .distinct()
    )
    if q:
        query = query.where(SheetMeta.value.ilike(f"%{q}%"))
    query = query.order_by(SheetMeta.value).limit(20)
    result = await db.execute(query)
    values = [row[0] for row in result.all()]
    return {"values": values}


@router.get("")
async def list_sheets(
    folder_id: int | None = None,
    filename: str | None = None,
    meta_key: str | None = None,
    meta_value: str | None = None,
    meta_filters: str | None = Query(None, description="JSON dict of {field: substring} filters"),
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

    # Legacy single meta filter
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

    # Multi-field meta filters: each key gets its own aliased join (AND semantics)
    if meta_filters:
        try:
            filters_dict = json.loads(meta_filters)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=400, detail="meta_filters must be valid JSON")
        for field_key, field_value in filters_dict.items():
            if not field_value:
                continue
            meta_alias = aliased(SheetMeta)
            query = query.join(
                meta_alias,
                (meta_alias.sheet_id == Sheet.id)
                & (meta_alias.key == field_key)
                & (meta_alias.value.ilike(f"%{field_value}%")),
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
        "backend_file_id": sheet.backend_file_id,
        "library_folder_id": sheet.library_folder_id,
        "metadata": {m.key: m.value for m in sheet.metadata_entries},
    }


@router.get("/{sheet_id}/pdf")
async def download_sheet_pdf(
    sheet_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Sheet).where(Sheet.id == sheet_id, Sheet.user_id == user.id)
    )
    sheet = result.scalar_one_or_none()
    if not sheet:
        raise HTTPException(status_code=404, detail="Sheet not found")

    if sheet.backend_type == "local":
        path = Path(sheet.backend_file_id)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="File not found on disk")
        return FileResponse(path, media_type="application/pdf", filename=sheet.filename)

    # gdrive
    try:
        access_token, updated_json = await get_valid_token(user)
    except DriveTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))
    if updated_json != user.drive_token_json:
        user.drive_token_json = updated_json
        await db.commit()

    content = await download_file(access_token, sheet.backend_file_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{sheet.filename}"'},
    )


@router.get("/{sheet_id}/pdf-metadata")
async def get_pdf_metadata(
    sheet_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract and return raw PDF metadata without saving it."""
    result = await db.execute(
        select(Sheet).where(Sheet.id == sheet_id, Sheet.user_id == user.id)
    )
    sheet = result.scalar_one_or_none()
    if not sheet:
        raise HTTPException(status_code=404, detail="Sheet not found")

    if sheet.backend_type == "local":
        path = Path(sheet.backend_file_id)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="File not found on disk")
        pdf_bytes = path.read_bytes()
    else:
        try:
            access_token, updated_json = await get_valid_token(user)
        except DriveTokenError as e:
            raise HTTPException(status_code=401, detail=str(e))
        if updated_json != user.drive_token_json:
            user.drive_token_json = updated_json
            await db.commit()
        pdf_bytes = await download_file(access_token, sheet.backend_file_id)

    metadata = extract_pdf_metadata(pdf_bytes)
    return {"sheet_id": sheet_id, "filename": sheet.filename, "metadata": metadata}


@router.patch("/{sheet_id}/metadata")
async def update_metadata(
    sheet_id: int,
    metadata: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update core metadata fields in the PDF (sheeetz namespace) and the index."""
    result = await db.execute(
        select(Sheet)
        .where(Sheet.id == sheet_id, Sheet.user_id == user.id)
        .options(selectinload(Sheet.metadata_entries))
    )
    sheet = result.scalar_one_or_none()
    if not sheet:
        raise HTTPException(status_code=404, detail="Sheet not found")

    # Only accept editable core keys
    core_updates = {k: v for k, v in metadata.items() if k in EDITABLE_CORE_KEYS}

    # --- Write to PDF ---
    if sheet.backend_type == "local":
        path = Path(sheet.backend_file_id)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="File not found on disk")
        pdf_bytes = path.read_bytes()
        try:
            updated_pdf = write_pdf_metadata(pdf_bytes, core_updates)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Failed to write PDF metadata: {e}")
        path.write_bytes(updated_pdf)
    else:
        # gdrive: download, modify, upload
        try:
            access_token, updated_json = await get_valid_token(user)
        except DriveTokenError as e:
            raise HTTPException(status_code=401, detail=str(e))
        if updated_json != user.drive_token_json:
            user.drive_token_json = updated_json

        pdf_bytes = await download_file(access_token, sheet.backend_file_id)
        try:
            updated_pdf = write_pdf_metadata(pdf_bytes, core_updates)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Failed to write PDF metadata: {e}")
        await upload_file_content(access_token, sheet.backend_file_id, updated_pdf)

    # --- Update index from the written PDF ---
    raw = extract_pdf_metadata(updated_pdf)
    mapped = map_raw_to_core(raw)

    # Delete existing metadata entries and replace
    for entry in list(sheet.metadata_entries):
        await db.delete(entry)
    await db.flush()

    for key, value in mapped.items():
        db.add(SheetMeta(sheet_id=sheet.id, key=key, value=value))

    await db.commit()

    # Reload to get fresh metadata
    await db.refresh(sheet)
    result2 = await db.execute(
        select(Sheet)
        .where(Sheet.id == sheet_id)
        .options(selectinload(Sheet.metadata_entries))
    )
    sheet = result2.scalar_one()

    return {
        "id": sheet.id,
        "metadata": {m.key: m.value for m in sheet.metadata_entries},
    }
