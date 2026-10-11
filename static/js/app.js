/**
 * PROJECT INDRADHANU - CENTRAL VERIFICATION & EDGE COORDINATION DASHBOARD ENGINE
 * Reflects real backend state from PostgreSQL / Central DB, Registered Edge Nodes,
 * Central AI Verification Engine, and Authenticated Village Siren Controller.
 */

let isSoundMuted = false;
let currentFilter = 'all';
let sightingsData = [];
let contactsData = [];
let registeredNodes = [];
let latestSystemStatus = null;
let latestThreatSighting = null;
let currentInspectedSighting = null;

document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initStationSelector();
    initStationPanel();
    initModals();
    initDeleteConfirmation();
    initEditContactModal();
    initLiveDetectionPoller();
    initSystemLocation();
    fetchSmsGatewayStatus();

    // Load real backend state
    fetchSystemStatus();
    setInterval(fetchSystemStatus, 5000);

    loadDetectionsFromDB();

    if (document.getElementById('contacts-page-table-body')) {
        loadContactsFromDB();
        initContactsSearch();
    }

    if (document.getElementById('system-cameras-hud-grid')) {
        initSystemHealthView();
    }

    if (document.getElementById('siren-history-body')) {
        loadSirenHistoryTable();
    }
});

/* ==========================================================================
   REAL BACKEND SYSTEM & EDGE TELEMETRY POLLING
   ========================================================================== */
function fetchSystemStatus() {
    fetch('/api/system/status')
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            latestSystemStatus = data;
            if (Array.isArray(data.nodes)) {
                registeredNodes = data.nodes;
                populateStationSelector(registeredNodes);
                if (window.renderStationsOnMap && document.getElementById('gis-map')) {
                    window.renderStationsOnMap(registeredNodes);
                }
            }
            updateTopBarTelemetry(data);
            const selector = document.getElementById('camera-node-selector');
            updateStationTelemetryUI(selector ? selector.value : 'ALL');
        })
        .catch(err => console.warn('[System Status Poll]', err));
}

function populateStationSelector(nodes) {
    const selector = document.getElementById('camera-node-selector');
    if (!selector) return;

    const currentVal = selector.value || 'ALL';
    let html = `<option value="ALL">ALL EDGE NODES (${nodes.length})</option>`;
    nodes.forEach(n => {
        const statusShort = n.status === 'ONLINE_ACTIVE' ? 'ONLINE' : 'OFFLINE';
        html += `<option value="${n.node_code}">${n.node_code}: ${n.node_name} [${statusShort}]</option>`;
    });
    selector.innerHTML = html;
    if ([...selector.options].some(o => o.value === currentVal)) {
        selector.value = currentVal;
    }
}

