from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from foundry.dashboard import db as _db
from foundry.dashboard.routes import (
    index as index_router,
    projects as projects_router,
    devices as devices_router,
    review as review_router,
    settings as settings_router,
    triage as triage_router,
)
from foundry.dashboard.routes.api import router as api_router

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app):
    load_dotenv()
    _db.init_db()
    yield


app = FastAPI(title="Foundry Dashboard", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")


app.include_router(index_router.router)
app.include_router(projects_router.router)
app.include_router(devices_router.router)
app.include_router(review_router.router)
app.include_router(settings_router.router)
app.include_router(triage_router.router)
app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}


app.state.templates = templates
