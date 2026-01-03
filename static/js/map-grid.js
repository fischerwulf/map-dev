/**
 * Map Grid - Synchronized MapLibre GL JS map comparison
 */

// Default view (Alps/Switzerland)
const DEFAULT_CENTER = [8.2275, 46.8182];
const DEFAULT_ZOOM = 10;

// Swiss Topo raster source
const SWISS_TOPO_SOURCE = {
    type: 'raster',
    tiles: ['/api/proxy/swisstopo/{z}/{x}/{y}.jpeg'],
    tileSize: 256,
    attribution: 'swisstopo',
    maxzoom: 18,
};

// State
let maps = [];
let availableStyles = [];
let syncEnabled = true;
let gridSize = 2;
let isSyncing = false;

// DOM Elements
const mapGrid = document.getElementById('map-grid');
const syncCheckbox = document.getElementById('sync-maps');
const gridSizeSelect = document.getElementById('grid-size');
const resetViewBtn = document.getElementById('reset-view');
const coordDisplay = document.getElementById('coord-display');
const cellTemplate = document.getElementById('map-cell-template');

/**
 * Initialize the application
 */
async function init() {
    // Register PMTiles protocol for local vector tiles
    if (typeof pmtiles !== 'undefined') {
        const protocol = new pmtiles.Protocol();
        maplibregl.addProtocol('pmtiles', protocol.tile);
        console.log('[INFO] PMTiles protocol registered');
    }

    // Load available styles
    await loadStyles();

    // Restore preferences
    restorePreferences();

    // Setup event listeners
    setupEventListeners();

    // Create initial grid
    createGrid(gridSize);

    // Parse URL hash for initial view
    parseUrlHash();
}

/**
 * Load available styles from the API
 */
async function loadStyles() {
    try {
        const response = await fetch('/api/styles');
        availableStyles = await response.json();
        console.log('[INFO] Loaded styles:', availableStyles);
    } catch (error) {
        console.error('[ERROR] Failed to load styles:', error);
        // Fallback to basic styles
        availableStyles = [
            { name: 'liberty', source: 'openfreemap', type: 'native' },
            { name: 'bright', source: 'openfreemap', type: 'native' },
            { name: 'positron', source: 'openfreemap', type: 'native' },
            { name: 'custom', source: 'local', type: 'editable' },
        ];
    }
}

/**
 * Setup global event listeners
 */
function setupEventListeners() {
    // Sync toggle
    syncCheckbox.addEventListener('change', (e) => {
        syncEnabled = e.target.checked;
        savePreferences();
    });

    // Grid size change
    gridSizeSelect.addEventListener('change', (e) => {
        gridSize = parseInt(e.target.value);
        createGrid(gridSize);
        savePreferences();
    });

    // Reset view
    resetViewBtn.addEventListener('click', () => {
        const view = { center: DEFAULT_CENTER, zoom: DEFAULT_ZOOM };
        maps.forEach(mapObj => {
            if (mapObj.map) {
                mapObj.map.jumpTo(view);
            }
        });
        updateUrlHash(DEFAULT_CENTER, DEFAULT_ZOOM);
    });

    // Update URL hash on window hash change
    window.addEventListener('hashchange', parseUrlHash);
}

/**
 * Create the map grid
 */
function createGrid(size) {
    // Store current map states
    const currentStates = maps.map(m => ({
        style: m.styleName,
        swissTopo: m.swissTopoEnabled,
        enabled: m.enabled,
    }));

    // Clear existing maps
    maps.forEach(m => {
        if (m.map) {
            m.map.remove();
        }
    });
    maps = [];

    // Clear grid
    mapGrid.innerHTML = '';
    mapGrid.className = `grid-${size}`;

    // Create cells
    const totalCells = size * size;
    for (let i = 0; i < totalCells; i++) {
        const cell = createMapCell(i);
        mapGrid.appendChild(cell);

        // Restore state if available
        const prevState = currentStates[i];
        if (prevState && prevState.enabled !== false) {
            maps[i].enabled = true;
            if (prevState.style) {
                setMapStyle(i, prevState.style);
            }
            if (prevState.swissTopo) {
                toggleSwissTopo(i, true);
            }
        }
    }
}

/**
 * Create a single map cell
 */
