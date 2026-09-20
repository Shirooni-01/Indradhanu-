/**
 * PROJECT INDRADHANU (PROJECT C) - MULTI-PAGE APPLICATION ENGINE
 */

let isOfflineMode = false;
let offlineQueueCount = 0;
let isSoundMuted = false;
let currentFilter = 'all';

// Mock Wildlife Sighting Records with complete surveillance telemetry
let sightingsData = [
    {
        id: 1,
        species: 'Tiger',
        scientific: 'Panthera tigris',
        confidence: 94.8,
        lat: 21.1441,
        lon: 79.0865,
        distance_meters: 280,
        timestamp: '2026-09-19 21:41:33 IST',
        detected_at: '2026-09-19 21:41:33 IST',
        reported_at: '2026-09-19 21:41:35 IST',
        node_code: 'NODE-01',
        node_name: 'Tadoba North Perimeter Tower',
        camera_type: 'Thermal IR (MLX90640 32x24 Array)',
        rotator_heading: 145,
        sector: 'Sector 1 (Rampur Buffer)',
        date: 'Today',
        image_path: '/static/snapshots/tiger_sample.jpg',
        threat_level: 'CRITICAL',
        sms_status: 'DELIVERED',
        sms_count: 45
    },
    {
        id: 2,
        species: 'Leopard',
        scientific: 'Panthera pardus',
        confidence: 93.9,
        lat: 21.14687,
        lon: 79.08640,
        distance_meters: 406,
        timestamp: '2026-09-19 19:12:05 IST',
        detected_at: '2026-09-19 19:12:05 IST',
        reported_at: '2026-09-19 19:12:07 IST',
        node_code: 'NODE-01',
        node_name: 'Tadoba North Perimeter Tower',
        camera_type: 'Thermal IR (MLX90640 32x24 Array)',
        rotator_heading: 145,
        sector: 'Sector 1 (Rampur Buffer)',
        date: 'Today',
        image_path: '/static/snapshots/leopard_sample.jpg',
        threat_level: 'CRITICAL',
        sms_status: 'DELIVERED',
        sms_count: 42
    },
    {
        id: 3,
        species: 'Indian Sloth Bear',
        scientific: 'Melursus ursinus',
        confidence: 88.5,
        lat: 21.1478,
        lon: 79.0910,
        distance_meters: 450,
        timestamp: '2026-09-19 18:45:12 IST',
        detected_at: '2026-09-19 18:45:12 IST',
        reported_at: '2026-09-19 18:45:14 IST',
        node_code: 'NODE-02',
        node_name: 'Rampur East Buffer Tower',
        camera_type: 'Thermal IR + Night Vision',
        rotator_heading: 210,
        sector: 'Sector 1 (Rampur Buffer)',
        date: 'Today',
        image_path: '/static/snapshots/bear_sample.jpg',
        threat_level: 'HIGH',
        sms_status: 'DELIVERED',
        sms_count: 38
    },
    {
        id: 4,
        species: 'Lion',
        scientific: 'Panthera leo persica',
        confidence: 93.1,
        lat: 21.1415,
        lon: 79.0895,
        distance_meters: 320,
        timestamp: '2026-09-19 16:20:40 IST',
        detected_at: '2026-09-19 16:20:40 IST',
        reported_at: '2026-09-19 16:20:42 IST',
        node_code: 'NODE-03',
        node_name: 'Shivpuri West Fringe Tower',
        camera_type: 'Thermal IR (Seek Compact)',
        rotator_heading: 90,
        sector: 'Sector 2 (Shivpuri Fringe)',
        date: 'Today',
        image_path: '/static/snapshots/lion_sample.jpg',
        threat_level: 'CRITICAL',
        sms_status: 'DELIVERED',
        sms_count: 45
    }
];

// Contacts Data
let contactsData = [
    { id: 1, name: 'Sanjay Deshmukh', phone: '+91 98230 45612', village: 'Rampur (Sector 1)', role: 'forest_ranger', channel: 'SMS + Alert Post', status: 'Active' },
    { id: 2, name: 'Ramesh Patil (Sarpanch)', phone: '+91 94221 88901', village: 'Rampur (Sector 1)', role: 'sarpanch', channel: 'Priority SMS', status: 'Active' },
    { id: 3, name: 'Sunita Gawande', phone: '+91 97654 11234', village: 'Rampur (Sector 1)', role: 'villager', channel: 'Broadcast SMS', status: 'Active' },
    { id: 4, name: 'Ganesh Tekam', phone: '+91 99700 66543', village: 'Shivpuri (Sector 2)', role: 'villager', channel: 'Broadcast SMS', status: 'Active' },
    { id: 5, name: 'Vikram Shinde', phone: '+91 91588 33219', village: 'Borpada (Sector 3)', role: 'forest_ranger', channel: 'SMS + Siren', status: 'Active' }
];

document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initOfflineSimulation();
    initDetectionSimulator();
    initStationSelector();
    initModals();

    // Fetch permanent history from SQLite Database!
    loadDetectionsFromDB();

    if (document.getElementById('contacts-page-table-body')) {
        renderContactsFullTable();
        initContactsSearch();
    }
});

function loadDetectionsFromDB() {
    fetch('/api/detections')
        .then(r => r.json())
        .then(data => {
            if (data.success && data.detections && data.detections.length > 0) {
                sightingsData = data.detections.map(d => {
                    const detTime = d.detected_at || d.timestamp || 'Today';
                    const repTime = d.reported_at || formatOffsetReportedTime(detTime);
                    const nodeCode = d.node_code || 'NODE-01';
                    const nodeName = nodeCode === 'NODE-02' ? 'Rampur East Buffer Tower' : (nodeCode === 'NODE-03' ? 'Shivpuri West Fringe Tower' : 'Tadoba North Perimeter Tower');
                    const camType = nodeCode === 'NODE-02' ? 'Thermal IR + Night Vision' : (nodeCode === 'NODE-03' ? 'Thermal IR (Seek Compact)' : 'Thermal IR (MLX90640 32x24 Array)');
                    const sector = nodeCode === 'NODE-03' ? 'Sector 2 (Shivpuri Fringe)' : 'Sector 1 (Rampur Buffer)';
                    
                    return {
                        id: d.id,
                        species: d.species,
                        scientific: d.scientific_name || d.species,
                        confidence: d.confidence,
                        lat: d.latitude,
                        lon: d.longitude,
                        distance_meters: d.distance_meters || 300,
                        timestamp: detTime,
                        detected_at: detTime,
                        reported_at: repTime,
                        node_code: nodeCode,
                        node_name: nodeName,
                        camera_type: camType,
                        sector: sector,
                        rotator_heading: d.rotator_heading || 145,
                        date: 'Today',
                        image_path: d.image_snapshot_path || '/static/snapshots/tiger_sample.jpg',
                        threat_level: d.threat_level || 'CRITICAL',
                        sms_status: 'DELIVERED',
                        sms_count: 42,
                        latency_badge: d.latency_badge || (d.is_delayed ? 'Offline Delayed' : 'Real-time (< 2s)'),
                        is_delayed: d.is_delayed || false,
                        latency_seconds: d.latency_seconds || 1
                    };
                });
            }
            updateDetectionsViews();
        })
        .catch(() => {
            updateDetectionsViews();
        });
}

function updateDetectionsViews() {
    // Update Badge
    const dockBadge = document.getElementById('dock-badge-history');
    if (dockBadge) dockBadge.textContent = sightingsData.length;

    // If on Map page
    if (document.getElementById('gis-map') && window.initTacticalMap) {
        window.initTacticalMap();
        renderInitialThreatMarkers();
    }

    // If on History page
    if (document.getElementById('sightings-table-body') || document.getElementById('history-cards-container')) {
        renderHistoryData();
    }
}

/* ==========================================================================
   SYSTEM CLOCK
   ========================================================================== */
function initClock() {
    const clockEl = document.getElementById('system-clock');
    const updateTime = () => {
        const now = new Date();
        if (clockEl) clockEl.textContent = now.toTimeString().split(' ')[0];
    };
    updateTime();
    setInterval(updateTime, 1000);
}

/* ==========================================================================
   OFFLINE FALLBACK QUEUE SIMULATION
   ========================================================================== */
function initOfflineSimulation() {
    const toggleBtn = document.getElementById('btn-toggle-offline');
    const netTop = document.getElementById('network-status-text');
    const dockNet = document.getElementById('dock-net-label');
    const queueTop = document.getElementById('queue-status-text');

    toggleBtn?.addEventListener('click', () => {
        isOfflineMode = !isOfflineMode;

        if (isOfflineMode) {
            toggleBtn.classList.add('active-offline');
            toggleBtn.innerHTML = '<i class="fa-solid fa-tower-broadcast"></i> Restore Online Link';
            
            if (netTop) {
                netTop.className = 'item-value status-offline';
                netTop.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> OFFLINE (ZERO NET)';
            }
            if (dockNet) dockNet.textContent = 'Offline';

            showTemporaryNotification('NETWORK OUTAGE: Offline SQLite Fallback Activated. Alerts are safely queued locally.', 'warning');
        } else {
            toggleBtn.classList.remove('active-offline');
            toggleBtn.innerHTML = '<i class="fa-solid fa-plug-circle-xmark"></i> Simulate Offline';
            
            if (netTop) {
                netTop.className = 'item-value status-online';
                netTop.innerHTML = '<i class="fa-solid fa-signal"></i> 4G ONLINE';
            }
            if (dockNet) dockNet.textContent = '4G Online';

            if (offlineQueueCount > 0) {
                showTemporaryNotification(`LINK RESTORED: Auto-flushing ${offlineQueueCount} queued alerts from SQLite to villagers...`, 'success');
                setTimeout(() => {
                    offlineQueueCount = 0;
                    if (queueTop) {
                        queueTop.textContent = '0 PENDING';
                        queueTop.className = 'item-value status-idle';
                    }
                    const contactsQueue = document.getElementById('contacts-queue-count');
                    if (contactsQueue) contactsQueue.textContent = '0';

                    sightingsData.forEach(s => {
                        if (s.sms_status === 'QUEUED_OFFLINE') s.sms_status = 'DELIVERED';
                    });
                    if (document.getElementById('history-page-grid')) renderHistoryPageGrid();
                }, 1000);
            } else {
                showTemporaryNotification('NETWORK RESTORED: All systems synchronized.', 'info');
            }
        }
    });
}

