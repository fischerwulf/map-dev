"""Page routes for the web interface."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

# Templates
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the main map comparison page."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "Topo Map Style Development",
        },
    )
