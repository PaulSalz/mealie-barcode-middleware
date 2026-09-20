/** Dashboard health, scanner and shopping-list polling. */
(function() {
    'use strict';

    var indicator = document.getElementById('health-indicator');
    var statusEl = document.getElementById('health-status');
    var scannerOnline = document.getElementById('stat-scanner-online');
    var scannerTotal = document.getElementById('stat-scanner-total');
    var listRoot = document.getElementById('shopping-lists-status');
    var mealieButton = document.querySelector('.page-header a.btn-primary[target="_blank"]');
    var mealieUrl = mealieButton ? mealieButton.href.replace(/\/$/, '') : '';
    if (!indicator || !statusEl) return;
    var timer = null;

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    function renderShoppingLists(rows) {
        if (!listRoot) return;
        if (!rows || !rows.length) {
            listRoot.innerHTML = '<div class="col-12 text-secondary">No shopping lists returned by Mealie.</div>';
            return;
        }
        listRoot.innerHTML = rows.map(function(row) {
            var href = mealieUrl ? mealieUrl + '/shopping-lists/' + encodeURIComponent(row.id) : '#';
            return '<div class="col-sm-6 col-lg-3" data-shopping-list-id="' + esc(row.id) + '"><a href="' + esc(href) + '" target="_blank" rel="noopener" class="border rounded p-3 h-100 d-block text-reset text-decoration-none b2m-shopping-list-link"><div class="d-flex align-items-center"><span class="avatar bg-blue-lt text-blue me-3"><i class="ti ti-list-check"></i></span><div class="min-w-0 flex-fill"><div class="fw-medium text-truncate">' + esc(row.name) + (row.default ? ' <span class="badge bg-blue-lt">default</span>' : '') + '</div><div class="h2 mb-0"><span class="shopping-list-count">' + Number(row.count || 0) + '</span> <span class="fs-5 fw-normal text-secondary">items</span></div></div><i class="ti ti-external-link text-secondary ms-2"></i></div></a></div>';
        }).join('');
    }

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

        fetch('/api/dashboard').then(function(r) { return r.json(); }).then(function(d) {
            if (scannerOnline) scannerOnline.textContent = d.scanner_online == null ? '0' : d.scanner_online;
            if (scannerTotal) scannerTotal.textContent = d.scanner_total == null ? '0' : d.scanner_total;
            renderShoppingLists(d.shopping_lists || []);
        }).catch(function() {});
    }

    function start() {
        if (timer) clearInterval(timer);
        poll();
        timer = setInterval(poll, 10000);
    }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }
    document.addEventListener('visibilitychange', function() { if (document.hidden) stop(); else start(); });
    start();
})();
