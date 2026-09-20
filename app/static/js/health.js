/** Dashboard health and scanner-status polling with visibility awareness. */
(function() {
    'use strict';

    var indicator = document.getElementById('health-indicator');
    var statusEl = document.getElementById('health-status');
    var scannerOnline = document.getElementById('stat-scanner-online');
    var scannerTotal = document.getElementById('stat-scanner-total');
    if (!indicator || !statusEl) return;

    var timer = null;

    function poll() {
        fetch('/health').then(function(r) { return r.json(); }).then(function(d) {
            var up = d.mealie_reachable;
            indicator.className = 'status-indicator status-' + (up ? 'green' : 'red') + (up ? ' status-indicator-animated' : '');
            statusEl.className = 'text-' + (up ? 'green' : 'red');
            statusEl.textContent = up ? 'Connected' : 'Unreachable';
        }).catch(function() {
            indicator.className = 'status-indicator status-red';
            statusEl.className = 'text-red';
            statusEl.textContent = 'Error';
        });

        if (scannerOnline || scannerTotal) {
            fetch('/api/dashboard').then(function(r) { return r.json(); }).then(function(d) {
                if (scannerOnline) scannerOnline.textContent = d.scanner_online == null ? '0' : d.scanner_online;
                if (scannerTotal) scannerTotal.textContent = d.scanner_total == null ? '0' : d.scanner_total;
            }).catch(function() {});
        }
    }

    function start() {
        if (timer) clearInterval(timer);
        poll();
        timer = setInterval(poll, 10000);
    }

    function stop() {
        if (timer) { clearInterval(timer); timer = null; }
    }

    document.addEventListener('visibilitychange', function() {
        if (document.hidden) stop(); else start();
    });

    start();
})();
