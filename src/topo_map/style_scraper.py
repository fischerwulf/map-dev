"""Style fetching and transformation utilities."""

import json
from pathlib import Path
from typing import Any

import httpx

# OpenFreeMap native styles (no transformation needed)
OPENFREEMAP_STYLES = {
    "liberty": "https://tiles.openfreemap.org/styles/liberty",
    "bright": "https://tiles.openfreemap.org/styles/bright",
    "positron": "https://tiles.openfreemap.org/styles/positron",
}

# OpenFreeMap TileJSON URL (resolves to actual tile URLs)
OPENFREEMAP_TILEJSON = "https://tiles.openfreemap.org/planet"

# Original sprite/glyph URLs for proxying (captured from scraped styles)
ASSET_SOURCES: dict[str, dict[str, str]] = {}


def transform_style_for_openfreemap(
    style: dict[str, Any],
    style_name: str,
    base_url: str = "",
) -> dict[str, Any]:
    """Transform a scraped style to use OpenFreeMap tiles and local proxy for assets.

    Args:
        style: The original style JSON
        style_name: Name identifier for this style (used in proxy URLs)
        base_url: Base URL of the server (for absolute proxy URLs)

    Returns:
        Transformed style with replaced sources
    """
    style = style.copy()

    # Store original asset URLs for proxying
    if "sprite" in style:
        ASSET_SOURCES.setdefault(style_name, {})["sprite"] = style["sprite"]
        style["sprite"] = f"{base_url}/api/proxy/sprites/{style_name}"

    if "glyphs" in style:
        ASSET_SOURCES.setdefault(style_name, {})["glyphs"] = style["glyphs"]
        style["glyphs"] = f"{base_url}/api/proxy/glyphs/{style_name}/{{fontstack}}/{{range}}.pbf"

    # Replace vector tile sources with OpenFreeMap TileJSON
    if "sources" in style:
        for source_name, source_config in style["sources"].items():
            if source_config.get("type") == "vector":
                # Replace with OpenFreeMap TileJSON URL
                source_config["url"] = OPENFREEMAP_TILEJSON
                # Remove any direct tiles array
                source_config.pop("tiles", None)

    return style


async def fetch_openfreemap_style(style_name: str) -> dict[str, Any] | None:
    """Fetch a native OpenFreeMap style.

    Args:
        style_name: One of 'liberty', 'bright', 'positron'

    Returns:
        Style JSON or None if not found
    """
    if style_name not in OPENFREEMAP_STYLES:
        return None

    url = OPENFREEMAP_STYLES[style_name]
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code == 200:
            return response.json()
    return None


def load_scraped_style(styles_dir: Path, style_name: str) -> dict[str, Any] | None:
    """Load a scraped and transformed style from disk.

    Args:
        styles_dir: Path to the styles directory
        style_name: Name of the style file (without .json)

    Returns:
        Style JSON or None if not found
    """
    style_path = styles_dir / "scraped" / f"{style_name}.json"
    if style_path.exists():
        return json.loads(style_path.read_text())
    return None


def load_custom_style(styles_dir: Path) -> dict[str, Any] | None:
    """Load the user's custom style.

    Args:
        styles_dir: Path to the styles directory

    Returns:
        Style JSON or None if not found
    """
    style_path = styles_dir / "custom.json"
    if style_path.exists():
        return json.loads(style_path.read_text())
    return None


def list_available_styles(styles_dir: Path) -> list[dict[str, str]]:
    """List all available styles.

    Args:
        styles_dir: Path to the styles directory

    Returns:
        List of style info dicts with 'name', 'source', and 'type'
    """
    styles = []

    # OpenFreeMap native styles
    for name in OPENFREEMAP_STYLES:
        styles.append({
            "name": name,
            "source": "openfreemap",
            "type": "native",
        })

    # Scraped styles
    scraped_dir = styles_dir / "scraped"
    if scraped_dir.exists():
        for style_file in scraped_dir.glob("*.json"):
            styles.append({
                "name": style_file.stem,
                "source": "scraped",
                "type": "transformed",
            })

    # Raster styles
    raster_dir = styles_dir / "raster"
    if raster_dir.exists():
        for style_file in raster_dir.glob("*.json"):
            styles.append({
                "name": style_file.stem,
                "source": "raster",
                "type": "raster",
            })

    # Custom style
    if (styles_dir / "custom.json").exists():
        styles.append({
            "name": "custom",
            "source": "local",
            "type": "editable",
        })

    # Remote vector styles (fetched dynamically)
    remote_vector_styles = [
        {"name": "basemap-at-vector", "source": "basemap.at", "type": "vector"},
        {"name": "swisstopo-base", "source": "swisstopo", "type": "vector"},
        {"name": "swisstopo-light", "source": "swisstopo", "type": "vector"},
        {"name": "swisstopo-winter", "source": "swisstopo", "type": "vector"},
        {"name": "swisstopo-imagery", "source": "swisstopo", "type": "vector"},
    ]
    styles.extend(remote_vector_styles)

    return styles