function updateTopBarTelemetry(statusData) {
    const onlineCount = statusData.online_nodes ?? 0;
    const totalCount = statusData.total_nodes ?? 0;
    const pendingQueue = statusData.total_pending_edge_queue ?? 0;
    const sirenInfo = statusData.siren_controller || {};
    const sirenStatus = sirenInfo.status || 'STANDBY';
    const sirenPhysical = Boolean(sirenInfo.physical_siren_active);

    // Top bar network status
    const netTop = document.getElementById('network-status-text');
    const dockNet = document.getElementById('dock-net-label');
    if (netTop) {
        if (onlineCount > 0) {
            netTop.className = 'item-value status-online';
            netTop.innerHTML = `<i class="fa-solid fa-signal"></i> ${onlineCount}/${totalCount} ONLINE`;
        } else {
            netTop.className = 'item-value status-offline';
            netTop.innerHTML = `<i class="fa-solid fa-plug-circle-xmark"></i> 0/${totalCount} ONLINE`;
        }
    }
    if (dockNet) {
        dockNet.textContent = onlineCount > 0 ? `${onlineCount}/${totalCount} Online` : 'Nodes Offline';
    }

    // Top bar queue status
    const queueTop = document.getElementById('queue-status-text');
    if (queueTop) {
        queueTop.textContent = `${pendingQueue} PENDING`;
        queueTop.className = pendingQueue > 0 ? 'item-value status-offline' : 'item-value status-idle';
    }

    // Top bar siren status
    const sirenTop = document.getElementById('telemetry-siren-status');
    if (sirenTop) {
        if (sirenPhysical) {
            sirenTop.className = 'item-value status-offline';
            sirenTop.innerHTML = `<i class="fa-solid fa-bullhorn"></i> SIREN: HARDWARE ACTIVE`;
        } else if (sirenStatus === 'TEST_MODE_VERIFIED') {
            sirenTop.className = 'item-value status-online';
            sirenTop.innerHTML = `<i class="fa-solid fa-vial-circle-check"></i> SIREN: SAFE TEST OK`;
        } else if (sirenStatus === 'CONTROLLER_UNREACHABLE') {
            sirenTop.className = 'item-value status-offline';
            sirenTop.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> SIREN: UNREACHABLE`;
        } else {
            sirenTop.className = 'item-value status-online';
            sirenTop.innerHTML = `<i class="fa-solid fa-bullhorn"></i> SIREN: ${sirenStatus}`;
        }
    }

    // Dashboard ribbon metrics
    const ribbonTitle = document.getElementById('ribbon-state-title');
    if (ribbonTitle) {
        ribbonTitle.textContent = onlineCount > 0
            ? 'CENTRAL COORDINATION SERVER: ONLINE · EDGE LINK ACTIVE'
            : 'CENTRAL COORDINATION SERVER: READY (AWAITING EDGE NODE)';
    }
    const ribbonNodes = document.getElementById('ribbon-nodes-metric');
    if (ribbonNodes) {
        ribbonNodes.innerHTML = `<i class="fa-solid fa-tower-broadcast"></i> ${onlineCount}/${totalCount} Nodes Online`;
    }
    const ribbonSiren = document.getElementById('ribbon-siren-metric');
    if (ribbonSiren) {
        ribbonSiren.innerHTML = `<i class="fa-solid fa-bullhorn"></i> Siren: ${sirenPhysical ? 'HARDWARE ACTIVE' : sirenStatus}`;
    }

    const covEl = document.getElementById('stat-coverage-nodes');
    if (covEl) {
        covEl.textContent = `${onlineCount} / ${totalCount} Nodes`;
    }
}

/* ==========================================================================
   LOAD DETECTIONS FROM CENTRAL DATABASE
   ========================================================================== */
function loadDetectionsFromDB() {
    fetch('/api/detections')
        .then(r => r.json())
        .then(data => {
            if (data.success && Array.isArray(data.detections)) {
                sightingsData = data.detections.map(normalizeDetectionRecord);
            }
            updateDetectionsViews();
        })
        .catch(() => {
            updateDetectionsViews();
        });
}

function normalizeDetectionRecord(d) {
    const detTime = d.detected_at || d.timestamp || d.time || 'Unknown';
    const repTime = d.reported_at || detTime;
    const nodeCode = d.node_code || 'NODE-01';
    const matchedNode = registeredNodes.find(n => n.node_code === nodeCode);

    return {
        id: d.id,
        event_id: d.event_id || `evt-${d.id}`,
        species: d.verified_species || d.species || 'Unknown',
        edge_species: d.edge_species || d.species || 'Unknown',
        edge_confidence: Number(d.edge_confidence ?? d.confidence ?? 0).toFixed(1),
        verified_species: d.verified_species || d.species || 'Unknown',
        verified_confidence: Number(d.verified_confidence ?? d.confidence ?? 0).toFixed(1),
        confidence: Number(d.verified_confidence ?? d.confidence ?? 0).toFixed(1),
        verification_status: d.verification_status || 'VERIFIED',
        verification_notes: d.verification_notes || 'Central AI verified snapshot.',
        siren_triggered: Boolean(d.siren_triggered),
        siren_status: d.siren_status || 'STANDBY',
        scientific: d.scientific_name || d.scientific || d.species,
        lat: Number(d.latitude ?? d.lat ?? 21.1440),
        lon: Number(d.longitude ?? d.lon ?? 79.0870),
        distance_meters: d.distance_meters || 300,
        timestamp: detTime,
        detected_at: detTime,
        reported_at: repTime,
        verified_at: d.verified_at || repTime,
        node_code: nodeCode,
        node_name: d.node_name || (matchedNode ? matchedNode.node_name : `Edge Device ${nodeCode}`),
        camera_type: d.camera_type || (matchedNode ? matchedNode.camera_type : 'Raspberry Pi Edge Camera'),
        sector: d.sector || (matchedNode ? matchedNode.sector : 'Protected Forest Perimeter'),
        rotator_heading: d.rotator_heading || (matchedNode ? matchedNode.rotator_heading : 145),
        image_path: d.image_snapshot_path || d.image_path || '/static/snapshots/tiger_sample.jpg',
        threat_level: d.threat_level || 'CRITICAL',
        latency_badge: d.latency_badge || (d.is_delayed ? 'Offline Delayed' : 'Real-time (< 2s)'),
        is_delayed: Boolean(d.is_delayed),
        latency_seconds: d.latency_seconds || 1
    };
}

function updateDetectionsViews() {
    const dockBadge = document.getElementById('dock-badge-history');
    if (dockBadge) dockBadge.textContent = sightingsData.length;

    if (document.getElementById('gis-map') && window.initTacticalMap) {
        window.initTacticalMap();
        renderInitialThreatMarkers();
    }

    renderDashboardFeed();

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
   AUDIO SIREN & DESKTOP NOTIFICATIONS FOR CENTRAL ALERTS
   ========================================================================== */
let audioCtx = null;
let activeSirenOsc = null;
let activeSirenGain = null;
let activeSirenTimer = null;

function getAudioContext() {
    if (!audioCtx) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (AudioContextClass) {
            audioCtx = new AudioContextClass();
        }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
        audioCtx.resume().catch(() => {});
    }
    return audioCtx;
}

['click', 'keydown', 'touchstart'].forEach(evt => {
    window.addEventListener(evt, () => {
        getAudioContext();
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission().catch(() => {});
        }
    }, { once: false, passive: true });
});

function stopTacticalSiren() {
    if (activeSirenTimer) {
        clearTimeout(activeSirenTimer);
        activeSirenTimer = null;
    }
    if (activeSirenOsc) {
        try {
            activeSirenOsc.stop();
            activeSirenOsc.disconnect();
        } catch (e) {}
        activeSirenOsc = null;
    }
    if (activeSirenGain) {
        try {
            activeSirenGain.disconnect();
        } catch (e) {}
        activeSirenGain = null;
    }
    const audioEl = document.getElementById('siren-audio');
    if (audioEl) {
        audioEl.pause();
        audioEl.currentTime = 0;
    }
}

function playTacticalSiren(durationSeconds = 6) {
    if (isSoundMuted) return;
    stopTacticalSiren();

    const audioEl = document.getElementById('siren-audio');
    if (audioEl) {
        audioEl.currentTime = 0;
        audioEl.play().catch(() => {});
    }

    try {
        const ctx = getAudioContext();
        if (!ctx) return;

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sawtooth';

        const startTime = ctx.currentTime;
        const stepTime = 0.35;
        const steps = Math.floor(durationSeconds / stepTime);

        for (let i = 0; i < steps; i++) {
            const t = startTime + (i * stepTime);
            const freq = (i % 2 === 0) ? 960 : 660;
            osc.frequency.setValueAtTime(freq, t);
        }

        gain.gain.setValueAtTime(0.2, startTime);
        gain.gain.setValueAtTime(0.2, startTime + durationSeconds - 0.4);
        gain.gain.exponentialRampToValueAtTime(0.001, startTime + durationSeconds);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(startTime);
        osc.stop(startTime + durationSeconds);

        activeSirenOsc = osc;
        activeSirenGain = gain;
        activeSirenTimer = setTimeout(() => {
            stopTacticalSiren();
        }, durationSeconds * 1000);
    } catch (err) {
        console.warn('[Audio Siren]', err);
    }
}

function sendDesktopNotification(sighting) {
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    try {
        const notif = new Notification(`🚨 CENTRAL VERIFIED: ${sighting.species.toUpperCase()}`, {
            body: `Node: ${sighting.node_code} | Central AI: ${sighting.verification_status} (${sighting.verified_confidence}%)\nSiren Status: ${sighting.siren_status}`,
            icon: sighting.image_path,
            tag: 'wildlife-alert-' + (sighting.event_id || sighting.id),
            requireInteraction: true
        });
        notif.onclick = () => {
            window.focus();
            openSnapshotModal(sighting);
            notif.close();
        };
    } catch (e) {}
}

/* ==========================================================================
   LIVE EDGE INGESTION LISTENER
   ========================================================================== */
function initLiveDetectionPoller() {
    const soundBtn = document.getElementById('btn-sound-toggle');
    soundBtn?.addEventListener('click', () => {
        isSoundMuted = !isSoundMuted;
        soundBtn.innerHTML = isSoundMuted
            ? '<i class="fa-solid fa-volume-xmark" style="color:#ef4444;"></i>'
            : '<i class="fa-solid fa-volume-high"></i>';
        if (isSoundMuted) stopTacticalSiren();
    });

    document.getElementById('btn-dismiss-threat')?.addEventListener('click', () => {
        document.getElementById('threat-banner')?.classList.add('hidden');
        stopTacticalSiren();
    });

    document.getElementById('btn-global-dismiss')?.addEventListener('click', () => {
        document.getElementById('global-threat-banner')?.classList.add('hidden');
        stopTacticalSiren();
    });

    document.getElementById('btn-threat-inspect')?.addEventListener('click', () => {
        if (latestThreatSighting) openSnapshotModal(latestThreatSighting);
        else if (sightingsData.length > 0) openSnapshotModal(sightingsData[0]);
    });

    document.getElementById('btn-global-inspect')?.addEventListener('click', () => {
        if (latestThreatSighting) openSnapshotModal(latestThreatSighting);
        else if (sightingsData.length > 0) openSnapshotModal(sightingsData[0]);
    });

    let lastSeenEventId = null;
    let isInitialFetch = true;

    setInterval(async () => {
        try {
            const res = await fetch('/api/detections/latest_live');
            const data = await res.json();
            if (data.success && data.latest) {
                const evtId = data.latest.event_id || data.latest.id;
                if (isInitialFetch) {
                    isInitialFetch = false;
                    lastSeenEventId = evtId;
                    return;
                }
                if (evtId && evtId !== lastSeenEventId) {
                    lastSeenEventId = evtId;
                    const newSighting = normalizeDetectionRecord(data.latest);
                    sightingsData = [newSighting, ...sightingsData.filter(s => s.event_id !== newSighting.event_id)];
                    handleNewDetectionUI(newSighting);
                }
            }
        } catch (e) {}
    }, 2000);
}

function handleNewDetectionUI(newSighting) {
    const dockBadge = document.getElementById('dock-badge-history');
    if (dockBadge) dockBadge.textContent = sightingsData.length;

    if (window.addMapThreat) {
        window.addMapThreat(newSighting);
        window.panToSighting(newSighting.lat, newSighting.lon);
    }

    const globalBanner = document.getElementById('global-threat-banner');
    if (globalBanner) {
        const title = document.getElementById('global-threat-title');
        const desc = document.getElementById('global-threat-desc');
        if (title) {
            title.textContent = `🚨 [${newSighting.verification_status}] ${newSighting.species.toUpperCase()} (${newSighting.verified_confidence}%) — NODE ${newSighting.node_code}`;
        }
        if (desc) {
            desc.textContent = `Event ID: ${newSighting.event_id} | Siren: ${newSighting.siren_status} | Location: ${newSighting.lat.toFixed(4)}° N, ${newSighting.lon.toFixed(4)}° E`;
        }
        globalBanner.classList.remove('hidden');
    }

    const banner = document.getElementById('threat-banner');
    if (banner) {
        const title = document.getElementById('threat-title');
        const desc = document.getElementById('threat-desc');
        if (title) title.textContent = `${newSighting.verification_status}: ${newSighting.species.toUpperCase()} ON ${newSighting.node_code}`;
        if (desc) desc.textContent = `Edge: ${newSighting.edge_species} (${newSighting.edge_confidence}%) → Central AI: ${newSighting.verified_species} (${newSighting.verified_confidence}%) | Siren: ${newSighting.siren_status}`;
        banner.classList.remove('hidden');
    }

    if (newSighting.verification_status === 'VERIFIED') {
        const isOnSite = !document.hidden && document.hasFocus();
        if (!isOnSite) {
            playTacticalSiren(8);
            sendDesktopNotification(newSighting);
        } else {
            playTacticalSiren(4);
        }
    }

    latestThreatSighting = newSighting;
    renderDashboardFeed();

    if (document.getElementById('sightings-table-body') || document.getElementById('history-cards-container')) {
        renderHistoryData();
    }

    showTemporaryNotification(
        `Edge Event ${newSighting.node_code}: ${newSighting.species} [${newSighting.verification_status}] — Siren: ${newSighting.siren_status}`,
        newSighting.verification_status === 'VERIFIED' ? 'danger' : 'warning'
    );
}

/* ==========================================================================
   STATION PANEL & NODE TELEMETRY
   ========================================================================== */
function initStationPanel() {
    document.getElementById('btn-close-station-panel')?.addEventListener('click', closeStationPanel);
}

function closeStationPanel() {
    document.querySelector('.dashboard-grid')?.classList.add('panel-closed');
    document.querySelector('.dashboard-sidebar')?.classList.add('panel-hidden');
    triggerMapResize();
}

function openStationPanel() {
    document.querySelector('.dashboard-grid')?.classList.remove('panel-closed');
    document.querySelector('.dashboard-sidebar')?.classList.remove('panel-hidden');
    triggerMapResize();
}

function triggerMapResize() {
    if (window.invalidateMapSize) window.invalidateMapSize();
    setTimeout(() => { if (window.invalidateMapSize) window.invalidateMapSize(); }, 100);
    setTimeout(() => { if (window.invalidateMapSize) window.invalidateMapSize(); }, 280);
}
window.openStationPanel = openStationPanel;
window.closeStationPanel = closeStationPanel;

function initStationSelector() {
    const selector = document.getElementById('camera-node-selector');
    if (!selector) return;

    selector.addEventListener('change', (e) => {
        const val = e.target.value;
        if (typeof window.switchMapStation === 'function') {
            window.switchMapStation(val);
        }
        updateStationTelemetryUI(val);
        openStationPanel();
    });
}

function updateStationTelemetryUI(nodeCode) {
    const panelTitle = document.getElementById('station-panel-title');
    const panelSector = document.getElementById('station-panel-sector');
    const panelStatus = document.getElementById('station-panel-status');
    const panelBattVal = document.getElementById('station-panel-battery-val');
    const panelBattBars = document.getElementById('station-panel-battery-bars');
    const panelBearing = document.getElementById('station-panel-bearing');
    const panelHeartbeat = document.getElementById('station-panel-heartbeat');
    const panelLastSync = document.getElementById('station-panel-last-sync');
    const panelQueue = document.getElementById('station-panel-queue');

    const selectedNode = nodeCode === 'ALL'
        ? (registeredNodes[0] || null)
        : (registeredNodes.find(n => n.node_code === nodeCode) || registeredNodes[0] || null);

    if (!selectedNode) return;

    const onlineCount = registeredNodes.filter(n => n.status === 'ONLINE_ACTIVE').length;
    const totalPending = registeredNodes.reduce((acc, n) => acc + (Number(n.pending_queue_count) || 0), 0);

    if (nodeCode === 'ALL' && registeredNodes.length > 1) {
        if (panelTitle) panelTitle.textContent = `ALL EDGE NODES (${registeredNodes.length})`;
        if (panelSector) panelSector.textContent = `Multi-Device Edge Network (${onlineCount}/${registeredNodes.length} Online)`;
        if (panelStatus) {
            panelStatus.className = onlineCount > 0 ? 'status-badge-online' : 'badge-idle';
            panelStatus.textContent = `${onlineCount}/${registeredNodes.length} ONLINE`;
        }
        if (panelQueue) panelQueue.textContent = `${totalPending} Pending`;
    } else {
        const isOnline = selectedNode.status === 'ONLINE_ACTIVE';
        if (panelTitle) panelTitle.textContent = `Edge Node ${selectedNode.node_code}`;
        if (panelSector) panelSector.textContent = `${selectedNode.node_name} (${selectedNode.sector})`;
        if (panelStatus) {
            panelStatus.className = isOnline ? 'status-badge-online' : 'badge-idle';
            panelStatus.textContent = selectedNode.status || 'OFFLINE';
        }
        if (panelQueue) panelQueue.textContent = `${selectedNode.pending_queue_count || 0} Pending`;
    }

    const batt = Number(selectedNode.battery_pct) || 88;
    const heading = Number(selectedNode.rotator_heading) || 145;

    if (panelBattVal) panelBattVal.textContent = `${batt}%`;
    if (panelBearing) panelBearing.innerHTML = `<i class="fa-solid fa-compass"></i> ${heading}° Azimuth`;
    if (panelHeartbeat) panelHeartbeat.textContent = selectedNode.last_heartbeat || 'Awaiting edge heartbeat';
    if (panelLastSync) panelLastSync.textContent = selectedNode.last_sync_at || 'Awaiting first upload';

    if (panelBattBars) {
        const fullSegments = Math.round(batt / 20);
        let barsHtml = '';
        for (let i = 0; i < 5; i++) {
            barsHtml += `<div class="bar-segment ${i < fullSegments ? 'fill' : 'empty'}"></div>`;
        }
        panelBattBars.innerHTML = barsHtml;
    }
}

window.onStationChanged = function(nodeCode) {
    updateStationTelemetryUI(nodeCode);
    openStationPanel();
};

function renderInitialThreatMarkers() {
    sightingsData.forEach(s => {
        if (window.addMapThreat) window.addMapThreat(s);
    });
}

function formatVerificationBadge(status) {
    if (status === 'VERIFIED') {
        return `<span class="badge-online" style="padding:2px 6px; font-size:9px;"><i class="fa-solid fa-Brain"></i> VERIFIED</span>`;
    }
    if (status === 'REJECTED_FALSE_POSITIVE') {
        return `<span class="badge-critical" style="padding:2px 6px; font-size:9px;"><i class="fa-solid fa-ban"></i> REJECTED FP</span>`;
    }
    return `<span class="badge-high" style="padding:2px 6px; font-size:9px;"><i class="fa-solid fa-circle-question"></i> ${status || 'PENDING'}</span>`;
}

function formatSirenBadge(sirenStatus) {
    const st = sirenStatus || 'STANDBY';
    if (st === 'ACKNOWLEDGED_ACTIVE') {
        return `<span class="badge-critical" style="padding:2px 6px; font-size:9px;"><i class="fa-solid fa-bullhorn"></i> SIREN ACTIVE (HW)</span>`;
    }
    if (st === 'TEST_MODE_VERIFIED') {
        return `<span class="badge-online" style="padding:2px 6px; font-size:9px;"><i class="fa-solid fa-vial-circle-check"></i> TEST MODE OK</span>`;
    }
    if (st === 'COMMAND_SENT') {
        return `<span class="badge-high" style="padding:2px 6px; font-size:9px;"><i class="fa-solid fa-paper-plane"></i> CMD SENT</span>`;
    }
    if (st.startsWith('SUPPRESSED')) {
        return `<span class="badge-idle" style="padding:2px 6px; font-size:9px;"><i class="fa-solid fa-shield"></i> ${st}</span>`;
    }
    return `<span class="badge-idle" style="padding:2px 6px; font-size:9px;"><i class="fa-solid fa-volume-off"></i> ${st}</span>`;
}

function renderDashboardFeed() {
    const feedContainer = document.getElementById('dashboard-recent-feed');
    if (!feedContainer) return;

    feedContainer.innerHTML = '';
    const recent = sightingsData.slice(0, 5);

    if (recent.length === 0) {
        feedContainer.innerHTML = `
            <div style="padding: 20px; text-align: center; color: var(--color-muted); font-size: 11px; font-family: var(--font-mono);">
                <i class="fa-solid fa-shield-cat" style="font-size: 20px; margin-bottom: 6px; display: block; color: var(--color-primary-dim);"></i>
                NO EDGE DETECTIONS RECEIVED YET
            </div>
        `;
        return;
    }

    recent.forEach(s => {
        const item = document.createElement('div');
        const isVerified = s.verification_status === 'VERIFIED';
        item.className = `feed-item ${isVerified ? 'critical' : 'warning'}`;

        item.innerHTML = `
            <div class="feed-item-top">
                <div class="feed-species-wrap">
                    <span class="feed-species-name">${s.species} <small class="font-mono text-info">[${s.node_code}]</small></span>
                    <span class="feed-scientific">Edge: ${s.edge_species} (${s.edge_confidence}%) → Central: ${s.verified_species} (${s.verified_confidence}%)</span>
                </div>
                ${formatVerificationBadge(s.verification_status)}
            </div>
            <div class="feed-item-meta">
                <span><i class="fa-solid fa-location-crosshairs text-info"></i> ${s.lat.toFixed(4)}°N, ${s.lon.toFixed(4)}°E</span>
                <span><i class="fa-regular fa-clock"></i> ${s.timestamp}</span>
            </div>
            <div class="feed-item-footer">
                <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                    <span class="${s.is_delayed ? 'badge-high' : 'badge-online'}" style="font-size: 8.5px; padding: 1px 5px; border-radius: 2px;">
                        <i class="fa-solid ${s.is_delayed ? 'fa-clock-rotate-left' : 'fa-bolt'}"></i> ${s.latency_badge}
                    </span>
                    ${formatSirenBadge(s.siren_status)}
                </div>
                <button class="btn-feed-inspect" onclick="openSnapshotModalById(${s.id})">
                    <i class="fa-solid fa-magnifying-glass-plus"></i> Inspect
                </button>
            </div>
        `;
        feedContainer.appendChild(item);
    });
}

/* ==========================================================================
   PAGE 2: SIGHTINGS HISTORY (LIST VIEW & CARDS VIEW)
   ========================================================================== */
let currentHistoryViewMode = 'list';

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
        btnCards?.classList.remove('active');
        listContainer?.classList.remove('hidden');
        cardsContainer?.classList.add('hidden');
        renderHistoryTableList();
    });

    btnCards?.addEventListener('click', () => {
        currentHistoryViewMode = 'cards';
        btnCards.classList.add('active');
        btnList?.classList.remove('active');
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
    const statTotal = document.getElementById('stat-total-sightings');
    const statCrit = document.getElementById('stat-critical-sightings');
    const statDel = document.getElementById('stat-delayed-sightings');
    const statCov = document.getElementById('stat-coverage-nodes');

    if (statTotal) statTotal.textContent = sightingsData.length;
    if (statCrit) {
        const verCount = sightingsData.filter(s => s.verification_status === 'VERIFIED').length;
        statCrit.textContent = `${verCount} VERIFIED`;
    }
    if (statDel) {
        const delCount = sightingsData.filter(s => s.is_delayed).length;
        statDel.textContent = `${delCount} Delayed`;
    }
    if (statCov && registeredNodes.length > 0) {
        const onlineCount = registeredNodes.filter(n => n.status === 'ONLINE_ACTIVE').length;
        statCov.textContent = `${onlineCount} / ${registeredNodes.length} Nodes`;
    }

    if (currentHistoryViewMode === 'list') {
        renderHistoryTableList();
    } else {
        renderHistoryPageGrid();
    }
}

function renderHistoryTableList() {
    const tbody = document.getElementById('sightings-table-body');
    if (!tbody) return;

    tbody.innerHTML = '';

    const filtered = sightingsData.filter(item => {
        if (currentFilter === 'all') return true;
        return item.species.toLowerCase().includes(currentFilter.toLowerCase()) ||
               item.edge_species.toLowerCase().includes(currentFilter.toLowerCase());
    });

    filtered.forEach(s => {
        const tr = document.createElement('tr');
        const isCritical = s.threat_level === 'CRITICAL';
        const threatBadge = isCritical
            ? '<span class="badge-critical" style="padding:2px 6px; border-radius:3px; font-size:10px;">CRITICAL</span>'
            : '<span class="badge-high" style="padding:2px 6px; border-radius:3px; font-size:10px;">HIGH</span>';

        tr.innerHTML = `
            <td>
                <div class="table-snapshot-thumb" onclick="openSnapshotModalById(${s.id})">
                    <img src="${s.image_path}" alt="${s.species}">
                </div>
            </td>
            <td>
                <strong>${s.edge_species}</strong> <span class="card-conf-badge">${s.edge_confidence}%</span><br>
                <span class="font-mono text-muted" style="font-size:10px;">ID: ${s.event_id.slice(0, 12)}...</span>
            </td>
            <td>
                ${formatVerificationBadge(s.verification_status)}<br>
                <span class="font-mono" style="font-size:11px;">${s.verified_species} (${s.verified_confidence}%)</span>
            </td>
            <td>${threatBadge}</td>
            <td class="font-mono">
                <strong class="text-primary">${s.node_code}</strong><br>
                <span class="text-info" style="font-size:11px;">${s.lat.toFixed(4)}° N, ${s.lon.toFixed(4)}° E</span>
            </td>
            <td class="font-mono">
                <span style="font-size:11px; color:var(--text-muted);">${s.detected_at}</span><br>
                <span class="${s.is_delayed ? 'badge-high' : 'badge-online'}" style="padding:1px 5px; font-size:9px; border-radius:2px; font-weight:700;">
                    <i class="fa-solid ${s.is_delayed ? 'fa-clock-rotate-left' : 'fa-bolt'}"></i> ${s.latency_badge}
                </span>
            </td>
            <td>${formatSirenBadge(s.siren_status)}</td>
            <td>
                <button class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="openSnapshotModalById(${s.id})">
                    <i class="fa-solid fa-magnifying-glass-plus"></i> Inspect
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

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
        const isVerified = s.verification_status === 'VERIFIED';
        const badgeClass = isVerified ? 'badge-critical' : 'badge-high';

        card.innerHTML = `
            <div class="history-card-img-wrap">
                <img src="${s.image_path}" alt="${s.species}">
                <span class="history-badge-top ${badgeClass}">${s.verification_status}</span>
                <span style="position:absolute; bottom:8px; left:8px; font-family:var(--font-mono); font-size:9px; background:rgba(0,0,0,0.8); border:1px solid ${s.is_delayed ? '#f59e0b' : '#10b981'}; color:${s.is_delayed ? '#f59e0b' : '#10b981'}; padding:2px 6px; border-radius:2px; font-weight:700;">
                    <i class="fa-solid ${s.is_delayed ? 'fa-clock-rotate-left' : 'fa-bolt'}"></i> ${s.latency_badge}
                </span>
            </div>
            <div class="history-card-body">
                <div class="card-title-line">
                    <h3>${s.species} <small class="font-mono text-info">[${s.node_code}]</small></h3>
                    <span class="card-conf-badge">${s.verified_confidence}% Ver.</span>
                </div>
                <div class="card-geo-line">
                    <i class="fa-solid fa-microchip"></i> Edge: ${s.edge_species} (${s.edge_confidence}%) · Siren: ${s.siren_status}
                </div>
                <div class="card-meta-line">
                    <span><i class="fa-regular fa-clock"></i> ${s.timestamp}</span>
                    <span>${s.lat.toFixed(4)}°N, ${s.lon.toFixed(4)}°E</span>
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
function loadContactsFromDB() {
    fetch('/api/contacts')
        .then(res => res.json())
        .then(data => {
            if (data.success && Array.isArray(data.contacts)) {
                contactsData = data.contacts.map(c => ({
                    id: c.id,
                    name: c.full_name || c.name,
                    phone: c.phone_number || c.phone,
                    village: c.village_name || c.village || 'Rampur',
                    role: c.role || 'villager',
                    channel: c.role === 'forest_ranger' ? 'SMS + Siren' : (c.role === 'sarpanch' ? 'Priority SMS' : 'Broadcast SMS'),
                    status: c.is_active !== 0 ? 'Active' : 'Inactive'
                }));
                const query = document.getElementById('contact-search-input')?.value.toLowerCase() || '';
                renderContactsFullTable(query);
            }
        })
        .catch(err => {
            console.warn('[Contacts] Failed to fetch contacts:', err);
            renderContactsFullTable();
        });
}

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
        const name = document.getElementById('contact-name').value.trim();
        const phone = document.getElementById('contact-phone').value.trim();
        const village = document.getElementById('contact-village').value;
        const role = document.getElementById('contact-role').value;

        fetch('/api/contacts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ full_name: name, phone_number: phone, village_name: village, role: role })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                e.target.reset();
                document.getElementById('modal-add-contact')?.classList.add('hidden');
                loadContactsFromDB();
                showTemporaryNotification(`Registered ${name} into village SMS alert pool.`, 'success');
            } else {
                showTemporaryNotification(data.message || 'Error saving contact.', 'danger');
            }
        })
        .catch(() => {
            showTemporaryNotification('Network error saving contact.', 'danger');
        });
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
            <td style="white-space: nowrap;">
                <button class="btn btn-warning btn-sm" style="padding: 4px 8px; font-size: 11px; margin-right: 6px;" onclick="testSmsToContact('${c.phone}', '${c.name.replace(/'/g, "\\'")}')" title="Send live test SMS to this contact">
                    <i class="fa-solid fa-paper-plane"></i> TEST SMS
                </button>
                <button class="btn btn-outline btn-sm" style="padding: 4px 8px; font-size: 11px; margin-right: 6px;" onclick="editContactRecord(${c.id})" title="Edit Villager">
                    <i class="fa-solid fa-user-pen text-link"></i> EDIT
                </button>
                <button class="btn btn-outline btn-sm" style="padding: 4px 8px; font-size: 11px;" onclick="deleteContactRecord(${c.id})" title="Delete Villager">
                    <i class="fa-solid fa-trash-can text-danger"></i> DELETE
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

window.editContactRecord = function(id) {
    const contact = contactsData.find(c => c.id === id);
    if (!contact) return;

    const modal = document.getElementById('modal-edit-contact');
    const idInput = document.getElementById('edit-contact-id');
    const nameInput = document.getElementById('edit-contact-name');
    const phoneInput = document.getElementById('edit-contact-phone');
    const villageSelect = document.getElementById('edit-contact-village');
    const roleSelect = document.getElementById('edit-contact-role');

    if (idInput) idInput.value = contact.id;
    if (nameInput) nameInput.value = contact.name || '';
    if (phoneInput) phoneInput.value = contact.phone || '';
    if (villageSelect && contact.village) villageSelect.value = contact.village;
    if (roleSelect && contact.role) roleSelect.value = contact.role;
    if (modal) modal.classList.remove('hidden');
};

function initEditContactModal() {
    const modal = document.getElementById('modal-edit-contact');
    const btnCancel = document.getElementById('btn-cancel-edit-contact');
    const btnClose = document.getElementById('btn-close-edit-contact');
    const form = document.getElementById('form-edit-contact');

    function dismissEditModal() {
        if (modal) modal.classList.add('hidden');
    }

    btnCancel?.addEventListener('click', dismissEditModal);
    btnClose?.addEventListener('click', dismissEditModal);

    form?.addEventListener('submit', (e) => {
        e.preventDefault();
        const id = Number(document.getElementById('edit-contact-id')?.value);
        const name = document.getElementById('edit-contact-name')?.value.trim();
        const phone = document.getElementById('edit-contact-phone')?.value.trim();
        const village = document.getElementById('edit-contact-village')?.value;
        const role = document.getElementById('edit-contact-role')?.value;

        fetch(`/api/contacts/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ full_name: name, phone_number: phone, village_name: village, role: role })
        })
        .then(res => res.json())
        .then(data => {
            dismissEditModal();
            if (data.success) {
                loadContactsFromDB();
                showTemporaryNotification(`Updated contact details for ${name}.`, 'success');
            } else {
                showTemporaryNotification(data.message || 'Error updating contact.', 'danger');
            }
        })
        .catch(() => {
            dismissEditModal();
            showTemporaryNotification('Network error updating contact.', 'danger');
        });
    });
}

