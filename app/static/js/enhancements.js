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

    async function addScannerHealth() {
        var params = new URLSearchParams(window.location.search);
        if (window.location.pathname !== '/settings' || params.get('tab') !== 'tokens' || document.getElementById('scanner-health-card')) return;
        try {
            var response = await fetch('/api/scanners', {headers: {'Accept': 'application/json'}});
            if (!response.ok) return;
            var data = await response.json();
            var items = data.items || [];
            var tables = document.querySelectorAll('.card-body .table-responsive');
            var anchor = tables.length ? tables[tables.length - 1] : document.querySelector('.card-body');
            if (!anchor) return;

            var card = document.createElement('div');
            card.id = 'scanner-health-card';
            card.className = 'card mt-4';
            var rows = items.length ? items.map(function(scanner) {
                return '<tr>' +
                    '<td><div class="fw-bold">' + esc(scanner.token_name) + '</div><div class="text-secondary small"><code>' + esc(scanner.token_prefix || '—') + '…</code></div></td>' +
                    '<td><div>' + esc(scanner.hostname || 'Unknown host') + '</div><div class="text-secondary small">v' + esc(scanner.version) + ' · ' + esc((scanner.layout || '?').toUpperCase()) + '</div></td>' +
                    '<td><span class="badge ' + (scanner.online ? 'bg-green text-green-fg' : 'bg-secondary-lt') + '">' + (scanner.online ? 'Online' : 'Offline') + '</span><div class="text-secondary small mt-1" title="' + esc(scanner.last_seen_absolute) + '">' + esc(scanner.last_seen) + '</div></td>' +
                    '<td><div>' + Number(scanner.scans || 0) + ' scans</div><div class="text-secondary small">' + Number(scanner.errors || 0) + ' errors · ' + (scanner.latency_ms == null ? '—' : Number(scanner.latency_ms) + ' ms') + '</div></td>' +
                    '<td class="text-secondary">' + esc(formatUptime(scanner.uptime_seconds)) + '</td>' +
                    '</tr>';
            }).join('') : '<tr><td colspan="5" class="text-center text-secondary py-4">No scanner bridge has reported telemetry yet. Install scanner.py v2.1.0 or newer.</td></tr>';
            card.innerHTML = '<div class="card-header"><div><h3 class="card-title">Scanner health</h3><p class="card-subtitle">Reported by the USB bridge and associated with its Bearer token.</p></div></div>' +
                '<div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Token</th><th>Scanner</th><th>Status</th><th>Statistics</th><th>Uptime</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
            anchor.insertAdjacentElement('afterend', card);
        } catch (error) {
            console.debug('Scanner health unavailable', error);
        }
    }

    function addHaWebhookTestButton() {
        var input = document.getElementById('setting_ha_webhook_url');
        if (!input || document.getElementById('ha-webhook-test')) return;

        var row = input.closest('.row.g-2') || input.parentElement;
        if (!row) return;

        var wrapper = document.createElement('div');
        wrapper.className = 'col-auto d-flex align-items-start';
        wrapper.innerHTML = '<button type="button" class="btn btn-outline-primary" id="ha-webhook-test">' +
            '<i class="ti ti-send icon"></i> Test webhook</button>';
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
                var response = await fetch('/api/settings/test-ha-webhook', {
                    method: 'POST',
                    headers: {'Accept': 'application/json'}
                });
                var data = await response.json();
                if (response.ok && data.ok) {
                    result.className = 'form-hint mt-2 text-success';
                    result.textContent = '✓ Delivered — HTTP ' + data.status + ' — ' + data.duration_ms + ' ms';
                } else {
                    result.className = 'form-hint mt-2 text-danger';
                    result.textContent = '✗ Failed — ' + (data.error || ('HTTP ' + data.status));
                }
            } catch (error) {
                result.className = 'form-hint mt-2 text-danger';
                result.textContent = '✗ Failed — ' + error.message;
            } finally {
                button.disabled = false;
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        exposeLabelsNav();
        addHaWebhookTestButton();
        addScannerHealth();
    });
})();
