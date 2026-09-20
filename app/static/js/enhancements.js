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

    function exposeLabelsNav() {
        document.querySelectorAll('a.nav-link[href="/labels"]').forEach(function(link) {
            var item = link.closest('.nav-item');
            if (item) item.classList.remove('d-md-none');
        });
    }

    function addPrintingNav() {
        if (window.location.pathname !== '/settings') return;
        var mealie = document.querySelector('a.list-group-item[href="/settings?tab=mealie"]');
        if (!mealie || document.querySelector('a[href="/settings?tab=printing"]')) return;
        var link = document.createElement('a');
        link.href = '/settings?tab=printing';
        link.className = 'list-group-item list-group-item-action d-flex align-items-center' +
            (new URLSearchParams(window.location.search).get('tab') === 'printing' ? ' active' : '');
        link.innerHTML = '<span class="me-2"><i class="ti ti-printer icon"></i></span>Printing';
        mealie.parentElement.appendChild(link);
    }

    async function renderPrintingSettings() {
        var params = new URLSearchParams(window.location.search);
        if (window.location.pathname !== '/settings' || params.get('tab') !== 'printing') return;
        var pane = document.querySelector('.col-12.col-md-9.d-flex.flex-column');
        if (!pane) return;
        pane.innerHTML = '<div class="card-body"><h2 class="mb-2">Printing</h2><p class="card-subtitle mb-4">Runtime configuration for niimblue-node and the NIIMBOT B21 Pro.</p><div id="niim-settings-body"><div class="text-secondary">Loading…</div></div></div>';
        try {
            var response = await fetch('/api/settings/niim', {headers: {'Accept': 'application/json'}});
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load printer settings');
            var c = data.config || {};
            var s = data.status || {};
            var status = s.configured
                ? (s.connected ? '<span class="badge bg-green text-green-fg">Connected</span>' : '<span class="badge bg-yellow text-yellow-fg">Configured / offline</span>')
                : '<span class="badge bg-secondary-lt">Not configured</span>';
            document.getElementById('niim-settings-body').innerHTML =
                '<div class="card mb-3"><div class="card-header"><div><h3 class="card-title">NIIMBOT B21 Pro</h3><p class="card-subtitle">Settings take effect on the next status check or print job. No B2M restart required.</p></div><div class="card-actions">' + status + '</div></div>' +
                '<form id="niim-settings-form"><div class="card-body"><div class="row g-3">' +
                '<div class="col-12"><label class="form-label">niimblue-node URL</label><input class="form-control" name="url" value="' + esc(c.url || '') + '" placeholder="http://127.0.0.1:5000"></div>' +
                '<div class="col-md-4"><label class="form-label">Transport</label><select class="form-select" name="transport"><option value="ble"' + (c.transport === 'ble' ? ' selected' : '') + '>BLE</option><option value="serial"' + (c.transport === 'serial' ? ' selected' : '') + '>Serial</option></select></div>' +
                '<div class="col-md-8"><label class="form-label">Printer address</label><input class="form-control font-monospace" name="address" value="' + esc(c.address || '') + '" placeholder="BLE address"></div>' +
                '<div class="col-md-6"><label class="form-label">Print task</label><input class="form-control font-monospace" name="print_task" value="' + esc(c.print_task || 'D110M_V4') + '"></div>' +
                '<div class="col-md-6"><label class="form-label">Direction</label><select class="form-select" name="print_direction"><option value="top"' + (c.print_direction === 'top' ? ' selected' : '') + '>top</option><option value="left"' + (c.print_direction === 'left' ? ' selected' : '') + '>left</option><option value="right"' + (c.print_direction === 'right' ? ' selected' : '') + '>right</option><option value="bottom"' + (c.print_direction === 'bottom' ? ' selected' : '') + '>bottom</option></select></div>' +
                '<div class="col-md-3"><label class="form-label">Density</label><input class="form-control" type="number" min="1" max="5" name="density" value="' + esc(c.density || 3) + '"></div>' +
                '<div class="col-md-3"><label class="form-label">Label type</label><input class="form-control" type="number" min="1" name="label_type" value="' + esc(c.label_type || 1) + '"></div>' +
                '<div class="col-md-3"><label class="form-label">DPI</label><input class="form-control" type="number" min="100" name="dpi" value="' + esc(c.dpi || 300) + '"></div>' +
                '<div class="col-md-3"><label class="form-label">Max width (mm)</label><input class="form-control" type="number" min="1" step="0.1" name="max_label_width_mm" value="' + esc(c.max_label_width_mm || 50) + '"></div>' +
                '<div class="col-md-4"><label class="form-label">Timeout (s)</label><input class="form-control" type="number" min="1" step="0.1" name="timeout" value="' + esc(c.timeout || 30) + '"></div>' +
                '<div class="col-12"><div id="niim-settings-result" class="form-hint"></div></div>' +
                '</div></div><div class="card-footer text-end"><button class="btn btn-primary" type="submit"><i class="ti ti-device-floppy icon"></i> Save & test status</button></div></form></div>';
            document.getElementById('niim-settings-form').addEventListener('submit', savePrintingSettings);
        } catch (error) {
            document.getElementById('niim-settings-body').innerHTML = '<div class="alert alert-danger">' + esc(error.message) + '</div>';
        }
    }

    async function savePrintingSettings(event) {
        event.preventDefault();
        var form = event.currentTarget;
        var result = document.getElementById('niim-settings-result');
        var body = {};
        new FormData(form).forEach(function(value, key) { body[key] = value; });
        result.textContent = 'Saving…';
        try {
            var response = await fetch('/api/settings/niim', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Save failed');
            result.className = 'form-hint text-success';
            result.textContent = data.status && data.status.connected ? 'Saved · printer connected.' : 'Saved · printer is not connected yet.';
        } catch (error) {
            result.className = 'form-hint text-danger';
            result.textContent = error.message;
        }
    }

    async function addShoppingListsCard() {
        var params = new URLSearchParams(window.location.search);
        if (window.location.pathname !== '/settings' || params.get('tab') !== 'mealie' || document.getElementById('shopping-lists-card')) return;
        try {
            var response = await fetch('/api/shopping-lists', {headers: {'Accept': 'application/json'}});
            if (!response.ok) return;
            var data = await response.json();
            var body = document.querySelector('.col-12.col-md-9 .card-body');
            if (!body) return;
            var card = document.createElement('div');
            card.id = 'shopping-lists-card';
            card.className = 'card mt-4';
            var rows = (data.items || []).map(function(row) {
                return '<tr><td><i class="ti ti-list-check me-2 text-secondary"></i>' + esc(row.name) + (row.default ? ' <span class="badge bg-blue-lt ms-2">default</span>' : '') + '</td><td><code>' + esc(row.id) + '</code></td></tr>';
            }).join('') || '<tr><td colspan="2" class="text-secondary">No Mealie shopping lists returned.</td></tr>';
            card.innerHTML = '<div class="card-header"><div><h3 class="card-title">Shopping lists</h3><p class="card-subtitle">Detected from Mealie. Foods and recipe codes can target any of these lists.</p></div></div><div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Name</th><th>ID</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
            body.appendChild(card);
        } catch (error) {
            console.debug('Shopping lists unavailable', error);
        }
    }

    function scannerRows(items) {
        if (!items.length) return '<tr><td colspan="5" class="text-center text-secondary py-4">No scanner bridge has reported telemetry yet. Install scanner.py v2.1.0 or newer.</td></tr>';
        return items.map(function(scanner) {
            return '<tr>' +
                '<td><div class="fw-bold">' + esc(scanner.token_name) + '</div><div class="text-secondary small"><code>' + esc(scanner.token_prefix || '—') + '…</code></div></td>' +
                '<td><div>' + esc(scanner.hostname || 'Unknown host') + '</div><div class="text-secondary small">v' + esc(scanner.version) + ' · ' + esc((scanner.layout || '?').toUpperCase()) + '</div></td>' +
                '<td><span class="badge ' + (scanner.online ? 'bg-green text-green-fg' : 'bg-secondary-lt') + '">' + (scanner.online ? 'Online' : 'Offline') + '</span><div class="text-secondary small mt-1" title="' + esc(scanner.last_seen_absolute) + '">' + esc(scanner.last_seen) + '</div></td>' +
                '<td><div>' + Number(scanner.scans || 0) + ' scans</div><div class="text-secondary small">' + Number(scanner.errors || 0) + ' errors · ' + (scanner.latency_ms == null ? '—' : Number(scanner.latency_ms) + ' ms') + '</div></td>' +
                '<td class="text-secondary">' + esc(formatUptime(scanner.uptime_seconds)) + '</td>' +
                '</tr>';
        }).join('');
    }

    async function refreshScannerHealth() {
        var tbody = document.getElementById('scanner-health-body');
        if (!tbody) return;
        try {
            var response = await fetch('/api/scanners', {headers: {'Accept': 'application/json'}});
            if (!response.ok) return;
            var data = await response.json();
            tbody.innerHTML = scannerRows(data.items || []);
        } catch (error) { console.debug('Scanner health unavailable', error); }
    }

    async function refreshRecentScanDebug() {
        var tbody = document.getElementById('scanner-recent-body');
        if (!tbody) return;
        try {
            var response = await fetch('/api/scanners/recent-scans?limit=5', {headers: {'Accept': 'application/json'}});
            if (!response.ok) return;
            var data = await response.json();
            var rows = (data.items || []).map(function(row) {
                return '<tr><td class="text-nowrap" title="' + esc(row.created_at_absolute) + '">' + esc(row.created_at) + '</td><td><a href="/barcodes/' + encodeURIComponent(row.barcode) + '"><code>' + esc(row.barcode) + '</code></a></td><td><span class="badge bg-muted-lt">' + esc(row.result) + '</span></td><td>' + esc(row.target_type || '—') + '</td><td>' + esc(row.target_name || '—') + '</td></tr>';
            }).join('') || '<tr><td colspan="5" class="text-center text-secondary">No scan events yet.</td></tr>';
            tbody.innerHTML = rows;
        } catch (error) { console.debug('Recent scan debug unavailable', error); }
    }

    async function addScannerHealth() {
        var params = new URLSearchParams(window.location.search);
        if (window.location.pathname !== '/settings' || params.get('tab') !== 'tokens') return;
        var tables = document.querySelectorAll('.card-body .table-responsive');
        var anchor = tables.length ? tables[tables.length - 1] : document.querySelector('.card-body');
        if (!anchor) return;
        if (!document.getElementById('scanner-health-card')) {
            var card = document.createElement('div');
            card.id = 'scanner-health-card';
            card.className = 'card mt-4';
            card.innerHTML = '<div class="card-header"><div><h3 class="card-title">Scanner health</h3><p class="card-subtitle">Live telemetry reported by the USB bridge.</p></div></div><div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Token</th><th>Scanner</th><th>Status</th><th>Statistics</th><th>Uptime</th></tr></thead><tbody id="scanner-health-body"></tbody></table></div>';
            anchor.insertAdjacentElement('afterend', card);
            var debug = document.createElement('div');
            debug.className = 'card mt-4';
            debug.innerHTML = '<div class="card-header"><div><h3 class="card-title">Last 5 scans</h3><p class="card-subtitle">Debug view from recorded scan events. Updates live.</p></div></div><div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Time</th><th>Code</th><th>Result</th><th>Target</th><th>Name</th></tr></thead><tbody id="scanner-recent-body"></tbody></table></div>';
            card.insertAdjacentElement('afterend', debug);
        }
        await Promise.all([refreshScannerHealth(), refreshRecentScanDebug()]);
        if (!window._scannerHealthTimer) {
            window._scannerHealthTimer = setInterval(function() {
                refreshScannerHealth();
                refreshRecentScanDebug();
            }, 5000);
        }
    }

    async function refreshBarcodeDestination() {
        if (!window.location.pathname.startsWith('/barcodes/') || window.location.pathname === '/barcodes/') return;
        var barcode;
        try { barcode = decodeURIComponent(window.location.pathname.substring('/barcodes/'.length)); } catch (e) { return; }
        var targetHeading = Array.from(document.querySelectorAll('h3.card-title')).find(function(h) { return h.textContent.trim() === 'Current target'; });
        if (!targetHeading) return;
        var body = targetHeading.closest('.card').querySelector('.card-body');
        if (!body) return;
        try {
            var response = await fetch('/api/barcode-destination?barcode=' + encodeURIComponent(barcode), {headers: {'Accept': 'application/json'}});
            if (!response.ok) return;
            var d = await response.json();
            var old = document.getElementById('barcode-destination-summary');
            if (old) old.remove();
            if (!d.mapped) return;
            var routeLabels = {default: 'Default → Mealie', mealie: 'Mealie', homeassistant: 'Home Assistant', both: 'Mealie + Home Assistant', none: 'No destination'};
            var el = document.createElement('div');
            el.id = 'barcode-destination-summary';
            el.className = 'border-top mt-3 pt-3 small';
            var listPart = ['mealie', 'both'].includes(d.effective_route)
                ? '<div><span class="text-secondary">Shopping list:</span> <strong>' + esc(d.shopping_list_name || d.shopping_list_id || 'default') + '</strong>' + (d.shopping_list_default ? ' <span class="badge bg-blue-lt">default</span>' : '') + '</div>'
                : '';
            el.innerHTML = '<div><span class="text-secondary">Route:</span> <strong>' + esc(routeLabels[d.route] || d.route) + '</strong></div>' + listPart + '<div><span class="text-secondary">Quantity:</span> ' + (d.quantity == null ? '<span class="text-secondary">none</span>' : esc(d.quantity)) + '</div>';
            body.appendChild(el);
        } catch (error) { console.debug('Barcode destination unavailable', error); }
    }

    function findCardByTitle(root, title) {
        return Array.from(root.querySelectorAll('h3.card-title')).find(function(h) { return h.textContent.trim().toLowerCase() === title.toLowerCase(); });
    }

    async function liveRefreshBarcode(data) {
        if (!window.location.pathname.startsWith('/barcodes/')) return;
        var current;
        try { current = decodeURIComponent(window.location.pathname.substring('/barcodes/'.length)); } catch (e) { return; }
        if (current !== data.barcode) return;
        try {
            var response = await fetch(window.location.pathname + '?live=1', {headers: {'Accept': 'text/html'}});
            if (!response.ok) return;
            var html = await response.text();
            var fresh = new DOMParser().parseFromString(html, 'text/html');
            var currentRows = Array.from(document.querySelectorAll('.row.row-cards.mb-3'));
            var freshRows = Array.from(fresh.querySelectorAll('.row.row-cards.mb-3'));
            var currentStats = currentRows.find(function(row) { return row.textContent.includes('All recorded') && row.textContent.includes('Last 7 days'); });
            var freshStats = freshRows.find(function(row) { return row.textContent.includes('All recorded') && row.textContent.includes('Last 7 days'); });
            if (currentStats && freshStats) currentStats.replaceWith(freshStats);
            var currentRecentH = findCardByTitle(document, 'Recent scans');
            var freshRecentH = findCardByTitle(fresh, 'Recent scans');
            if (currentRecentH && freshRecentH) currentRecentH.closest('.card').replaceWith(freshRecentH.closest('.card'));
            refreshBarcodeDestination();
        } catch (error) { console.debug('Barcode live refresh failed', error); }
    }

    function actionPresentation(data) {
        var map = {
            action_queued: ['purple', 'Action queued'],
            action_triggered: ['green', 'Action triggered'],
            action_ignored: ['secondary', 'Action ignored (cooldown)'],
            action_paused: ['azure', 'Action skipped (scan & link)'],
            action_disabled: ['red', 'Action disabled'],
            unknown_action: ['red', 'Unknown action']
        };
        return map[data.result] || null;
    }

    var toastGroups = {};
    function reconcileScanToast(data) {
        var presentation = actionPresentation(data);
        var container = document.getElementById('scan-toasts');
        if (!container) return;
        var candidates = Array.from(container.querySelectorAll('.toast'));
        var newest = candidates.find(function(t) { return t.textContent.includes(data.barcode); });
        if (!newest) return;
        if (presentation) {
            var title = newest.querySelector('.toast-header strong');
            if (title) title.textContent = presentation[1];
            var avatar = newest.querySelector('.toast-header .avatar');
            if (avatar) avatar.className = 'avatar avatar-xs me-2 bg-' + presentation[0];
            var body = newest.querySelector('.toast-body');
            if (body) body.innerHTML = esc(data.item || data.barcode) + ' (' + esc(data.barcode) + ') &mdash; <a href="/barcodes/' + encodeURIComponent(data.barcode) + '">View</a>';
            if ('Notification' in window && Notification.permission === 'granted' && navigator.serviceWorker) {
                navigator.serviceWorker.ready.then(function(reg) {
                    reg.showNotification(presentation[1], {body: (data.item || data.barcode), tag: data.barcode, data: {url: '/barcodes/' + encodeURIComponent(data.barcode)}});
                }).catch(function() {});
            }
        }
        var signature = [data.barcode, data.result, data.item || '', data.paused ? '1' : '0'].join('|');
        var group = toastGroups[signature];
        if (group && group.el && group.el.isConnected && group.el !== newest) {
            newest.remove();
            group.count += 1;
            var badge = group.el.querySelector('.b2m-toast-count');
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'badge bg-secondary-lt ms-2 b2m-toast-count';
                var strong = group.el.querySelector('.toast-header strong');
                if (strong) strong.insertAdjacentElement('afterend', badge);
            }
            badge.textContent = '×' + group.count;
        } else {
            toastGroups[signature] = {el: newest, count: 1};
        }
    }

    function addHaWebhookTestButton() {
        var input = document.getElementById('setting_ha_webhook_url');
        if (!input || document.getElementById('ha-webhook-test')) return;
        var row = input.closest('.row.g-2') || input.parentElement;
        if (!row) return;
        var wrapper = document.createElement('div');
        wrapper.className = 'col-auto d-flex align-items-start';
        wrapper.innerHTML = '<button type="button" class="btn btn-outline-primary" id="ha-webhook-test"><i class="ti ti-send icon"></i> Test webhook</button>';
        row.appendChild(wrapper);
        var result = document.createElement('div');
        result.id = 'ha-webhook-test-result';
        result.className = 'form-hint mt-2';
        row.parentElement.appendChild(result);
        wrapper.querySelector('button').addEventListener('click', async function() {
            var button = this;
            button.disabled = true;
            result.className = 'form-hint mt-2 text-secondary';
            result.textContent = 'Sending test webhook…';
            try {
                var response = await fetch('/api/settings/test-ha-webhook', {method: 'POST', headers: {'Accept': 'application/json'}});
                var data = await response.json();
                if (response.ok && data.ok) {
                    result.className = 'form-hint mt-2 text-success';
                    result.textContent = '✓ Delivered — HTTP ' + data.status + ' — ' + data.duration_ms + ' ms';
                } else throw new Error(data.error || ('HTTP ' + data.status));
            } catch (error) {
                result.className = 'form-hint mt-2 text-danger';
                result.textContent = '✗ Failed — ' + error.message;
            } finally { button.disabled = false; }
        });
    }

    function refreshDisplayedVersion() {
        fetch('/api/version').then(function(r) { return r.json(); }).then(function(data) {
            Array.from(document.querySelectorAll('span')).forEach(function(span) {
                if (/^v20\d\d\./.test(span.textContent.trim())) span.textContent = 'v' + data.version;
            });
        }).catch(function() {});
    }

    function connectLiveEnhancements() {
        if (!window.EventSource) return;
        var events = new EventSource('/events');
        events.addEventListener('scan', function(event) {
            var data;
            try { data = JSON.parse(event.data); } catch (e) { return; }
            window.dispatchEvent(new CustomEvent('b2m:scan', {detail: data}));
            setTimeout(function() { reconcileScanToast(data); }, 80);
            liveRefreshBarcode(data);
            refreshScannerHealth();
            refreshRecentScanDebug();
        });
        window.addEventListener('beforeunload', function() { events.close(); });
    }

    document.addEventListener('DOMContentLoaded', function() {
        exposeLabelsNav();
        addPrintingNav();
        renderPrintingSettings();
        addHaWebhookTestButton();
        addScannerHealth();
        addShoppingListsCard();
        refreshBarcodeDestination();
        refreshDisplayedVersion();
        connectLiveEnhancements();
    });
})();
