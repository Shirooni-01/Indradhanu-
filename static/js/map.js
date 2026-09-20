/**
 * PROJECT INDRADHANU - GIS TACTICAL SURVEILLANCE MAP (LEAFLET.JS)
 * Features: Satellite Tiles, Dynamic Radar Scanning Cone, Village Perimeter, Threat Markers
 */

// Multi-Camera Station Network (Tadoba-Andhari Buffer Zone Perimeter)
const CAMERA_STATIONS = {
    'NODE-01': {
        code: 'NODE-01',
        name: 'Tadoba North Perimeter Tower',
        sector: 'Sector 1 (Rampur Buffer)',
        coords: [21.1458, 79.0882],
        heading: 145,
        battery: 88,
        status: 'ONLINE_ACTIVE',
        color: '#06b6d4',
        camType: 'Thermal IR (MLX90640)'
    },
    'NODE-02': {
        code: 'NODE-02',
        name: 'Rampur East Buffer Tower',
        sector: 'Sector 1 (Rampur Buffer)',
        coords: [21.1410, 79.0940],
        heading: 210,
        battery: 94,
        status: 'STANDBY',
        color: '#f59e0b',
        camType: 'Thermal IR + Night Vision'
    },
    'NODE-03': {
        code: 'NODE-03',
        name: 'Shivpuri West Fringe Tower',
        sector: 'Sector 2 (Shivpuri Fringe)',
        coords: [21.1495, 79.0790],
        heading: 90,
        battery: 79,
        status: 'STANDBY',
        color: '#10b981',
        camType: 'Thermal IR (Seek Compact)'
    }
};

let activeStationCode = 'NODE-01';
let currentRadarOrigin = [21.1458, 79.0882];
let stationMarkers = {};
const VILLAGE_COORDS = [21.1390, 79.0830]; // Rampur Village Center

let map = null;
let satLayer = null;
let osmLayer = null;
let radarConePolygon = null;
let sightingMarkersGroup = null;

// Current radar orientation (matches physical rotator heading)
let currentHeadingAngle = 145; // Degrees
const SCAN_RANGE_METERS = 450; // Camera thermal sensing distance
const SCAN_FOV_DEG = 60; // Field of View angle

