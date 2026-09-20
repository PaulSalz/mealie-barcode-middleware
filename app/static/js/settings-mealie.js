(function() {
    'use strict';

    if (window.location.pathname !== '/settings' || new URLSearchParams(window.location.search).get('tab') !== 'mealie') return;

    var CACHE_KEY = 'b2m-shopping-lists-cache-v1';
    var body = document.querySelector('.col-12.col-md-9 .card-body');
    if (!body || document.getElementById('shopping-lists-card')) return;

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    var card = document.createElement('div');
    card.id = 'shopping-lists-card';
    card.className = 'card mt-4';
    card.innerHTML =
        '<div class="card-header"><div><h3 class="card-title">Shopping lists</h3><p class="card-subtitle">B2M discovers list IDs from Mealie. The selected default is used whenever a target does not choose a list explicitly.</p></div><div class="card-actions" id="default-shopping-list-badge"><span class="badge bg-secondary-lt">Loading…</span></div></div>' +
        '<div class="card-body"><div class="row g-3 align-items-end"><div class="col-md-7"><label class="form-label">Default shopping list</label><select class="form-select" id="default-shopping-list" disabled><option>Loading shopping lists…</option></select><div class="form-hint" id="shopping-list-refresh-state">Using cached data while Mealie is refreshed in the background.</div></div><div class="col-md-5"><div class="btn-list"><button class="btn btn-primary" type="button" id="save-default-shopping-list" disabled>Save default</button><button class="btn btn-outline-primary" type="button" id="refresh-shopping-lists"><i class="ti ti-refresh icon"></i> Refresh lists</button><button class="btn btn-outline-primary" type="button" id="test-mealie-connection"><i class="ti ti-plug-connected icon"></i> Test connection</button></div></div><div class="col-12"><div class="form-hint" id="mealie-runtime-result"></div></div></div></div>';
    body.appendChild(card);

    var select = document.getElementById('default-shopping-list');
    var badge = document.getElementById('default-shopping-list-badge');
    var refreshState = document.getElementById('shopping-list-refresh-state');
    var result = document.getElementById('mealie-runtime-result');
    var saveButton = document.getElementById('save-default-shopping-list');

    function render(data, source) {
        var rows = (data && data.items) || [];
        var defaultId = String((data && data.default_id) || '');
        if (!rows.length) {
            select.innerHTML = '<option value="">No shopping lists available</option>';
            select.disabled = true;
            saveButton.disabled = true;
            badge.innerHTML = '<span class="badge bg-yellow-lt text-yellow">No lists</span>';
            return;
        }
        select.innerHTML = rows.map(function(row) {
            var isDefault = String(row.id) === defaultId || !!row.default;
            return '<option value="' + esc(row.id) + '"' + (isDefault ? ' selected' : '') + '>' + esc(row.name) + (isDefault ? ' · default' : '') + '</option>';
        }).join('');
        select.disabled = false;
        saveButton.disabled = false;
        var current = rows.find(function(row) { return String(row.id) === String(select.value); });
        badge.innerHTML = '<span class="badge bg-blue-lt text-blue"><i class="ti ti-star me-1"></i>Default: ' + esc(current ? current.name : select.options[select.selectedIndex].text.replace(/ · default$/, '')) + '</span>';
        refreshState.textContent = source === 'cache' ? 'Showing cached lists; refreshing from Mealie…' : 'Lists synchronized with Mealie.';
    }

    function saveCache(data) {
        try { localStorage.setItem(CACHE_KEY, JSON.stringify(data)); } catch (e) {}
    }

    function cachedData() {
        try { return JSON.parse(localStorage.getItem(CACHE_KEY) || 'null'); } catch (e) { return null; }
    }

    var cached = cachedData();
    if (cached && Array.isArray(cached.items) && cached.items.length) render(cached, 'cache');

    async function loadLists(force) {
        if (force) refreshState.textContent = 'Refreshing shopping lists from Mealie…';
        try {
            var response = await fetch('/api/shopping-lists' + (force ? '?force=true' : ''), {headers: {'Accept': 'application/json'}});
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load shopping lists');
            saveCache(data);
            render(data, 'server');
            return data;
        } catch (error) {
            refreshState.textContent = cached ? 'Could not refresh Mealie; showing cached lists.' : 'Could not load shopping lists.';
            result.className = 'form-hint text-danger';
            result.textContent = error.message;
            return null;
        }
    }

    select.addEventListener('change', function() {
        var name = select.options[select.selectedIndex] ? select.options[select.selectedIndex].text.replace(/ · default$/, '') : 'selected list';
        badge.innerHTML = '<span class="badge bg-yellow-lt text-yellow">Pending default: ' + esc(name) + '</span>';
    });

    saveButton.addEventListener('click', async function() {
        saveButton.disabled = true;
        result.className = 'form-hint text-secondary';
        result.textContent = 'Saving default list…';
        try {
            var response = await fetch('/api/settings/mealie/default-list', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({list_id: select.value})
            });
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Save failed');
            result.className = 'form-hint text-success';
            result.textContent = 'Default shopping list saved.';
            await loadLists(false);
        } catch (error) {
            result.className = 'form-hint text-danger';
            result.textContent = error.message;
        } finally {
            saveButton.disabled = false;
        }
    });

    document.getElementById('refresh-shopping-lists').addEventListener('click', function() { loadLists(true); });
    document.getElementById('test-mealie-connection').addEventListener('click', async function() {
        result.className = 'form-hint text-secondary'; result.textContent = 'Testing Mealie…';
        try {
            var response = await fetch('/api/settings/mealie/test', {method: 'POST'});
            var data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'Connection failed');
            result.className = 'form-hint text-success';
            result.textContent = 'Connected · HTTP ' + data.status + ' · ' + data.latency_ms + ' ms';
        } catch (error) {
            result.className = 'form-hint text-danger'; result.textContent = error.message;
        }
    });

    // Fast path uses the server-side cache. A forced refresh follows afterwards,
    // so navigation is never blocked on a fresh Mealie request.
    loadLists(false).then(function() {
        setTimeout(function() { loadLists(true); }, 250);
    });
})();
