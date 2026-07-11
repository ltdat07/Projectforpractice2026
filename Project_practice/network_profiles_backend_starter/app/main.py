from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import repository
from app.config import ensure_runtime_dirs, get_core_mode
from app.core_manager import core_manager
from app.database import init_database
from app.routers.actions import router as actions_router
from app.routers.profiles import router as profiles_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    ensure_runtime_dirs()
    repository.reset_active_statuses()
    yield
    core_manager.shutdown()


app = FastAPI(
    title="Network Core Management Backend",
    description=(
        "Backend for a demonstration web panel that manages network profiles "
        "and can control Xray Core."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profiles_router)
app.include_router(actions_router)


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "core_mode": get_core_mode()}
