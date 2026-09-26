/** Settings page client behavior. */

(function settingsBasicAdvancedUx() {
    'use strict';
    if (window.location.pathname !== '/settings') return;

    var form = document.querySelector('form[action="/settings/configuration"]');
    if (!form) return;
    var body = form.querySelector('.card-body');
    if (!body) return;

    var advancedFields = [
        'lookup_primary', 'lookup_strategy', 'lookup_enrich_in_background',
        'fuzzy_match_threshold', 'fuzzy_ambiguity_gap', 'item_sync_interval_hours',
        'lookup_ttl_days', 'max_retry_attempts', 'notification_toast_seconds',
        'notification_group_window_seconds', 'dashboard_poll_interval_seconds',
        'health_poll_interval_seconds', 'shopping_print_poll_interval_seconds',
        'log_level', 'middleware_base_url'
    ];
    var advancedNodes = [];

    function fieldContainer(field) {
        return field.closest('.col-md-6, .col-12, .card-actions') || field.parentElement;
    }

    advancedFields.forEach(function(name) {
        var field = document.getElementById('setting_' + name);
        if (!field) return;
        var node = fieldContainer(field);
        if (!node || advancedNodes.indexOf(node) !== -1) return;
        node.classList.add('b2m-advanced-setting');
        node.dataset.advancedSetting = '1';
        advancedNodes.push(node);
    });

    Array.from(form.querySelectorAll('.card')).forEach(function(card) {
        var title = card.querySelector('.card-title');
        if (title && title.textContent.trim() === 'Infrastructure') {
            card.classList.add('b2m-advanced-section');
            card.dataset.advancedSetting = '1';
            advancedNodes.push(card);
        }
    });
    Array.from(form.querySelectorAll('label.form-label')).forEach(function(label) {
        if (label.textContent.trim().replace(/\s+/g, ' ') !== 'API endpoint') return;
        var node = label.closest('.col-md-6');
        if (node && advancedNodes.indexOf(node) === -1) {
            node.classList.add('b2m-advanced-setting');
            node.dataset.advancedSetting = '1';
            advancedNodes.push(node);
        }
    });

    var toolbar = document.createElement('div');
    toolbar.className = 'card bg-muted-lt mb-3';
    toolbar.id = 'settings-view-tools';
    toolbar.innerHTML =
        '<div class="card-body py-3"><div class="row g-3 align-items-center">' +
        '<div class="col-md"><div class="input-icon"><span class="input-icon-addon"><i class="ti ti-search"></i></span>' +
        '<input type="search" class="form-control" id="settings-search" placeholder="Search settings on this page…" autocomplete="off"></div></div>' +
        '<div class="col-md-auto"><label class="form-check form-switch mb-0"><input class="form-check-input" type="checkbox" id="settings-show-advanced">' +
        '<span class="form-check-label"><strong>Advanced settings</strong><span class="d-block text-secondary small">Technical tuning and diagnostics</span></span></label></div>' +
        '</div><div class="text-secondary small mt-2" id="settings-search-state"></div></div>';

    var firstSection = body.querySelector('.card.mt-3');
    if (firstSection) body.insertBefore(toolbar, firstSection);
    else body.appendChild(toolbar);

    var advancedToggle = document.getElementById('settings-show-advanced');
    var search = document.getElementById('settings-search');
    var searchState = document.getElementById('settings-search-state');
    var storageKey = 'b2m-settings-advanced-v1';
    try { advancedToggle.checked = localStorage.getItem(storageKey) === '1'; } catch (e) {}

    function normalized(value) { return String(value || '').toLocaleLowerCase().trim(); }
    function isSearchMatch(node, query) { return !query || normalized(node.textContent).indexOf(query) !== -1; }

    function refreshView() {
        var query = normalized(search.value);
        var showAdvanced = advancedToggle.checked;
        var matches = 0;
        advancedNodes.forEach(function(node) {
            var show = showAdvanced || (query && isSearchMatch(node, query));
            node.classList.toggle('d-none', !show);
        });
        Array.from(form.querySelectorAll('.card.mt-3')).forEach(function(card) {
            if (card.id === 'settings-view-tools') return;
            var matchesSearch = isSearchMatch(card, query);
            var advancedSection = card.classList.contains('b2m-advanced-section');
            var visibleForMode = !advancedSection || showAdvanced || (query && matchesSearch);
            card.classList.toggle('d-none', !(visibleForMode && matchesSearch));
            if (visibleForMode && matchesSearch) matches += 1;
        });
        if (query) searchState.textContent = matches ? matches + ' matching section' + (matches === 1 ? '' : 's') + '.' : 'No settings match this search.';
        else if (!showAdvanced && advancedNodes.length) searchState.textContent = advancedNodes.length + ' technical setting' + (advancedNodes.length === 1 ? '' : 's') + ' hidden. Enable Advanced settings to show them.';
        else searchState.textContent = '';
    }

    advancedToggle.addEventListener('change', function() {
        try { localStorage.setItem(storageKey, advancedToggle.checked ? '1' : '0'); } catch (e) {}
        refreshView();
    });
    search.addEventListener('input', refreshView);
    refreshView();

    var submit = form.querySelector('button[type="submit"]');
    if (submit) {
        var state = document.createElement('span');
        state.id = 'settings-save-state';
        state.className = 'text-secondary small me-3';
        var footerRow = submit.parentElement;
        if (footerRow) footerRow.insertBefore(state, submit);
        var dirty = false;
        function markDirty(event) {
            if (event && event.target && !event.target.matches('input[name^="setting_"], select[name^="setting_"]')) return;
            dirty = true;
            state.className = 'text-warning small me-3';
            state.textContent = 'Unsaved changes';
        }
        form.addEventListener('input', markDirty);
        form.addEventListener('change', markDirty);
        form.addEventListener('submit', function() {
            dirty = false;
            state.className = 'text-secondary small me-3';
            state.textContent = 'Saving…';
            submit.disabled = true;
        });
        window.addEventListener('beforeunload', function(event) {
            if (!dirty) return;
            event.preventDefault();
            event.returnValue = '';
        });
        if (new URLSearchParams(window.location.search).get('saved') === '1') {
            state.className = 'text-success small me-3';
            state.textContent = 'Saved';
        }
    }
})();

