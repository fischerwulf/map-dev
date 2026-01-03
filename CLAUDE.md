# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run development server (auto-reload on port 8000)
uv run python -m topo_map.main

# Scrape styles from public map demos (requires playwright)
uv run playwright install chromium
uv run scripts/scrape_styles.py
```

## Architecture

FastAPI backend + MapLibre GL JS frontend for developing custom topographic map styles.

**Key data flow:**
- Browser loads style from `/api/styles/{name}`
- Styles reference tile/sprite/glyph URLs pointing to local proxy endpoints
- Proxy endpoints (`/api/proxy/*`) fetch from upstream providers, injecting auth from `secrets.json`
- Tiles are cached in `cache/tiles/` with 24h TTL

**Authentication system:**
- API keys stored in `secrets.json` (gitignored), keyed by provider name
- Scraped styles reference provider via `_meta.tile_auth_provider` field
- `api.py` loads secrets at startup and injects into proxy requests

**Style sources:**
- `styles/custom.json` - Editable custom style (served with no-cache)
- `styles/scraped/*.json` - Captured from MapTiler/Tracestrack via headless browser
- `styles/raster/*.json` - Simple raster tile wrappers
- OpenFreeMap styles fetched live from tiles.openfreemap.org

## Key Files

| File | Purpose |
|------|---------|
| `src/topo_map/routes/api.py` | All proxy endpoints, style serving, cache management |
| `src/topo_map/style_scraper.py` | Style loading, transformation, OpenFreeMap fetching |
| `scripts/scrape_styles.py` | Playwright-based style capture with API key extraction |
| `static/js/map-grid.js` | Frontend grid UI, map synchronization, PMTiles support |
| `styles/custom.json` | Main editable style (~6k lines, MapLibre style spec v8) |

## Adding New Providers

1. Add target config to `SCRAPE_TARGETS` in `scripts/scrape_styles.py`
2. Add provider to `PROVIDER_MAP` in same file
3. Run scraper - keys auto-saved to `secrets.json`, style to `styles/scraped/`
4. If needed, add proxy endpoint in `api.py` and style entry in `style_scraper.py`
