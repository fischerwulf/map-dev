"""API routes for styles and asset proxying."""

import json
from pathlib import Path
from urllib.parse import urlparse, urlencode, parse_qs

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from topo_map.style_scraper import (
    OPENFREEMAP_STYLES,
    fetch_openfreemap_style,
    list_available_styles,
    load_custom_style,
    load_scraped_style,
)
from topo_map.tile_cache import TileCache

router = APIRouter()

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
STYLES_DIR = BASE_DIR / "styles"
CACHE_DIR = BASE_DIR / "cache" / "tiles"
SECRETS_FILE = BASE_DIR / "secrets.json"

# Initialize tile cache (24 hour TTL by default)
tile_cache = TileCache(CACHE_DIR, default_ttl=86400)

# Secrets loaded at startup
SECRETS: dict = {}


def load_secrets() -> None:
    """Load authentication secrets from secrets.json.

    Called at module initialization. Secrets are used to inject
    API keys into proxied tile requests.
    """
    global SECRETS
    if SECRETS_FILE.exists():
        try:
            SECRETS = json.loads(SECRETS_FILE.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"[WARN] Failed to load secrets.json: {e}")
            SECRETS = {}


# Load secrets at module initialization
load_secrets()


def get_asset_sources(style_name: str) -> dict[str, str] | None:
    """Load asset source URLs and auth from a scraped style's _meta field."""
    style = load_scraped_style(STYLES_DIR, style_name)
    if style and "_meta" in style:
        meta = style["_meta"]

        # Get auth from secrets based on provider reference
        provider = meta.get("tile_auth_provider", "")
        auth = SECRETS.get(provider, {})

        return {
            "sprite": meta.get("original_sprite"),
            "glyphs": meta.get("original_glyphs"),
            "auth": auth,
        }
    return None


def get_tile_info(style_name: str) -> dict | None:
    """Load tile source URLs and auth from a scraped style's _meta field.

    Auth credentials are loaded from secrets.json based on the provider
    specified in the style's _meta.tile_auth_provider field.
    """
    style = load_scraped_style(STYLES_DIR, style_name)
    if style and "_meta" in style:
        meta = style["_meta"]

        # Get auth from secrets based on provider reference
        provider = meta.get("tile_auth_provider", "")
        auth = SECRETS.get(provider, {})

        # Fall back to embedded tile_auth for backwards compatibility
        if not auth:
            auth = meta.get("tile_auth", {})

        return {
            "auth": auth,
            "sources": meta.get("tile_sources", {}),
        }
    return None