(function prewarmMealieShoppingLists() {
    'use strict';
    if (window.location.pathname !== '/settings') return;
    var key = 'b2m-shopping-lists-cache-v1';
    fetch('/api/shopping-lists?force=true', {headers: {'Accept': 'application/json'}})
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(data) { if (data && Array.isArray(data.items)) localStorage.setItem(key, JSON.stringify(data)); })
        .catch(function() {});
})();

(function renderMealieShoppingListsEarly() {
    'use strict';
    if (window.location.pathname !== '/settings' || (new URLSearchParams(window.location.search).get('tab') || 'mealie') !== 'mealie') return;
    var CACHE_KEY = 'b2m-shopping-lists-cache-v1';
    var body = document.querySelector('.col-12.col-md-9 .card-body');
    if (!body || document.getElementById('shopping-lists-card')) return;
    function esc(value) {
        return String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }
    var card = document.createElement('div');
    card.id = 'shopping-lists-card'; card.className = 'card mt-4';
    card.innerHTML = '<div class="card-header"><div><h3 class="card-title">Shopping lists</h3><p class="card-subtitle">B2M discovers list IDs from Mealie. The selected default is used whenever a target does not choose a list explicitly.</p></div><div class="card-actions" id="default-shopping-list-badge"><span class="badge bg-secondary-lt">Loading…</span></div></div>' +
        '<div class="card-body"><div class="row g-3 align-items-end"><div class="col-md-7"><label class="form-label">Default shopping list</label><select class="form-select" id="default-shopping-list" disabled><option>Loading shopping lists…</option></select><div class="form-hint" id="shopping-list-refresh-state">Loading cached list information…</div></div><div class="col-md-5"><div class="btn-list"><button class="btn btn-primary" type="button" id="save-default-shopping-list" disabled>Save default</button><button class="btn btn-outline-primary" type="button" id="refresh-shopping-lists"><i class="ti ti-refresh icon"></i> Refresh lists</button><button class="btn btn-outline-primary" type="button" id="test-mealie-connection"><i class="ti ti-plug-connected icon"></i> Test connection</button></div></div><div class="col-12"><div class="form-hint" id="mealie-runtime-result"></div></div></div></div>';
    body.appendChild(card);
    var select = document.getElementById('default-shopping-list');
    var badge = document.getElementById('default-shopping-list-badge');
    var state = document.getElementById('shopping-list-refresh-state');
    var result = document.getElementById('mealie-runtime-result');
    var saveButton = document.getElementById('save-default-shopping-list');
    function cachedData() { try { return JSON.parse(localStorage.getItem(CACHE_KEY) || 'null'); } catch (e) { return null; } }
    function saveCache(data) { try { localStorage.setItem(CACHE_KEY, JSON.stringify(data)); } catch (e) {} }
    function render(data, source) {
        var rows = (data && data.items) || []; var defaultId = String((data && data.default_id) || '');
        if (!rows.length) { select.innerHTML = '<option value="">No shopping lists available</option>'; select.disabled = true; saveButton.disabled = true; badge.innerHTML = '<span class="badge bg-yellow-lt text-yellow">No lists</span>'; return; }
        select.innerHTML = rows.map(function(row) { var isDefault = String(row.id) === defaultId || !!row.default; return '<option value="' + esc(row.id) + '"' + (isDefault ? ' selected' : '') + '>' + esc(row.name) + (isDefault ? ' · default' : '') + '</option>'; }).join('');
        select.disabled = false; saveButton.disabled = false;
        var current = rows.find(function(row) { return String(row.id) === String(select.value); });
        var name = current ? current.name : select.options[select.selectedIndex].text.replace(/ · default$/, '');
        badge.innerHTML = '<span class="badge bg-blue-lt text-blue"><i class="ti ti-star me-1"></i>Default: ' + esc(name) + '</span>';
        state.textContent = source === 'cache' ? 'Cached lists shown immediately; checking Mealie in the background…' : 'Lists synchronized with Mealie.';
    }
    var cached = cachedData(); if (cached && Array.isArray(cached.items) && cached.items.length) render(cached, 'cache');
    async function loadLists(force) {
        if (force) state.textContent = 'Refreshing shopping lists from Mealie…';
        try {
            var response = await fetch('/api/shopping-lists' + (force ? '?force=true' : ''), {headers: {'Accept': 'application/json'}}); var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load shopping lists');
            saveCache(data); render(data, 'server'); return data;
        } catch (error) { state.textContent = cached ? 'Could not refresh Mealie; showing cached lists.' : 'Could not load shopping lists.'; result.className = 'form-hint text-danger'; result.textContent = error.message; return null; }
    }
    select.addEventListener('change', function() { var name = select.options[select.selectedIndex] ? select.options[select.selectedIndex].text.replace(/ · default$/, '') : 'selected list'; badge.innerHTML = '<span class="badge bg-yellow-lt text-yellow">Pending default: ' + esc(name) + '</span>'; });
    saveButton.addEventListener('click', async function() {
        saveButton.disabled = true; result.className = 'form-hint text-secondary'; result.textContent = 'Saving default list…';
        try { var response = await fetch('/api/settings/mealie/default-list', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({list_id: select.value})}); var data = await response.json(); if (!response.ok) throw new Error(data.error || 'Save failed'); result.className = 'form-hint text-success'; result.textContent = 'Default shopping list saved.'; await loadLists(false); }
        catch (error) { result.className = 'form-hint text-danger'; result.textContent = error.message; }
        finally { saveButton.disabled = false; }
    });
    document.getElementById('refresh-shopping-lists').addEventListener('click', function() { loadLists(true); });
    document.getElementById('test-mealie-connection').addEventListener('click', async function() {
        result.className = 'form-hint text-secondary'; result.textContent = 'Testing Mealie…';
        try { var response = await fetch('/api/settings/mealie/test', {method: 'POST'}); var data = await response.json(); if (!response.ok || !data.ok) throw new Error(data.error || 'Connection failed'); result.className = 'form-hint text-success'; result.textContent = 'Connected · HTTP ' + data.status + ' · ' + data.latency_ms + ' ms'; }
        catch (error) { result.className = 'form-hint text-danger'; result.textContent = error.message; }
    });
    loadLists(false);
})();

