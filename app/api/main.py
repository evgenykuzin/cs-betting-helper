"""
FastAPI application.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router as api_router
from app.api.pages import router as pages_router

app = FastAPI(title="CS Betting Helper", version="0.2.0")

# Static files + templates
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")

# Routes
app.include_router(api_router, prefix="/api")
app.include_router(pages_router)