let pendingDeleteContactId = null;

window.deleteContactRecord = function(id) {
    pendingDeleteContactId = id;
    const modal = document.getElementById('modal-delete-confirm');
    const contact = contactsData.find(c => c.id === id);
    const subEl = document.getElementById('delete-confirm-sub');
    if (subEl && contact) {
        subEl.textContent = `Target: ${contact.name} (${contact.village} • ${contact.phone}) will be removed from directory.`;
    }
    modal?.classList.remove('hidden');
};

function initDeleteConfirmation() {
    const modal = document.getElementById('modal-delete-confirm');
    const dismiss = () => {
        pendingDeleteContactId = null;
        modal?.classList.add('hidden');
    };
    document.getElementById('btn-cancel-delete')?.addEventListener('click', dismiss);
    document.getElementById('btn-close-delete-confirm')?.addEventListener('click', dismiss);
    document.getElementById('btn-confirm-delete')?.addEventListener('click', () => {
        if (pendingDeleteContactId !== null) {
            fetch(`/api/contacts/${pendingDeleteContactId}`, { method: 'DELETE' })
                .then(res => res.json())
                .then(() => {
                    dismiss();
                    loadContactsFromDB();
                    showTemporaryNotification('Village contact removed from directory.', 'warning');
                })
                .catch(() => dismiss());
        }
    });
}

