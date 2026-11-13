/**
 * PROJECT INDRADHANU - GIS TACTICAL SURVEILLANCE MAP (LEAFLET.JS)
 * Dynamically renders registered edge nodes, verified threat markers, and radar cones from backend state.
 */

let CAMERA_STATIONS = {};
let activeStationCode = 'ALL';
let currentRadarOrigin = [19.9152, 74.7279];
let stationMarkers = {};
const VILLAGE_COORDS = [21.1390, 79.0830];

let map = null;
let satLayer = null;
let osmLayer = null;
let radarConePolygon = null;
let sightingMarkersGroup = null;

let currentHeadingAngle = 145;
const SCAN_RANGE_METERS = 450;
const SCAN_FOV_DEG = 60;

function initTacticalMap() {
    const mapContainer = document.getElementById('gis-map');
    if (!mapContainer) return;
    if (map) {
        map.invalidateSize();
        return;
    }

    map = L.map('gis-map', {
        center: [21.1435, 79.0860],
        zoom: 14,
        zoomControl: false,
        attributionControl: false
    });

    L.control.zoom({ position: 'topright' }).addTo(map);

    satLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 18,
        attribution: 'Esri World Imagery'
    }).addTo(map);

    osmLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
        maxZoom: 19,
        attribution: 'CartoDB'
    });

    const villageCircle = L.circle(VILLAGE_COORDS, {
        color: '#f59e0b',
        fillColor: '#f59e0b',
        fillOpacity: 0.12,
        weight: 2,
        dashArray: '6, 6',
        radius: 650
    }).addTo(map);
    villageCircle.bindTooltip("Protected Village Safety Zone (650m)", { permanent: true, direction: "center", className: "map-label-village" });

    const villageIcon = L.divIcon({
        className: 'custom-map-icon',
        html: `<div style="background:#f59e0b; color:#000; padding:3px 6px; border-radius:4px; font-weight:700; font-size:10px; font-family:sans-serif; white-space:nowrap;"><i class="fa-solid fa-house-chimney"></i> Protected Settlement</div>`,
        iconSize: [115, 24],
        iconAnchor: [57, 12]
    });
    L.marker(VILLAGE_COORDS, { icon: villageIcon }).addTo(map);

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

    sightingMarkersGroup = L.layerGroup().addTo(map);

    // Fetch real registered edge nodes from backend
    fetch('/api/nodes')
        .then(r => r.json())
        .then(data => {
            if (data.success && Array.isArray(data.nodes)) {
                renderStationsOnMap(data.nodes);
            }
        })
        .catch(err => console.warn('[Map Nodes Sync]', err));

    document.getElementById('btn-layer-sat')?.addEventListener('click', function() {
        if (!map.hasLayer(satLayer)) {
            map.removeLayer(osmLayer);
            map.addLayer(satLayer);
            this.classList.add('active');
            document.getElementById('btn-layer-osm')?.classList.remove('active');
        }
    });

    document.getElementById('btn-layer-osm')?.addEventListener('click', function() {
        if (!map.hasLayer(osmLayer)) {
            map.removeLayer(satLayer);
            map.addLayer(osmLayer);
            this.classList.add('active');
            document.getElementById('btn-layer-sat')?.classList.remove('active');
        }
    });

    document.getElementById('btn-recenter')?.addEventListener('click', function() {
        if (map) map.setView(currentRadarOrigin, 15, { animate: true });
    });

    setTimeout(() => {
        if (map) map.invalidateSize();
    }, 250);

    window.addEventListener('resize', () => {
        if (map) map.invalidateSize();
    });
}

function renderStationsOnMap(nodes) {
    if (!map) return;

    Object.values(stationMarkers).forEach(m => map.removeLayer(m));
    stationMarkers = {};
    CAMERA_STATIONS = {};

    nodes.forEach((n, idx) => {
        const code = n.node_code;
        const isOnline = n.status === 'ONLINE_ACTIVE';
        const color = isOnline ? '#10b981' : '#06b6d4';
        const lat = Number(n.latitude) || 21.1450;
        const lon = Number(n.longitude) || 79.0860;
        const heading = Number(n.rotator_heading) || 145;

        CAMERA_STATIONS[code] = {
            code: code,
            name: n.node_name,
            sector: n.sector,
            coords: [lat, lon],
            heading: heading,
            battery: n.battery_pct || 0,
            status: n.status || 'OFFLINE',
            last_heartbeat: n.last_heartbeat || 'Never',
            last_sync_at: n.last_sync_at || 'Never',
            pending_queue_count: n.pending_queue_count || 0,
            color: color,
            camType: n.camera_type
        };

        if (idx === 0) {
            currentRadarOrigin = [lat, lon];
            currentHeadingAngle = heading;
        }

        const towerIcon = L.divIcon({
            className: `tower-icon-wrapper tower-${code.toLowerCase()}`,
            html: `
                <div style="position:relative; width:34px; height:34px; background:rgba(0,0,0,0.8); border:2px solid ${color}; border-radius:50%; display:flex; align-items:center; justify-content:center; box-shadow:0 0 12px ${color}; cursor:pointer;">
                    <i class="fa-solid fa-tower-broadcast" style="color:${color}; font-size:13px;"></i>
                    <div style="position:absolute; bottom:-16px; font-family:'JetBrains Mono',monospace; font-size:9px; font-weight:700; color:#fff; background:#000; padding:1px 4px; border:1px solid ${color}; border-radius:2px; white-space:nowrap;">
                        ${code}
                    </div>
                </div>
            `,
            iconSize: [34, 34],
            iconAnchor: [17, 17]
        });

        const marker = L.marker([lat, lon], { icon: towerIcon }).addTo(map);
        marker.bindPopup(`
            <div style="font-family:'JetBrains Mono', monospace; font-size:12px; color:#0f172a; min-width:190px;">
                <strong style="color:${color};"><i class="fa-solid fa-tower-broadcast"></i> ${code}: ${n.node_name}</strong><br>
                <span style="font-size:11px; color:#475569;">Sector: ${n.sector}</span><br>
                <span>Status: <b>${n.status}</b></span><br>
                <span>Last Heartbeat: <b>${n.last_heartbeat || 'Never'}</b></span><br>
                <span>Last Sync: <b>${n.last_sync_at || 'Never'}</b></span><br>
                <span>Pending Queue: <b>${n.pending_queue_count || 0}</b></span><br>
                <div style="margin-top:8px;">
                    <button onclick="window.switchMapStation('${code}'); if(typeof window.openStationPanel==='function') window.openStationPanel();" style="background:#0f172a; color:#fff; border:1px solid #38bdf8; padding:4px 8px; font-size:10px; cursor:pointer; border-radius:2px; width:100%; font-family:'JetBrains Mono',monospace;">
                        <i class="fa-solid fa-crosshairs"></i> Inspect Edge Node
                    </button>
                </div>
            </div>
        `);

        marker.on('click', () => {
            switchActiveStation(code);
            if (typeof window.openStationPanel === 'function') {
                window.openStationPanel();
            }
        });

        stationMarkers[code] = marker;
    });

    updateRadarCone(currentHeadingAngle, currentRadarOrigin);
}

