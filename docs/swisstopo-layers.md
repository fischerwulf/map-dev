# Swisstopo4guru Layer Reference

## Summary

The swisstopo4guru maps are **offline packages** (MBTiles, RMaps) designed for mobile apps like OsmAnd - they are NOT a live tile service. However, the same data is available directly from official Swiss government WMTS services.

This document catalogs available layers for future reference.

---

## Base Maps (for comparison)

### Swisstopo Raster Base Maps

| Layer ID | Description | Format | URL |
|----------|-------------|--------|-----|
| `ch.swisstopo.pixelkarte-farbe` | Color topographic map (1:25k) | JPEG | `https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/{z}/{x}/{y}.jpeg` |
| `ch.swisstopo.pixelkarte-grau` | Grayscale topographic map | JPEG | `https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-grau/default/current/3857/{z}/{x}/{y}.jpeg` |
| `ch.swisstopo.swissimage` | Aerial imagery (orthophoto) | JPEG | `https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swissimage/default/current/3857/{z}/{x}/{y}.jpeg` |
| `ch.swisstopo.swisstlm3d-karte-farbe` | Vector-derived color map | PNG | `https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swisstlm3d-karte-farbe/default/current/3857/{z}/{x}/{y}.png` |
| `ch.swisstopo.swisstlm3d-karte-grau` | Vector-derived grayscale map | PNG | `https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swisstlm3d-karte-grau/default/current/3857/{z}/{x}/{y}.png` |

**Note**: `ch.swisstopo.pixelkarte-farbe` is already integrated as toggleable overlay.

### Winter/Ski Specific Base Maps

| Layer ID | Description | Format | URL |
|----------|-------------|--------|-----|
| `ch.swisstopo.pixelkarte-farbe-winter` | Winter edition color topo | JPEG | `https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe-winter/default/current/3857/{z}/{x}/{y}.jpeg` |
| `ch.swisstopo.pixelkarte-grau-winter` | Winter edition grayscale | JPEG | `https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-grau-winter/default/current/3857/{z}/{x}/{y}.jpeg` |

---

## Overlay Layers (for future reference)

### Route Overlays (Swisstopo)

| Layer ID | Description | Notes |
|----------|-------------|-------|
| `ch.swisstopo-karto.skitouren` | Ski touring routes | Changed to vector in late 2024 |
| `ch.swisstopo-karto.schneeschuhrouten` | Snowshoe routes | Changed to vector in late 2024 |
| `ch.swisstopo.swisstlm3d-wanderwege` | Hiking trails | Vector data |
| `ch.swisstopo.hangneigung-ueber_30` | Slopes >30 degrees | Avalanche terrain indicator |

### Avalanche/Terrain (SLF - map.slf.ch)

| Layer ID | Description | URL |
|----------|-------------|-----|
| `ch.slf.terrainclassification-hybr` | Avalanche terrain (hybrid) | `https://map.slf.ch/mapcache/wmts/1.0.0/ch.slf.terrainclassification-hybr/default/GoogleMapsCompatible/{z}/{x}/{y}.png` |
| `ch.slf.terrainclassification-hom` | Avalanche terrain (homogeneous) | `https://map.slf.ch/mapcache/wmts/1.0.0/ch.slf.terrainclassification-hom/default/GoogleMapsCompatible/{z}/{x}/{y}.png` |
| `ch.slf.whiterisk-pistes` | Ski pistes (WhiteRisk) | `https://map.slf.ch/mapcache/wmts/1.0.0/ch.slf.whiterisk-pistes/default/2056/{z}/{x}/{y}.png` |

### Other Useful Overlays

| Layer ID | Description |
|----------|-------------|
| `ch.bafu.wrz-wildruhezonen_portal` | Wildlife rest zones (important for ski touring) |
| `ch.swisstopo.vec25-eisenbahnnetz` | Railway network |

---

## Technical Notes

- **Projection**: Use `3857` (Web Mercator) for MapLibre compatibility
- **Alternative projections**: `2056` (Swiss LV95), `21781` (Swiss LV03), `4326` (WGS84)
- **CORS**: Proxy required - direct browser requests blocked
- **Caching**: Recommended 24h TTL for tiles
- **Coverage**: Swiss layers only cover Switzerland and border regions

## Licensing

- **Swisstopo**: Free for private, non-commercial use (since 2021)
- **SLF layers**: Public access via WhiteRisk
- **Attribution required**: "Source: Federal Office of Topography swisstopo"

## Sources

- [Swisstopo Geoservices](https://www.swisstopo.admin.ch/en/geoservices-with-swisstopo-geodata)
- [GeoAdmin API](https://api3.geo.admin.ch/services/sdiservices.html)
- [WMTS Capabilities](https://wmts.geo.admin.ch/EPSG/3857/1.0.0/WMTSCapabilities.xml)
- [Swisstopo4guru Info](https://info.skitourenguru.ch/index.php/swisstopo4guru)
- [SLF Map Service](https://map.slf.ch/WMTSCapabilities.public.xml)