(function settingsForms() {
    'use strict';
    function fieldValue(el) { if (el.type === 'checkbox') return el.checked ? 'True' : 'False'; return el.value; }
    function syncResetButton(field, btn) { var def = field.dataset.default; if (def !== undefined) btn.disabled = (fieldValue(field) === def); }
    function resetField(field) { var def = field.dataset.default; if (def === undefined) return; if (field.type === 'checkbox') field.checked = (def === 'True'); else field.value = def; }
    document.querySelectorAll('.btn-reset').forEach(function(btn) {
        var container = btn.closest('.row, .d-flex, .card-actions'); var field = container ? container.querySelector('input, select') : null; if (!field) return;
        syncResetButton(field, btn); field.addEventListener('input', function() { syncResetButton(field, btn); }); field.addEventListener('change', function() { syncResetButton(field, btn); });
        btn.addEventListener('click', function(e) { e.preventDefault(); resetField(field); syncResetButton(field, btn); field.dispatchEvent(new Event('change', {bubbles:true})); });
    });

    var themeForm = document.querySelector('form[action="/settings/theme"]');
    if (themeForm) {
        var COLOR_CSS = {blue:{hex:'#066fd1',rgb:'6,111,209'},azure:{hex:'#4299e1',rgb:'66,153,225'},indigo:{hex:'#4263eb',rgb:'66,99,235'},purple:{hex:'#ae3ec9',rgb:'174,62,201'},pink:{hex:'#d6336c',rgb:'214,51,108'},red:{hex:'#d63939',rgb:'214,57,57'},orange:{hex:'#f76707',rgb:'247,103,7'},yellow:{hex:'#f59f00',rgb:'245,159,0'},lime:{hex:'#74b816',rgb:'116,184,22'},green:{hex:'#2fb344',rgb:'47,179,68'},teal:{hex:'#0ca678',rgb:'12,166,120'},cyan:{hex:'#17a2b8',rgb:'23,162,184'}};
        var FONT_CSS = {'sans-serif':'"Inter Var",Inter,-apple-system,BlinkMacSystemFont,San Francisco,Segoe UI,Roboto,Helvetica Neue,sans-serif','serif':'Georgia,Times New Roman,times,serif','monospace':'Monaco,Consolas,Liberation Mono,Courier New,monospace','comic':'Comic Sans MS,Comic Sans,Chalkboard SE,Comic Neue,sans-serif,cursive','dyslexia':'OpenDyslexic,"Atkinson Hyperlegible",Verdana,Tahoma,Arial,sans-serif'};
        var GRAY_CSS = {gray:null,slate:{50:'#f8fafc',100:'#f1f5f9',200:'#e2e8f0',300:'#cbd5e1',400:'#94a3b8',500:'#64748b',600:'#475569',700:'#334155',800:'#1e293b',900:'#0f172a',950:'#020617'},zinc:{50:'#fafafa',100:'#f4f4f5',200:'#e4e4e7',300:'#d4d4d8',400:'#a1a1aa',500:'#71717a',600:'#52525b',700:'#3f3f46',800:'#27272a',900:'#18181b',950:'#09090b'},neutral:{50:'#fafafa',100:'#f5f5f5',200:'#e5e5e5',300:'#d4d4d4',400:'#a3a3a3',500:'#737373',600:'#525252',700:'#404040',800:'#262626',900:'#171717',950:'#0a0a0a'},stone:{50:'#fafaf9',100:'#f5f5f4',200:'#e7e5e4',300:'#d6d3d1',400:'#a8a29e',500:'#78716c',600:'#57534e',700:'#44403c',800:'#292524',900:'#1c1917',950:'#0c0a09'}};
        var DEFAULT_GRAYS = {50:'#f9fafb',100:'#f3f4f6',200:'#e5e7eb',300:'#d1d5db',400:'#9ca3af',500:'#6b7280',600:'#4b5563',700:'#374151',800:'#1f2937',900:'#111827',950:'#030712'};
        var root = document.documentElement;
        function applyColor(name) { var c=COLOR_CSS[name]; if(c){root.style.setProperty('--tblr-primary',c.hex);root.style.setProperty('--tblr-primary-rgb',c.rgb);} }
        function applyFont(name) { var stack=FONT_CSS[name]; if(stack) root.style.setProperty('--tblr-body-font-family',stack); document.body.style.letterSpacing=name==='dyslexia'?'.018em':''; document.body.style.wordSpacing=name==='dyslexia'?'.045em':''; }
        function applyBase(name) { var vals=GRAY_CSS[name]||DEFAULT_GRAYS; for(var step in vals) root.style.setProperty('--tblr-gray-'+step,vals[step]); }
        function applyRadius(val) { root.style.setProperty('--tblr-border-radius-scale',val); }
        function applyMode(val) { root.setAttribute('data-bs-theme',val); }
        themeForm.addEventListener('change', function(e) { var el=e.target; if(!el.name||el.type!=='radio'||!el.checked) return; switch(el.name){case 'theme_mode':applyMode(el.value);break;case 'theme_color':applyColor(el.value);break;case 'theme_font':applyFont(el.value);break;case 'theme_base':applyBase(el.value);break;case 'theme_radius':applyRadius(el.value);break;} });
        var access = document.createElement('div'); access.id = 'theme-accessibility';
        access.innerHTML = '<hr class="my-4"><h3 class="card-title">Display accessibility</h3><p class="card-subtitle">Optional monochrome high-contrast rendering for e-paper and low-color displays.</p><div class="row g-3 mt-1"><div class="col-md-5"><label class="form-check form-switch"><input class="form-check-input" type="checkbox" id="theme-epaper"><span class="form-check-label"><strong>E-paper / monochrome mode</strong><span class="d-block text-secondary small">Removes color dependence and most shadows.</span></span></label></div><div class="col-md-7"><label class="form-label">Contrast <strong id="theme-contrast-value">65</strong>%</label><input type="range" class="form-range" id="theme-contrast" min="0" max="100" step="1" value="65"><div class="form-hint">Controls border strength and secondary-text separation.</div></div></div>';
        themeForm.querySelector('.card-body').appendChild(access);
        var epaper = document.getElementById('theme-epaper'); var contrast = document.getElementById('theme-contrast'); var contrastValue = document.getElementById('theme-contrast-value');
        fetch('/api/theme').then(function(r){return r.json();}).then(function(t){epaper.checked=t.epaper==='true';contrast.value=t.contrast||65;contrastValue.textContent=contrast.value;}).catch(function(){});
        contrast.addEventListener('input', function(){ contrastValue.textContent=contrast.value; });
        themeForm.addEventListener('submit', async function(e) {
            if (themeForm.dataset.accessSaved === '1') return; e.preventDefault();
            try { var r = await fetch('/api/theme/accessibility', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({epaper:epaper.checked, contrast:Number(contrast.value)})}); if (!r.ok) throw new Error('Accessibility settings could not be saved'); themeForm.dataset.accessSaved = '1'; HTMLFormElement.prototype.submit.call(themeForm); }
            catch (error) { window.alert(error.message); }
        });
    }
    var tokenTrigger = document.getElementById('token-modal-trigger'); if (tokenTrigger) tokenTrigger.click();
})();