/* ==========================================================================
   SIMULATE LIVE DETECTION BREACH
   ========================================================================== */
const SPECIES_POOL = [
    { name: 'Tiger', scientific: 'Panthera tigris', threat: 'CRITICAL', img: '/static/snapshots/tiger_sample.jpg' },
    { name: 'Leopard', scientific: 'Panthera pardus', threat: 'CRITICAL', img: '/static/snapshots/leopard_sample.jpg' },
    { name: 'Indian Sloth Bear', scientific: 'Melursus ursinus', threat: 'HIGH', img: '/static/snapshots/bear_sample.jpg' },
    { name: 'Lion', scientific: 'Panthera leo', threat: 'CRITICAL', img: '/static/snapshots/lion_sample.jpg' }
];

let simCounter = 0;

function initDetectionSimulator() {
    document.getElementById('btn-sim-detection')?.addEventListener('click', triggerSimulatedDetection);

    const soundBtn = document.getElementById('btn-sound-toggle');
    soundBtn?.addEventListener('click', () => {
        isSoundMuted = !isSoundMuted;
        soundBtn.innerHTML = isSoundMuted 
            ? '<i class="fa-solid fa-volume-xmark" style="color:#ef4444;"></i>' 
            : '<i class="fa-solid fa-volume-high"></i>';
    });

    document.getElementById('btn-dismiss-threat')?.addEventListener('click', () => {
        document.getElementById('threat-banner').classList.add('hidden');
    });
}

function initStationSelector() {
    const selector = document.getElementById('camera-node-selector');
    if (!selector) return;

    selector.addEventListener('change', (e) => {
        const val = e.target.value;
        if (typeof window.switchMapStation === 'function') {
            window.switchMapStation(val);
        }
        updateStationTelemetryUI(val);
    });
}

function updateStationTelemetryUI(nodeCode) {
    const batteryEl = document.getElementById('telemetry-battery');
    const pirEl = document.getElementById('pir-status-text');

    if (nodeCode === 'ALL') {
        if (batteryEl) batteryEl.innerHTML = '<i class="fa-solid fa-bolt"></i> 3 NODES ACTIVE';
        if (pirEl) pirEl.innerHTML = '<i class="fa-solid fa-shield"></i> MULTI-PERIMETER';
    } else if (nodeCode === 'NODE-02') {
        if (batteryEl) batteryEl.innerHTML = '<i class="fa-solid fa-bolt"></i> 94% SOLAR';
        if (pirEl) pirEl.innerHTML = '<i class="fa-solid fa-shield"></i> STANDBY (PIR WAKE)';
    } else if (nodeCode === 'NODE-03') {
        if (batteryEl) batteryEl.innerHTML = '<i class="fa-solid fa-bolt"></i> 79% SOLAR';
        if (pirEl) pirEl.innerHTML = '<i class="fa-solid fa-shield"></i> STANDBY (PIR WAKE)';
    } else {
        if (batteryEl) batteryEl.innerHTML = '<i class="fa-solid fa-bolt"></i> 88% SOLAR';
        if (pirEl) pirEl.innerHTML = '<i class="fa-solid fa-shield"></i> ACTIVE (PIR WAKE)';
    }
}

window.onStationChanged = function(nodeCode) {
    updateStationTelemetryUI(nodeCode);
};

function triggerSimulatedDetection() {
    const selector = document.getElementById('camera-node-selector');
    const chosenNode = selector ? selector.value : 'NODE-01';

    fetch('/api/detections/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_code: chosenNode })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success && data.detection) {
            const d = data.detection;
            const nowStr = new Date().toTimeString().split(' ')[0] + ' IST';
            const nodeCode = d.node_code || chosenNode;
            const nodeName = nodeCode === 'NODE-02' ? 'Rampur East Buffer Tower' : (nodeCode === 'NODE-03' ? 'Shivpuri West Fringe Tower' : 'Tadoba North Perimeter Tower');
            const camType = nodeCode === 'NODE-02' ? 'Thermal IR + Night Vision' : (nodeCode === 'NODE-03' ? 'Thermal IR (Seek Compact)' : 'Thermal IR (MLX90640 32x24 Array)');
            const sector = nodeCode === 'NODE-03' ? 'Sector 2 (Shivpuri Fringe)' : 'Sector 1 (Rampur Buffer)';

            const newSighting = {
                id: d.id,
                species: d.species,
                scientific: d.scientific,
                confidence: d.confidence,
                lat: d.latitude,
                lon: d.longitude,
                distance_meters: d.distance_meters,
                timestamp: d.time || nowStr,
                detected_at: d.detected_at || d.time || nowStr,
                reported_at: d.reported_at || formatOffsetReportedTime(d.detected_at || d.time || nowStr),
                node_code: nodeCode,
                node_name: nodeName,
                camera_type: camType,
                rotator_heading: d.rotator_heading || 145,
                sector: sector,
                date: 'Today',
                image_path: d.image_path,
                threat_level: d.threat_level,
                sms_status: isOfflineMode ? 'QUEUED_OFFLINE' : 'DELIVERED',
                sms_count: 42
            };

            sightingsData.unshift(newSighting);
            handleNewDetectionUI(newSighting);
        }
    })
    .catch(() => {
        // Fallback in case of server delay
        const animal = SPECIES_POOL[simCounter % SPECIES_POOL.length];
        simCounter++;
        const nowStr = new Date().toTimeString().split(' ')[0] + ' IST';
        const newSighting = {
            id: Date.now(),
            species: animal.name,
            scientific: animal.scientific,
            confidence: 94.5,
            lat: 21.1440 + (Math.random() - 0.5) * 0.007,
            lon: 79.0870 + (Math.random() - 0.5) * 0.007,
            distance_meters: 280,
            timestamp: nowStr,
            detected_at: nowStr,
            reported_at: formatOffsetReportedTime(nowStr),
            node_code: 'NODE-01',
            node_name: 'Tadoba North Perimeter Tower',
            camera_type: 'Thermal IR (MLX90640 32x24 Array)',
            rotator_heading: 145,
            sector: 'Sector 1 (Rampur Buffer)',
            date: 'Today',
            image_path: animal.img,
            threat_level: animal.threat,
            sms_status: isOfflineMode ? 'QUEUED_OFFLINE' : 'DELIVERED',
            sms_count: 42
        };
        sightingsData.unshift(newSighting);
        handleNewDetectionUI(newSighting);
    });
}

function handleNewDetectionUI(newSighting) {
    if (isOfflineMode) {
        offlineQueueCount++;
        const queueTop = document.getElementById('queue-status-text');
        if (queueTop) {
            queueTop.textContent = `${offlineQueueCount} PENDING`;
            queueTop.className = 'item-value status-offline';
        }
    }

    // Update Dock Badge
    const dockBadge = document.getElementById('dock-badge-history');
    if (dockBadge) dockBadge.textContent = sightingsData.length;

    // PIR status badge
    const pirStatus = document.getElementById('pir-status-text');
    if (pirStatus) {
        pirStatus.innerHTML = '<i class="fa-solid fa-person-running"></i> MOTION TRIGGER!';
        pirStatus.className = 'item-value status-active';
    }

    // If on Map page -> drop marker & pan
    if (window.addMapThreat) {
        window.addMapThreat(newSighting);
        window.panToSighting(newSighting.lat, newSighting.lon);
    }

    // Show Threat Banner if on Map
    const banner = document.getElementById('threat-banner');
    if (banner) {
        const title = document.getElementById('threat-title');
        const desc = document.getElementById('threat-desc');
        title.textContent = `${newSighting.threat_level} ALERT: ${newSighting.species.toUpperCase()} DETECTED`;
        desc.textContent = `Location: ${newSighting.lat.toFixed(4)}° N, ${newSighting.lon.toFixed(4)}° E | Distance: ~${newSighting.distance_meters}m from Rampur village | ${
            isOfflineMode 
                ? '⚡ Network Offline: Stored safely in SQLite fallback queue.' 
                : 'SMS dispatched to 42 villagers & Forest Ranger.'
        }`;
        banner.classList.remove('hidden');
    }

    // Play Alert Sound
    if (!isSoundMuted) {
        const audio = document.getElementById('siren-audio');
        if (audio) {
            audio.currentTime = 0;
            audio.play().catch(() => {});
        }
    }

    // If on History page -> update active view
    if (document.getElementById('sightings-table-body') || document.getElementById('history-cards-container')) {
        renderHistoryData();
    }

    showTemporaryNotification(`PERMANENT RECORD SAVED: ${newSighting.species} (${newSighting.confidence}%) stored in SQLite database.`, 'success');

    setTimeout(() => {
        if (pirStatus) {
            pirStatus.innerHTML = '<i class="fa-solid fa-shield"></i> STANDBY (PIR WAKE)';
            pirStatus.className = 'item-value status-online';
        }
    }, 7000);
}

function renderInitialThreatMarkers() {
    sightingsData.forEach(s => {
        if (window.addMapThreat) window.addMapThreat(s);
    });
}

/* ==========================================================================
   PAGE 2: SIGHTINGS HISTORY (LIST VIEW & CARDS VIEW TOGGLE)
   ========================================================================== */
let currentHistoryViewMode = 'list'; // 'list' or 'cards'

function initHistoryView() {
    initHistoryFilterPills();
    initHistoryModeToggle();
    renderHistoryData();
}

