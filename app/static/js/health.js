/** Dashboard Mealie health polling. */
(function() {
    'use strict';

    var indicator = document.getElementById('health-indicator');
    var statusEl = document.getElementById('health-status');
    if (!indicator || !statusEl) return;

    var config = document.getElementById('dashboard-poll-config');
    var pollSeconds = Math.max(1, Number(config && config.dataset.healthSeconds || 5));
    var timer = null;
    var busy = false;

    function poll() {
        if (busy || document.hidden) return;
        busy = true;
        fetch('/health?_=' + Date.now(), {
            headers: {Accept: 'application/json', 'Cache-Control': 'no-cache'},
            cache: 'no-store'
        }).then(function(r) { return r.json(); }).then(function(d) {
            var up = !!d.mealie_reachable;
            indicator.className = 'status-indicator status-' + (up ? 'green' : 'red') + (up ? ' status-indicator-animated' : '');
            statusEl.className = 'text-' + (up ? 'green' : 'red');
            statusEl.textContent = up ? 'Connected' : 'Unreachable';
        }).catch(function() {
            indicator.className = 'status-indicator status-red';
            statusEl.className = 'text-red';
            statusEl.textContent = 'Error';
        }).finally(function() {
            busy = false;
        });
    }

    function start() {
        if (timer) clearInterval(timer);
        poll();
        timer = setInterval(poll, pollSeconds * 1000);
    }

    function stop() {
        if (timer) {
            clearInterval(timer);
            timer = null;
        }
    }

    document.addEventListener('visibilitychange', function() {
        if (document.hidden) stop();
        else start();
    });
    window.addEventListener('focus', poll);
    start();
})();