function initTacticalMap() {
    // 1. Initialize Map
    map = L.map('gis-map', {
        center: [21.1435, 79.0860],
        zoom: 15,
        zoomControl: false,
        attributionControl: false
    });

    // Custom Zoom control position
    L.control.zoom({ position: 'topright' }).addTo(map);

    // 2. Tile Layers: Esri World Imagery (Satellite) & CartoDB Dark Matter
    satLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 18,
        attribution: 'Esri World Imagery'
    }).addTo(map);

    osmLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        maxZoom: 19,
        attribution: 'CartoDB'
    });

    // 3. Draw Village Buffer Zone (Orange Warning Ring)
    const villageCircle = L.circle(VILLAGE_COORDS, {
        color: '#f59e0b',
        fillColor: '#f59e0b',
        fillOpacity: 0.12,
        weight: 2,
        dashArray: '6, 6',
        radius: 650
    }).addTo(map);
    villageCircle.bindTooltip("Rampur Village Safety Zone (650m)", { permanent: true, direction: "center", className: "map-label-village" });

    // Village center icon
    const villageIcon = L.divIcon({
        className: 'custom-map-icon',
        html: `<div style="background:#f59e0b; color:#000; padding:3px 6px; border-radius:4px; font-weight:700; font-size:10px; font-family:sans-serif; white-space:nowrap;"><i class="fa-solid fa-house-chimney"></i> Rampur Village</div>`,
        iconSize: [100, 24],
        iconAnchor: [50, 12]
    });
    L.marker(VILLAGE_COORDS, { icon: villageIcon }).addTo(map);

    // 4. Draw Forest Fringe Boundary Line (Green)
    const forestBoundary = L.polyline([
        [21.1520, 79.0750],
        [21.1490, 79.0820],
        [21.1470, 79.0920],
        [21.1430, 79.0980],
        [21.1380, 79.1020]
    ], {
        color: '#10b981',
        weight: 3,
        opacity: 0.8,
        dashArray: '8, 8'
    }).addTo(map);
    forestBoundary.bindTooltip("Protected Forest Perimeter", { sticky: true, className: "map-label-forest" });

    // 5. Draw All Camera Tower Stations
    Object.keys(CAMERA_STATIONS).forEach(code => {
        const st = CAMERA_STATIONS[code];
        const color = st.color || '#06b6d4';
        
        const towerIcon = L.divIcon({
            className: `tower-icon-wrapper tower-${code.toLowerCase()}`,
            html: `
                <div style="position:relative; width:34px; height:34px; background:rgba(0,0,0,0.75); border:2px solid ${color}; border-radius:50%; display:flex; align-items:center; justify-content:center; box-shadow:0 0 12px ${color}; cursor:pointer;">
                    <i class="fa-solid fa-tower-broadcast" style="color:${color}; font-size:13px;"></i>
                    <div style="position:absolute; bottom:-16px; font-family:'JetBrains Mono',monospace; font-size:9px; font-weight:700; color:#fff; background:#000; padding:1px 4px; border:1px solid ${color}; border-radius:2px; white-space:nowrap;">
                        ${code}
                    </div>
                </div>
            `,
            iconSize: [34, 34],
            iconAnchor: [17, 17]
        });

        const marker = L.marker(st.coords, { icon: towerIcon }).addTo(map);
        marker.bindPopup(`
            <div style="font-family:'JetBrains Mono', monospace; font-size:12px; color:#0f172a; min-width:180px;">
                <strong style="color:${color};"><i class="fa-solid fa-tower-broadcast"></i> ${st.code}: ${st.name}</strong><br>
                <span style="font-size:11px; color:#475569;">Sector: ${st.sector}</span><br>
                <span>Status: <b>${st.status}</b></span><br>
                <span>Battery: <b>${st.battery}% Solar</b></span><br>
                <span>Heading: <b>${st.heading}°</b></span><br>
                <div style="margin-top:8px;">
                    <button onclick="window.switchMapStation('${code}')" style="background:#0f172a; color:#fff; border:1px solid #38bdf8; padding:4px 8px; font-size:10px; cursor:pointer; border-radius:2px; width:100%; font-family:'JetBrains Mono',monospace;">
                        <i class="fa-solid fa-crosshairs"></i> Select Station & Aim Radar
                    </button>
                </div>
            </div>
        `);

        marker.on('click', () => {
            switchActiveStation(code);
        });

        stationMarkers[code] = marker;
    });

    // Group for sighting markers
    sightingMarkersGroup = L.layerGroup().addTo(map);

    // 6. Draw Initial Radar Scanning Cone on default station (NODE-01)
    updateRadarCone(currentHeadingAngle, currentRadarOrigin);

    // Bind Layer Toggle Buttons
    document.getElementById('btn-layer-sat')?.addEventListener('click', function() {
        if (!map.hasLayer(satLayer)) {
            map.removeLayer(osmLayer);
            map.addLayer(satLayer);
            this.classList.add('active');
            document.getElementById('btn-layer-osm').classList.remove('active');
        }
    });

    document.getElementById('btn-layer-osm')?.addEventListener('click', function() {
        if (!map.hasLayer(osmLayer)) {
            map.removeLayer(satLayer);
            map.addLayer(osmLayer);
            this.classList.add('active');
            document.getElementById('btn-layer-sat').classList.remove('active');
        }
    });

    document.getElementById('btn-recenter')?.addEventListener('click', function() {
        map.setView([21.1435, 79.0860], 15, { animate: true });
    });

    setTimeout(() => {
        if (map) map.invalidateSize();
    }, 250);

    window.addEventListener('resize', () => {
        if (map) map.invalidateSize();
    });
}

/**
 * Calculates GPS coordinates given a starting point, distance (meters), and bearing (degrees).
 */
function destinationPoint(lat, lon, distanceMeters, bearingDegrees) {
    const R = 6378137; // Earth's radius in meters
    const d = distanceMeters / R;
    const brng = bearingDegrees * Math.PI / 180;
    const lat1 = lat * Math.PI / 180;
    const lon1 = lon * Math.PI / 180;

    const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(brng));
    const lon2 = lon1 + Math.atan2(Math.sin(brng) * Math.sin(d) * Math.cos(lat1), Math.cos(d) - Math.sin(lat1) * Math.sin(lat2));

    return [lat2 * 180 / Math.PI, lon2 * 180 / Math.PI];
}

/**
 * Redraws the dynamic Radar Scanning Cone radiating from the tower
 * based on current rotator heading angle.
 */
function updateRadarCone(headingDegrees, originCoords = null) {
    if (originCoords) {
        currentRadarOrigin = originCoords;
    }
    currentHeadingAngle = headingDegrees;

    const startAngle = headingDegrees - (SCAN_FOV_DEG / 2);
    const endAngle = headingDegrees + (SCAN_FOV_DEG / 2);

    const conePoints = [currentRadarOrigin];
    const steps = 15;

    for (let i = 0; i <= steps; i++) {
        const stepAngle = startAngle + (i * (SCAN_FOV_DEG / steps));
        const pt = destinationPoint(currentRadarOrigin[0], currentRadarOrigin[1], SCAN_RANGE_METERS, stepAngle);
        conePoints.push(pt);
    }
    conePoints.push(currentRadarOrigin);

    if (radarConePolygon) {
        radarConePolygon.setLatLngs(conePoints);
    } else {
        radarConePolygon = L.polygon(conePoints, {
            color: '#06b6d4',
            weight: 1.5,
            fillColor: '#06b6d4',
            fillOpacity: 0.18,
            dashArray: '4, 4'
        }).addTo(map);
    }
}

