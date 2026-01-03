# Topo Map Style Editor

Development environment for custom topographic map styles using OpenFreeMap vector tiles.

## Features

- **Side-by-side comparison**: Compare up to 16 map styles in a synchronized grid
- **Custom style editing**: Edit `styles/custom.json` with live reload
- **Tile proxying**: Proxy tiles from MapTiler, Tracestrack, Swisstopo, basemap.at
- **Style scraping**: Capture styles from public map demos with API key extraction
- **Local contours**: PMTiles-based contour line overlay

## Quick Start

```bash
# Install dependencies
uv sync

# Set up API keys (optional - for scraped styles)
cp secrets.json.example secrets.json
# Edit secrets.json with your API keys

# Start the development server
uv run python -m topo_map.main

# Open in browser
open http://localhost:8000
```

## Project Structure

```text
topo_map/
├── src/topo_map/           # FastAPI application
│   ├── main.py             # Entry point
│   ├── routes/
│   │   ├── api.py          # Style and tile proxy endpoints
│   │   └── pages.py        # Page routes
│   ├── style_scraper.py    # Style loading and transformation
│   └── tile_cache.py       # File-based tile cache
├── scripts/
│   └── scrape_styles.py    # Scrape styles from public demos
├── styles/
│   ├── custom.json         # Your custom style (edit this!)
│   ├── scraped/            # Scraped external styles
│   └── raster/             # Simple raster tile styles
├── static/
│   ├── css/style.css
│   ├── js/map-grid.js
│   └── tiles/              # Local PMTiles (gitignored)
├── templates/
│   └── index.html          # Grid comparison UI
└── docs/
    ├── architecture.md     # System architecture
    └── contour-generation.md
```

## Available Styles

### OpenFreeMap (Built-in)

- `liberty` - Default OSM style
- `bright` - Bright colored style
- `positron` - Light minimal style

### Custom

- `custom` - Your editable style at `styles/custom.json`

### Scraped (Requires API Keys)

- `maptiler-outdoor` - MapTiler outdoor map
- `maptiler-topo` - MapTiler topographic
- `tracestrack-topo` - Tracestrack topo style

### Raster

- `opentopomap` - OpenTopoMap (public)
- `swisstopo` - Swiss topographic map
- `basemap-at-*` - Austrian basemap variants
- `bayern-topo` - Bavarian topographic map

### Remote Vector

- `swisstopo-base` - Swiss vector base map
- `basemap-at-vector` - Austrian vector basemap

## Working with Custom Styles

Edit `styles/custom.json` to create your custom topographic style. The file is based on OpenFreeMap's liberty style and uses:

- **openmaptiles**: Vector tiles from OpenFreeMap
- **terrain-dem**: DEM tiles for hillshading
- **contours**: Local PMTiles contour lines (if available)

Changes are reflected immediately when you reload the map (the custom style is served with no-cache headers).

## Adding Scraped Styles

To capture a new style from a public map demo:

1. Add the target to `SCRAPE_TARGETS` in `scripts/scrape_styles.py`
2. Run the scraper:
   ```bash
   uv run scripts/scrape_styles.py
   ```
3. API keys are automatically saved to `secrets.json`
4. The style is saved to `styles/scraped/`

## API Endpoints

| Endpoint                                               | Description          |
| ------------------------------------------------------ | -------------------- |
| `GET /`                                                | Grid comparison UI   |
| `GET /api/styles`                                      | List available styles |
| `GET /api/styles/{name}`                               | Get style JSON       |
| `GET /api/proxy/tiles/{style}/{source}/{z}/{x}/{y}.*`  | Proxy tiles          |
| `GET /api/proxy/sprites/{style}*`                      | Proxy sprite sheets  |
| `GET /api/proxy/glyphs/{style}/{font}/{range}`         | Proxy font glyphs    |
| `GET /api/cache/stats`                                 | Cache statistics     |
| `DELETE /api/cache/{key}`                              | Invalidate cache     |

## Contour Lines

Contour lines are provided via a PMTiles file at `static/tiles/contours.pmtiles`. This file is not tracked in git due to its size.

See [docs/contour-generation.md](docs/contour-generation.md) for instructions on generating contours.

## Configuration

### Environment Variables

None required. API keys are loaded from `secrets.json`.

### secrets.json

```json
{
  "maptiler": { "key": "YOUR_KEY" },
  "tracestrack": { "key": "YOUR_KEY" },
  "mapbox": { "access_token": "YOUR_TOKEN" }
}
```

## Development

```bash
# Run with auto-reload
uv run python -m topo_map.main

# Scrape styles (requires playwright)
uv run playwright install chromium
uv run scripts/scrape_styles.py
```

## License

TBD

## Acknowledgments

- [OpenFreeMap](https://openfreemap.org/) - Free vector tiles
- [MapLibre GL JS](https://maplibre.org/) - Open-source map rendering
- [PMTiles](https://protomaps.com/docs/pmtiles) - Single-file tile archives
