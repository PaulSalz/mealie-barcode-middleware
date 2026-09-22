(function() {
    'use strict';

    var STATE_KEY = 'b2m-items-list-v2';
    var cfg = document.getElementById('items-page-config');
    var search = document.getElementById('items-table-search');
    var filterForm = document.getElementById('items-filter-form');
    var refreshTimer = null;

    function loadState() {
        try { return JSON.parse(localStorage.getItem(STATE_KEY) || '{}') || {}; }
        catch (e) { return {}; }
    }

    function saveState(patch) {
        var state = loadState();
        Object.keys(patch).forEach(function(key) { state[key] = patch[key]; });
        localStorage.setItem(STATE_KEY, JSON.stringify(state));
    }

    var saved = loadState();
    if (cfg && !window.location.search && saved.server) {
        var server = saved.server;
        var differs = (server.filter && server.filter !== 'all') || server.label || (server.sort && server.sort !== 'name') || (server.order && server.order !== 'asc');
        if (differs) {
            var restore = new URLSearchParams();
            restore.set('filter', server.filter || 'all');
            if (server.label) restore.set('label', server.label);
            restore.set('sort', server.sort || 'name');
            restore.set('order', server.order || 'asc');
            window.location.replace('/items?' + restore.toString());
            return;
        }
    }

    if (cfg) {
        saveState({server: {
            filter: cfg.dataset.filter || 'all',
            label: cfg.dataset.label || '',
            sort: cfg.dataset.sort || 'name',
            order: cfg.dataset.order || 'asc'
        }});
    }

    window._itemsTable = initAdvancedTable({
        tableId: 'items-table',
        searchId: 'items-table-search',
        paginationId: 'items-pagination',
        pageSizeId: 'page-size-label',
        defaultSort: 'sort-name',
        numericCols: ['sort-mappings', 'sort-scans', 'sort-last-scan', 'sort-updated'],
        emptyRowClass: 'items-empty-row'
    });

    if (search) {
        search.value = saved.search || '';
        if (search.value) search.dispatchEvent(new Event('input', {bubbles: true}));
        search.addEventListener('input', function() { saveState({search: search.value}); });
    }

    document.querySelectorAll('[data-page-size]').forEach(function(link) {
        link.addEventListener('click', function() { saveState({pageSize: Number(link.dataset.pageSize) || 20}); });
    });
    if (saved.pageSize && saved.pageSize !== 20) {
        var pageLink = document.querySelector('[data-page-size="' + Number(saved.pageSize) + '"]');
        if (pageLink) pageLink.click();
    }

    if (filterForm) {
        function rememberServerFilters() {
            var data = new FormData(filterForm);
            saveState({server: {
                filter: String(data.get('filter') || 'all'),
                label: String(data.get('label') || ''),
                sort: String(data.get('sort') || 'name'),
                order: String(data.get('order') || 'asc')
            }});
        }
        filterForm.addEventListener('submit', rememberServerFilters);

        // Inline onchange handlers are intentionally blocked by the app CSP.
        // Bind the four server filters here so changing any select performs the
        // same GET navigation without requiring unsafe-inline JavaScript.
        filterForm.querySelectorAll('select[name="filter"],select[name="label"],select[name="sort"],select[name="order"]').forEach(function(select) {
            select.removeAttribute('onchange');
            select.addEventListener('change', function() {
                rememberServerFilters();
                if (typeof filterForm.requestSubmit === 'function') filterForm.requestSubmit();
                else filterForm.submit();
            });
        });
    }

    async function refreshList() {
        try {
            var response = await fetch(window.location.pathname + window.location.search, {headers: {'Accept': 'text/html', 'X-B2M-Live': '1'}});
            if (!response.ok) return;
            var fresh = new DOMParser().parseFromString(await response.text(), 'text/html');
            var freshBody = fresh.getElementById('items-table-body');
            var currentBody = document.getElementById('items-table-body');
            if (freshBody && currentBody) currentBody.innerHTML = freshBody.innerHTML;
            var freshCount = fresh.getElementById('items-count');
            var currentCount = document.getElementById('items-count');
            if (freshCount && currentCount) currentCount.innerHTML = freshCount.innerHTML;
            var freshSync = fresh.getElementById('items-last-sync');
            var currentSync = document.getElementById('items-last-sync');
            if (freshSync && currentSync) currentSync.innerHTML = freshSync.innerHTML;
            if (window._itemsTable) window._itemsTable.reload();
            if (search && search.value) search.dispatchEvent(new Event('input', {bubbles: true}));
        } catch (error) {
            console.debug('Item list live refresh failed', error);
        }
    }

    function scheduleRefresh() {
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(refreshList, 180);
    }
    window.addEventListener('b2m:scan', scheduleRefresh);

    var modal = document.getElementById('modal-add-item');
    var input = document.getElementById('item-name');
    if (modal && input) modal.addEventListener('shown.bs.modal', function() { input.focus(); });
})();