(function databaseSafetyUx() {
    'use strict';
    if (window.location.pathname !== '/settings' || (new URLSearchParams(window.location.search).get('tab') || 'mealie') !== 'admin') return;
    var cards = Array.from(document.querySelectorAll('.col-12.col-md-9 .card.mt-3'));
    var backupCard = cards.find(function(card) { var title = card.querySelector('.card-title'); return title && title.textContent.trim() === 'Backup'; });
    var dangerCard = cards.find(function(card) { var title = card.querySelector('.card-title'); return title && title.textContent.trim() === 'Danger Zone'; });
    if (backupCard) {
        var subtitle = backupCard.querySelector('.card-subtitle');
        if (subtitle) subtitle.textContent = 'Create a consistent SQLite snapshot. WAL data is included and the copy is verified before download.';
        var button = backupCard.querySelector('form[action="/settings/admin/backup"] button');
        if (button) button.innerHTML = '<i class="ti ti-shield-check icon"></i> Create verified backup';
        var body = backupCard.querySelector('.card-body');
        if (body && !document.getElementById('verified-backup-state')) {
            var note = document.createElement('div');
            note.id = 'verified-backup-state';
            note.className = 'alert alert-info mt-3 mb-0 py-2';
            note.innerHTML = '<i class="ti ti-shield-check me-2"></i><span>Checking backup status…</span>';
            body.appendChild(note);
        }
    }
    if (dangerCard && !document.getElementById('database-backup-first')) {
        var warning = document.createElement('div');
        warning.id = 'database-backup-first';
        warning.className = 'alert alert-warning m-3 mb-0';
        warning.innerHTML = '<div class="d-flex align-items-center gap-3"><i class="ti ti-shield-check fs-2"></i><div class="flex-fill"><strong>Back up before deleting data</strong><div class="small">Create a verified backup first so reset or purge actions remain recoverable.</div></div><form method="post" action="/settings/admin/backup" class="m-0"><button class="btn btn-warning" type="submit">Create backup</button></form></div>';
        var body = dangerCard.querySelector('.card-body');
        if (body) dangerCard.insertBefore(warning, body);
    }
    fetch('/api/database/backup-status', {headers:{Accept:'application/json'}, cache:'no-store'})
        .then(function(response) { return response.ok ? response.json() : null; })
        .then(function(data) {
            if (!data) return;
            var box = document.getElementById('verified-backup-state');
            if (!box) return;
            if (data.last_verified_backup) {
                var when = new Date(data.last_verified_backup);
                box.className = 'alert alert-success mt-3 mb-0 py-2';
                box.innerHTML = '<i class="ti ti-circle-check me-2"></i>Last verified backup: <strong>' + when.toLocaleString() + '</strong>. The snapshot passed SQLite integrity_check.';
            } else {
                box.className = 'alert alert-warning mt-3 mb-0 py-2';
                box.innerHTML = '<i class="ti ti-alert-triangle me-2"></i>No verified backup has been downloaded from this installation yet.';
            }
        }).catch(function() {
            var box = document.getElementById('verified-backup-state');
            if (box) box.textContent = 'Backup status could not be loaded.';
        });
})();