/* ==========================================================================
   MODALS: SNAPSHOT VERIFICATION DOSSIER
   ========================================================================== */
function initModals() {
    const snapModal = document.getElementById('modal-snapshot') || document.getElementById('snapshot-modal');
    const nodeHealthModal = document.getElementById('modal-node-health');
    const addContactModal = document.getElementById('modal-add-contact');

    const closeBtn = document.getElementById('btn-close-snapshot') || document.getElementById('btn-close-modal');
    closeBtn?.addEventListener('click', () => snapModal?.classList.add('hidden'));

    document.getElementById('btn-close-node-health')?.addEventListener('click', () => {
        nodeHealthModal?.classList.add('hidden');
    });

    window.addEventListener('click', (e) => {
        if (e.target === snapModal) snapModal.classList.add('hidden');
        if (e.target === nodeHealthModal) nodeHealthModal.classList.add('hidden');
        if (e.target === addContactModal) addContactModal.classList.add('hidden');
    });

    window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            snapModal?.classList.add('hidden');
            nodeHealthModal?.classList.add('hidden');
            addContactModal?.classList.add('hidden');
        }
    });

    document.querySelectorAll('.toolbar-filter-buttons .filter-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.toolbar-filter-buttons .filter-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            const img = document.getElementById('snapshot-modal-img');
            if (!img) return;
            const mode = this.dataset.imgFilter;
            if (mode === 'normal') img.style.filter = 'none';
            else if (mode === 'ironbow') img.style.filter = 'contrast(1.35) saturate(1.8) hue-rotate(330deg)';
            else if (mode === 'invert') img.style.filter = 'invert(1) hue-rotate(180deg)';
            else if (mode === 'contrast') img.style.filter = 'contrast(2.2) brightness(1.1) grayscale(0.25)';
        });
    });

    document.getElementById('btn-inspect-dispatch-sms')?.addEventListener('click', () => {
        triggerManualAlert();
    });
}

