#!/usr/bin/env python3
"""Scrape map styles from public demo pages using Playwright.

This script captures complete styles including API keys from tile requests,
then transforms them to use local proxy endpoints.

API keys are saved to secrets.json (gitignored) and referenced by provider
name in the scraped style files.

Usage:
    uv run scripts/scrape_styles.py
"""

import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import httpx
from playwright.sync_api import sync_playwright, Response

# Base directory for file paths
BASE_DIR = Path(__file__).parent.parent
SECRETS_FILE = BASE_DIR / "secrets.json"

# Map style names to provider identifiers
PROVIDER_MAP = {
    "maptiler-outdoor": "maptiler",
    "maptiler-topo": "maptiler",
    "tracestrack-topo": "tracestrack",
    "mapbox-outdoors": "mapbox",
}


def get_provider_for_style(style_name: str) -> str:
    """Get the provider identifier for a style name."""
    return PROVIDER_MAP.get(style_name, style_name.split("-")[0])


def save_auth_to_secrets(style_name: str, auth: dict) -> None:
    """Save authentication credentials to secrets.json.

    Args:
        style_name: Name of the style (e.g., "maptiler-outdoor")
        auth: Auth dict with keys like "key" or "access_token"
    """
    if not auth:
        return

    # Load existing secrets
    secrets = {}
    if SECRETS_FILE.exists():
        try:
            secrets = json.loads(SECRETS_FILE.read_text())
        except json.JSONDecodeError:
            secrets = {}

    # Map style to provider
    provider = get_provider_for_style(style_name)

    # Update secrets for this provider
    secrets[provider] = auth

    # Write back
    SECRETS_FILE.write_text(json.dumps(secrets, indent=2))
    print(f"  [OK] Saved auth to secrets.json under '{provider}'")

# Target pages and URL patterns to intercept
SCRAPE_TARGETS = {
    "mapbox-outdoors": {
        "url": "https://www.mapbox.com/maps/outdoors",
        "style_pattern": "api.mapbox.com/styles/v1",
        "tile_patterns": ["api.mapbox.com/v4", "api.mapbox.com"],
        "wait_for": "style.json",
    },
    "maptiler-outdoor": {
        "url": "https://www.maptiler.com/maps/#style=outdoor",
        "style_pattern": "api.maptiler.com/maps",
        "tile_patterns": ["api.maptiler.com/tiles"],
        "wait_for": "style.json",
    },
    "maptiler-topo": {
        "url": "https://www.maptiler.com/maps/#style=topo-v2",
        "style_pattern": "api.maptiler.com/maps",
        "tile_patterns": ["api.maptiler.com/tiles"],
        "wait_for": "style.json",
    },
    "tracestrack-topo": {
        "url": "https://console.tracestrack.com/vector-explorer",
        "style_pattern": "tile.tracestrack.com",
        "tile_patterns": ["tile.tracestrack.com"],
        "wait_for": "style.json",
        # Select "Topo" style from the dropdown (default is Carto)
        "pre_scrape_actions": [
            {"action": "select", "selector": "select", "value": "topo", "wait_after": 3000},
        ],
    },
}


def extract_auth_from_url(url: str) -> dict:
    """Extract authentication parameters from URL.

    Returns dict with 'key' and/or 'access_token' if found.
    """
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    auth = {}
    if "key" in params:
        auth["key"] = params["key"][0]
    if "access_token" in params:
        auth["access_token"] = params["access_token"][0]

    return auth


