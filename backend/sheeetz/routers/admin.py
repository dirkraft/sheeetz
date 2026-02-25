from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Sheet, SheetMeta, User
from .auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/clear-index")
async def clear_index(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count_q = select(func.count()).select_from(
        select(Sheet).where(Sheet.user_id == user.id).subquery()
    )
    total = (await db.execute(count_q)).scalar_one()

    # SheetMeta cascades from Sheet, but explicit delete is faster for bulk
    await db.execute(
        delete(SheetMeta).where(
            SheetMeta.sheet_id.in_(
                select(Sheet.id).where(Sheet.user_id == user.id)
            )
        )
    )
    await db.execute(delete(Sheet).where(Sheet.user_id == user.id))
    await db.commit()

    return {"deleted": total}