function triggerManualAlert() {
    const speciesName = currentInspectedSighting?.species || 'Tiger';
    const nodeCode = currentInspectedSighting?.node_code || 'NODE-01';
    const scientificName = currentInspectedSighting?.scientific || 'Panthera tigris';
    const threatLevel = currentInspectedSighting?.threat_level || 'CRITICAL';
    const distanceM = currentInspectedSighting?.distance_meters || 280;

    showTemporaryNotification(`[DISPATCHING SMS] Transmitting emergency alert to registered contacts...`, 'info');

    fetch('/api/sms/dispatch-alert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            species: speciesName,
            scientific_name: scientificName,
            threat_level: threatLevel,
            node_code: nodeCode,
            distance_m: distanceM
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showTemporaryNotification(`[SMS PROCESSED] Alert processed for ${data.sent_count}/${data.total_contacts} contacts.`, 'success');
        } else {
            showTemporaryNotification(`[SMS Failed] ${data.message}`, 'danger');
        }
    })
    .catch(err => {
        showTemporaryNotification(`[SMS Error] ${err.message}`, 'danger');
    });
}
window.triggerManualAlert = triggerManualAlert;

function openSnapshotModal(sighting) {
    const modal = document.getElementById('modal-snapshot') || document.getElementById('snapshot-modal');
    if (!modal) return;

    currentInspectedSighting = sighting;

    const species = sighting.species || 'Unknown Wildlife';
    const edgeSpecies = sighting.edge_species || species;
    const edgeConf = sighting.edge_confidence || sighting.confidence || '0.0';
    const verSpecies = sighting.verified_species || species;
    const verConf = sighting.verified_confidence || sighting.confidence || '0.0';
    const verStatus = sighting.verification_status || 'VERIFIED';
    const verNotes = sighting.verification_notes || 'Central AI verified snapshot.';
    const sirenStatus = sighting.siren_status || 'STANDBY';
    const eventId = sighting.event_id || `evt-${sighting.id}`;
    const lat = Number(sighting.lat) || 21.1440;
    const lon = Number(sighting.lon) || 79.0870;
    const distanceMeters = sighting.distance_meters || 300;
    const threatLevel = sighting.threat_level || 'CRITICAL';
    const isCritical = threatLevel === 'CRITICAL';
    const imagePath = sighting.image_path || '/static/snapshots/tiger_sample.jpg';
    const nodeCode = sighting.node_code || 'NODE-01';
    const nodeName = sighting.node_name || `Edge Node ${nodeCode}`;
    const cameraType = sighting.camera_type || 'Raspberry Pi Edge Camera';
    const sector = sighting.sector || 'Protected Forest Perimeter';
    const detectedAt = sighting.detected_at || sighting.timestamp;
    const reportedAt = sighting.reported_at || detectedAt;

    const title = document.getElementById('snapshot-modal-title');
    if (title) {
        title.innerHTML = `<i class="fa-solid fa-paw" style="color:${isCritical ? '#ef4444' : '#f59e0b'};"></i> ${species.toUpperCase()} — CENTRAL VERIFICATION DOSSIER`;
    }

    const nodePill = document.getElementById('dossier-node-pill');
    if (nodePill) {
        nodePill.innerHTML = `<i class="fa-solid fa-tower-broadcast"></i> ${nodeCode}`;
    }

    const autoStatus = document.getElementById('dossier-auto-status');
    if (autoStatus) {
        autoStatus.textContent = `SIREN: ${sirenStatus}`;
    }

    const img = document.getElementById('snapshot-modal-img');
    if (img) {
        img.src = imagePath;
        img.alt = `${species} Snapshot`;
        img.style.filter = 'none';
    }

    const sensorEl = document.getElementById('dossier-hud-sensor');
    if (sensorEl) sensorEl.textContent = cameraType;

    const tempEl = document.getElementById('dossier-hud-temp');
    if (tempEl) tempEl.innerHTML = `<i class="fa-solid fa-brain"></i> CENTRAL AI: ${verStatus}`;

    const reticleLabel = document.getElementById('reticle-species-label');
    if (reticleLabel) reticleLabel.textContent = `${verSpecies.toUpperCase()} (${verConf}%)`;

    const hudNodeEl = document.getElementById('dossier-hud-node');
    if (hudNodeEl) hudNodeEl.innerHTML = `<i class="fa-solid fa-camera"></i> ${nodeCode}`;

    const filePathEl = document.getElementById('dossier-filepath');
    if (filePathEl) filePathEl.innerHTML = `<i class="fa-regular fa-file-image"></i> <span>Event ID: ${eventId} · ${imagePath}</span>`;

    const meta = document.getElementById('snapshot-modal-meta');
    if (meta) {
        meta.innerHTML = `
            <div class="dossier-card">
                <label><i class="fa-solid fa-microchip text-info"></i> 1. EDGE DEVICE DETECTION</label>
                <div class="card-value-primary">
                    <span style="color:var(--color-primary); font-size:14px; font-weight:700;">${edgeSpecies} (${edgeConf}%)</span>
                    <span class="badge-active" style="padding:2px 6px; font-size:8.5px;">EDGE AI</span>
                </div>
                <div class="card-value-sub font-mono" style="font-size:10px;">Event ID: ${eventId}</div>
                <div class="card-value-sub" style="font-size:9px; color:var(--color-muted-soft);">Raspberry Pi Local SQLite Buffered</div>
            </div>

            <div class="dossier-card">
                <label><i class="fa-solid fa-brain text-success"></i> 2. CENTRAL AI VERIFICATION</label>
                <div class="card-value-primary">
                    <span style="color:#10b981; font-size:14px; font-weight:700;">${verSpecies} (${verConf}%)</span>
                    ${formatVerificationBadge(verStatus)}
                </div>
                <div class="conf-meter-track">
                    <div class="conf-meter-fill" style="width:${Math.min(100, parseFloat(verConf) || 0)}%;"></div>
                </div>
                <div class="card-value-sub" style="font-size:9.5px;">${verNotes}</div>
            </div>

            <div class="dossier-card">
                <label><i class="fa-solid fa-tower-broadcast text-info"></i> 3. EDGE NODE ORIGIN</label>
                <div class="card-value-primary">
                    <span style="color:var(--color-link); font-size:14px; font-weight:700;"><i class="fa-solid fa-camera"></i> ${nodeCode}</span>
                </div>
                <div class="card-value-sub">${nodeName}</div>
                <div class="card-value-sub" style="font-size:9px; color:var(--color-muted-soft);">${cameraType}</div>
            </div>

            <div class="dossier-card">
                <label><i class="fa-solid fa-location-crosshairs text-info"></i> 4. LOCATION &amp; SECTOR</label>
                <div class="card-value-primary">
                    <span style="color:#06b6d4; font-size:12px; font-weight:700;">${lat.toFixed(5)}° N, ${lon.toFixed(5)}° E</span>
                </div>
                <div class="card-value-sub">${sector} (~${distanceMeters}m from village)</div>
            </div>

            <div class="dossier-card">
                <label><i class="fa-solid fa-clock text-info"></i> 5. EDGE DETECTED AT</label>
                <div class="card-value-primary">
                    <span style="color:var(--color-primary); font-size:12px; font-weight:700;">${detectedAt}</span>
                </div>
                <div class="card-value-sub">Captured on edge device before upload</div>
            </div>

            <div class="dossier-card">
                <label><i class="fa-solid fa-cloud-arrow-up text-warning"></i> 6. CENTRAL SYNC &amp; LATENCY</label>
                <div class="card-value-primary">
                    <span style="color:var(--color-warning); font-size:12px; font-weight:700;">${reportedAt}</span>
                    <span class="${sighting.is_delayed ? 'badge-high' : 'badge-online'}" style="padding:2px 5px; font-size:8.5px; font-weight:700;">
                        ${sighting.latency_badge}
                    </span>
                </div>
                <div class="card-value-sub">
                    ${sighting.is_delayed ? '⚠️ Delayed sync after offline outage (Siren auto-suppressed if stale)' : '⚡ Real-time authenticated edge upload'}
                </div>
            </div>

            <div class="dossier-card card-span-2">
                <label><i class="fa-solid fa-bullhorn text-danger"></i> 7. VILLAGE SIREN ACTIVATION STATUS</label>
                <div class="card-value-primary">
                    ${formatSirenBadge(sirenStatus)}
                    <span style="font-size:11px; color:var(--color-muted);">
                        ${sirenStatus === 'ACKNOWLEDGED_ACTIVE'
                            ? 'Physical GPIO Relay Confirmed Active'
                            : (sirenStatus === 'TEST_MODE_VERIFIED'
                                ? 'Verified in SAFE_TEST Mode (Physical Siren Relay Not Energized)'
                                : 'Siren policy evaluated by Central Server')}
                    </span>
                </div>
            </div>
        `;
    }

    modal.classList.remove('hidden');
}

