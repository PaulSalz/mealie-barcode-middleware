(function() {
    'use strict';

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }
    function formatUptime(seconds) {
        seconds = Number(seconds || 0);
        if (seconds < 60) return seconds + 's';
        if (seconds < 3600) return Math.floor(seconds / 60) + 'm';
        if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ' + Math.floor((seconds % 3600) / 60) + 'm';
        return Math.floor(seconds / 86400) + 'd ' + Math.floor((seconds % 86400) / 3600) + 'h';
    }

    function addSettingsLink(afterSelector, tab, label, icon) {
        if (window.location.pathname !== '/settings' || document.querySelector('a[href="/settings?tab=' + tab + '"]')) return;
        var after = document.querySelector(afterSelector);
        if (!after || !after.parentElement) return;
        var link = document.createElement('a');
        link.href = '/settings?tab=' + tab;
        link.className = 'list-group-item list-group-item-action d-flex align-items-center' +
            (new URLSearchParams(window.location.search).get('tab') === tab ? ' active' : '');
        link.innerHTML = '<span class="me-2"><i class="ti ' + icon + ' icon"></i></span>' + esc(label);
        after.insertAdjacentElement('afterend', link);
    }

    function settingsPane() { return document.querySelector('.col-12.col-md-9.d-flex.flex-column'); }

    async function renderPrintingSettings() {
        var params = new URLSearchParams(window.location.search);
        if (window.location.pathname !== '/settings' || params.get('tab') !== 'printing') return;
        var pane = settingsPane();
        if (!pane) return;
        pane.innerHTML = '<div class="card-body"><h2 class="mb-2">Printing</h2><p class="card-subtitle mb-4">Runtime configuration for niimblue-node and the NIIMBOT B21 Pro.</p><div id="niim-settings-body"><div class="text-secondary">Loading…</div></div></div>';
        try {
            var response = await fetch('/api/settings/niim', {headers: {'Accept': 'application/json'}});
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load printer settings');
            var c = data.config || {}, s = data.status || {};
            var state = s.configured ? (s.connected ? '<span class="badge bg-green text-green-fg">Connected</span>' : '<span class="badge bg-yellow text-yellow-fg">Configured / offline</span>') : '<span class="badge bg-secondary-lt">Not configured</span>';
            document.getElementById('niim-settings-body').innerHTML =
                '<div class="card"><div class="card-header"><div><h3 class="card-title">NIIMBOT B21 Pro</h3><p class="card-subtitle">Changes apply to the next print/status request; no B2M restart.</p></div><div class="card-actions">' + state + '</div></div>' +
                '<form id="niim-settings-form"><div class="card-body"><div class="row g-3">' +
                '<div class="col-12"><label class="form-label">niimblue-node URL</label><input class="form-control" name="url" value="' + esc(c.url || '') + '" placeholder="http://127.0.0.1:5000"></div>' +
                '<div class="col-md-4"><label class="form-label">Transport</label><select class="form-select" name="transport"><option value="ble"' + (c.transport === 'ble' ? ' selected' : '') + '>BLE</option><option value="serial"' + (c.transport === 'serial' ? ' selected' : '') + '>Serial</option></select></div>' +
                '<div class="col-md-8"><label class="form-label">Printer address</label><input class="form-control font-monospace" name="address" value="' + esc(c.address || '') + '"></div>' +
                '<div class="col-md-6"><label class="form-label">Print task</label><input class="form-control font-monospace" name="print_task" value="' + esc(c.print_task || 'D110M_V4') + '"></div>' +
                '<div class="col-md-6"><label class="form-label">Direction</label><select class="form-select" name="print_direction">' + ['top','left','right','bottom'].map(function(v) { return '<option value="' + v + '"' + (c.print_direction === v ? ' selected' : '') + '>' + v + '</option>'; }).join('') + '</select></div>' +
                '<div class="col-md-3"><label class="form-label">Density</label><input class="form-control" type="number" min="1" max="5" name="density" value="' + esc(c.density || 3) + '"></div>' +
                '<div class="col-md-3"><label class="form-label">Label type</label><input class="form-control" type="number" min="1" name="label_type" value="' + esc(c.label_type || 1) + '"></div>' +
                '<div class="col-md-3"><label class="form-label">DPI</label><input class="form-control" type="number" min="100" name="dpi" value="' + esc(c.dpi || 300) + '"></div>' +
                '<div class="col-md-3"><label class="form-label">Max width (mm)</label><input class="form-control" type="number" min="1" step="0.1" name="max_label_width_mm" value="' + esc(c.max_label_width_mm || 50) + '"></div>' +
                '<div class="col-md-4"><label class="form-label">Timeout (s)</label><input class="form-control" type="number" min="1" step="0.1" name="timeout" value="' + esc(c.timeout || 30) + '"></div>' +
                '<div class="col-12"><div id="niim-settings-result" class="form-hint"></div></div></div></div>' +
                '<div class="card-footer text-end"><button class="btn btn-primary" type="submit"><i class="ti ti-device-floppy icon"></i> Save & test status</button></div></form></div>';
            document.getElementById('niim-settings-form').addEventListener('submit', savePrintingSettings);
        } catch (error) {
            document.getElementById('niim-settings-body').innerHTML = '<div class="alert alert-danger">' + esc(error.message) + '</div>';
        }
    }

    async function savePrintingSettings(event) {
        event.preventDefault();
        var body = {};
        new FormData(event.currentTarget).forEach(function(value, key) { body[key] = value; });
        var result = document.getElementById('niim-settings-result');
        result.textContent = 'Saving…';
        try {
            var response = await fetch('/api/settings/niim', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Save failed');
            result.className = 'form-hint text-success';
            result.textContent = data.status && data.status.connected ? 'Saved · printer connected.' : 'Saved · printer not connected yet.';
        } catch (error) { result.className = 'form-hint text-danger'; result.textContent = error.message; }
    }

    async function renderNotificationSettings() {
        var params = new URLSearchParams(window.location.search);
        if (window.location.pathname !== '/settings' || params.get('tab') !== 'notifications') return;
        var pane = settingsPane();
        if (!pane) return;
        pane.innerHTML = '<div class="card-body"><h2 class="mb-2">Notifications</h2><p class="card-subtitle mb-4">Web notification timing and duplicate-scan decluttering.</p><div id="notification-settings-body">Loading…</div></div>';
        try {
            var response = await fetch('/api/settings/notifications');
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load settings');
            document.getElementById('notification-settings-body').innerHTML =
                '<form id="notification-settings-form"><div class="card"><div class="card-header"><h3 class="card-title">Web UI</h3></div><div class="card-body"><div class="row g-3">' +
                '<div class="col-md-6"><label class="form-label">Notification visibility</label><div class="input-group"><input class="form-control" type="number" min="3" max="120" name="toast_seconds" value="' + Number(data.toast_seconds || 12) + '"><span class="input-group-text">seconds</span></div><div class="form-hint">How long scan toasts remain visible.</div></div>' +
                '<div class="col-md-6"><label class="form-label">Duplicate grouping window</label><div class="input-group"><input class="form-control" type="number" min="1" max="300" name="group_window_seconds" value="' + Number(data.group_window_seconds || 30) + '"><span class="input-group-text">seconds</span></div><div class="form-hint">Same barcode + result + target gets collapsed to ×2, ×3, … inside this window.</div></div>' +
                '<div class="col-12"><div id="notification-settings-result" class="form-hint"></div></div></div></div><div class="card-footer text-end"><button class="btn btn-primary" type="submit"><i class="ti ti-device-floppy icon"></i> Save</button></div></div></form>';
            document.getElementById('notification-settings-form').addEventListener('submit', async function(event) {
                event.preventDefault();
                var fd = new FormData(event.currentTarget);
                var result = document.getElementById('notification-settings-result');
                try {
                    var r = await fetch('/api/settings/notifications', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({toast_seconds: fd.get('toast_seconds'), group_window_seconds: fd.get('group_window_seconds')})});
                    var saved = await r.json();
                    if (!r.ok) throw new Error(saved.error || 'Save failed');
                    result.className = 'form-hint text-success'; result.textContent = 'Saved. New scan notifications use these values immediately.';
                    window.dispatchEvent(new CustomEvent('b2m:ui-settings', {detail: saved}));
                } catch (error) { result.className = 'form-hint text-danger'; result.textContent = error.message; }
            });
        } catch (error) { document.getElementById('notification-settings-body').innerHTML = '<div class="alert alert-danger">' + esc(error.message) + '</div>'; }
    }

    async function addShoppingListsCard() {
        var params = new URLSearchParams(window.location.search);
        if (window.location.pathname !== '/settings' || params.get('tab') !== 'mealie' || document.getElementById('shopping-lists-card')) return;
        var body = document.querySelector('.col-12.col-md-9 .card-body');
        if (!body) return;
        try {
            var response = await fetch('/api/shopping-lists?force=true');
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load shopping lists');
            var card = document.createElement('div');
            card.id = 'shopping-lists-card'; card.className = 'card mt-4';
            var options = (data.items || []).map(function(row) { return '<option value="' + esc(row.id) + '"' + (row.default ? ' selected' : '') + '>' + esc(row.name) + '</option>'; }).join('');
            card.innerHTML = '<div class="card-header"><div><h3 class="card-title">Shopping lists</h3><p class="card-subtitle">B2M discovers list IDs from Mealie. Select which list is used when a target does not specify one.</p></div></div>' +
                '<div class="card-body"><div class="row g-3 align-items-end"><div class="col-md-7"><label class="form-label">Default shopping list</label><select class="form-select" id="default-shopping-list">' + options + '</select></div><div class="col-md-5"><div class="btn-list"><button class="btn btn-primary" type="button" id="save-default-shopping-list">Save default</button><button class="btn btn-outline-primary" type="button" id="test-mealie-connection"><i class="ti ti-plug-connected icon"></i> Test connection</button></div></div><div class="col-12"><div class="form-hint" id="mealie-runtime-result"></div></div></div></div>';
            body.appendChild(card);
            var result = document.getElementById('mealie-runtime-result');
            document.getElementById('save-default-shopping-list').addEventListener('click', async function() {
                try {
                    var r = await fetch('/api/settings/mealie/default-list', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({list_id: document.getElementById('default-shopping-list').value})});
                    var d = await r.json(); if (!r.ok) throw new Error(d.error || 'Save failed');
                    result.className = 'form-hint text-success'; result.textContent = 'Default shopping list saved.';
                } catch (error) { result.className = 'form-hint text-danger'; result.textContent = error.message; }
            });
            document.getElementById('test-mealie-connection').addEventListener('click', async function() {
                result.className = 'form-hint text-secondary'; result.textContent = 'Testing Mealie…';
                try {
                    var r = await fetch('/api/settings/mealie/test', {method: 'POST'}); var d = await r.json();
                    if (!r.ok || !d.ok) throw new Error(d.error || 'Connection failed');
                    result.className = 'form-hint text-success'; result.textContent = 'Connected · HTTP ' + d.status + ' · ' + d.latency_ms + ' ms';
                } catch (error) { result.className = 'form-hint text-danger'; result.textContent = error.message; }
            });
        } catch (error) { console.debug('Shopping lists unavailable', error); }
    }

    function scannerRows(items) {
        if (!items.length) return '<tr><td colspan="5" class="text-center text-secondary py-4">No scanner bridge telemetry yet.</td></tr>';
        return items.map(function(scanner) {
            return '<tr><td><div class="fw-bold">' + esc(scanner.token_name) + '</div><code class="text-secondary small">' + esc(scanner.token_prefix || '—') + '…</code></td><td><div>' + esc(scanner.hostname || 'Unknown host') + '</div><div class="text-secondary small">v' + esc(scanner.version) + ' · ' + esc((scanner.layout || '?').toUpperCase()) + '</div></td><td><span class="badge ' + (scanner.online ? 'bg-green text-green-fg' : 'bg-secondary-lt') + '">' + (scanner.online ? 'Online' : 'Offline') + '</span><div class="text-secondary small" title="' + esc(scanner.last_seen_absolute) + '">' + esc(scanner.last_seen) + '</div></td><td>' + Number(scanner.scans || 0) + ' scans<div class="text-secondary small">' + Number(scanner.errors || 0) + ' errors · ' + (scanner.latency_ms == null ? '—' : Number(scanner.latency_ms) + ' ms') + '</div></td><td class="text-secondary">' + esc(formatUptime(scanner.uptime_seconds)) + '</td></tr>';
        }).join('');
    }
    async function refreshScannerHealth() {
        var tbody = document.getElementById('scanner-health-body'); if (!tbody) return;
        try { var r = await fetch('/api/scanners'); if (!r.ok) return; tbody.innerHTML = scannerRows((await r.json()).items || []); } catch (e) {}
    }
    async function refreshRecentScanDebug() {
        var tbody = document.getElementById('scanner-recent-body'); if (!tbody) return;
        try {
            var r = await fetch('/api/scanners/recent-scans?limit=5'); if (!r.ok) return;
            var data = await r.json();
            tbody.innerHTML = (data.items || []).map(function(row) { return '<tr><td title="' + esc(row.created_at_absolute) + '">' + esc(row.created_at) + '</td><td><a href="/barcodes/' + encodeURIComponent(row.barcode) + '"><code>' + esc(row.barcode) + '</code></a></td><td><span class="badge bg-muted-lt">' + esc(row.result) + '</span></td><td>' + esc(row.target_type || '—') + '</td><td>' + esc(row.target_name || '—') + '</td></tr>'; }).join('') || '<tr><td colspan="5" class="text-center text-secondary">No scan events yet.</td></tr>';
        } catch (e) {}
    }
    async function addScannerHealth() {
        var params = new URLSearchParams(window.location.search);
        if (window.location.pathname !== '/settings' || params.get('tab') !== 'tokens') return;
        var tables = document.querySelectorAll('.card-body .table-responsive');
        var anchor = tables.length ? tables[tables.length - 1] : document.querySelector('.card-body');
        if (!anchor || document.getElementById('scanner-health-card')) return;
        var card = document.createElement('div'); card.id = 'scanner-health-card'; card.className = 'card mt-4';
        card.innerHTML = '<div class="card-header"><div><h3 class="card-title">Scanner health</h3><p class="card-subtitle">Live telemetry reported by the USB bridge.</p></div></div><div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Token</th><th>Scanner</th><th>Status</th><th>Statistics</th><th>Uptime</th></tr></thead><tbody id="scanner-health-body"></tbody></table></div>';
        anchor.insertAdjacentElement('afterend', card);
        var debug = document.createElement('div'); debug.className = 'card mt-4';
        debug.innerHTML = '<div class="card-header"><div><h3 class="card-title">Last 5 scans</h3><p class="card-subtitle">Raw scan result/target debug view.</p></div></div><div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Time</th><th>Code</th><th>Result</th><th>Target</th><th>Name</th></tr></thead><tbody id="scanner-recent-body"></tbody></table></div>';
        card.insertAdjacentElement('afterend', debug);
        await Promise.all([refreshScannerHealth(), refreshRecentScanDebug()]);
        if (!window._scannerHealthTimer) window._scannerHealthTimer = setInterval(function() { refreshScannerHealth(); refreshRecentScanDebug(); }, 5000);
    }

    function findCardByTitle(root, title) {
        return Array.from(root.querySelectorAll('h3.card-title')).find(function(h) { return h.textContent.trim().toLowerCase().startsWith(title.toLowerCase()); });
    }
    async function liveRefreshBarcode(data) {
        if (!window.location.pathname.startsWith('/barcodes/')) return;
        var current; try { current = decodeURIComponent(window.location.pathname.substring('/barcodes/'.length)); } catch (e) { return; }
        if (current !== data.barcode) return;
        try {
            var response = await fetch(window.location.pathname + '?live=1', {headers: {'Accept': 'text/html'}}); if (!response.ok) return;
            var fresh = new DOMParser().parseFromString(await response.text(), 'text/html');
            var currentStats = Array.from(document.querySelectorAll('.row.row-cards.mb-3')).find(function(row) { return row.textContent.includes('All recorded') && row.textContent.includes('Last 7 days'); });
            var freshStats = Array.from(fresh.querySelectorAll('.row.row-cards.mb-3')).find(function(row) { return row.textContent.includes('All recorded') && row.textContent.includes('Last 7 days'); });
            if (currentStats && freshStats) currentStats.replaceWith(freshStats);
            var currentRecent = findCardByTitle(document, 'Recent scan history');
            var freshRecent = findCardByTitle(fresh, 'Recent scan history');
            if (currentRecent && freshRecent) currentRecent.closest('.card').replaceWith(freshRecent.closest('.card'));
        } catch (error) { console.debug('Barcode live refresh failed', error); }
    }

    function addHaWebhookTestButton() {
        var input = document.getElementById('setting_ha_webhook_url');
        if (!input || document.getElementById('ha-webhook-test')) return;
        var row = input.closest('.row.g-2') || input.parentElement; if (!row) return;
        var wrapper = document.createElement('div'); wrapper.className = 'col-auto d-flex align-items-start';
        wrapper.innerHTML = '<button type="button" class="btn btn-outline-primary" id="ha-webhook-test"><i class="ti ti-send icon"></i> Test webhook</button>';
        row.appendChild(wrapper);
        var result = document.createElement('div'); result.id = 'ha-webhook-test-result'; result.className = 'form-hint mt-2'; row.parentElement.appendChild(result);
        wrapper.querySelector('button').addEventListener('click', async function() {
            this.disabled = true; result.textContent = 'Sending test webhook…';
            try { var r = await fetch('/api/settings/test-ha-webhook', {method: 'POST'}); var d = await r.json(); if (!r.ok || !d.ok) throw new Error(d.error || ('HTTP ' + d.status)); result.className = 'form-hint mt-2 text-success'; result.textContent = 'Delivered · HTTP ' + d.status + ' · ' + d.duration_ms + ' ms'; }
            catch (error) { result.className = 'form-hint mt-2 text-danger'; result.textContent = error.message; }
            finally { this.disabled = false; }
        });
    }

    function refreshDisplayedVersion() {
        fetch('/api/version').then(function(r) { return r.json(); }).then(function(data) {
            Array.from(document.querySelectorAll('span')).forEach(function(span) { if (/^v20\d\d\./.test(span.textContent.trim())) span.textContent = 'v' + data.version; });
        }).catch(function() {});
    }

    document.addEventListener('DOMContentLoaded', function() {
        addSettingsLink('a.list-group-item[href="/settings?tab=mealie"]', 'printing', 'Printing', 'ti-printer');
        addSettingsLink('a.list-group-item[href="/settings?tab=scanning"]', 'notifications', 'Notifications', 'ti-bell-cog');
        renderPrintingSettings();
        renderNotificationSettings();
        addShoppingListsCard();
        addHaWebhookTestButton();
        addScannerHealth();
        refreshDisplayedVersion();
        window.addEventListener('b2m:scan', function(event) {
            liveRefreshBarcode(event.detail || {});
            refreshScannerHealth();
            refreshRecentScanDebug();
        });
    });
})();
