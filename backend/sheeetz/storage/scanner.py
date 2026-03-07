from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import LibraryFolder, Sheet, SheetMeta
from .metadata import extract_pdf_metadata, map_raw_to_core


@dataclass
class ScanResult:
    new_count: int
    total_count: int
    skipped_count: int


# Callback signature: (current_filename, processed_count, total_count_or_none)
ProgressCallback = Callable[[str, int, int | None], None]

_noop_progress: ProgressCallback = lambda *_: None


def _store_metadata(sheet: Sheet, pdf_bytes: bytes, db: AsyncSession) -> None:
    """Extract PDF metadata, map to core fields, and add SheetMeta rows."""
    try:
        raw = extract_pdf_metadata(pdf_bytes)
        core = map_raw_to_core(raw)
        for key, value in core.items():
            db.add(SheetMeta(sheet_id=sheet.id, key=key, value=value))
    except Exception:
        pass  # One bad PDF shouldn't abort the scan


async def scan_local_folder(
    folder: LibraryFolder,
    db: AsyncSession,
    on_progress: ProgressCallback = _noop_progress,
) -> ScanResult:
    root = Path(folder.backend_folder_id)
    pdf_files = sorted(root.rglob("*.pdf"))
    total = len(pdf_files)

    new_count = 0
    skipped_count = 0

    for i, pdf_path in enumerate(pdf_files):
        on_progress(pdf_path.name, i, total)

        file_id = str(pdf_path)
        existing = await db.execute(
            select(Sheet).where(
                Sheet.user_id == folder.user_id,
                Sheet.backend_type == "local",
                Sheet.backend_file_id == file_id,
            )
        )
        if existing.scalar_one_or_none():
            skipped_count += 1
            continue

        sheet = Sheet(
            user_id=folder.user_id,
            library_folder_id=folder.id,
            backend_type="local",
            backend_file_id=file_id,
            filename=pdf_path.name,
            folder_path=str(pdf_path.parent),
        )
        db.add(sheet)
        await db.flush()  # Get sheet.id assigned

        _store_metadata(sheet, pdf_path.read_bytes(), db)
        new_count += 1

    await db.commit()
    return ScanResult(new_count=new_count, total_count=total, skipped_count=skipped_count)


async def scan_gdrive_folder(
    folder: LibraryFolder,
    access_token: str,
    db: AsyncSession,
    on_progress: ProgressCallback = _noop_progress,
) -> ScanResult:
    from .drive_api import download_file, list_pdf_files_recursive

    on_progress("Listing files...", 0, None)
    pdf_files = await list_pdf_files_recursive(access_token, folder.backend_folder_id)
    total = len(pdf_files)

    new_count = 0
    skipped_count = 0

    for i, file_info in enumerate(pdf_files):
        on_progress(file_info["name"], i, total)

        existing = await db.execute(
            select(Sheet).where(
                Sheet.user_id == folder.user_id,
                Sheet.backend_type == "gdrive",
                Sheet.backend_file_id == file_info["id"],
            )
        )
        if existing.scalar_one_or_none():
            skipped_count += 1
            continue

        sheet = Sheet(
            user_id=folder.user_id,
            library_folder_id=folder.id,
            backend_type="gdrive",
            backend_file_id=file_info["id"],
            filename=file_info["name"],
            folder_path=file_info.get("folder_path", ""),
        )
        db.add(sheet)
        await db.flush()  # Get sheet.id assigned

        try:
            pdf_bytes = await download_file(access_token, file_info["id"])
            _store_metadata(sheet, pdf_bytes, db)
        except Exception:
            pass  # Don't abort scan for download/extraction failures

        new_count += 1

    await db.commit()
    return ScanResult(
        new_count=new_count, total_count=total, skipped_count=skipped_count
    )