def get_proxy_headers(target_url: str) -> dict[str, str]:
    """Get appropriate headers for proxying to tile providers.

    Providers often restrict API keys by referrer/origin.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if "maptiler.com" in target_url:
        headers["Referer"] = "https://www.maptiler.com/"
        headers["Origin"] = "https://www.maptiler.com"
    elif "mapbox.com" in target_url:
        headers["Referer"] = "https://www.mapbox.com/"
        headers["Origin"] = "https://www.mapbox.com"
    elif "tracestrack.com" in target_url:
        headers["Referer"] = "https://console.tracestrack.com/"
        headers["Origin"] = "https://console.tracestrack.com"
    return headers


def build_tile_url(url_template: str, z: int, x: int, y: int, auth: dict) -> str:
    """Build a tile URL from template with auth params injected.

    Args:
        url_template: URL template with {z}, {x}, {y} placeholders
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate
        auth: Auth params dict (key, access_token, etc.)

    Returns:
        Complete URL with coordinates and auth
    """
    # Replace coordinate placeholders
    url = url_template.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))

    # Parse existing query params
    parsed = urlparse(url)
    existing_params = parse_qs(parsed.query)

    # Add auth params
    params = {k: v[0] if isinstance(v, list) else v for k, v in existing_params.items()}
    params.update(auth)

    # Rebuild URL with auth
    if params:
        query = urlencode(params)
        url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query}"

    return url


@router.get("/styles")
async def get_styles() -> list[dict[str, str]]:
    """List all available styles."""
    return list_available_styles(STYLES_DIR)


@router.get("/styles/{style_name}")
async def get_style(style_name: str, request: Request) -> Response:
    """Get a style JSON by name.

    For custom.json, returns with no-cache headers.
    """
    # Determine base URL for proxy paths
    base_url = str(request.base_url).rstrip("/")

    # Custom style (no cache)
    if style_name == "custom":
        style = load_custom_style(STYLES_DIR)
        if style is None:
            raise HTTPException(status_code=404, detail="Custom style not found")
        return Response(
            content=json.dumps(style),
            media_type="application/json",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    # OpenFreeMap native styles
    if style_name in OPENFREEMAP_STYLES:
        style = await fetch_openfreemap_style(style_name)
        if style is None:
            raise HTTPException(status_code=502, detail=f"Failed to fetch {style_name} style")
        return Response(
            content=json.dumps(style),
            media_type="application/json",
        )

    # basemap.at vector style (fetched from remote, rewritten to use proxy)
    if style_name == "basemap-at-vector":
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://mapsneu.wien.gv.at/basemapvectorneu/root.json",
                follow_redirects=True,
            )
            if response.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to fetch basemap.at vector style")

            style = response.json()

            # Rewrite sprite URL to use our proxy
            style["sprite"] = f"{base_url}/api/proxy/basemap-at-vector/sprites/sprite"

            # Rewrite glyphs URL to use our proxy
            style["glyphs"] = f"{base_url}/api/proxy/basemap-at-vector/fonts/{{fontstack}}/{{range}}.pbf"

            # Rewrite tile source to use our proxy (with correct coordinate order)
            if "esri" in style.get("sources", {}):
                style["sources"]["esri"] = {
                    "type": "vector",
                    "tiles": [f"{base_url}/api/proxy/basemap-at-vector/{{z}}/{{x}}/{{y}}.pbf"],
                    "minzoom": 0,
                    "maxzoom": 19,
                }

            # Add background layer at the beginning (basemap.at only covers Austria)
            background_layer = {
                "id": "background",
                "type": "background",
                "paint": {"background-color": "#f8f4f0"},  # Light cream/paper color
            }
            if style.get("layers") and style["layers"][0].get("id") != "background":
                style["layers"].insert(0, background_layer)

            return Response(
                content=json.dumps(style),
                media_type="application/json",
            )

    # Swisstopo vector styles (fetched from remote)
    SWISSTOPO_VECTOR_STYLES = {
        "swisstopo-base": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.basemap.vt/style.json",
        "swisstopo-light": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.lightbasemap.vt/style.json",
        "swisstopo-winter": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.basemap-winter.vt/style.json",
        "swisstopo-imagery": "https://vectortiles.geo.admin.ch/styles/ch.swisstopo.imagerybasemap.vt/style.json",
    }

    if style_name in SWISSTOPO_VECTOR_STYLES:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                SWISSTOPO_VECTOR_STYLES[style_name],
                follow_redirects=True,
            )
            if response.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Failed to fetch {style_name}")

            style = response.json()

            # Add background layer (swisstopo only covers CH/LI)
            background_layer = {
                "id": "background",
                "type": "background",
                "paint": {"background-color": "#f8f4f0"},
            }
            if style.get("layers") and style["layers"][0].get("id") != "background":
                style["layers"].insert(0, background_layer)

            return Response(
                content=json.dumps(style),
                media_type="application/json",
            )

    # Raster styles
    raster_path = STYLES_DIR / "raster" / f"{style_name}.json"
    if raster_path.exists():
        return Response(
            content=raster_path.read_text(),
            media_type="application/json",
        )

    # Scraped styles
    style = load_scraped_style(STYLES_DIR, style_name)
    if style is None:
        raise HTTPException(status_code=404, detail=f"Style '{style_name}' not found")

    # Update proxy URLs with current base URL
    if "sprite" in style and "/api/proxy/sprites/" in style["sprite"]:
        style["sprite"] = f"{base_url}/api/proxy/sprites/{style_name}"
    if "glyphs" in style and "/api/proxy/glyphs/" in style["glyphs"]:
        style["glyphs"] = f"{base_url}/api/proxy/glyphs/{style_name}/{{fontstack}}/{{range}}.pbf"

    # Update tile source proxy URLs with current base URL
    for source_name, source_config in style.get("sources", {}).items():
        tiles = source_config.get("tiles", [])
        if tiles and len(tiles) > 0 and "/api/proxy/tiles/" in tiles[0]:
            # Update relative URLs to absolute
            source_config["tiles"] = [
                f"{base_url}{tile}" if tile.startswith("/") else tile
                for tile in tiles
            ]

    return Response(
        content=json.dumps(style),
        media_type="application/json",
    )


@router.get("/proxy/sprites/{style_name}")
@router.get("/proxy/sprites/{style_name}.json")
@router.get("/proxy/sprites/{style_name}.png")
@router.get("/proxy/sprites/{style_name}@2x")
@router.get("/proxy/sprites/{style_name}@2x.json")
@router.get("/proxy/sprites/{style_name}@2x.png")
async def proxy_sprites(style_name: str, request: Request) -> Response:
    """Proxy sprite requests to the original source."""
    # Get original sprite URL from style metadata
    assets = get_asset_sources(style_name)
    if not assets or not assets.get("sprite"):
        raise HTTPException(status_code=404, detail=f"No sprite source for {style_name}")

    original_url = assets["sprite"]
    auth = assets.get("auth", {})

    # Determine file extension from request path
    path = request.url.path
    suffix = ""
    if path.endswith(".json"):
        suffix = ".json"
    elif path.endswith(".png"):
        suffix = ".png"
    if "@2x" in path:
        suffix = "@2x" + suffix

    target_url = original_url + suffix

    # Add auth params to URL
    if auth:
        parsed = urlparse(target_url)
        existing_params = parse_qs(parsed.query)
        params = {k: v[0] if isinstance(v, list) else v for k, v in existing_params.items()}
        params.update(auth)
        query = urlencode(params)
        target_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query}"

    headers = get_proxy_headers(target_url)
    async with httpx.AsyncClient() as client:
        response = await client.get(target_url, headers=headers, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch sprite")

        content_type = response.headers.get("content-type", "application/octet-stream")
        return Response(content=response.content, media_type=content_type)


@router.get("/proxy/glyphs/{style_name}/{fontstack}/{range_file}")
async def proxy_glyphs(style_name: str, fontstack: str, range_file: str) -> Response:
    """Proxy glyph requests to the original source."""
    # Get original glyphs URL template from style metadata
    assets = get_asset_sources(style_name)
    if not assets or not assets.get("glyphs"):
        raise HTTPException(status_code=404, detail=f"No glyph source for {style_name}")

    original_template = assets["glyphs"]
    auth = assets.get("auth", {})

    # Build target URL - handle range with or without .pbf extension
    range_value = range_file.replace(".pbf", "")
    target_url = original_template.replace("{fontstack}", fontstack).replace("{range}", range_value)

    # Add auth params to URL
    if auth:
        parsed = urlparse(target_url)
        existing_params = parse_qs(parsed.query)
        params = {k: v[0] if isinstance(v, list) else v for k, v in existing_params.items()}
        params.update(auth)
        query = urlencode(params)
        target_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query}"

    headers = get_proxy_headers(target_url)
    async with httpx.AsyncClient() as client:
        response = await client.get(target_url, headers=headers, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch glyph")

        return Response(
            content=response.content,
            media_type="application/x-protobuf",
        )


@router.get("/proxy/swisstopo/{z}/{x}/{y}.jpeg")
async def proxy_swisstopo(z: int, x: int, y: int) -> Response:
    """Proxy Swiss topo WMTS tiles."""
    url = f"https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/{z}/{x}/{y}.jpeg"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch Swiss topo tile")

        return Response(
            content=response.content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )


@router.get("/proxy/basemap-at-terrain/{z}/{x}/{y}.jpeg")
async def proxy_basemap_at_terrain(z: int, x: int, y: int) -> Response:
    """Proxy Austrian basemap.at terrain/hillshade tiles."""
    url = f"https://mapsneu.wien.gv.at/basemap/bmapgelaende/grau/google3857/{z}/{y}/{x}.jpeg"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch Austrian basemap tile")

        return Response(
            content=response.content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )


@router.get("/proxy/basemap-at-standard/{z}/{x}/{y}.png")
async def proxy_basemap_at_standard(z: int, x: int, y: int) -> Response:
    """Proxy Austrian basemap.at standard colored tiles."""
    url = f"https://mapsneu.wien.gv.at/basemap/geolandbasemap/normal/google3857/{z}/{y}/{x}.png"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch Austrian basemap tile")

        return Response(
            content=response.content,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )


@router.get("/proxy/basemap-at-grau/{z}/{x}/{y}.png")
async def proxy_basemap_at_grau(z: int, x: int, y: int) -> Response:
    """Proxy Austrian basemap.at grayscale tiles with contour lines."""
    url = f"https://mapsneu.wien.gv.at/basemap/bmapgrau/normal/google3857/{z}/{y}/{x}.png"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch Austrian basemap tile")

        return Response(
            content=response.content,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )


@router.get("/proxy/basemap-at-ortho/{z}/{x}/{y}.jpeg")
async def proxy_basemap_at_ortho(z: int, x: int, y: int) -> Response:
    """Proxy Austrian basemap.at orthophoto/aerial imagery tiles."""
    url = f"https://mapsneu.wien.gv.at/basemap/bmaporthofoto30cm/normal/google3857/{z}/{y}/{x}.jpeg"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch Austrian basemap tile")

        return Response(
            content=response.content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )


@router.get("/proxy/basemap-at-surface/{z}/{x}/{y}.jpeg")
async def proxy_basemap_at_surface(z: int, x: int, y: int) -> Response:
    """Proxy Austrian basemap.at surface shading tiles."""
    url = f"https://mapsneu.wien.gv.at/basemap/bmapoberflaeche/grau/google3857/{z}/{y}/{x}.jpeg"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch Austrian basemap tile")

        return Response(
            content=response.content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )


@router.get("/proxy/basemap-at-hidpi/{z}/{x}/{y}.jpeg")
async def proxy_basemap_at_hidpi(z: int, x: int, y: int) -> Response:
    """Proxy Austrian basemap.at HiDPI tiles (512x512 for retina displays)."""
    url = f"https://mapsneu.wien.gv.at/basemap/bmaphidpi/normal/google3857/{z}/{y}/{x}.jpeg"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch Austrian basemap tile")

        return Response(
            content=response.content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )


@router.get("/proxy/bayern/{z}/{x}/{y}.png")
async def proxy_bayern(z: int, x: int, y: int) -> Response:
    """Proxy Bavarian LDBV topographic tiles."""
    # Uses bayernwolke.de CDN with format {z}/{x}/{y} (no extension)
    url = f"https://wmtsod1.bayernwolke.de/wmts/by_amtl_karte/smerc/{z}/{x}/{y}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch Bayern topo tile")

        return Response(
            content=response.content,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )


@router.get("/proxy/basemap-at-vector/sprites/sprite.json")
@router.get("/proxy/basemap-at-vector/sprites/sprite.png")
@router.get("/proxy/basemap-at-vector/sprites/sprite@2x.json")
@router.get("/proxy/basemap-at-vector/sprites/sprite@2x.png")
async def proxy_basemap_at_vector_sprites(request: Request) -> Response:
    """Proxy Austrian basemap.at vector style sprites."""
    path = request.url.path
    # Extract sprite file from path
    sprite_file = path.split("/sprites/")[-1]
    url = f"https://mapsneu.wien.gv.at/basemapv/bmapv/3857/resources/sprites/{sprite_file}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch basemap.at sprite",
            )

        content_type = "application/json" if path.endswith(".json") else "image/png"
        return Response(
            content=response.content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )


@router.get("/proxy/basemap-at-vector/fonts/{fontstack}/{range_file}")
async def proxy_basemap_at_vector_glyphs(fontstack: str, range_file: str) -> Response:
    """Proxy Austrian basemap.at vector style glyphs/fonts."""
    url = f"https://mapsneu.wien.gv.at/basemapv/bmapv/3857/resources/fonts/{fontstack}/{range_file}"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch basemap.at glyph",
            )

        return Response(
            content=response.content,
            media_type="application/x-protobuf",
            headers={"Cache-Control": "public, max-age=86400"},
        )


@router.get("/proxy/basemap-at-vector/{z}/{x}/{y}.pbf")
async def proxy_basemap_at_vector_tiles(z: int, x: int, y: int) -> Response:
    """Proxy Austrian basemap.at vector tiles.

    Note: basemap.at uses {z}/{y}/{x} order (row before column),
    but we expose standard {z}/{x}/{y} for MapLibre compatibility.
    """
    # Convert from standard web map order to basemap.at order
    url = f"https://mapsneu.wien.gv.at/basemapv/bmapv/3857/tile/{z}/{y}/{x}.pbf"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, follow_redirects=True)
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch Austrian vector tile",
            )

        return Response(
            content=response.content,
            media_type="application/x-protobuf",
            headers={"Cache-Control": "public, max-age=86400"},
        )


# ----- Tile Proxy Endpoints -----


@router.get("/proxy/tiles/{style_name}/{source_name}/{z}/{x}/{y}.pbf")
async def proxy_vector_tiles(
    style_name: str, source_name: str, z: int, x: int, y: int
) -> Response:
    """Proxy vector tile requests with caching and auth injection.

    Args:
        style_name: Name of the style (e.g., "maptiler-outdoor")
        source_name: Name of the source within the style (e.g., "maptiler_planet")
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate

    Returns:
        Vector tile response with X-Cache header
    """
    # Check cache first
    cache_key = f"{style_name}_{source_name}"
    cached = tile_cache.get(cache_key, z, x, y, "pbf")
    if cached:
        return Response(
            content=cached.content,
            media_type=cached.content_type,
            headers={
                "X-Cache": "HIT",
                "Cache-Control": "public, max-age=86400",
                **cached.headers,
            },
        )

    # Get tile auth and source URL
    tile_info = get_tile_info(style_name)
    if not tile_info:
        raise HTTPException(
            status_code=404, detail=f"No tile info for style {style_name}"
        )

    original_url = tile_info["sources"].get(source_name)
    if not original_url:
        raise HTTPException(
            status_code=404, detail=f"Source {source_name} not found in {style_name}"
        )

    # Build target URL with auth
    auth = tile_info["auth"]
    target_url = build_tile_url(original_url, z, x, y, auth)

    # Fetch tile from upstream with appropriate headers
    headers = get_proxy_headers(target_url)
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(target_url, headers=headers, follow_redirects=True)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch tile: {e}")

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Upstream returned {response.status_code}",
            )

        content_type = response.headers.get("content-type", "application/x-protobuf")

        # Cache the tile
        tile_cache.put(
            cache_key,
            z,
            x,
            y,
            "pbf",
            content=response.content,
            content_type=content_type,
            headers={},
        )

        return Response(
            content=response.content,
            media_type=content_type,
            headers={
                "X-Cache": "MISS",
                "Cache-Control": "public, max-age=86400",
            },
        )


@router.get("/proxy/tiles/{style_name}/{source_name}/{z}/{x}/{y}.png")
async def proxy_raster_tiles(
    style_name: str, source_name: str, z: int, x: int, y: int
) -> Response:
    """Proxy raster tile requests (PNG) with caching.

    Args:
        style_name: Name of the style
        source_name: Name of the source within the style
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate

    Returns:
        Raster tile response with X-Cache header
    """
    # Check cache first
    cache_key = f"{style_name}_{source_name}"
    cached = tile_cache.get(cache_key, z, x, y, "png")
    if cached:
        return Response(
            content=cached.content,
            media_type=cached.content_type,
            headers={
                "X-Cache": "HIT",
                "Cache-Control": "public, max-age=86400",
                **cached.headers,
            },
        )

    # Get tile auth and source URL
    tile_info = get_tile_info(style_name)
    if not tile_info:
        raise HTTPException(
            status_code=404, detail=f"No tile info for style {style_name}"
        )

    original_url = tile_info["sources"].get(source_name)
    if not original_url:
        raise HTTPException(
            status_code=404, detail=f"Source {source_name} not found in {style_name}"
        )

    # Build target URL with auth
    auth = tile_info["auth"]
    target_url = build_tile_url(original_url, z, x, y, auth)

    # Fetch tile from upstream with appropriate headers
    headers = get_proxy_headers(target_url)
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(target_url, headers=headers, follow_redirects=True)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch tile: {e}")

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Upstream returned {response.status_code}",
            )

        content_type = response.headers.get("content-type", "image/png")

        # Cache the tile
        tile_cache.put(
            cache_key,
            z,
            x,
            y,
            "png",
            content=response.content,
            content_type=content_type,
            headers={},
        )

        return Response(
            content=response.content,
            media_type=content_type,
            headers={
                "X-Cache": "MISS",
                "Cache-Control": "public, max-age=86400",
            },
        )


@router.get("/proxy/tiles/{style_name}/{source_name}/{z}/{x}/{y}.webp")
async def proxy_terrain_tiles(
    style_name: str, source_name: str, z: int, x: int, y: int
) -> Response:
    """Proxy terrain/DEM tile requests (WebP) with caching.

    Args:
        style_name: Name of the style
        source_name: Name of the source within the style
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate

    Returns:
        Terrain tile response with X-Cache header
    """
    # Check cache first
    cache_key = f"{style_name}_{source_name}"
    cached = tile_cache.get(cache_key, z, x, y, "webp")
    if cached:
        return Response(
            content=cached.content,
            media_type=cached.content_type,
            headers={
                "X-Cache": "HIT",
                "Cache-Control": "public, max-age=86400",
                **cached.headers,
            },
        )

    # Get tile auth and source URL
    tile_info = get_tile_info(style_name)
    if not tile_info:
        raise HTTPException(
            status_code=404, detail=f"No tile info for style {style_name}"
        )

    original_url = tile_info["sources"].get(source_name)
    if not original_url:
        raise HTTPException(
            status_code=404, detail=f"Source {source_name} not found in {style_name}"
        )

    # Build target URL with auth
    auth = tile_info["auth"]
    target_url = build_tile_url(original_url, z, x, y, auth)

    # Fetch tile from upstream with appropriate headers
    headers = get_proxy_headers(target_url)
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(target_url, headers=headers, follow_redirects=True)
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch tile: {e}")

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Upstream returned {response.status_code}",
            )

        content_type = response.headers.get("content-type", "image/webp")

        # Cache the tile
        tile_cache.put(
            cache_key,
            z,
            x,
            y,
            "webp",
            content=response.content,
            content_type=content_type,
            headers={},
        )

        return Response(
            content=response.content,
            media_type=content_type,
            headers={
                "X-Cache": "MISS",
                "Cache-Control": "public, max-age=86400",
            },
        )


# ----- Cache Management Endpoints -----


@router.get("/cache/stats")
async def cache_stats() -> dict:
    """Get tile cache statistics."""
    return tile_cache.stats()


@router.delete("/cache/{cache_key}")
async def invalidate_cache(cache_key: str) -> dict:
    """Invalidate cache for a specific key or all caches.

    Args:
        cache_key: Cache key to invalidate, or "all" for everything

    Returns:
        Dict with count of invalidated files
    """
    key = None if cache_key == "all" else cache_key
    count = tile_cache.invalidate(key)
    return {"invalidated": count, "key": cache_key}