def scrape_style(name: str, config: dict) -> dict | None:
    """Scrape a style from a public demo page.

    Captures:
    - style.json
    - Original sprite/glyph URLs
    - API keys from tile requests

    Args:
        name: Style identifier
        config: Configuration dict

    Returns:
        Style JSON with _scrape_data containing auth and original URLs, or None
    """
    captured_style = None
    captured_sprite = None
    captured_glyphs = None
    captured_auth = {}
    captured_tile_urls = []

    def handle_response(response: Response) -> None:
        nonlocal captured_style, captured_sprite, captured_glyphs, captured_auth, captured_tile_urls

        url = response.url

        # Capture style.json
        if config["style_pattern"] in url and config["wait_for"] in url:
            try:
                captured_style = response.json()
                captured_sprite = captured_style.get("sprite")
                captured_glyphs = captured_style.get("glyphs")
                print(f"  [OK] Captured style from: {url[:80]}...")

                # Extract auth from style URL
                auth = extract_auth_from_url(url)
                if auth:
                    captured_auth.update(auth)
                    print(f"  [OK] Captured auth from style URL: {list(auth.keys())}")
            except Exception as e:
                print(f"  [WARN] Failed to parse style JSON: {e}")

        # Capture tile requests for auth extraction
        for pattern in config.get("tile_patterns", []):
            if pattern in url and (".pbf" in url or ".mvt" in url or ".png" in url):
                auth = extract_auth_from_url(url)
                if auth:
                    captured_auth.update(auth)
                    if url not in captured_tile_urls:
                        captured_tile_urls.append(url)
                        print(f"  [OK] Captured tile auth: {list(auth.keys())}")
                break

    print(f"[INFO] Scraping {name}...")
    print(f"  URL: {config['url']}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        page = context.new_page()

        # Listen for responses
        page.on("response", handle_response)

        try:
            # Navigate and wait for network idle
            page.goto(config["url"], wait_until="networkidle", timeout=30000)

            # Execute pre-scrape actions (e.g., click style selector)
            for action in config.get("pre_scrape_actions", []):
                action_type = action.get("action")
                selector = action.get("selector")
                wait_after = action.get("wait_after", 2000)

                try:
                    # Reset captured style BEFORE action to capture the new one
                    captured_style = None

                    if action_type == "click":
                        print(f"  [INFO] Clicking: {selector}")
                        page.click(selector, timeout=5000)
                    elif action_type == "select":
                        value = action.get("value")
                        print(f"  [INFO] Selecting '{value}' from: {selector}")
                        page.select_option(selector, value, timeout=5000)

                    page.wait_for_timeout(wait_after)
                except Exception as e:
                    print(f"  [WARN] Action '{action_type}' failed: {e}")

            # Additional wait for dynamic loading (tiles need to load)
            page.wait_for_timeout(5000)

            if captured_style is None:
                print("  [WARN] No style captured, waiting longer...")
                page.wait_for_timeout(5000)

            # If no auth captured yet, try scrolling/zooming to trigger tile loads
            if not captured_auth:
                print("  [WARN] No auth captured, trying to trigger tile loads...")
                page.wait_for_timeout(3000)

        except Exception as e:
            print(f"  [ERROR] Navigation failed: {e}")
        finally:
            browser.close()

    if captured_style:
        # Attach scrape data for later processing
        captured_style["_scrape_data"] = {
            "original_sprite": captured_sprite,
            "original_glyphs": captured_glyphs,
            "tile_auth": captured_auth,
            "sample_tile_urls": captured_tile_urls[:3],  # Keep a few samples for debugging
        }
        return captured_style

    return None


def fetch_tilejson_tile_url(url: str) -> str | None:
    """Fetch a TileJSON URL and extract the actual tile URL template.

    Args:
        url: TileJSON URL

    Returns:
        Tile URL template from the TileJSON, or None if fetch failed
    """
    # Determine referrer based on provider
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    if "maptiler.com" in url:
        headers["Referer"] = "https://www.maptiler.com/"
        headers["Origin"] = "https://www.maptiler.com"
    elif "mapbox.com" in url:
        headers["Referer"] = "https://www.mapbox.com/"
        headers["Origin"] = "https://www.mapbox.com"
    elif "tracestrack.com" in url:
        headers["Referer"] = "https://console.tracestrack.com/"
        headers["Origin"] = "https://console.tracestrack.com"

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=headers, follow_redirects=True)
            if response.status_code == 200:
                data = response.json()
                tiles = data.get("tiles", [])
                if tiles:
                    print(f"    [OK] Fetched TileJSON, got tile URL: {tiles[0][:60]}...")
                    return tiles[0]
    except Exception as e:
        print(f"    [WARN] Failed to fetch TileJSON: {e}")

    return None


