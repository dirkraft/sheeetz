from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import admin, auth, folders, sheets


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Sheeetz", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(folders.router)
app.include_router(sheets.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/config")
async def client_config():
    backends = ["gdrive"]
    if settings.enable_local_backend:
        backends.insert(0, "local")
    return {"backends": backends}
