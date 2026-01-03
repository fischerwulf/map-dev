# Architecture

## Overview

Topo Map is a FastAPI web application for developing custom map styles. It provides:

1. A grid-based UI for comparing multiple map styles side-by-side
2. A proxy layer for fetching tiles from various providers
3. A caching system to reduce external requests
4. Style scraping capabilities to capture styles from public demos

```
┌──────────────────────────────────────────────────────────────┐
│                        Browser                                │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              MapLibre GL JS (map-grid.js)              │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│                    FastAPI Application                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  pages.py    │  │   api.py     │  │  style_scraper   │   │
│  │  (routes)    │  │  (proxy/API) │  │  (style loading) │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│                              │                                │
│                    ┌─────────┴─────────┐                     │
│                    │    tile_cache     │                     │
│                    │   (file-based)    │                     │
│                    └───────────────────┘                     │
└──────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │OpenFreeMap│   │ MapTiler │   │Swisstopo │
        │  (tiles)  │   │ (proxy)  │   │ (proxy)  │
        └──────────┘   └──────────┘   └──────────┘
```

---

## Components

### Frontend (`static/js/map-grid.js`)

- Grid layout manager (1x1, 2x2, 3x3, 4x4)
- Synchronized map navigation (pan, zoom, rotation)
- Style selector per map cell
- PMTiles protocol support for local tiles
- URL hash state management
- LocalStorage preferences

### FastAPI Application (`src/topo_map/`)

#### `main.py`
Entry point. Mounts static files and includes routers.

#### `routes/pages.py`
Simple page routes. Currently only serves the index page.

#### `routes/api.py`
Core API functionality:

- **Style endpoints**: List and serve map styles
- **Tile proxy**: Fetch tiles from external providers with auth injection
- **Asset proxy**: Proxy sprites and font glyphs
- **Cache management**: Stats and invalidation

#### `style_scraper.py`
Style loading and transformation:

- Fetches OpenFreeMap styles from remote
- Loads custom and scraped styles from disk
- Transforms styles for proxy usage

#### `tile_cache.py`
File-based tile cache:

- Directory structure: `cache/{key}/{z}/{x}/{y}.{ext}`
- Metadata files for TTL and headers
- Default 24-hour TTL

---

## Data Flow

### Style Loading

```
1. Browser requests /api/styles/{name}
2. api.py determines style source:
   - OpenFreeMap: fetch from tiles.openfreemap.org
   - Custom: load from styles/custom.json
   - Scraped: load from styles/scraped/
   - Raster: load from styles/raster/
3. For scraped styles, proxy URLs are rewritten
4. Style JSON returned to browser
```

### Tile Proxying

```
1. Browser requests /api/proxy/tiles/{style}/{source}/{z}/{x}/{y}.pbf
2. api.py checks tile_cache for cached tile
3. If cache miss:
   a. Load tile source URL from style's _meta
   b. Load auth from secrets.json based on provider
   c. Build URL with auth params
   d. Fetch from upstream provider
   e. Cache response
4. Return tile with X-Cache header
```

### Style Scraping

```
1. scrape_styles.py launches headless browser
2. Navigates to target page (MapTiler, Tracestrack, etc.)
3. Intercepts network requests for:
   - style.json (the full style definition)
   - Tile requests (to capture API keys)
4. Transforms style:
   - Rewrites tile URLs to use local proxy
   - Rewrites sprite/glyph URLs to use local proxy
   - Stores original URLs in _meta
5. Saves auth to secrets.json
6. Saves style to styles/scraped/
```

---

## File Locations

| Path | Description |
|------|-------------|
| `styles/custom.json` | User-editable custom style |
| `styles/scraped/*.json` | Scraped external styles |
| `styles/raster/*.json` | Simple raster tile styles |
| `static/tiles/*.pmtiles` | Local vector tiles (gitignored) |
| `cache/tiles/` | Tile cache directory (gitignored) |
| `secrets.json` | API keys (gitignored) |

---

## Authentication

API keys are managed through two mechanisms:

1. **secrets.json**: Primary source of auth credentials
   - Loaded at application startup
   - Keyed by provider name (maptiler, tracestrack, mapbox)

2. **Style _meta**: Provider reference
   - `tile_auth_provider` field references secrets.json key
   - Fall back to embedded `tile_auth` for backwards compatibility

### Adding a New Provider

1. Add to `PROVIDER_MAP` in `scripts/scrape_styles.py`
2. Add credentials to `secrets.json`
3. Run scraper to capture style

---

## Caching Strategy

### Tile Cache
- **Location**: `cache/tiles/{cache_key}/{z}/{x}/{y}.{ext}`
- **TTL**: 24 hours (configurable)
- **Key format**: `{style_name}_{source_name}`
- **Metadata**: `.meta` JSON files alongside tiles

### Style Cache
- Custom style: no-cache headers (always fresh)
- OpenFreeMap styles: cached by browser (public, max-age=3600)
- Scraped styles: cached by browser (public, max-age=3600)

---

## External Services

| Service | Usage | Auth |
|---------|-------|------|
| OpenFreeMap | Vector tiles, sprites, fonts | None (free) |
| MapTiler | Vector tiles, terrain DEM | API key |
| Tracestrack | Vector tiles, contours | API key |
| Swisstopo | Raster tiles, vector tiles | None (free) |
| basemap.at | Raster tiles, vector tiles | None (free) |
| OpenTopoMap | Raster tiles | None (free) |
| Bayern LDBV | Raster tiles | None (free) |

---

## Extending

### Adding a New Raster Style

1. Create `styles/raster/{name}.json`:
   ```json
   {
     "version": 8,
     "sources": {
       "raster": {
         "type": "raster",
         "tiles": ["https://example.com/{z}/{x}/{y}.png"],
         "tileSize": 256
       }
     },
     "layers": [
       {"id": "raster", "type": "raster", "source": "raster"}
     ]
   }
   ```

### Adding a New Proxy Endpoint

1. Add route in `api.py`
2. Handle coordinate order if non-standard
3. Add to `list_available_styles()` in `style_scraper.py`

### Adding Contour Overlay

1. Generate PMTiles file (see contour-generation.md)
2. Place in `static/tiles/`
3. Add source and layers to `custom.json`:
   ```json
   "sources": {
     "contours": {
       "type": "vector",
       "url": "pmtiles:///static/tiles/contours.pmtiles"
     }
   }
   ```