def tilejson_to_tile_url(url: str) -> str:
    """Convert a TileJSON URL to a tile URL template.

    First tries to fetch the TileJSON to get the actual tile URL.
    Falls back to pattern-based transformation if fetch fails.

    Args:
        url: TileJSON URL

    Returns:
        Tile URL template with {z}/{x}/{y} placeholders
    """
    # Check if this looks like a TileJSON URL
    is_tilejson = (
        "/tilejson.json" in url
        or "/tiles.json" in url
        or url.endswith("/tiles")
    )

    if is_tilejson:
        # Try to fetch the actual tile URL from TileJSON
        fetched_url = fetch_tilejson_tile_url(url)
        if fetched_url:
            return fetched_url

    # Fallback: pattern-based transformation
    # MapTiler pattern: replace /tiles.json with /{z}/{x}/{y}.pbf
    if "api.maptiler.com" in url:
        if "/tiles.json" in url:
            # Determine extension based on tileset type
            if "terrain-rgb" in url:
                ext = "webp"
            elif "hillshade" in url:
                ext = "webp"
            else:
                ext = "pbf"
            return url.replace("/tiles.json", f"/{{z}}/{{x}}/{{y}}.{ext}")

    # Mapbox pattern
    if "api.mapbox.com" in url:
        if "/tiles.json" in url:
            return url.replace("/tiles.json", "/{z}/{x}/{y}.vector.pbf")

    # Tracestrack pattern (fallback)
    if "tile.tracestrack.com" in url:
        if "/tilejson.json" in url:
            return url.replace("/tilejson.json", "/{z}/{x}/{y}.pbf")
        if "/tiles.json" in url:
            return url.replace("/tiles.json", "/{z}/{x}/{y}.pbf")

    # Generic fallback: try common TileJSON patterns
    if "/tilejson.json" in url:
        return url.replace("/tilejson.json", "/{z}/{x}/{y}.pbf")
    if "/tiles.json" in url:
        return url.replace("/tiles.json", "/{z}/{x}/{y}.pbf")

    return url