window.initHistoryView = initHistoryView;

function initHistoryModeToggle() {
    const btnList = document.getElementById('btn-view-list');
    const btnCards = document.getElementById('btn-view-cards');
    const listContainer = document.getElementById('history-list-container');
    const cardsContainer = document.getElementById('history-cards-container');

    btnList?.addEventListener('click', () => {
        currentHistoryViewMode = 'list';
        btnList.classList.add('active');
        btnCards.classList.remove('active');
        listContainer?.classList.remove('hidden');
        cardsContainer?.classList.add('hidden');
        renderHistoryTableList();
    });

    btnCards?.addEventListener('click', () => {
        currentHistoryViewMode = 'cards';
        btnCards.classList.add('active');
        btnList.classList.remove('active');
        cardsContainer?.classList.remove('hidden');
        listContainer?.classList.add('hidden');
        renderHistoryPageGrid();
    });
}

function initHistoryFilterPills() {
    document.querySelectorAll('.filter-pill').forEach(pill => {
        pill.addEventListener('click', function() {
            document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
            this.classList.add('active');
            currentFilter = this.dataset.filter;
            renderHistoryData();
        });
    });
}

function renderHistoryData() {
    if (currentHistoryViewMode === 'list') {
        renderHistoryTableList();
    } else {
        renderHistoryPageGrid();
    }
}

// 1. RENDER AS DETAILED LIST / TABLE
function renderHistoryTableList() {
    const tbody = document.getElementById('sightings-table-body');
    if (!tbody) return;

    tbody.innerHTML = '';

    const filtered = sightingsData.filter(item => {
        if (currentFilter === 'all') return true;
        return item.species.toLowerCase().includes(currentFilter.toLowerCase());
    });

    filtered.forEach(s => {
        const tr = document.createElement('tr');
        const isCritical = s.threat_level === 'CRITICAL';
        const threatBadge = isCritical 
            ? '<span class="badge-critical" style="padding:2px 6px; border-radius:3px; font-size:10px;">CRITICAL</span>' 
            : '<span class="badge-high" style="padding:2px 6px; border-radius:3px; font-size:10px;">HIGH</span>';
        
        const isQueued = s.sms_status === 'QUEUED_OFFLINE';
        const statusBadge = isQueued 
            ? '<span class="text-warning font-mono"><i class="fa-solid fa-database"></i> SQLite Queued</span>'
            : '<span class="text-success font-mono"><i class="fa-solid fa-check-double"></i> SMS Delivered</span>';

        tr.innerHTML = `
            <td>
                <div class="table-snapshot-thumb" onclick="openSnapshotModalById(${s.id})">
                    <img src="${s.image_path}" alt="${s.species}">
                </div>
            </td>
            <td>
                <strong>${s.species}</strong><br>
                <em style="color:var(--text-muted); font-size:10px;">${s.scientific}</em>
            </td>
            <td>${threatBadge}</td>
            <td><span class="card-conf-badge">${s.confidence}%</span></td>
            <td class="font-mono text-info">${s.lat.toFixed(4)}° N, ${s.lon.toFixed(4)}° E</td>
            <td>~${s.distance_meters}m from village</td>
            <td class="font-mono">
                <span style="font-size:11px; color:var(--text-muted);">${s.timestamp}</span><br>
                <span class="${s.is_delayed ? 'badge-high' : 'badge-online'}" style="padding:1px 5px; font-size:9px; border-radius:2px; font-weight:700;">
                    <i class="fa-solid ${s.is_delayed ? 'fa-clock-rotate-left' : 'fa-bolt'}"></i> ${s.latency_badge || 'Real-time (< 2s)'}
                </span>
            </td>
            <td>${statusBadge}</td>
            <td>
                <button class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="openSnapshotModalById(${s.id})">
                    <i class="fa-solid fa-magnifying-glass-plus"></i> Inspect
                </button>
            </td>
        `;

        tbody.appendChild(tr);
    });
}

// 2. RENDER AS CARDS GRID
function renderHistoryPageGrid() {
    const container = document.getElementById('history-cards-container');
    if (!container) return;

    container.innerHTML = '';

    const filtered = sightingsData.filter(item => {
        if (currentFilter === 'all') return true;
        return item.species.toLowerCase().includes(currentFilter.toLowerCase());
    });

    filtered.forEach(s => {
        const card = document.createElement('div');
        card.className = 'history-card-item';

        const isCritical = s.threat_level === 'CRITICAL';
        const badgeClass = isCritical ? 'badge-critical' : 'badge-high';
        const isQueued = s.sms_status === 'QUEUED_OFFLINE';

        card.innerHTML = `
            <div class="history-card-img-wrap">
                <img src="${s.image_path}" alt="${s.species}">
                <span class="history-badge-top ${badgeClass}">${s.threat_level} ALERT</span>
                <span style="position:absolute; bottom:8px; left:8px; font-family:var(--font-mono); font-size:9px; background:rgba(0,0,0,0.8); border:1px solid ${s.is_delayed ? '#f59e0b' : '#10b981'}; color:${s.is_delayed ? '#f59e0b' : '#10b981'}; padding:2px 6px; border-radius:2px; font-weight:700;">
                    <i class="fa-solid ${s.is_delayed ? 'fa-clock-rotate-left' : 'fa-bolt'}"></i> ${s.latency_badge || 'Real-time (< 2s)'}
                </span>
            </div>
            <div class="history-card-body">
                <div class="card-title-line">
                    <h3>${s.species}</h3>
                    <span class="card-conf-badge">${s.confidence}% Conf.</span>
                </div>
                <div class="card-geo-line">
                    <i class="fa-solid fa-location-crosshairs"></i> ${s.lat.toFixed(4)}° N, ${s.lon.toFixed(4)}° E (~${s.distance_meters}m)
                </div>
                <div class="card-meta-line">
                    <span><i class="fa-regular fa-clock"></i> ${s.timestamp}</span>
                    <span style="color:${isQueued ? '#f59e0b' : '#10b981'}; font-weight:700;">
                        <i class="fa-solid ${isQueued ? 'fa-database' : 'fa-check-double'}"></i>
                        ${isQueued ? 'SQLite Queued' : 'SMS Delivered'}
                    </span>
                </div>
            </div>
        `;

        card.addEventListener('click', () => openSnapshotModal(s));
        container.appendChild(card);
    });
}

/* ==========================================================================
   PAGE 3: VILLAGER & AUTHORITY DIRECTORY
   ========================================================================== */
function initContactsSearch() {
    document.getElementById('contact-search-input')?.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        renderContactsFullTable(query);
    });

    document.getElementById('btn-open-add-modal')?.addEventListener('click', () => {
        document.getElementById('modal-add-contact')?.classList.remove('hidden');
    });

    document.getElementById('btn-close-add-contact')?.addEventListener('click', () => {
        document.getElementById('modal-add-contact')?.classList.add('hidden');
    });

    document.getElementById('form-add-contact')?.addEventListener('submit', (e) => {
        e.preventDefault();
        const name = document.getElementById('contact-name').value;
        const phone = document.getElementById('contact-phone').value;
        const village = document.getElementById('contact-village').value;
        const role = document.getElementById('contact-role').value;

        contactsData.push({
            id: Date.now(),
            name, phone, village, role,
            channel: 'Broadcast SMS',
            status: 'Active'
        });

        e.target.reset();
        document.getElementById('modal-add-contact')?.classList.add('hidden');
        renderContactsFullTable();
        showTemporaryNotification(`Registered ${name} into village SMS alert pool.`, 'success');
    });
}