/**
 * Switches the active camera station on the tactical map.
 */
function switchActiveStation(nodeCode) {
    activeStationCode = nodeCode;

    // Sync header dropdown if available
    const selector = document.getElementById('camera-node-selector');
    if (selector && selector.value !== nodeCode) {
        selector.value = nodeCode;
    }

    if (nodeCode === 'ALL') {
        map.setView([21.1450, 79.0865], 14, { animate: true });
        const def = CAMERA_STATIONS['NODE-01'];
        if (def) updateRadarCone(def.heading, def.coords);
    } else if (CAMERA_STATIONS[nodeCode]) {
        const st = CAMERA_STATIONS[nodeCode];
        map.setView(st.coords, 16, { animate: true });
        updateRadarCone(st.heading, st.coords);

        if (stationMarkers[nodeCode]) {
            stationMarkers[nodeCode].openPopup();
        }
    }

    // Notify app.js of station change
    if (typeof window.onStationChanged === 'function') {
        window.onStationChanged(nodeCode);
    }
}

/**
 * Adds an animal threat marker to the map with pulsing halo.
 */
function addThreatMarker(sighting) {
    const isCritical = sighting.species.toLowerCase() === 'tiger' || sighting.species.toLowerCase() === 'lion';
    const markerColor = isCritical ? '#ef4444' : '#f59e0b';
    const pulseClass = isCritical ? 'pulse-marker-critical' : 'pulse-marker-warning';

    const threatIcon = L.divIcon({
        className: 'custom-threat-icon',
        html: `
            <div style="position:relative; width:28px; height:28px; display:flex; align-items:center; justify-content:center;">
                <div style="position:absolute; width:100%; height:100%; border-radius:50%; background:${markerColor}; opacity:0.3; animation: pulseGlow 1.2s infinite;"></div>
                <div style="width:20px; height:20px; border-radius:50%; background:${markerColor}; border:2px solid #ffffff; display:flex; align-items:center; justify-content:center; box-shadow:0 0 10px ${markerColor};">
                    <i class="fa-solid fa-paw" style="color:#ffffff; font-size:10px;"></i>
                </div>
            </div>
        `,
        iconSize: [28, 28],
        iconAnchor: [14, 14]
    });

    const marker = L.marker([sighting.lat, sighting.lon], { icon: threatIcon });

    const popupHtml = `
        <div style="font-family:'Inter', sans-serif; font-size:12px; min-width:200px; color:#0f172a; padding:4px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <strong style="color:${markerColor}; font-size:13px; text-transform:uppercase;">
                    <i class="fa-solid fa-triangle-exclamation"></i> ${sighting.species}
                </strong>
                <span style="font-size:10px; background:#e2e8f0; padding:2px 5px; border-radius:3px; font-weight:600;">${sighting.confidence}%</span>
            </div>
            <div style="margin-bottom:8px; border-radius:4px; overflow:hidden; height:100px; background:#000;">
                <img src="${sighting.image_path}" style="width:100%; height:100%; object-fit:cover;" onerror="this.style.display='none'">
            </div>
            <div style="font-family:'JetBrains Mono', monospace; font-size:11px; line-height:1.5;">
                <div><strong>Coords:</strong> ${sighting.lat.toFixed(4)}° N, ${sighting.lon.toFixed(4)}° E</div>
                <div><strong>Distance:</strong> ${sighting.distance_meters}m from Rampur</div>
                <div><strong>Time:</strong> ${sighting.timestamp}</div>
                <div style="margin-top:4px; color:${sighting.sms_status === 'DELIVERED' ? '#15803d' : '#b45309'}; font-weight:700;">
                    <i class="fa-solid fa-comment-sms"></i> ${sighting.sms_status === 'DELIVERED' ? 'SMS Delivered (Villagers Alerted)' : 'Queued (Offline Mode)'}
                </div>
            </div>
        </div>
    `;

    marker.bindPopup(popupHtml);
    sightingMarkersGroup.addLayer(marker);

    return marker;
}

// Global hook to pan to sighting
window.panToSighting = function(lat, lon) {
    if (map) {
        map.setView([lat, lon], 16, { animate: true });
    }
};

window.updateMapRadarAngle = updateRadarCone;
window.addMapThreat = addThreatMarker;
window.initTacticalMap = initTacticalMap;
window.switchMapStation = switchActiveStation;
window.CAMERA_STATIONS = CAMERA_STATIONS;
