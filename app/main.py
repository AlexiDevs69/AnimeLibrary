from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import BASE_DIR, settings
from app.database import Base, engine
from app.realtime import room_state_cache
from app.routers import anime, profiles, rooms, ws


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        # Convenient locally. Production deployments should run Alembic instead.
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    yield
    await room_state_cache.close()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

app.include_router(anime.router)
app.include_router(rooms.router)
app.include_router(profiles.router)
app.include_router(ws.router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"app_name": settings.app_name},
    )


@app.get("/room/{invite_code}", response_class=HTMLResponse, include_in_schema=False)
@app.get("/watch/{invite_code}", response_class=HTMLResponse, include_in_schema=False)
async def room_page(request: Request, invite_code: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="room.html",
        context={"app_name": settings.app_name, "invite_code": invite_code.upper()},
    )


@app.get("/profile", response_class=HTMLResponse, include_in_schema=False)
async def own_profile_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={"app_name": settings.app_name, "profile_username": ""},
    )


@app.get("/u/{username}", response_class=HTMLResponse, include_in_schema=False)
async def public_profile_page(request: Request, username: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={"app_name": settings.app_name, "profile_username": username},
    )


@app.get("/api/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