function createMapCell(index) {
    const template = cellTemplate.content.cloneNode(true);
    const cell = template.querySelector('.map-cell');
    cell.dataset.cellIndex = index;

    // Populate style selector
    const styleSelect = cell.querySelector('.style-select');
    populateStyleSelect(styleSelect);

    // Setup cell event listeners
    const toggleBtn = cell.querySelector('.cell-toggle');
    const swissTopoCheckbox = cell.querySelector('.swiss-topo-checkbox');

    styleSelect.addEventListener('change', (e) => {
        setMapStyle(index, e.target.value);
        savePreferences();
    });

    toggleBtn.addEventListener('click', () => {
        toggleCell(index);
        savePreferences();
    });

    swissTopoCheckbox.addEventListener('change', (e) => {
        toggleSwissTopo(index, e.target.checked);
        savePreferences();
    });

    // Initialize map state
    maps[index] = {
        map: null,
        container: cell.querySelector('.map-container'),
        styleSelect: styleSelect,
        styleName: null,
        swissTopoEnabled: false,
        swissTopoCheckbox: swissTopoCheckbox,
        enabled: true,
        cell: cell,
    };

    return cell;
}

/**
 * Populate a style selector with available styles
 */
function populateStyleSelect(select) {
    // Group styles by source
    const groups = {
        'OpenFreeMap': [],
        'Scraped': [],
        'Local': [],
    };

    availableStyles.forEach(style => {
        const option = document.createElement('option');
        option.value = style.name;
        option.textContent = formatStyleName(style.name);
        option.dataset.source = style.source;

        if (style.source === 'openfreemap') {
            groups['OpenFreeMap'].push(option);
        } else if (style.source === 'scraped') {
            groups['Scraped'].push(option);
        } else {
            groups['Local'].push(option);
        }
    });

    // Add grouped options
    for (const [groupName, options] of Object.entries(groups)) {
        if (options.length > 0) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = groupName;
            options.forEach(opt => optgroup.appendChild(opt));
            select.appendChild(optgroup);
        }
    }
}

/**
 * Format style name for display
 */