window.openSnapshotModal = openSnapshotModal;
window.openSnapshotModalById = function(id) {
    const item = sightingsData.find(s => s.id === id || s.id === Number(id));
    if (item) openSnapshotModal(item);
};

function showTemporaryNotification(message, type = 'info') {
    const toast = document.createElement('div');
    const color = type === 'danger' ? '#ef4444' : (type === 'warning' ? '#f59e0b' : (type === 'success' ? '#10b981' : '#06b6d4'));

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
        max-width: 360px;
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
   PAGE 5: EDGE NODES NETWORK
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
            if (data.success && Array.isArray(data.nodes)) {
                registeredNodes = data.nodes;
                renderNodesGrid(data.nodes);
            }
        })
        .catch(err => console.warn('[Load Nodes]', err));
}

function renderNodesGrid(nodes) {
    const container = document.getElementById('nodes-page-grid');
    if (!container) return;

    container.innerHTML = '';
    const totalEl = document.getElementById('stat-total-nodes');
    if (totalEl) totalEl.textContent = nodes.length;
    const activeEl = document.getElementById('stat-active-nodes');
    if (activeEl) {
        const activeCount = nodes.filter(n => n.status === 'ONLINE_ACTIVE').length;
        const offlineCount = nodes.length - activeCount;
        activeEl.textContent = `${activeCount} Online / ${offlineCount} Offline`;
    }

    nodes.forEach(node => {
        const card = document.createElement('div');
        card.className = 'node-card';
        const isActive = node.status === 'ONLINE_ACTIVE';
        const statusBadge = isActive
            ? '<span class="badge-online"><i class="fa-solid fa-circle"></i> ONLINE_ACTIVE</span>'
            : '<span class="badge-idle"><i class="fa-solid fa-plug-circle-xmark"></i> OFFLINE</span>';

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
                    <label>Camera Hardware</label>
                    <span>${node.camera_type}</span>
                </div>
                <div class="node-spec-item">
                    <label>GPS Coordinates</label>
                    <span class="font-mono text-info">${Number(node.latitude).toFixed(4)}°N, ${Number(node.longitude).toFixed(4)}°E</span>
                </div>
                <div class="node-spec-item">
                    <label>Last Heartbeat</label>
                    <span class="font-mono">${node.last_heartbeat || 'Never'}</span>
                </div>
                <div class="node-spec-item">
                    <label>Last Sync / Queue</label>
                    <span class="font-mono">${node.last_sync_at || 'Never'} (${node.pending_queue_count || 0} pending)</span>
                </div>
            </div>
            <div class="node-card-actions">
                <a href="/" class="btn btn-primary" style="width: 100%; justify-content: center;"><i class="fa-solid fa-map-location-dot"></i> View on Map</a>
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
            node_code: document.getElementById('node-code').value.trim(),
            node_name: document.getElementById('node-name').value.trim(),
            sector: document.getElementById('node-sector').value.trim(),
            latitude: parseFloat(document.getElementById('node-lat').value),
            longitude: parseFloat(document.getElementById('node-lon').value),
            camera_type: document.getElementById('node-camera-type').value,
            api_key: document.getElementById('node-api-key')?.value.trim() || ''
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
                fetchSystemStatus();
                showTemporaryNotification(`Registered edge device ${payload.node_code}.`, 'success');
            } else {
                showTemporaryNotification(data.message || 'Failed to register edge device.', 'danger');
            }
        });
    });
}

/* ==========================================================================
   PAGE 4: SYSTEM HEALTH, EDGE FLEET DIAGNOSTICS & SIREN CONTROLLER
   ========================================================================== */
