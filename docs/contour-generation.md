# Contour Line Generation

This document describes how to generate contour lines for the topo map style editor.

## Overview

Contour lines are generated from SRTM (Shuttle Radar Topography Mission) elevation data and stored as PMTiles vector tiles. The generation pipeline is maintained in a separate repository.

## Quick Start

If you have a pre-generated `contours.pmtiles` file:

1. Copy it to `static/tiles/contours.pmtiles`
2. The custom style already includes contour layers

## Generation Pipeline

The contour generation uses:

- **SRTM 90m DEM**: Digital elevation model from CGIAR
- **GDAL**: Contour extraction from elevation data
- **Tippecanoe**: Vector tile generation
- **PMTiles**: Single-file tile archive format

### Pipeline Steps

```
SRTM .hgt files (elevation data)
        ↓
    gdal_merge.py (merge tiles)
        ↓
    contour.tif (composite DEM)
        ↓
    gdal_contour (extract contours at 10m intervals)
        ↓
    contours.geojson (with elevation property)
        ↓
    tippecanoe (generate vector tiles)
        ↓
    contours.mbtiles
        ↓
    pmtiles convert
        ↓
    contours.pmtiles
```

### Contour Classification

Contours are classified by zoom level visibility:

| Interval | Min Zoom | Description |
|----------|----------|-------------|
| 100m | 10 | Index lines (major contours) |
| 20m | 12 | Intermediate contours |
| 10m | 14 | Detail contours |

## Using Contours in Styles

### Source Definition

```json
{
  "sources": {
    "contours": {
      "type": "vector",
      "url": "pmtiles:///static/tiles/contours.pmtiles"
    }
  }
}
```

### Layer Examples

**100m contours (index lines):**

```json
{
  "id": "contour-100m",
  "type": "line",
  "source": "contours",
  "source-layer": "contours",
  "minzoom": 10,
  "filter": ["==", ["%", ["get", "elev"], 100], 0],
  "paint": {
    "line-color": "#8B4513",
    "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.8, 14, 1.5]
  }
}
```

**Contour labels:**

```json
{
  "id": "contour-label",
  "type": "symbol",
  "source": "contours",
  "source-layer": "contours",
  "minzoom": 12,
  "filter": ["==", ["%", ["get", "elev"], 100], 0],
  "layout": {
    "symbol-placement": "line",
    "text-field": "{elev}",
    "text-font": ["Noto Sans Italic"],
    "text-size": 10
  },
  "paint": {
    "text-color": "#8B4513",
    "text-halo-color": "rgba(255,255,255,0.8)",
    "text-halo-width": 1
  }
}
```

## Properties

Each contour line feature has:

| Property | Type | Description |
|----------|------|-------------|
| `elev` | integer | Elevation in meters above sea level |

## Data Sources

### SRTM 90m

- **Source**: https://srtm.csi.cgiar.org/
- **Resolution**: 90m (3 arc-seconds)
- **Coverage**: 60N to 60S latitude
- **Format**: HGT (height) files

### Alternative Sources

For higher resolution (30m), consider:

- **Copernicus DEM**: 30m global coverage
- **ASTER GDEM**: 30m global coverage
- **National DEMs**: Country-specific high-resolution data

## File Size Considerations

PMTiles file sizes depend on:

- Geographic coverage
- Contour interval
- Zoom level range

Typical sizes:

| Coverage | Size |
|----------|------|
| Alps (10-14 zoom, 10m interval) | ~1.5 GB |
| Single country | 100-500 MB |
| Regional (small area) | 10-100 MB |

## Troubleshooting

### Contours not visible

1. Check that `contours.pmtiles` exists in `static/tiles/`
2. Verify PMTiles protocol is registered in map-grid.js
3. Check browser console for loading errors
4. Verify zoom level is within layer minzoom/maxzoom

### Jagged contours

- Use higher resolution DEM source
- Apply smoothing during contour generation
- Reduce tippecanoe simplification

### Missing contours at high zoom

- Ensure tippecanoe maxzoom matches layer maxzoom
- Check that features aren't being dropped by size filter

## References

- [GDAL Contour](https://gdal.org/programs/gdal_contour.html)
- [Tippecanoe](https://github.com/felt/tippecanoe)
- [PMTiles Specification](https://github.com/protomaps/PMTiles)
- [SRTM Data](https://srtm.csi.cgiar.org/)
