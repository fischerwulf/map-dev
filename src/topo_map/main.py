"""FastAPI application for topo map style development."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from topo_map.routes import api, pages

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
STYLES_DIR = BASE_DIR / "styles"

# Create app
app = FastAPI(
    title="Topo Map Style Development",
    description="Side-by-side comparison of topographic map styles",
)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Setup templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Include routers
app.include_router(pages.router, tags=["pages"])
app.include_router(api.router, prefix="/api", tags=["api"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("topo_map.main:app", host="0.0.0.0", port=8000, reload=True)