function initSystemHealthView() {
    if (window.systemHealthInitialized) {
        loadPlantedCamerasHealth();
        loadSirenHistoryTable();
        return;
    }
    window.systemHealthInitialized = true;

    const btnCards = document.getElementById('btn-cam-view-cards');
    const btnList = document.getElementById('btn-cam-view-list');
    const hudGrid = document.getElementById('system-cameras-hud-grid');
    const tableWrap = document.getElementById('system-cameras-table-wrap');

    function switchToCardsView() {
        btnCards?.classList.add('active');
        btnList?.classList.remove('active');
        hudGrid?.classList.remove('hidden');
        tableWrap?.classList.add('hidden');
    }

    function switchToListView() {
        btnList?.classList.add('active');
        btnCards?.classList.remove('active');
        tableWrap?.classList.remove('hidden');
        hudGrid?.classList.add('hidden');
    }

    switchToCardsView();
    btnCards?.addEventListener('click', (e) => { e.preventDefault(); switchToCardsView(); });
    btnList?.addEventListener('click', (e) => { e.preventDefault(); switchToListView(); });

    loadPlantedCamerasHealth();
    loadSirenHistoryTable();

    document.getElementById('btn-scan-fleet-health')?.addEventListener('click', () => {
        showTemporaryNotification('Refreshing live edge node telemetry & siren history...', 'info');
        loadPlantedCamerasHealth();
        loadSirenHistoryTable();
    });

    document.getElementById('btn-manual-sync')?.addEventListener('click', () => {
        fetch('/api/offline/flush', { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                showTemporaryNotification(data.message || 'Offline SMS queue processed.', data.success ? 'success' : 'warning');
            });
    });

    document.addEventListener('click', (e) => {
        const inspectBtn = e.target.closest('.btn-inspect-health');
        if (inspectBtn) {
            const nodeCode = inspectBtn.getAttribute('data-node');
            if (nodeCode) openNodeDiagnosticsModal(nodeCode);
        }
    });
}
window.initSystemHealthView = initSystemHealthView;

function loadPlantedCamerasHealth() {
    fetch('/api/nodes')
        .then(r => r.json())
        .then(data => {
            if (data.success && Array.isArray(data.nodes)) {
                registeredNodes = data.nodes;
                renderSystemCamerasHud(data.nodes);
                renderSystemCamerasTable(data.nodes);
                const badge = document.getElementById('fleet-health-summary-badge');
                if (badge) {
                    const online = data.nodes.filter(n => n.status === 'ONLINE_ACTIVE').length;
                    badge.className = online > 0 ? 'badge-online' : 'badge-idle';
                    badge.innerHTML = `<i class="fa-solid fa-tower-broadcast"></i> ${online}/${data.nodes.length} NODES ONLINE`;
                }
            }
        })
        .catch(err => console.error('Failed to load edge nodes:', err));
}

function renderSystemCamerasHud(nodes) {
    const grid = document.getElementById('system-cameras-hud-grid');
    if (!grid) return;

    grid.innerHTML = '';
    nodes.forEach(n => {
        const card = document.createElement('div');
        card.className = 'cam-hud-card';
        const batt = n.battery_pct || 88;
        const isActive = n.status === 'ONLINE_ACTIVE';
        const statusBadge = isActive
            ? '<span class="badge-online" style="padding: 2px 8px; font-size: 9px; margin-left: 4px;"><i class="fa-solid fa-circle"></i> ONLINE_ACTIVE</span>'
            : '<span class="badge-idle" style="padding: 2px 8px; font-size: 9px; margin-left: 4px;"><i class="fa-solid fa-plug-circle-xmark"></i> OFFLINE</span>';

        card.innerHTML = `
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
            </div>
            <div class="cam-hud-instruments">
                <div class="hud-instrument-box">
                    <span class="hud-inst-title"><i class="fa-solid fa-heart-pulse"></i> Last Heartbeat</span>
                    <span class="hud-inst-readout font-mono text-link">${n.last_heartbeat || 'Never'}</span>
                </div>
                <div class="hud-instrument-box">
                    <span class="hud-inst-title"><i class="fa-solid fa-cloud-arrow-up"></i> Last Event Sync</span>
                    <span class="hud-inst-readout font-mono text-success">${n.last_sync_at || 'Never'}</span>
                </div>
                <div class="hud-instrument-box">
                    <span class="hud-inst-title"><i class="fa-solid fa-database"></i> Edge SQLite Queue</span>
                    <span class="hud-inst-readout font-mono text-accent">${n.pending_queue_count || 0} Pending · ${batt}% Batt</span>
                </div>
            </div>
            <div class="cam-hud-footer">
                <div class="cam-hud-telemetry-pills">
                    <div class="latency-meter-badge">
                        <i class="fa-solid fa-camera text-info"></i>
                        <span>${n.camera_type}</span>
                    </div>
                </div>
                <div class="cam-hud-actions">
                    <button class="btn btn-outline btn-sm btn-inspect-health" data-node="${n.node_code}" style="padding: 5px 12px; width: 100%; justify-content: center;">
                        <i class="fa-solid fa-chart-line"></i> Edge Diagnostics
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
        const isActive = n.status === 'ONLINE_ACTIVE';
        const statusBadge = isActive
            ? '<span class="badge-online"><i class="fa-solid fa-circle"></i> ONLINE_ACTIVE</span>'
            : '<span class="badge-idle"><i class="fa-solid fa-plug-circle-xmark"></i> OFFLINE</span>';

        tr.innerHTML = `
            <td>
                <strong>${n.node_code}</strong>
                <div style="font-size: 11px; color: var(--color-muted);">${n.node_name}</div>
            </td>
            <td>
                <span class="node-sector-tag">${n.sector}</span>
                <div class="font-mono text-info" style="font-size: 11px;">${Number(n.latitude).toFixed(4)}°N, ${Number(n.longitude).toFixed(4)}°E</div>
            </td>
            <td>${n.camera_type}</td>
            <td class="font-mono">${n.last_heartbeat || 'Never'}</td>
            <td class="font-mono">${n.last_sync_at || 'Never'}</td>
            <td class="font-mono">${n.pending_queue_count || 0} Pending</td>
            <td class="font-mono">${n.battery_pct || 88}%</td>
            <td>${statusBadge}</td>
            <td style="text-align: right;">
                <button class="btn btn-outline btn-sm btn-inspect-health" data-node="${n.node_code}">
                    <i class="fa-solid fa-stethoscope"></i> Inspect
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function openNodeDiagnosticsModal(nodeCode) {
    const modal = document.getElementById('modal-node-health');
    const modalBody = document.getElementById('node-health-modal-body');
    if (!modal || !modalBody) return;

    modal.classList.remove('hidden');
    modalBody.innerHTML = `<div style="padding:30px; text-align:center; font-family:var(--font-mono);">Querying ${nodeCode} diagnostics...</div>`;

    fetch(`/api/nodes/${nodeCode}/diagnostics`)
        .then(r => r.json())
        .then(data => {
            if (data.success && data.diagnostics) {
                renderNodeDiagnosticsDetails(data.diagnostics);
            } else {
                modalBody.innerHTML = `<div style="color:var(--color-alert); padding:30px; text-align:center;">Failed to query telemetry for ${nodeCode}.</div>`;
            }
        })
        .catch(() => {
            modalBody.innerHTML = `<div style="color:var(--color-alert); padding:30px; text-align:center;">Error querying diagnostics.</div>`;
        });
}

function renderNodeDiagnosticsDetails(diag) {
    const modalBody = document.getElementById('node-health-modal-body');
    if (!modalBody) return;

    const cam = diag.camera_sensor || {};
    const edgeAi = diag.edge_ai || {};
    const syncEng = diag.sync_engine || {};
    const pwr = diag.power || {};

    modalBody.innerHTML = `
        <div class="diag-summary-banner">
            <div class="diag-summary-node">
                <div class="diag-summary-badge-line">
                    <span class="diag-node-pill"><i class="fa-solid fa-tower-broadcast"></i> ${diag.node_code}</span>
                    <span class="${diag.status === 'ONLINE_ACTIVE' ? 'badge-online' : 'badge-idle'}">${diag.status}</span>
                </div>
                <div class="diag-summary-station-title">${diag.node_name}</div>
                <div class="diag-summary-geo">
                    <span>${diag.sector}</span> ·
                    <span class="font-mono text-info">${Number(diag.latitude).toFixed(4)}°N, ${Number(diag.longitude).toFixed(4)}°E</span>
                </div>
            </div>
        </div>
        <div class="diag-modules-grid">
            <div class="diag-module-card">
                <div class="diag-module-header">
                    <div class="diag-module-title"><i class="fa-solid fa-camera text-primary"></i> <span>Edge Camera &amp; AI</span></div>
                    <span class="badge-online">${cam.status || 'STANDBY'}</span>
                </div>
                <div class="diag-fields-list">
                    <div class="diag-field-row"><span class="diag-field-label">CAMERA</span><span class="diag-field-val">${cam.model || 'USB/CSI Camera'}</span></div>
                    <div class="diag-field-row"><span class="diag-field-label">EDGE AI MODEL</span><span class="diag-field-val">${edgeAi.model || 'YOLOv8n + MobileNetV3'}</span></div>
                    <div class="diag-field-row"><span class="diag-field-label">TARGET HARDWARE</span><span class="diag-field-val">${edgeAi.target_hardware || 'Raspberry Pi 3 Model B+'}</span></div>
                    <div class="diag-field-row"><span class="diag-field-label">SUPPORTED ANIMALS</span><span class="diag-field-val">${(edgeAi.supported_species || []).join(', ')}</span></div>
                </div>
            </div>
            <div class="diag-module-card">
                <div class="diag-module-header">
                    <div class="diag-module-title"><i class="fa-solid fa-arrows-rotate text-info"></i> <span>Offline SQLite &amp; Sync</span></div>
                    <span class="badge-active">${syncEng.pending_queue_count || 0} Queued</span>
                </div>
                <div class="diag-fields-list">
                    <div class="diag-field-row"><span class="diag-field-label">LAST HEARTBEAT</span><span class="diag-field-val font-mono">${syncEng.last_heartbeat || 'Never'}</span></div>
                    <div class="diag-field-row"><span class="diag-field-label">LAST SYNC AT</span><span class="diag-field-val font-mono">${syncEng.last_sync_at || 'Never'}</span></div>
                    <div class="diag-field-row"><span class="diag-field-label">LOCAL BUFFER</span><span class="diag-field-val">${syncEng.local_buffer || 'SQLite (edge.db)'}</span></div>
                    <div class="diag-field-row"><span class="diag-field-label">BATTERY</span><span class="diag-field-val">${pwr.battery_pct || 88}%</span></div>
                </div>
            </div>
        </div>
    `;
}

/* ==========================================================================
   VILLAGE SIREN CONTROLLER HISTORY & SAFE TEST TRIGGER
   ========================================================================== */
function loadSirenHistoryTable() {
    const tbody = document.getElementById('siren-history-body');
    const modeBadge = document.getElementById('siren-controller-mode-badge');

    fetch('/api/siren/history')
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            if (modeBadge && data.current_status) {
                const st = data.current_status;
                modeBadge.className = st.physical_siren_active ? 'badge-critical' : 'badge-online';
                modeBadge.innerHTML = `<i class="fa-solid fa-bullhorn"></i> MODE: ${st.mode || 'SAFE_TEST'} · STATUS: ${st.status || 'STANDBY'}`;
            }
            if (!tbody) return;
            const alerts = data.alerts || [];
            if (alerts.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:18px; color:var(--color-muted);">No siren activations recorded yet.</td></tr>`;
                return;
            }
            tbody.innerHTML = '';
            alerts.forEach(a => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="font-mono" style="font-size:11px;">${a.event_id}</td>
                    <td class="font-mono">${a.node_code}</td>
                    <td><strong>${a.species}</strong> (${Number(a.verified_confidence || 0).toFixed(1)}%)</td>
                    <td><span class="badge-active">${a.trigger_mode}</span></td>
                    <td class="font-mono">${a.command_sent ? '<span class="text-success">YES</span>' : '<span class="text-muted">NO</span>'}</td>
                    <td class="font-mono">${a.controller_ack ? '<span class="text-success">ACK</span>' : '<span class="text-warning">NO ACK</span>'}</td>
                    <td class="font-mono">${a.physical_siren_active ? '<span class="badge-critical">ENERGIZED</span>' : '<span class="badge-idle">0 (SAFE)</span>'}</td>
                    <td>${formatSirenBadge(a.status)}<div style="font-size:10px; color:var(--color-muted); margin-top:2px;">${a.detail || ''}</div></td>
                    <td class="font-mono" style="font-size:11px;">${a.triggered_at || ''}</td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(err => console.warn('[Siren History]', err));
}

window.triggerSafeSirenTest = function() {
    showTemporaryNotification('Sending authenticated SAFE_TEST command to Siren Controller...', 'info');
    fetch('/api/siren/trigger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            mode: 'SAFE_TEST',
            species: 'tiger',
            verified_confidence: 99.0,
            node_code: 'NODE-01',
            duration_sec: 5
        })
    })
    .then(r => r.json())
    .then(data => {
        const res = data.siren_result || {};
        showTemporaryNotification(
            `Siren Test Result: [${res.status || 'UNKNOWN'}] ${res.detail || ''}`,
            res.status === 'TEST_MODE_VERIFIED' ? 'success' : 'warning'
        );
        loadSirenHistoryTable();
        fetchSystemStatus();
    })
    .catch(err => {
        showTemporaryNotification(`Siren test error: ${err.message}`, 'danger');
    });
};

/* ==========================================================================
   SMS ALERT GATEWAY & SYSTEM LOCATION
   ========================================================================== */
function fetchSmsGatewayStatus() {
    fetch('/api/sms/config')
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            const modeBadge = document.getElementById('sms-gateway-mode-badge');
            const keyBadge = document.getElementById('sms-gateway-key-badge');
            const phoneInput = document.getElementById('test-sms-phone-input');

            if (phoneInput && data.test_mobile_number) {
                phoneInput.value = data.test_mobile_number;
            }
            if (modeBadge) {
                modeBadge.textContent = data.sms_mode || 'SIMULATION';
            }
            if (keyBadge) {
                keyBadge.textContent = (data.has_fast2sms_key || data.has_twilio_token) ? 'API Key Configured' : 'Simulation Mode';
            }
        })
        .catch(() => {});
}