window.updateMapLocation = function(lat, lon) {
    currentRadarOrigin = [lat, lon];
    if (map) {
        map.setView([lat, lon], 15);
        updateRadarCone(currentHeadingAngle, [lat, lon]);
    }
};

function destinationPoint(lat, lon, distanceMeters, bearingDegrees) {
    const R = 6378137;
    const d = distanceMeters / R;
    const brng = bearingDegrees * Math.PI / 180;
    const lat1 = lat * Math.PI / 180;
    const lon1 = lon * Math.PI / 180;

    const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(brng));
    const lon2 = lon1 + Math.atan2(Math.sin(brng) * Math.sin(d) * Math.cos(lat1), Math.cos(d) - Math.sin(lat1) * Math.sin(lat2));

    return [lat2 * 180 / Math.PI, lon2 * 180 / Math.PI];
}

function updateRadarCone(headingDegrees, originCoords = null) {
    if (!map) return;
    if (originCoords) {
        currentRadarOrigin = originCoords;
    }
    currentHeadingAngle = headingDegrees;

    const startAngle = headingDegrees - (SCAN_FOV_DEG / 2);
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

function switchActiveStation(nodeCode) {
    activeStationCode = nodeCode;

    const selector = document.getElementById('camera-node-selector');
    if (selector && selector.value !== nodeCode) {
        selector.value = nodeCode;
    }

    if (nodeCode === 'ALL') {
        const firstKey = Object.keys(CAMERA_STATIONS)[0];
        if (firstKey && map) {
            const st = CAMERA_STATIONS[firstKey];
            map.setView(st.coords, 14, { animate: true });
            updateRadarCone(st.heading, st.coords);
        }
    } else if (CAMERA_STATIONS[nodeCode] && map) {
        const st = CAMERA_STATIONS[nodeCode];
        map.setView(st.coords, 16, { animate: true });
        updateRadarCone(st.heading, st.coords);
        if (stationMarkers[nodeCode]) {
            stationMarkers[nodeCode].openPopup();
        }
    }

    if (typeof window.onStationChanged === 'function') {
        window.onStationChanged(nodeCode);
    }
    if (typeof window.openStationPanel === 'function') {
        window.openStationPanel();
    }
}

function addThreatMarker(sighting) {
    if (!map || !sightingMarkersGroup) return null;
    const isCritical = (sighting.threat_level || 'CRITICAL') === 'CRITICAL';
    const markerColor = isCritical ? '#ef4444' : '#f59e0b';

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

    const lat = Number(sighting.lat) || 21.1440;
    const lon = Number(sighting.lon) || 79.0870;
    const marker = L.marker([lat, lon], { icon: threatIcon });

    const verStatus = sighting.verification_status || 'VERIFIED';
    const sirenStatus = sighting.siren_status || 'STANDBY';

    const popupHtml = `
        <div style="font-family:'Inter', sans-serif; font-size:12px; min-width:210px; color:#0f172a; padding:4px;">
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
                <div><strong>Node:</strong> ${sighting.node_code || 'NODE-01'}</div>
                <div><strong>Central AI:</strong> ${verStatus} (${sighting.verified_species || sighting.species})</div>
                <div><strong>Siren:</strong> ${sirenStatus}</div>
                <div><strong>Coords:</strong> ${lat.toFixed(4)}° N, ${lon.toFixed(4)}° E</div>
                <div><strong>Time:</strong> ${sighting.timestamp}</div>
            </div>
        </div>
    `;

    marker.bindPopup(popupHtml);
    sightingMarkersGroup.addLayer(marker);
    return marker;
}

window.panToSighting = function(lat, lon) {
    if (map) {
        map.setView([lat, lon], 16, { animate: true });
    }
};

window.updateMapRadarAngle = updateRadarCone;
window.addMapThreat = addThreatMarker;
window.initTacticalMap = initTacticalMap;
window.renderStationsOnMap = renderStationsOnMap;
window.switchMapStation = switchActiveStation;
window.CAMERA_STATIONS = CAMERA_STATIONS;
window.invalidateMapSize = function() {
    if (map) {
        map.invalidateSize();
    }
};
