import json

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import (
    build_auth_url,
    create_session_token,
    exchange_code,
    get_user_info,
    verify_session_token,
)
from ..config import settings
from ..db import get_db
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])


async def get_current_user(
    session_token: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    data = verify_session_token(session_token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    user = await db.get(User, data["uid"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.get("/login")
async def login():
    url = build_auth_url()
    return RedirectResponse(url)


@router.get("/callback")
async def callback(code: str, db: AsyncSession = Depends(get_db)):
    tokens = await exchange_code(code)
    user_info = await get_user_info(tokens["access_token"])

    result = await db.execute(
        select(User).where(User.google_id == user_info["sub"])
    )
    user = result.scalar_one_or_none()

    if user:
        user.email = user_info.get("email", user.email)
        user.name = user_info.get("name", user.name)
        user.drive_token_json = json.dumps(tokens)
    else:
        user = User(
            google_id=user_info["sub"],
            email=user_info.get("email", ""),
            name=user_info.get("name", ""),
            drive_token_json=json.dumps(tokens),
        )
        db.add(user)

    await db.commit()
    await db.refresh(user)

    token = create_session_token(user.id)
    response = RedirectResponse(url=settings.frontend_url)
    response.set_cookie(
        "session_token",
        token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
    )
    return response


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "name": user.name}


@router.get("/logout")
async def logout():
    response = RedirectResponse(url=settings.frontend_url, status_code=303)
    response.delete_cookie("session_token")
    return response