window.openSmsSettingsModal = function() {
    document.getElementById('modal-sms-settings')?.classList.remove('hidden');
};
window.closeSmsSettingsModal = function() {
    document.getElementById('modal-sms-settings')?.classList.add('hidden');
};
window.toggleSmsProviderFields = function() {
    const mode = document.getElementById('sms-mode-select')?.value;
    const fastFields = document.getElementById('fields-fast2sms');
    const twilioFields = document.getElementById('fields-twilio');
    if (fastFields) fastFields.style.display = (mode === 'FAST2SMS') ? 'block' : 'none';
    if (twilioFields) twilioFields.style.display = (mode === 'TWILIO') ? 'block' : 'none';
};

window.saveSmsGatewayConfig = function(e) {
    if (e) e.preventDefault();
    const payload = {
        sms_mode: document.getElementById('sms-mode-select')?.value,
        fast2sms_api_key: document.getElementById('cfg-fast2sms-key')?.value.trim(),
        twilio_account_sid: document.getElementById('cfg-twilio-sid')?.value.trim(),
        twilio_auth_token: document.getElementById('cfg-twilio-token')?.value.trim(),
        twilio_from_number: document.getElementById('cfg-twilio-from')?.value.trim()
    };
    fetch('/api/sms/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showTemporaryNotification('SMS Gateway settings updated.', 'success');
            window.closeSmsSettingsModal();
            fetchSmsGatewayStatus();
        }
    });
};

window.sendDirectTestSms = function() {
    const phone = document.getElementById('test-sms-phone-input')?.value.trim();
    if (!phone) {
        showTemporaryNotification('Please enter a recipient phone number first.', 'warning');
        return;
    }
    fetch('/api/sms/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone })
    })
    .then(r => r.json())
    .then(data => {
        const res = data.result || {};
        showTemporaryNotification(`[SMS: ${res.provider || 'TEST'}] ${res.detail || 'Processed'}`, res.success ? 'success' : 'warning');
    });
};

window.testSmsToContact = function(phone, name) {
    fetch('/api/sms/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone })
    })
    .then(r => r.json())
    .then(data => {
        const res = data.result || {};
        showTemporaryNotification(`Test SMS to ${name}: ${res.detail || 'Processed'}`, res.success ? 'success' : 'warning');
    });
};

function updateLocationDisplay(lat, lon) {
    const textEl = document.getElementById('gps-lat-lon');
    if (textEl && lat && lon) {
        textEl.textContent = `${Number(lat).toFixed(4)}°N, ${Number(lon).toFixed(4)}°E`;
    }
}

function initSystemLocation() {
    fetch('/api/system/location')
        .then(r => r.json())
        .then(data => {
            if (data.success && data.latitude && data.longitude) {
                updateLocationDisplay(data.latitude, data.longitude);
            }
        })
        .catch(() => {});
}

window.openLocationCalibrator = function() {
    document.getElementById('modal-calibrate-location')?.classList.remove('hidden');
};
window.closeLocationCalibrator = function() {
    document.getElementById('modal-calibrate-location')?.classList.add('hidden');
};
window.saveCustomLocation = function(e) {
    if (e) e.preventDefault();
    const lat = parseFloat(document.getElementById('calib-lat')?.value);
    const lon = parseFloat(document.getElementById('calib-lon')?.value);
    if (isNaN(lat) || isNaN(lon)) return;
    fetch('/api/system/location', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ latitude: lat, longitude: lon, source: 'MANUAL' })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            updateLocationDisplay(lat, lon);
            window.closeLocationCalibrator();
            if (window.updateMapLocation) window.updateMapLocation(lat, lon);
        }
    });
};
