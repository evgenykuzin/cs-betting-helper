"""
FastAPI application.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router as api_router
from app.api.pages import router as pages_router
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    # Startup
    await init_db()
    yield
    # Shutdown


app = FastAPI(title="CS Betting Helper", version="0.2.0", lifespan=lifespan)

# Static files + templates
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")

# Routes
app.include_router(api_router, prefix="/api")
app.include_router(pages_router)
