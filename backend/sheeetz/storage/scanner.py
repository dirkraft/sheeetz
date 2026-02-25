from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import LibraryFolder, Sheet


@dataclass
class ScanResult:
    new_count: int
    total_count: int
    skipped_count: int


async def scan_local_folder(folder: LibraryFolder, db: AsyncSession) -> ScanResult:
    root = Path(folder.backend_folder_id)
    pdf_files = sorted(root.rglob("*.pdf"))

    new_count = 0
    skipped_count = 0

    for pdf_path in pdf_files:
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
        new_count += 1

    await db.commit()
    return ScanResult(new_count=new_count, total_count=len(pdf_files), skipped_count=skipped_count)


async def scan_gdrive_folder(
    folder: LibraryFolder, access_token: str, db: AsyncSession
) -> ScanResult:
    from .drive_api import list_pdf_files_recursive

    pdf_files = await list_pdf_files_recursive(access_token, folder.backend_folder_id)

    new_count = 0
    skipped_count = 0

    for file_info in pdf_files:
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
        new_count += 1

    await db.commit()
    return ScanResult(
        new_count=new_count, total_count=len(pdf_files), skipped_count=skipped_count
    )
