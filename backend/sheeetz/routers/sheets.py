from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import User
from .auth import get_current_user

router = APIRouter(prefix="/sheets", tags=["sheets"])


@router.get("")
async def list_sheets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # TODO: query Sheet index for this user
    return {"sheets": [], "total": 0}


@router.get("/{sheet_id}")
async def get_sheet(
    sheet_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # TODO: fetch sheet + metadata from index
    return {"id": sheet_id, "filename": "stub.pdf", "metadata": {}}


@router.patch("/{sheet_id}/metadata")
async def update_metadata(
    sheet_id: int,
    metadata: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # TODO: update metadata in PDF and index
    return {"id": sheet_id, "metadata": metadata, "updated": True}