def transform_for_tile_proxy(style: dict, name: str) -> dict:
    """Transform a scraped style to use tile proxy endpoints.

    This keeps the original tile schema intact (no OpenFreeMap conversion)
    and rewrites tile URLs to use local proxy.

    Args:
        style: Original style JSON with _scrape_data
        name: Style identifier

    Returns:
        Transformed style with proxy URLs and _meta
    """
    scrape_data = style.pop("_scrape_data", {})
    style = style.copy()

    original_sprite = scrape_data.get("original_sprite")
    original_glyphs = scrape_data.get("original_glyphs")
    tile_auth = scrape_data.get("tile_auth", {})

    # Store original tile source URLs for proxy lookup
    tile_sources = {}

    # Transform sources to use proxy
    for source_name, source_config in style.get("sources", {}).items():
        source_type = source_config.get("type", "")

        if source_type == "vector":
            # Capture original URL
            original_url = source_config.get("url")
            if not original_url:
                tiles = source_config.get("tiles", [])
                if tiles:
                    original_url = tiles[0]

            if original_url:
                # If it's a TileJSON URL, convert to tile URL template
                if "tiles.json" in original_url or "tilejson.json" in original_url or original_url.endswith("/tiles"):
                    original_url = tilejson_to_tile_url(original_url)
                    print(f"  Converted TileJSON to tile URL for {source_name}")

                tile_sources[source_name] = original_url
                # Replace with proxy URL
                source_config["tiles"] = [f"/api/proxy/tiles/{name}/{source_name}/{{z}}/{{x}}/{{y}}.pbf"]
                source_config.pop("url", None)
                print(f"  Proxied vector source: {source_name}")

        elif source_type == "raster":
            # Capture original URL for raster tiles
            tiles = source_config.get("tiles", [])
            if tiles:
                original_url = tiles[0]
                tile_sources[source_name] = original_url
                # Replace with proxy URL
                source_config["tiles"] = [f"/api/proxy/tiles/{name}/{source_name}/{{z}}/{{x}}/{{y}}.png"]
                print(f"  Proxied raster source: {source_name}")

        elif source_type == "raster-dem":
            # Keep raster-dem sources as-is (terrain) unless from paid provider
            url = source_config.get("url", "")
            if "maptiler.com" in url or "mapbox.com" in url:
                # Convert TileJSON URL to tile URL template
                if "tiles.json" in url or url.endswith("/tiles"):
                    url = tilejson_to_tile_url(url)
                    print(f"  Converted TileJSON to tile URL for {source_name}")

                tile_sources[source_name] = url
                source_config["tiles"] = [f"/api/proxy/tiles/{name}/{source_name}/{{z}}/{{x}}/{{y}}.webp"]
                source_config.pop("url", None)
                print(f"  Proxied raster-dem source: {source_name}")

    # Update sprite to use proxy
    if original_sprite:
        style["sprite"] = f"/api/proxy/sprites/{name}"

    # Update glyphs to use proxy
    if original_glyphs:
        style["glyphs"] = f"/api/proxy/glyphs/{name}/{{fontstack}}/{{range}}.pbf"

    # Determine provider for secrets lookup
    provider = get_provider_for_style(name)

    # Store metadata for runtime proxy (auth referenced by provider, not embedded)
    style["_meta"] = {
        "source": "scraped",
        "original_sprite": original_sprite,
        "original_glyphs": original_glyphs,
        "tile_auth_provider": provider,
        "tile_sources": tile_sources,
    }

    # Save auth to secrets file (separate from style JSON)
    save_auth_to_secrets(name, tile_auth)

    return style


def save_style(style: dict, name: str, output_dir: Path) -> None:
    """Save transformed style to disk.

    Args:
        style: Transformed style JSON
        name: Style identifier
        output_dir: Directory to save to
    """
    output_path = output_dir / f"{name}.json"
    output_path.write_text(json.dumps(style, indent=2))

    # Count layers and sources for summary
    layer_count = len(style.get("layers", []))
    source_count = len(style.get("sources", {}))
    tile_sources = len(style.get("_meta", {}).get("tile_sources", {}))
    auth_provider = style.get("_meta", {}).get("tile_auth_provider", "")

    print(f"  [OK] Saved to: {output_path}")
    print(f"       Layers: {layer_count}, Sources: {source_count}, Proxied: {tile_sources}")
    print(f"       Auth provider: {auth_provider or 'none'}")


def main() -> None:
    """Main entry point."""
    # Setup paths
    base_dir = Path(__file__).parent.parent
    output_dir = base_dir / "styles" / "scraped"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Style Scraper - Tile Proxy Mode")
    print("=" * 60)
    print(f"Output directory: {output_dir}")
    print()

    success_count = 0
    fail_count = 0

    for name, config in SCRAPE_TARGETS.items():
        print("-" * 40)
        style = scrape_style(name, config)

        if style:
            transformed = transform_for_tile_proxy(style, name)
            save_style(transformed, name, output_dir)
            success_count += 1
        else:
            print(f"  [ERROR] Failed to scrape {name}")
            fail_count += 1
        print()

    print("=" * 60)
    print(f"Complete: {success_count} succeeded, {fail_count} failed")
    print("=" * 60)


if __name__ == "__main__":
    main()
