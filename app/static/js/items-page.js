(function() {
    'use strict';

    var STORAGE_KEY = 'b2m-items-view-v1';
    var filterForm = document.getElementById('items-filter-form');
    var searchInput = document.getElementById('items-table-search');
    var tbody = document.querySelector('#items-table tbody');
    var countEl = document.getElementById('items-count');
    var refreshTimer = null;

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    function loadState() {
        try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') || {}; }
        catch (e) { return {}; }
    }

    function saveState(extra) {
        var state = loadState();
        if (filterForm) {
            new FormData(filterForm).forEach(function(value, key) { state[key] = value; });
        }
        if (searchInput) state.search = searchInput.value;
        Object.assign(state, extra || {});
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    }

    // Navigating to a bare /items restores the last server-side view. A URL with
    // explicit query parameters always wins, so shared/bookmarked links stay exact.
    var state = loadState();
    var params = new URLSearchParams(window.location.search);
    if (!params.toString() && (state.filter || state.label || state.sort || state.order)) {
        var restore = new URLSearchParams();
        if (state.filter && state.filter !== 'all') restore.set('filter', state.filter);
        if (state.label) restore.set('label', state.label);
        if (state.sort && state.sort !== 'name') restore.set('sort', state.sort);
        if (state.order && state.order !== 'asc') restore.set('order', state.order);
        if (restore.toString()) {
            window.location.replace('/items?' + restore.toString());
            return;
        }
    }

    if (searchInput && state.search) searchInput.value = state.search;

    if (filterForm) {
        filterForm.addEventListener('submit', function() { saveState(); });
        filterForm.querySelectorAll('select').forEach(function(select) {
            select.addEventListener('change', function() { saveState(); });
        });
    }
    if (searchInput) searchInput.addEventListener('input', function() { saveState(); });
    document.querySelectorAll('[data-page-size]').forEach(function(link) {
        link.addEventListener('click', function() { saveState({pageSize: Number(link.dataset.pageSize || 20)}); });
    });

    window._itemsTable = initAdvancedTable({
        tableId: 'items-table',
        searchId: 'items-table-search',
        paginationId: 'items-pagination',
        pageSizeId: 'page-size-label',
        defaultSort: 'sort-name',
        numericCols: ['sort-mappings', 'sort-scans', 'sort-last-scan', 'sort-updated'],
        emptyRowClass: 'items-empty-row',
        initialPageSize: Number(state.pageSize || 20)
    });

    function aliasHtml(raw) {
        if (!raw) return '';
        try {
            var aliases = JSON.parse(raw);
            if (Array.isArray(aliases) && aliases.length) return '<div class="text-secondary small">' + aliases.map(esc).join(', ') + '</div>';
        } catch (e) {}
        return '';
    }

    function rowHtml(item) {
        var source = item.source === 'mealie'
            ? '<span class="badge bg-blue text-blue-fg">Mealie</span>'
            : '<span class="badge bg-purple text-purple-fg">Custom</span>';
        return '<tr>' +
            '<td class="sort-name"><a href="/items/' + encodeURIComponent(item.id) + '">' + esc(item.name) + '</a>' + aliasHtml(item.aliases) + '</td>' +
            '<td class="sort-category">' + esc(item.category || '—') + '</td>' +
            '<td class="sort-source">' + source + '</td>' +
            '<td class="sort-mappings" data-sort-value="' + Number(item.mapping_count || 0) + '">' + Number(item.mapping_count || 0) + '</td>' +
            '<td class="sort-scans" data-sort-value="' + Number(item.scan_count || 0) + '">' + Number(item.scan_count || 0) + '</td>' +
            '<td class="sort-last-scan" data-sort-value="' + Number(item.last_scan_sort || 0) + '" title="' + esc(item.last_scan_absolute || '') + '">' + esc(item.last_scan || 'Never') + '</td>' +
            '<td class="sort-updated" data-sort-value="' + Number(item.updated_sort || 0) + '" title="' + esc(item.updated_absolute || '') + '">' + esc(item.updated || '—') + '</td>' +
            '</tr>';
    }

    async function refreshItems() {
        if (!tbody) return;
        try {
            var query = new URLSearchParams(window.location.search);
            var response = await fetch('/api/items-list?' + query.toString(), {headers: {'Accept': 'application/json'}});
            if (!response.ok) return;
            var data = await response.json();
            var items = data.items || [];
            tbody.innerHTML = items.length
                ? items.map(rowHtml).join('')
                : '<tr class="items-empty-row"><td colspan="7"><div class="empty py-4"><p class="empty-title">No matching items</p></div></td></tr>';
            if (countEl) countEl.textContent = items.length;
            if (window._itemsTable) window._itemsTable.reload();
        } catch (error) {
            console.debug('Item live refresh failed', error);
        }
    }

    window.addEventListener('b2m:scan', function() {
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(refreshItems, 250);
    });

    // Focus the name input when the add-item modal opens.
    var modal = document.getElementById('modal-add-item');
    var input = document.getElementById('item-name');
    if (modal && input) modal.addEventListener('shown.bs.modal', function() { input.focus(); });
})();