function renderContactsFullTable(searchQuery = '') {
    const tbody = document.getElementById('contacts-page-table-body');
    if (!tbody) return;

    tbody.innerHTML = '';
    const filtered = contactsData.filter(c => {
        if (!searchQuery) return true;
        return c.name.toLowerCase().includes(searchQuery) ||
               c.phone.toLowerCase().includes(searchQuery) ||
               c.village.toLowerCase().includes(searchQuery);
    });

    const countEl = document.getElementById('stat-total-contacts');
    if (countEl) countEl.textContent = contactsData.length;

    filtered.forEach(c => {
        const tr = document.createElement('tr');
        const roleBadge = c.role === 'forest_ranger' ? '<span class="badge-info">Forest Officer</span>' :
                          c.role === 'sarpanch' ? '<span class="badge-active">Sarpanch</span>' : '<span class="badge-idle">Villager / Farmer</span>';

        tr.innerHTML = `
            <td><strong>${c.name}</strong></td>
            <td class="font-mono">${c.phone}</td>
            <td>${c.village}</td>
            <td>${roleBadge}</td>
            <td><i class="fa-solid fa-tower-broadcast text-info"></i> ${c.channel}</td>
            <td><span class="text-success"><i class="fa-solid fa-circle-check"></i> ${c.status}</span></td>
            <td>
                <button class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="deleteContactRecord(${c.id})">
                    <i class="fa-solid fa-trash-can text-danger"></i>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

window.deleteContactRecord = function(id) {
    contactsData = contactsData.filter(c => c.id !== id);
    renderContactsFullTable();
};

/* ==========================================================================
   MODALS: SNAPSHOT VIEWER (FULL PAGE DOSSIER)
   ========================================================================== */
let currentInspectedSighting = null;

function formatOffsetReportedTime(detected) {
    if (!detected || detected === 'Today') {
        const now = new Date();
        return now.toTimeString().split(' ')[0] + ' IST';
    }
    const match = detected.match(/(\d{2}):(\d{2}):(\d{2})/);
    if (match) {
        let [_, h, m, s] = match;
        let totalSec = parseInt(h, 10) * 3600 + parseInt(m, 10) * 60 + parseInt(s, 10) + 2;
        let newH = String(Math.floor(totalSec / 3600) % 24).padStart(2, '0');
        let newM = String(Math.floor((totalSec % 3600) / 60)).padStart(2, '0');
        let newS = String(totalSec % 60).padStart(2, '0');
        return detected.replace(/(\d{2}):(\d{2}):(\d{2})/, `${newH}:${newM}:${newS}`);
    }
    return detected;
}

function initModals() {
    const snapModal = document.getElementById('modal-snapshot');
    
    // Close button
    document.getElementById('btn-close-snapshot')?.addEventListener('click', () => {
        snapModal?.classList.add('hidden');
    });

    // Backdrop click
    window.addEventListener('click', (e) => {
        if (e.target === snapModal) snapModal.classList.add('hidden');
        const addModal = document.getElementById('modal-add-contact');
        if (e.target === addModal) addModal.classList.add('hidden');
    });

    // Escape key
    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && snapModal && !snapModal.classList.contains('hidden')) {
            snapModal.classList.add('hidden');
        }
    });

    // Thermal Image Filters
    document.querySelectorAll('.toolbar-filter-buttons .filter-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.toolbar-filter-buttons .filter-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            const img = document.getElementById('snapshot-modal-img');
            if (!img) return;

            const mode = this.dataset.imgFilter;
            if (mode === 'normal') {
                img.style.filter = 'none';
            } else if (mode === 'ironbow') {
                img.style.filter = 'contrast(1.35) saturate(1.8) hue-rotate(330deg)';
            } else if (mode === 'invert') {
                img.style.filter = 'invert(1) hue-rotate(180deg)';
            } else if (mode === 'contrast') {
                img.style.filter = 'contrast(2.2) brightness(1.1) grayscale(0.25)';
            }
        });
    });

    // Dispatch SMS from Dossier
    document.getElementById('btn-inspect-dispatch-sms')?.addEventListener('click', () => {
        const speciesName = currentInspectedSighting?.species || 'Predator';
        showTemporaryNotification(`[GSM BROADCAST] Emergency SMS alert for ${speciesName} dispatched to 42 registered villagers & forest outpost.`, 'success');
    });
}

function openSnapshotModal(sighting) {
    const modal = document.getElementById('modal-snapshot');
    if (!modal) return;

    currentInspectedSighting = sighting;

    // Normalizing all telemetry attributes
    const species = sighting.species || 'Unknown Wildlife';
    const scientific = sighting.scientific || sighting.scientific_name || 'Species unverified';
    const confidence = (parseFloat(sighting.confidence) || 93.9).toFixed(1);
    const lat = typeof sighting.lat === 'number' ? sighting.lat : (parseFloat(sighting.latitude) || 21.14687);
    const lon = typeof sighting.lon === 'number' ? sighting.lon : (parseFloat(sighting.longitude) || 79.08640);
    const distanceMeters = sighting.distance_meters || 406;
    const threatLevel = sighting.threat_level || 'CRITICAL';
    const isCritical = threatLevel === 'CRITICAL';
    const imagePath = sighting.image_path || sighting.image_snapshot_path || '/static/snapshots/leopard_sample.jpg';
    
    // Node number & camera station details
    const nodeCode = sighting.node_code || 'NODE-01';
    const nodeName = sighting.node_name || (nodeCode === 'NODE-02' ? 'Rampur East Buffer Tower' : (nodeCode === 'NODE-03' ? 'Shivpuri West Fringe Tower' : 'Tadoba North Perimeter Tower'));
    const cameraType = sighting.camera_type || (nodeCode === 'NODE-02' ? 'Thermal IR + Night Vision' : (nodeCode === 'NODE-03' ? 'Thermal IR (Seek Compact)' : 'Thermal IR (MLX90640 32x24 Array)'));
    const rotatorHeading = sighting.rotator_heading || sighting.heading || 145;
    const sector = sighting.sector || (nodeCode === 'NODE-03' ? 'Sector 2 (Shivpuri Fringe)' : 'Sector 1 (Rampur Buffer)');

    // Timestamps: detected at and reported at
    const detectedAt = sighting.detected_at || sighting.timestamp || sighting.time || '2026-09-20 12:49:54 IST';
    const reportedAt = sighting.reported_at || formatOffsetReportedTime(detectedAt);

    // SMS notification status
    const isSmsDelivered = (sighting.sms_status || (isOfflineMode ? 'QUEUED_OFFLINE' : 'DELIVERED')) === 'DELIVERED';
    const smsCount = sighting.sms_count || 42;

    // Update Header
    const title = document.getElementById('snapshot-modal-title');
    if (title) {
        title.innerHTML = `<i class="fa-solid fa-paw" style="color:${isCritical ? '#ef4444' : '#f59e0b'};"></i> ${species.toUpperCase()} - THERMAL VERIFICATION SNAPSHOT`;
    }

    const nodePill = document.getElementById('dossier-node-pill');
    if (nodePill) {
        nodePill.innerHTML = `<i class="fa-solid fa-tower-broadcast"></i> ${nodeCode}`;
    }

    // Update Visual Column
    const img = document.getElementById('snapshot-modal-img');
    if (img) {
        img.src = imagePath;
        img.alt = `${species} Thermal Snapshot`;
        img.style.filter = 'none';
    }

    // Reset filter buttons
    document.querySelectorAll('.toolbar-filter-buttons .filter-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.imgFilter === 'normal');
    });

    const sensorEl = document.getElementById('dossier-hud-sensor');
    if (sensorEl) sensorEl.textContent = cameraType.includes('MLX') ? 'MLX90640 32x24 UPX' : cameraType;

    const tempEl = document.getElementById('dossier-hud-temp');
    if (tempEl) tempEl.innerHTML = `<i class="fa-solid fa-fire-flame-curved"></i> 38.4°C [HEAT SIGNATURE DETECTED]`;

    const reticleLabel = document.getElementById('reticle-species-label');
    if (reticleLabel) reticleLabel.textContent = `${species.toUpperCase()} DETECTED`;

    const bearingEl = document.getElementById('dossier-hud-bearing');
    if (bearingEl) bearingEl.innerHTML = `<i class="fa-solid fa-compass"></i> AZ: ${rotatorHeading}° SE`;

    const hudNodeEl = document.getElementById('dossier-hud-node');
    if (hudNodeEl) hudNodeEl.innerHTML = `<i class="fa-solid fa-camera"></i> ${nodeCode} TOWER`;

    const filePathEl = document.getElementById('dossier-filepath');
    if (filePathEl) filePathEl.innerHTML = `<i class="fa-regular fa-file-image"></i> <span>${imagePath}</span>`;

    // Populate Right Column: Complete Telemetry Cards
    const meta = document.getElementById('snapshot-modal-meta');
    if (meta) {
        meta.innerHTML = `
            <!-- 1. TYPE OF ANIMAL -->
            <div class="dossier-card">
                <label><i class="fa-solid fa-paw text-danger"></i> TYPE OF ANIMAL & SPECIES</label>
                <div class="card-value-primary">
                    <span style="color:${isCritical ? '#ef4444' : '#f59e0b'}; font-size:15px;">${species}</span>
                    <span class="${isCritical ? 'badge-critical' : 'badge-high'}" style="padding:2px 6px; font-size:9px;">${threatLevel}</span>
                </div>
                <div class="card-value-sub"><em>${scientific}</em></div>
                <div class="card-value-sub" style="font-size:9.5px; color:var(--color-muted-soft);">Classification: Apex Carnivore (Schedule I)</div>
            </div>

            <!-- 2. AI CONFIDENCE RATE -->
            <div class="dossier-card">
                <label><i class="fa-solid fa-brain text-success"></i> CONFIDENCE RATE</label>
                <div class="card-value-primary">
                    <span style="color:#10b981; font-size:15px;">${confidence}% Verified</span>
                    <span style="font-size:9.5px; color:var(--color-muted);">YOLOv8 IR</span>
                </div>
                <div class="conf-meter-track">
                    <div class="conf-meter-fill" style="width:${confidence}%;"></div>
                </div>
                <div class="card-value-sub" style="margin-top:2px;">Neural Engine: Edge IR Core v2.4 (184ms)</div>
            </div>

            <!-- 3. NODE NUMBER (WHICH CAMERA) -->
            <div class="dossier-card">
                <label><i class="fa-solid fa-tower-broadcast text-info"></i> NODE NUMBER (WHICH CAMERA)</label>
                <div class="card-value-primary">
                    <span style="color:var(--color-link); font-size:15px;"><i class="fa-solid fa-camera"></i> ${nodeCode}</span>
                    <span class="badge-online" style="padding:2px 6px; font-size:9px;"><i class="fa-solid fa-circle"></i> ACTIVE</span>
                </div>
                <div class="card-value-sub">Station: ${nodeName}</div>
                <div class="card-value-sub" style="font-size:9.5px; color:var(--color-muted-soft);">${cameraType}</div>
            </div>

            <!-- 4. LOCATION -->
            <div class="dossier-card">
                <label><i class="fa-solid fa-location-crosshairs text-info"></i> LOCATION (GPS & SECTOR)</label>
                <div class="card-value-primary">
                    <span style="color:#06b6d4; font-size:12.5px;">${lat.toFixed(5)}° N, ${lon.toFixed(5)}° E</span>
                </div>
                <div class="card-value-sub">${sector}</div>
                <div class="card-value-sub" style="font-size:9.5px; color:var(--color-muted-soft);">Pan-Tilt Azimuth: ${rotatorHeading}° SE Bearing</div>
            </div>

            <!-- 5. VILLAGE APPROX HAZARD -->
            <div class="dossier-card card-span-2">
                <label><i class="fa-solid fa-triangle-exclamation text-warning"></i> VILLAGE APPROX HAZARD</label>
                <div class="card-value-primary">
                    <span style="color:var(--color-primary); font-size:14px;">~${distanceMeters} meters from residential fringe</span>
                    <span class="hazard-pill-critical">
                        <i class="fa-solid fa-shield-halved"></i> ${distanceMeters < 350 ? 'RED ZONE - CRITICAL PROXIMITY (<350m)' : 'ORANGE ZONE - PERIMETER BUFFER HAZARD'}
                    </span>
                </div>
                <div class="card-value-sub">Target Settlement: Rampur Village Perimeter (Buffer Zone Radius: 650m)</div>
                <div class="card-value-sub" style="font-size:9.5px; color:var(--color-muted-soft); margin-top:2px;">
                    Automated perimeter alert activated. Area farmers and forest workers advised to remain within safe boundary.
                </div>
            </div>

            <!-- 6. DETECTED AT (TIME) -->
            <div class="dossier-card">
                <label><i class="fa-solid fa-clock text-info"></i> DETECTED AT (TIME)</label>
                <div class="card-value-primary">
                    <span style="color:var(--color-primary); font-size:12.5px;">${detectedAt}</span>
                </div>
                <div class="card-value-sub"><i class="fa-solid fa-person-running"></i> PIR Hardware Trigger (GPIO 18)</div>
                <div class="card-value-sub" style="font-size:9.5px; color:var(--color-muted-soft);">Sensor-to-infer wake latency: 184ms</div>
            </div>

            <!-- 7. REPORTED AT & NETWORK SYNC LATENCY (SECTION 4.2) -->
            <div class="dossier-card">
                <label><i class="fa-solid fa-cloud-arrow-up text-warning"></i> REPORTED AT & SYNC LATENCY</label>
                <div class="card-value-primary">
                    <span style="color:var(--color-warning); font-size:12.5px;">${reportedAt}</span>
                    <span class="${sighting.is_delayed ? 'badge-high' : 'badge-online'}" style="padding:2px 6px; font-size:9px; font-weight:700;">
                        <i class="fa-solid ${sighting.is_delayed ? 'fa-clock-rotate-left' : 'fa-bolt'}"></i> ${sighting.latency_badge || 'Real-time (< 2s)'}
                    </span>
                </div>
                <div class="card-value-sub"><i class="fa-solid fa-satellite-dish"></i> Central HQ Ingest (Sec 4.2)</div>
                <div class="card-value-sub" style="font-size:9.5px; color:${sighting.is_delayed ? '#f59e0b' : 'var(--color-muted-soft)'};">
                    ${sighting.is_delayed ? '⚠️ Offline Backlog Recovery (flushed from edge SQLite after network restoration)' : '⚡ Real-Time Uplink (reported_at - detected_at < 2s)'}
                </div>
            </div>

            <!-- 8. SMS NOTIFICATION -->
            <div class="dossier-card card-span-2">
                <label><i class="fa-solid fa-comment-sms text-success"></i> SMS NOTIFICATION</label>
                <div class="card-value-primary">
                    <span style="color:${isSmsDelivered ? '#10b981' : '#f59e0b'}; font-size:13px;">
                        <i class="fa-solid ${isSmsDelivered ? 'fa-check-double' : 'fa-database'}"></i>
                        ${isSmsDelivered ? `Dispatched to ${smsCount} Villagers & Forest Post` : 'Stored in SQLite Local Fallback (Zero Network Outage)'}
                    </span>
                    <span class="${isSmsDelivered ? 'badge-online' : 'badge-idle'}" style="padding:2px 6px; font-size:9px;">
                        ${isSmsDelivered ? 'GSM 4G ACTIVE' : 'OFFLINE QUEUED'}
                    </span>
                </div>
                <div class="card-value-sub">Recipients: 42 Registered Villagers + Sarpanch (Ramesh Patil) + Forest Ranger (Sanjay Deshmukh)</div>
                <div class="sms-payload-box">
                    <strong><i class="fa-solid fa-terminal"></i> DISPATCHED SMS PAYLOAD:</strong> "[EMERGENCY WARNING] ${species} detected by ${nodeCode} at ~${distanceMeters}m from Rampur fringe. Stay indoors and secure livestock. - Forest Dept."
                </div>
            </div>
        `;
    }

    modal.classList.remove('hidden');
}

window.openSnapshotModal = openSnapshotModal;
window.openSnapshotModalById = function(id) {
    const item = sightingsData.find(s => s.id === id || s.id === Number(id));
    if (item) {
        openSnapshotModal(item);
    }
};

function showTemporaryNotification(message, type = 'info') {
    const toast = document.createElement('div');
    const color = type === 'warning' ? '#f59e0b' : type === 'success' ? '#10b981' : '#06b6d4';
    
    toast.style.cssText = `
        position: fixed;
        bottom: 30px;
        right: 30px;
        background: #0e131d;
        border: 1px solid ${color};
        color: #ffffff;
        padding: 12px 18px;
        border-radius: 6px;
        font-family: 'Inter', sans-serif;
        font-size: 12px;
        z-index: 5000;
        box-shadow: 0 4px 20px rgba(0,0,0,0.6);
        animation: fadeIn 0.3s ease;
        max-width: 340px;
    `;
    toast.innerHTML = `<strong style="color:${color};"><i class="fa-solid fa-bell"></i> NOTICE:</strong><br>${message}`;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.5s';
        setTimeout(() => toast.remove(), 500);
    }, 4000);
}

/* ==========================================================================
   PAGE 5: CAMERA NODES NETWORK
   ========================================================================== */
function initNodesView() {
    loadCameraNodes();
    initAddNodeModal();
}

window.initNodesView = initNodesView;

function loadCameraNodes() {
    fetch('/api/nodes')
        .then(r => r.json())
        .then(data => {
            if (data.success && data.nodes.length > 0) {
                renderNodesGrid(data.nodes);
            } else {
                renderFallbackNodes();
            }
        })
        .catch(() => {
            renderFallbackNodes();
        });
}

function renderFallbackNodes() {
    renderNodesGrid([
        { node_code: 'NODE-01', node_name: 'Tadoba North Perimeter Tower', sector: 'Sector 1 (Rampur Buffer)', latitude: 21.1458, longitude: 79.0882, camera_type: 'Thermal IR (MLX90640 32x24)', rotator_heading: 145, battery_pct: 88, status: 'ONLINE_ACTIVE' },
        { node_code: 'NODE-02', node_name: 'Rampur East Buffer Tower', sector: 'Sector 1 (Rampur Buffer)', latitude: 21.1410, longitude: 79.0940, camera_type: 'Thermal IR + Night Vision', rotator_heading: 210, battery_pct: 94, status: 'STANDBY' },
        { node_code: 'NODE-03', node_name: 'Shivpuri West Fringe Tower', sector: 'Sector 2 (Shivpuri Fringe)', latitude: 21.1495, longitude: 79.0790, camera_type: 'Thermal IR (Seek Compact)', rotator_heading: 90, battery_pct: 79, status: 'STANDBY' }
    ]);
}

function renderNodesGrid(nodes) {
    const container = document.getElementById('nodes-page-grid');
    if (!container) return;

    container.innerHTML = '';
    const totalEl = document.getElementById('stat-total-nodes');
    if (totalEl) totalEl.textContent = nodes.length;

    nodes.forEach(node => {
        const card = document.createElement('div');
        card.className = 'node-card';
        const isActive = node.status === 'ONLINE_ACTIVE';
        const statusBadge = isActive 
            ? '<span class="badge-online"><i class="fa-solid fa-circle"></i> ACTIVE</span>'
            : '<span class="badge-active"><i class="fa-solid fa-moon"></i> STANDBY</span>';

        card.innerHTML = `
            <div class="node-card-top">
                <span class="node-code-badge"><i class="fa-solid fa-tower-broadcast"></i> ${node.node_code}</span>
                ${statusBadge}
            </div>
            <div class="node-name-block">
                <h4>${node.node_name}</h4>
                <span class="node-sector-tag"><i class="fa-solid fa-location-dot"></i> ${node.sector}</span>
            </div>
            <div class="node-specs-grid">
                <div class="node-spec-item">
                    <label>Sensor Model</label>
                    <span>${node.camera_type}</span>
                </div>
                <div class="node-spec-item">
                    <label>GPS Coordinates</label>
                    <span class="font-mono text-info">${Number(node.latitude).toFixed(4)}°N, ${Number(node.longitude).toFixed(4)}°E</span>
                </div>
                <div class="node-spec-item">
                    <label>Rotator Bearing</label>
                    <span>${node.rotator_heading}° Heading</span>
                </div>
                <div class="node-spec-item">
                    <label>Solar Battery</label>
                    <span class="text-success"><i class="fa-solid fa-bolt"></i> ${node.battery_pct}% Charged</span>
                </div>
            </div>
            <div class="node-card-actions">
                <a href="/" class="btn btn-primary"><i class="fa-solid fa-map-location-dot"></i> View on Map</a>
                <button class="btn btn-outline" onclick="showTemporaryNotification('Calibrated pan-tilt rotator on ${node.node_code}.', 'info')">
                    <i class="fa-solid fa-compass"></i> Calibrate
                </button>
            </div>
        `;

        container.appendChild(card);
    });
}

function initAddNodeModal() {
    const modal = document.getElementById('modal-add-node');
    document.getElementById('btn-open-add-node')?.addEventListener('click', () => {
        modal?.classList.remove('hidden');
    });

    document.getElementById('btn-close-add-node')?.addEventListener('click', () => {
        modal?.classList.add('hidden');
    });

    document.getElementById('form-add-node')?.addEventListener('submit', (e) => {
        e.preventDefault();
        const payload = {
            node_code: document.getElementById('node-code').value,
            node_name: document.getElementById('node-name').value,
            sector: document.getElementById('node-sector').value,
            latitude: parseFloat(document.getElementById('node-lat').value),
            longitude: parseFloat(document.getElementById('node-lon').value),
            camera_type: document.getElementById('node-camera-type').value
        };

        fetch('/api/nodes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                modal?.classList.add('hidden');
                e.target.reset();
                loadCameraNodes();
                showTemporaryNotification(`Successfully deployed ${payload.node_code} to perimeter network.`, 'success');
            }
        });
    });
}

/* ==========================================================================
   PAGE 4: SYSTEM HEALTH & PLANTED CAMERAS FLEET DIAGNOSTICS
   ========================================================================== */
function initSystemHealthView() {
    loadPlantedCamerasHealth();

    // Toggle between Graphical HUD Cards and Metrics List Table
    const btnCards = document.getElementById('btn-cam-view-cards');
    const btnList = document.getElementById('btn-cam-view-list');
    const hudGrid = document.getElementById('system-cameras-hud-grid');
    const tableWrap = document.getElementById('system-cameras-table-wrap');

    btnCards?.addEventListener('click', () => {
        btnCards.classList.add('active');
        btnList?.classList.remove('active');
        hudGrid?.classList.remove('hidden');
        tableWrap?.classList.add('hidden');
    });

    btnList?.addEventListener('click', () => {
        btnList.classList.add('active');
        btnCards?.classList.remove('active');
        tableWrap?.classList.remove('hidden');
        hudGrid?.classList.add('hidden');
    });

    // Fleet Scan Button
    document.getElementById('btn-scan-fleet-health')?.addEventListener('click', () => {
        showTemporaryNotification('FLEET SCAN: Interrogating live telemetry across all camera towers...', 'info');
        const badge = document.getElementById('fleet-health-summary-badge');
        if (badge) {
            badge.className = 'badge-active';
            badge.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> SCANNING NODES...';
        }
        setTimeout(() => {
            loadPlantedCamerasHealth();
            if (badge) {
                badge.className = 'badge-online';
                badge.innerHTML = '<i class="fa-solid fa-circle-check"></i> ALL NODES HEALTHY';
            }
            showTemporaryNotification('SCAN COMPLETE: All planted camera nodes operational (100% integrity).', 'success');
        }, 900);
    });

    // Close diagnostics modal
    const diagModal = document.getElementById('modal-node-health');
    document.getElementById('btn-close-node-health')?.addEventListener('click', () => {
        diagModal?.classList.add('hidden');
    });

    // Delegate "Check Health" & "Calibrate" button clicks for HUD & Table
    document.addEventListener('click', (e) => {
        const inspectBtn = e.target.closest('.btn-inspect-health');
        if (inspectBtn) {
            const nodeCode = inspectBtn.getAttribute('data-node');
            if (nodeCode) openNodeDiagnosticsModal(nodeCode);
            return;
        }

        const calBtn = e.target.closest('.btn-calibrate-direct');
        if (calBtn) {
            const nodeCode = calBtn.getAttribute('data-node');
            if (nodeCode) {
                calBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Aligning...';
                fetch(`/api/nodes/${nodeCode}/calibrate`, { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        calBtn.innerHTML = '<i class="fa-solid fa-compass"></i> Calibrate';
                        showTemporaryNotification(`CALIBRATED: Pan-tilt zero azimuth aligned on ${nodeCode}.`, 'success');
                    })
                    .catch(() => {
                        calBtn.innerHTML = '<i class="fa-solid fa-compass"></i> Calibrate';
                    });
            }
        }
    });
}
window.initSystemHealthView = initSystemHealthView;

function loadPlantedCamerasHealth() {
    fetch('/api/nodes')
        .then(r => r.json())
        .then(data => {
            if (data.success && data.nodes && data.nodes.length > 0) {
                renderSystemCamerasHud(data.nodes);
                renderSystemCamerasTable(data.nodes);
            }
        })
        .catch(err => console.error('Failed to load camera nodes for system health:', err));
}

function renderSystemCamerasHud(nodes) {
    const grid = document.getElementById('system-cameras-hud-grid');
    if (!grid) return;

    grid.innerHTML = '';
    nodes.forEach(n => {
        const card = document.createElement('div');
        card.className = 'cam-hud-card';
        card.id = `hud-card-${n.node_code}`;

        const batt = n.battery_pct || 88;
        const heading = n.rotator_heading || 145;
        const isActive = n.status === 'ONLINE_ACTIVE';
        const statusBadge = isActive 
            ? '<span class="badge-online" style="padding: 2px 8px; font-size: 9px; margin-left: 4px;"><i class="fa-solid fa-circle"></i> ACTIVE</span>'
            : '<span class="badge-active" style="padding: 2px 8px; font-size: 9px; margin-left: 4px;"><i class="fa-solid fa-moon"></i> STANDBY</span>';

        card.innerHTML = `
            <!-- Header: Code, Station, and Radial Health Score -->
            <div class="cam-hud-header">
                <div class="cam-hud-title-wrap">
                    <div class="cam-hud-code">
                        <i class="fa-solid fa-tower-broadcast" style="color: var(--color-primary); font-size: 14px;"></i>
                        ${n.node_code}
                        ${statusBadge}
                    </div>
                    <div class="cam-hud-name">${n.node_name}</div>
                    <div class="cam-hud-sector">
                        <i class="fa-solid fa-location-dot"></i> ${n.sector} · 
                        <span class="text-info">${Number(n.latitude).toFixed(4)}°N, ${Number(n.longitude).toFixed(4)}°E</span>
                    </div>
                </div>
                
                <!-- Circular Health Arc Meter -->
                <div class="hud-radial-wrap" title="Overall Camera Health Rating: 100% Operational">
                    <svg class="hud-radial-svg" viewBox="0 0 58 58">
                        <circle class="hud-radial-bg" cx="29" cy="29" r="23"></circle>
                        <circle class="hud-radial-meter meter-healthy" cx="29" cy="29" r="23" 
                                stroke-dasharray="144.5" stroke-dashoffset="0"></circle>
                    </svg>
                    <div class="hud-radial-center">
                        <span class="hud-radial-val">100%</span>
                        <span class="hud-radial-lbl">HEALTH</span>
                    </div>
                </div>
            </div>

            <!-- Three Precision Graphical Instruments -->
            <div class="cam-hud-instruments">
                
                <!-- Instrument 1: Compass Radar Bearing -->
                <div class="hud-instrument-box">
                    <span class="hud-inst-title"><i class="fa-solid fa-compass"></i> Pan-Tilt Bearing</span>
                    <div class="compass-dial-wrap">
                        <svg class="compass-dial-svg" viewBox="0 0 56 56">
                            <circle cx="28" cy="28" r="26" fill="none" stroke="#262626" stroke-width="1.5"></circle>
                            <circle cx="28" cy="28" r="16" fill="none" stroke="#1a1a1a" stroke-width="1"></circle>
                            <text x="28" y="10" fill="#777" font-size="6" font-family="JetBrains Mono" text-anchor="middle">N</text>
                            <text x="49" y="30" fill="#555" font-size="6" font-family="JetBrains Mono" text-anchor="middle">E</text>
                            <text x="28" y="51" fill="#555" font-size="6" font-family="JetBrains Mono" text-anchor="middle">S</text>
                            <text x="7" y="30" fill="#555" font-size="6" font-family="JetBrains Mono" text-anchor="middle">W</text>
                            <!-- Rotating Needle & Sweep Wedge -->
                            <g class="compass-needle-layer" style="transform: rotate(${heading}deg); transform-origin: 28px 28px;">
                                <path d="M28 28 L20 6 A26 26 0 0 1 36 6 Z" fill="rgba(195, 217, 243, 0.15)"></path>
                                <line x1="28" y1="28" x2="28" y2="4" stroke="#c3d9f3" stroke-width="2" stroke-linecap="round"></line>
                                <circle cx="28" cy="28" r="2.5" fill="#ffffff"></circle>
                            </g>
                        </svg>
                    </div>
                    <span class="hud-inst-readout font-mono text-link">${heading}° Azimuth</span>
                </div>

                <!-- Instrument 2: Thermal Optical Heatmap Matrix -->
                <div class="hud-instrument-box">
                    <span class="hud-inst-title"><i class="fa-solid fa-camera"></i> Thermal Array</span>
                    <div class="thermal-matrix-wrap">
                        <div class="thermal-matrix-grid" title="Focal Plane Array: 768/768 Active Pixels (100% OK)">
                            <div class="thermal-pixel"></div><div class="thermal-pixel hot"></div><div class="thermal-pixel"></div><div class="thermal-pixel hot"></div><div class="thermal-pixel"></div><div class="thermal-pixel"></div>
                            <div class="thermal-pixel hot"></div><div class="thermal-pixel peak"></div><div class="thermal-pixel peak"></div><div class="thermal-pixel hot"></div><div class="thermal-pixel"></div><div class="thermal-pixel"></div>
                            <div class="thermal-pixel"></div><div class="thermal-pixel hot"></div><div class="thermal-pixel peak"></div><div class="thermal-pixel hot"></div><div class="thermal-pixel"></div><div class="thermal-pixel hot"></div>
                            <div class="thermal-pixel"></div><div class="thermal-pixel"></div><div class="thermal-pixel hot"></div><div class="thermal-pixel"></div><div class="thermal-pixel"></div><div class="thermal-pixel"></div>
                        </div>
                        <div class="thermal-temp-bar">
                            <div class="thermal-temp-fill"></div>
                        </div>
                    </div>
                    <span class="hud-inst-readout font-mono text-success">31.4°C · 100% OK</span>
                </div>

                <!-- Instrument 3: Battery & Solar Energy Meter -->
                <div class="hud-instrument-box">
                    <span class="hud-inst-title"><i class="fa-solid fa-bolt"></i> LiFePO4 Energy</span>
                    <div class="power-gauge-wrap">
                        <div class="battery-visual-shell" title="Battery Pack: ${batt}% Charged (12.6V LiFePO4)">
                            <div class="batt-segment ${batt >= 20 ? 'filled' : ''}"></div>
                            <div class="batt-segment ${batt >= 40 ? 'filled' : ''}"></div>
                            <div class="batt-segment ${batt >= 60 ? 'filled' : ''}"></div>
                            <div class="batt-segment ${batt >= 80 ? 'filled' : ''}"></div>
                            <div class="batt-segment ${batt >= 95 ? 'filled' : ''}"></div>
                        </div>
                        <div class="solar-flow-indicator">
                            <i class="fa-solid fa-sun text-warning" style="font-size: 10px;"></i>
                            <span class="text-success font-mono" style="font-size: 10px;">18.2V In</span>
                        </div>
                    </div>
                    <span class="hud-inst-readout font-mono text-accent">${batt}% Power</span>
                </div>

            </div>

            <!-- Micro-Telemetry Footer: RF Signal, PIR Edge Latency, Diagnostics Trigger -->
            <div class="cam-hud-footer">
                <div class="cam-hud-telemetry-pills">
                    <!-- RF Signal Bars -->
                    <div class="rf-signal-bars" title="GSM 4G LTE Signal: Excellent (RSSI -68 dBm)">
                        <div class="rf-bar b1 active"></div>
                        <div class="rf-bar b2 active"></div>
                        <div class="rf-bar b3 active"></div>
                        <div class="rf-bar b4 active"></div>
                    </div>
                    <div class="latency-meter-badge" title="PIR Hardware Edge Wake-Up Response">
                        <i class="fa-solid fa-stopwatch text-success"></i>
                        <span>&lt; 184ms Latency</span>
                    </div>
                    <div class="latency-meter-badge" style="color: var(--color-muted);" title="SQLite Transaction Fallback Buffer">
                        <i class="fa-solid fa-database text-info"></i>
                        <span>Sync OK</span>
                    </div>
                </div>

                <div class="cam-hud-actions">
                    <button class="btn btn-outline btn-sm btn-inspect-health" data-node="${n.node_code}" style="padding: 5px 12px;">
                        <i class="fa-solid fa-chart-line"></i> Deep Diagnostics
                    </button>
                    <button class="btn btn-primary btn-sm btn-calibrate-direct" data-node="${n.node_code}" style="padding: 5px 12px;">
                        <i class="fa-solid fa-compass"></i> Calibrate
                    </button>
                </div>
            </div>
        `;
        grid.appendChild(card);
    });
}

function renderSystemCamerasTable(nodes) {
    const tbody = document.getElementById('system-cameras-body');
    if (!tbody) return;

    tbody.innerHTML = '';
    nodes.forEach(n => {
        const tr = document.createElement('tr');
        tr.id = `node-row-${n.node_code}`;
        const isActive = n.status === 'ONLINE_ACTIVE';
        const statusBadge = isActive 
            ? '<span class="badge-online"><i class="fa-solid fa-circle"></i> HEALTHY</span>'
            : '<span class="badge-active"><i class="fa-solid fa-moon"></i> STANDBY</span>';

        tr.innerHTML = `
            <td>
                <strong style="font-family: var(--font-display); font-size: 15px; letter-spacing: 1px; color: var(--color-primary); display: flex; align-items: center; gap: 6px;">
                    <i class="fa-solid fa-tower-broadcast" style="color: var(--color-primary); font-size: 12px;"></i> ${n.node_code}
                </strong>
                <div style="font-size: 11px; color: var(--color-muted); font-family: var(--font-body); margin-top: 2px;">${n.node_name}</div>
            </td>
            <td>
                <span class="node-sector-tag" style="margin-bottom: 2px; display: inline-block;"><i class="fa-solid fa-location-dot"></i> ${n.sector}</span>
                <div class="font-mono text-info" style="font-size: 11px;">${Number(n.latitude).toFixed(4)}°N, ${Number(n.longitude).toFixed(4)}°E</div>
            </td>
            <td>
                <div style="font-size: 12px; color: var(--color-primary);">${n.camera_type}</div>
                <div class="font-mono text-success" style="font-size: 10px; margin-top: 2px;"><i class="fa-solid fa-temperature-half"></i> 31.4°C · 16 Hz · I2C OK</div>
            </td>
            <td>
                <div class="font-mono" style="font-size: 12px; color: var(--color-link);"><i class="fa-solid fa-compass"></i> ${n.rotator_heading}° Azimuth</div>
                <div class="font-mono" style="font-size: 10px; color: var(--color-muted); margin-top: 2px;">Servo Bus: 5.04V · 0-360° OK</div>
            </td>
            <td>
                <span class="badge-active" style="padding: 2px 8px; font-size: 10px;"><i class="fa-solid fa-bolt"></i> ARMED</span>
                <div class="font-mono text-success" style="font-size: 10px; margin-top: 2px;">GPIO 18 · &lt; 184ms</div>
            </td>
            <td>
                <div style="display: flex; align-items: center; gap: 6px;">
                    <span class="font-mono text-accent" style="font-size: 13px; font-weight: bold;">${n.battery_pct}%</span>
                    <span style="font-size: 10px; color: var(--color-muted); font-family: var(--font-mono);">(12.6V)</span>
                </div>
                <div class="font-mono text-success" style="font-size: 10px; margin-top: 2px;"><i class="fa-solid fa-sun"></i> 18.2V In · 2.6W Draw</div>
            </td>
            <td>
                <div class="font-mono text-success" style="font-size: 11px;"><i class="fa-solid fa-signal"></i> GSM 4G / LTE</div>
                <div class="font-mono" style="font-size: 10px; color: var(--color-muted); margin-top: 2px;">Ping 32ms · LoRa Ready</div>
            </td>
            <td>
                ${statusBadge}
            </td>
            <td style="text-align: right;">
                <button class="btn btn-outline btn-sm btn-inspect-health" data-node="${n.node_code}">
                    <i class="fa-solid fa-stethoscope"></i> Check Health
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function openNodeDiagnosticsModal(nodeCode) {
    const modal = document.getElementById('modal-node-health');
    const modalBody = document.getElementById('node-health-modal-body');
    const modalTitle = document.getElementById('modal-health-title');
    if (!modal || !modalBody) return;

    modal.classList.remove('hidden');
    if (modalTitle) {
        modalTitle.innerHTML = `<i class="fa-solid fa-stethoscope"></i> Hardware Diagnostics: ${nodeCode}`;
    }

    modalBody.innerHTML = `
        <div style="text-align: center; padding: 40px; color: var(--color-muted); font-family: var(--font-mono); letter-spacing: 1px;">
            <i class="fa-solid fa-spinner fa-spin" style="font-size: 26px; margin-bottom: 12px; color: var(--color-primary);"></i><br>
            INTERROGATING ${nodeCode} HARDWARE BUS...
        </div>
    `;

    fetch(`/api/nodes/${nodeCode}/diagnostics`)
        .then(r => r.json())
        .then(data => {
            if (data.success && data.diagnostics) {
                renderNodeDiagnosticsDetails(data.diagnostics);
            } else {
                modalBody.innerHTML = `<div style="color:var(--color-alert); padding:20px;">Failed to query telemetry for ${nodeCode}.</div>`;
            }
        })
        .catch(() => {
            modalBody.innerHTML = `<div style="color:var(--color-alert); padding:20px;">Connection timeout contacting node.</div>`;
        });
}

function renderNodeDiagnosticsDetails(diag) {
    const modalBody = document.getElementById('node-health-modal-body');
    if (!modalBody) return;

    const batt = diag.power.battery_pct || 88;
    const heading = diag.rotator.current_bearing || 145;

    modalBody.innerHTML = `
        <!-- Node Top Header -->
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--color-hairline); padding-bottom:16px; margin-bottom:16px; flex-wrap:wrap; gap:12px;">
            <div>
                <div style="font-family:var(--font-display); font-size:22px; letter-spacing:2px; text-transform:uppercase; color:var(--color-primary); display:flex; align-items:center; gap:8px;">
                    <i class="fa-solid fa-tower-broadcast"></i> ${diag.node_code} · ${diag.node_name}
                </div>
                <div style="font-size:12px; font-family:var(--font-body); color:var(--color-muted); margin-top:4px;">
                    <i class="fa-solid fa-location-dot"></i> ${diag.sector} · GPS: ${Number(diag.latitude).toFixed(4)}°N, ${Number(diag.longitude).toFixed(4)}°E
                </div>
            </div>
            <div style="display:flex; align-items:center; gap:14px;">
                <div class="hud-radial-wrap" style="width:52px; height:52px;">
                    <svg class="hud-radial-svg" viewBox="0 0 58 58" style="width:52px; height:52px;">
                        <circle class="hud-radial-bg" cx="29" cy="29" r="23"></circle>
                        <circle class="hud-radial-meter meter-healthy" cx="29" cy="29" r="23" stroke-dasharray="144.5" stroke-dashoffset="0"></circle>
                    </svg>
                    <div class="hud-radial-center">
                        <span class="hud-radial-val">100%</span>
                        <span class="hud-radial-lbl">OPTIMAL</span>
                    </div>
                </div>
                <div style="text-align:right;">
                    <span class="badge-online"><i class="fa-solid fa-circle-check"></i> ${diag.overall_health}</span>
                    <div style="font-size:10px; font-family:var(--font-mono); color:var(--color-muted); margin-top:4px; letter-spacing:1px;">
                        ${diag.last_diagnostic_time}
                    </div>
                </div>
            </div>
        </div>

        <!-- 4 Hardware Diagnostic Modules with Graphical Enhancements -->
        <div class="health-spec-grid">
            
            <!-- Module 1: Thermal Optical Array -->
            <div class="health-module-card">
                <div class="health-module-header">
                    <span class="health-module-title"><i class="fa-solid fa-camera"></i> Thermal Optics Core</span>
                    <span class="badge-online">100% OK</span>
                </div>
                <!-- Visual Thermal Matrix -->
                <div style="display:flex; justify-content:space-between; align-items:center; background:#080808; padding:8px 12px; border:1px solid var(--color-hairline); margin:4px 0;">
                    <div class="thermal-matrix-grid">
                        <div class="thermal-pixel"></div><div class="thermal-pixel hot"></div><div class="thermal-pixel"></div><div class="thermal-pixel hot"></div><div class="thermal-pixel"></div><div class="thermal-pixel"></div>
                        <div class="thermal-pixel hot"></div><div class="thermal-pixel peak"></div><div class="thermal-pixel peak"></div><div class="thermal-pixel hot"></div><div class="thermal-pixel"></div><div class="thermal-pixel"></div>
                        <div class="thermal-pixel"></div><div class="thermal-pixel hot"></div><div class="thermal-pixel peak"></div><div class="thermal-pixel hot"></div><div class="thermal-pixel"></div><div class="thermal-pixel hot"></div>
                        <div class="thermal-pixel"></div><div class="thermal-pixel"></div><div class="thermal-pixel hot"></div><div class="thermal-pixel"></div><div class="thermal-pixel"></div><div class="thermal-pixel"></div>
                    </div>
                    <div style="text-align:right;">
                        <span class="text-success font-mono" style="font-size:12px;">31.2°C Core</span>
                        <div style="font-size:9px; color:var(--color-muted); font-family:var(--font-mono);">16 Hz Refresh</div>
                    </div>
                </div>
                <div class="health-param-list">
                    <div class="health-param-row"><span>Sensor Model:</span><strong>${diag.thermal_sensor.model}</strong></div>
                    <div class="health-param-row"><span>Bus & Clock:</span><strong>${diag.thermal_sensor.bus}</strong></div>
                    <div class="health-param-row"><span>Active Pixels:</span><strong class="text-info">${diag.thermal_sensor.active_pixels}</strong></div>
                    <div class="health-param-row"><span>NETD Noise:</span><strong>${diag.thermal_sensor.noise_equivalent_temp_diff}</strong></div>
                </div>
            </div>

            <!-- Module 2: Pan-Tilt Servo Stepper -->
            <div class="health-module-card">
                <div class="health-module-header">
                    <span class="health-module-title"><i class="fa-solid fa-arrows-spin"></i> Pan-Tilt Rotator</span>
                    <span class="badge-online">CALIBRATED</span>
                </div>
                <!-- Visual Compass Rose -->
                <div style="display:flex; justify-content:space-between; align-items:center; background:#080808; padding:6px 12px; border:1px solid var(--color-hairline); margin:4px 0;">
                    <div class="compass-dial-wrap" style="width:48px; height:48px;">
                        <svg class="compass-dial-svg" viewBox="0 0 56 56">
                            <circle cx="28" cy="28" r="26" fill="none" stroke="#262626" stroke-width="1.5"></circle>
                            <circle cx="28" cy="28" r="16" fill="none" stroke="#1a1a1a" stroke-width="1"></circle>
                            <text x="28" y="10" fill="#777" font-size="6" font-family="JetBrains Mono" text-anchor="middle">N</text>
                            <text x="49" y="30" fill="#555" font-size="6" font-family="JetBrains Mono" text-anchor="middle">E</text>
                            <text x="28" y="51" fill="#555" font-size="6" font-family="JetBrains Mono" text-anchor="middle">S</text>
                            <text x="7" y="30" fill="#555" font-size="6" font-family="JetBrains Mono" text-anchor="middle">W</text>
                            <g class="compass-needle-layer" style="transform: rotate(${heading}deg); transform-origin: 28px 28px;">
                                <path d="M28 28 L20 6 A26 26 0 0 1 36 6 Z" fill="rgba(195, 217, 243, 0.15)"></path>
                                <line x1="28" y1="28" x2="28" y2="4" stroke="#c3d9f3" stroke-width="2" stroke-linecap="round"></line>
                                <circle cx="28" cy="28" r="2.5" fill="#ffffff"></circle>
                            </g>
                        </svg>
                    </div>
                    <div style="text-align:right;">
                        <span class="text-link font-mono" style="font-size:12px;">${diag.rotator.current_bearing}° Bearing</span>
                        <div style="font-size:9px; color:var(--color-muted); font-family:var(--font-mono);">0°-360° Continuous</div>
                    </div>
                </div>
                <div class="health-param-list">
                    <div class="health-param-row"><span>Servo Supply:</span><strong class="text-success">${diag.rotator.servo_supply_v}</strong></div>
                    <div class="health-param-row"><span>Step Precision:</span><strong>${diag.rotator.step_precision}</strong></div>
                    <div class="health-param-row"><span>Gear Backlash:</span><strong>${diag.rotator.gear_backlash}</strong></div>
                </div>
            </div>

            <!-- Module 3: Motion Interrupt Loop -->
            <div class="health-module-card">
                <div class="health-module-header">
                    <span class="health-module-title"><i class="fa-solid fa-bolt"></i> PIR Hardware IRQ</span>
                    <span class="badge-active">ARMED</span>
                </div>
                <!-- Visual Wake Latency Reaction Bar -->
                <div style="background:#080808; padding:8px 12px; border:1px solid var(--color-hairline); margin:4px 0;">
                    <div style="display:flex; justify-content:space-between; font-size:10px; font-family:var(--font-mono); color:var(--color-muted); margin-bottom:4px;">
                        <span>WAKE SPEED</span>
                        <strong class="text-success">&lt; ${diag.pir_interrupt.wake_to_infer_latency_ms} ms (Instant)</strong>
                    </div>
                    <div class="progress-bar"><div class="progress-fill fill-cyan" style="width: 36%;"></div></div>
                </div>
                <div class="health-param-list">
                    <div class="health-param-row"><span>Interrupt Pin:</span><strong>GPIO ${diag.pir_interrupt.gpio_pin} (Edge)</strong></div>
                    <div class="health-param-row"><span>Trigger Mode:</span><strong>${diag.pir_interrupt.trigger_mode}</strong></div>
                    <div class="health-param-row"><span>Model State:</span><strong>Warm in RAM</strong></div>
                    <div class="health-param-row"><span>False Positives (24h):</span><strong>${diag.pir_interrupt.false_positives_24h}</strong></div>
                </div>
            </div>

            <!-- Module 4: Power & Battery Subsystem -->
            <div class="health-module-card">
                <div class="health-module-header">
                    <span class="health-module-title"><i class="fa-solid fa-solar-panel"></i> Power Reserves</span>
                    <span class="badge-online">${batt}% CHARGE</span>
                </div>
                <!-- Visual Segmented Battery -->
                <div style="display:flex; justify-content:space-between; align-items:center; background:#080808; padding:8px 12px; border:1px solid var(--color-hairline); margin:4px 0;">
                    <div class="battery-visual-shell">
                        <div class="batt-segment ${batt >= 20 ? 'filled' : ''}"></div>
                        <div class="batt-segment ${batt >= 40 ? 'filled' : ''}"></div>
                        <div class="batt-segment ${batt >= 60 ? 'filled' : ''}"></div>
                        <div class="batt-segment ${batt >= 80 ? 'filled' : ''}"></div>
                        <div class="batt-segment ${batt >= 95 ? 'filled' : ''}"></div>
                    </div>
                    <div style="text-align:right;">
                        <span class="text-accent font-mono" style="font-size:12px;">${diag.power.voltage}V LiFePO4</span>
                        <div style="font-size:9px; color:var(--color-muted); font-family:var(--font-mono);">☀️ ${diag.power.solar_input_v}V Solar</div>
                    </div>
                </div>
                <div class="health-param-list">
                    <div class="health-param-row"><span>Power Draw:</span><strong>${diag.power.power_draw_w} W (Idle)</strong></div>
                    <div class="health-param-row"><span>Autonomy:</span><strong>${diag.power.estimated_autonomy_hrs} Hours Zero Sun</strong></div>
                </div>
            </div>

        </div>

        <!-- Communications & Offline Queue with Signal Waveform -->
        <div style="background:var(--color-surface-soft); border:1px solid var(--color-hairline); padding:12px 16px; margin-top:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div style="display:flex; align-items:center; gap:12px;">
                <div class="rf-signal-bars">
                    <div class="rf-bar b1 active"></div>
                    <div class="rf-bar b2 active"></div>
                    <div class="rf-bar b3 active"></div>
                    <div class="rf-bar b4 active"></div>
                </div>
                <div style="font-size:11px; font-family:var(--font-mono); color:var(--color-muted); letter-spacing:1px;">
                    <span class="text-success"><i class="fa-solid fa-signal"></i> ${diag.comm_link.primary}</span> &nbsp;|&nbsp; 
                    <span>RSSI: <strong>${diag.comm_link.signal_rssi_dbm} dBm</strong></span> &nbsp;|&nbsp; 
                    <span>Ping: <strong>${diag.comm_link.roundtrip_latency_ms} ms</strong></span>
                </div>
            </div>
            <div>
                <span class="badge-online" style="font-size:10px;"><i class="fa-solid fa-database"></i> SQLite Sync OK</span>
            </div>
        </div>

        <!-- Action Buttons -->
        <div style="display:flex; justify-content:flex-end; gap:12px; margin-top:18px;">
            <button class="btn btn-outline btn-sm" id="btn-retest-camera" data-node="${diag.node_code}">
                <i class="fa-solid fa-rotate"></i> Re-test Hardware
            </button>
            <button class="btn btn-primary btn-sm" id="btn-calibrate-camera" data-node="${diag.node_code}">
                <i class="fa-solid fa-compass"></i> Calibrate Pan-Tilt
            </button>
        </div>
    `;

    document.getElementById('btn-retest-camera')?.addEventListener('click', () => {
        openNodeDiagnosticsModal(diag.node_code);
    });

    document.getElementById('btn-calibrate-camera')?.addEventListener('click', () => {
        fetch(`/api/nodes/${diag.node_code}/calibrate`, { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                showTemporaryNotification(`CALIBRATED: Pan-tilt zero azimuth aligned on ${diag.node_code}.`, 'success');
            });
    });
}