(function settingsPrinterDisconnect() {
    'use strict';
    if (window.location.pathname !== '/settings') return;

    var status = document.getElementById('b2m-printer-connection-status');
    var button = document.getElementById('b2m-printer-force-disconnect');
    if (!status || !button) return;

    function show(text, tone) {
        status.className = 'small ' + (tone || 'text-secondary');
        status.textContent = text;
    }

    async function refresh() {
        try {
            var response = await fetch('/labels/b21/status', {headers:{'Accept':'application/json'}, cache:'no-store'});
            var data = await response.json().catch(function () { return {}; });
            if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
            if (!data.configured) show('Printer not configured', 'text-secondary');
            else if (data.connected) show('Connected · ' + (data.address || 'printer'), 'text-success');
            else show('Disconnected · ' + (data.address || 'printer'), 'text-warning');
        } catch (error) {
            show('Printer status unavailable · ' + error.message, 'text-warning');
        }
    }

    button.addEventListener('click', async function () {
        button.disabled = true;
        show('Disconnecting…', 'text-secondary');
        try {
            var response = await fetch('/labels/b21/disconnect', {
                method:'POST',
                headers:{'Accept':'application/json','Content-Type':'application/json'},
                body:'{}'
            });
            var data = await response.json().catch(function () { return {}; });
            if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
            show('Disconnect requested · ' + (data.address || 'printer'), 'text-success');
            await refresh();
        } catch (error) {
            show('Disconnect failed · ' + error.message, 'text-danger');
        } finally {
            button.disabled = false;
        }
    });

    refresh();
    window.setInterval(refresh, 8000);
})();