function formatStyleName(name) {
    return name
        .split('-')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

/**
 * Set the style for a map cell
 */
async function setMapStyle(index, styleName) {
    const mapObj = maps[index];
    if (!mapObj || !styleName) return;

    mapObj.styleName = styleName;
    mapObj.styleSelect.value = styleName;

    // Get current view from any existing map
    let currentView = getSharedView();

    // Build style URL
    const styleUrl = `/api/styles/${styleName}`;

    try {
        // Remove existing map if any
        if (mapObj.map) {
            mapObj.map.remove();
            mapObj.map = null;
        }

        // Create new map
        const map = new maplibregl.Map({
            container: mapObj.container,
            style: styleUrl,
            center: currentView.center,
            zoom: currentView.zoom,
            bearing: currentView.bearing || 0,
            pitch: currentView.pitch || 0,
        });

        mapObj.map = map;

        // Setup sync events
        map.on('move', () => {
            if (!isSyncing && syncEnabled) {
                syncMapsFrom(map);
            }
            updateCoordinateDisplay(map);
        });

        map.on('moveend', () => {
            updateUrlHash(map.getCenter().toArray(), map.getZoom());
        });

        // Re-add Swiss Topo layer if it was enabled
        map.on('load', () => {
            if (mapObj.swissTopoEnabled) {
                addSwissTopoLayer(map);
            }
        });

        console.log(`[INFO] Map ${index} loaded with style: ${styleName}`);
    } catch (error) {
        console.error(`[ERROR] Failed to load style ${styleName}:`, error);
    }
}

/**
 * Toggle a cell on/off
 */
function toggleCell(index) {
    const mapObj = maps[index];
    if (!mapObj) return;

    mapObj.enabled = !mapObj.enabled;
    mapObj.cell.classList.toggle('disabled', !mapObj.enabled);

    if (!mapObj.enabled && mapObj.map) {
        mapObj.map.remove();
        mapObj.map = null;
        mapObj.styleName = null;
        mapObj.styleSelect.value = '';
    }
}

/**
 * Toggle Swiss Topo overlay for a map
 */
function toggleSwissTopo(index, enabled) {
    const mapObj = maps[index];
    if (!mapObj) return;

    mapObj.swissTopoEnabled = enabled;
    mapObj.swissTopoCheckbox.checked = enabled;

    if (mapObj.map) {
        if (enabled) {
            addSwissTopoLayer(mapObj.map);
        } else {
            removeSwissTopoLayer(mapObj.map);
        }
    }
}

/**
 * Add Swiss Topo raster layer to a map
 */
function addSwissTopoLayer(map) {
    if (!map.getSource('swiss-topo')) {
        map.addSource('swiss-topo', SWISS_TOPO_SOURCE);
    }

    if (!map.getLayer('swiss-topo-layer')) {
        // Find the first symbol layer to insert before
        const layers = map.getStyle().layers;
        let firstSymbolId = null;
        for (const layer of layers) {
            if (layer.type === 'symbol') {
                firstSymbolId = layer.id;
                break;
            }
        }

        map.addLayer({
            id: 'swiss-topo-layer',
            type: 'raster',
            source: 'swiss-topo',
            paint: {
                'raster-opacity': 0.6,
            },
        }, firstSymbolId);
    }
}

/**
 * Remove Swiss Topo layer from a map
 */
function removeSwissTopoLayer(map) {
    if (map.getLayer('swiss-topo-layer')) {
        map.removeLayer('swiss-topo-layer');
    }
    if (map.getSource('swiss-topo')) {
        map.removeSource('swiss-topo');
    }
}

/**
 * Get shared view from any active map
 */
function getSharedView() {
    for (const mapObj of maps) {
        if (mapObj && mapObj.map) {
            return {
                center: mapObj.map.getCenter().toArray(),
                zoom: mapObj.map.getZoom(),
                bearing: mapObj.map.getBearing(),
                pitch: mapObj.map.getPitch(),
            };
        }
    }
    return {
        center: DEFAULT_CENTER,
        zoom: DEFAULT_ZOOM,
        bearing: 0,
        pitch: 0,
    };
}

/**
 * Sync all maps to match the source map's view
 */
function syncMapsFrom(sourceMap) {
    if (isSyncing) return;

    isSyncing = true;

    const center = sourceMap.getCenter();
    const zoom = sourceMap.getZoom();
    const bearing = sourceMap.getBearing();
    const pitch = sourceMap.getPitch();

    maps.forEach(mapObj => {
        if (mapObj && mapObj.map && mapObj.map !== sourceMap) {
            mapObj.map.jumpTo({ center, zoom, bearing, pitch });
        }
    });

    isSyncing = false;
}

/**
 * Update the coordinate display
 */
function updateCoordinateDisplay(map) {
    const center = map.getCenter();
    const zoom = map.getZoom();
    coordDisplay.textContent = `${zoom.toFixed(2)} / ${center.lat.toFixed(5)} / ${center.lng.toFixed(5)}`;
}

/**
 * Update URL hash with current view
 */
function updateUrlHash(center, zoom) {
    const hash = `#${zoom.toFixed(2)}/${center[1].toFixed(5)}/${center[0].toFixed(5)}`;
    if (window.location.hash !== hash) {
        history.replaceState(null, '', hash);
    }
}

/**
 * Parse URL hash and set view
 */
function parseUrlHash() {
    const hash = window.location.hash.slice(1);
    if (!hash) return;

    const parts = hash.split('/');
    if (parts.length >= 3) {
        const zoom = parseFloat(parts[0]);
        const lat = parseFloat(parts[1]);
        const lng = parseFloat(parts[2]);

        if (!isNaN(zoom) && !isNaN(lat) && !isNaN(lng)) {
            const view = { center: [lng, lat], zoom };
            maps.forEach(mapObj => {
                if (mapObj && mapObj.map) {
                    mapObj.map.jumpTo(view);
                }
            });
        }
    }
}

/**
 * Save preferences to localStorage
 */
function savePreferences() {
    const prefs = {
        syncEnabled,
        gridSize,
        cells: maps.map(m => ({
            style: m.styleName,
            swissTopo: m.swissTopoEnabled,
            enabled: m.enabled,
        })),
    };
    localStorage.setItem('topomap-prefs', JSON.stringify(prefs));
}

/**
 * Restore preferences from localStorage
 */
function restorePreferences() {
    try {
        const prefs = JSON.parse(localStorage.getItem('topomap-prefs'));
        if (prefs) {
            syncEnabled = prefs.syncEnabled !== false;
            gridSize = prefs.gridSize || 2;

            syncCheckbox.checked = syncEnabled;
            gridSizeSelect.value = gridSize;
        }
    } catch (error) {
        console.warn('[WARN] Failed to restore preferences:', error);
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', init);
