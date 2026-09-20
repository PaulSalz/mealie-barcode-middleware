/** Settings page client behavior. */

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
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    var card = document.createElement('div');
    card.id = 'shopping-lists-card';
    card.className = 'card mt-4';
    card.innerHTML =
        '<div class="card-header"><div><h3 class="card-title">Shopping lists</h3><p class="card-subtitle">B2M discovers list IDs from Mealie. The selected default is used whenever a target does not choose a list explicitly.</p></div><div class="card-actions" id="default-shopping-list-badge"><span class="badge bg-secondary-lt">Loading…</span></div></div>' +
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
        var rows = (data && data.items) || [];
        var defaultId = String((data && data.default_id) || '');
        if (!rows.length) {
            select.innerHTML = '<option value="">No shopping lists available</option>';
            select.disabled = true; saveButton.disabled = true;
            badge.innerHTML = '<span class="badge bg-yellow-lt text-yellow">No lists</span>';
            return;
        }
        select.innerHTML = rows.map(function(row) {
            var isDefault = String(row.id) === defaultId || !!row.default;
            return '<option value="' + esc(row.id) + '"' + (isDefault ? ' selected' : '') + '>' + esc(row.name) + (isDefault ? ' · default' : '') + '</option>';
        }).join('');
        select.disabled = false; saveButton.disabled = false;
        var current = rows.find(function(row) { return String(row.id) === String(select.value); });
        var name = current ? current.name : select.options[select.selectedIndex].text.replace(/ · default$/, '');
        badge.innerHTML = '<span class="badge bg-blue-lt text-blue"><i class="ti ti-star me-1"></i>Default: ' + esc(name) + '</span>';
        state.textContent = source === 'cache' ? 'Cached lists shown immediately; checking Mealie in the background…' : 'Lists synchronized with Mealie.';
    }

    var cached = cachedData();
    if (cached && Array.isArray(cached.items) && cached.items.length) render(cached, 'cache');

    async function loadLists(force) {
        if (force) state.textContent = 'Refreshing shopping lists from Mealie…';
        try {
            var response = await fetch('/api/shopping-lists' + (force ? '?force=true' : ''), {headers: {'Accept': 'application/json'}});
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Could not load shopping lists');
            saveCache(data); render(data, 'server'); return data;
        } catch (error) {
            state.textContent = cached ? 'Could not refresh Mealie; showing cached lists.' : 'Could not load shopping lists.';
            result.className = 'form-hint text-danger'; result.textContent = error.message;
            return null;
        }
    }

    select.addEventListener('change', function() {
        var name = select.options[select.selectedIndex] ? select.options[select.selectedIndex].text.replace(/ · default$/, '') : 'selected list';
        badge.innerHTML = '<span class="badge bg-yellow-lt text-yellow">Pending default: ' + esc(name) + '</span>';
    });
    saveButton.addEventListener('click', async function() {
        saveButton.disabled = true; result.className = 'form-hint text-secondary'; result.textContent = 'Saving default list…';
        try {
            var response = await fetch('/api/settings/mealie/default-list', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({list_id: select.value})});
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Save failed');
            result.className = 'form-hint text-success'; result.textContent = 'Default shopping list saved.';
            await loadLists(false);
        } catch (error) { result.className = 'form-hint text-danger'; result.textContent = error.message; }
        finally { saveButton.disabled = false; }
    });
    document.getElementById('refresh-shopping-lists').addEventListener('click', function() { loadLists(true); });
    document.getElementById('test-mealie-connection').addEventListener('click', async function() {
        result.className = 'form-hint text-secondary'; result.textContent = 'Testing Mealie…';
        try {
            var response = await fetch('/api/settings/mealie/test', {method: 'POST'}); var data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || 'Connection failed');
            result.className = 'form-hint text-success'; result.textContent = 'Connected · HTTP ' + data.status + ' · ' + data.latency_ms + ' ms';
        } catch (error) { result.className = 'form-hint text-danger'; result.textContent = error.message; }
    });
    loadLists(false);
})();

(function settingsForms() {
    'use strict';

    function fieldValue(el) { if (el.type === 'checkbox') return el.checked ? 'True' : 'False'; return el.value; }
    function syncResetButton(field, btn) { var def = field.dataset.default; if (def !== undefined) btn.disabled = (fieldValue(field) === def); }
    function resetField(field) { var def = field.dataset.default; if (def === undefined) return; if (field.type === 'checkbox') field.checked = (def === 'True'); else field.value = def; }

    document.querySelectorAll('.btn-reset').forEach(function(btn) {
        var container = btn.closest('.row, .d-flex, .card-actions');
        var field = container ? container.querySelector('input, select') : null;
        if (!field) return;
        syncResetButton(field, btn);
        field.addEventListener('input', function() { syncResetButton(field, btn); });
        field.addEventListener('change', function() { syncResetButton(field, btn); });
        btn.addEventListener('click', function(e) { e.preventDefault(); resetField(field); syncResetButton(field, btn); field.dispatchEvent(new Event('change', {bubbles:true})); });
    });

    var themeForm = document.querySelector('form[action="/settings/theme"]');
    if (themeForm) {
        var COLOR_CSS = {
            blue:{hex:'#066fd1',rgb:'6,111,209'}, azure:{hex:'#4299e1',rgb:'66,153,225'}, indigo:{hex:'#4263eb',rgb:'66,99,235'}, purple:{hex:'#ae3ec9',rgb:'174,62,201'}, pink:{hex:'#d6336c',rgb:'214,51,108'}, red:{hex:'#d63939',rgb:'214,57,57'}, orange:{hex:'#f76707',rgb:'247,103,7'}, yellow:{hex:'#f59f00',rgb:'245,159,0'}, lime:{hex:'#74b816',rgb:'116,184,22'}, green:{hex:'#2fb344',rgb:'47,179,68'}, teal:{hex:'#0ca678',rgb:'12,166,120'}, cyan:{hex:'#17a2b8',rgb:'23,162,184'}
        };
        var FONT_CSS = {
            'sans-serif':'"Inter Var",Inter,-apple-system,BlinkMacSystemFont,San Francisco,Segoe UI,Roboto,Helvetica Neue,sans-serif',
            'serif':'Georgia,Times New Roman,times,serif', 'monospace':'Monaco,Consolas,Liberation Mono,Courier New,monospace', 'comic':'Comic Sans MS,Comic Sans,Chalkboard SE,Comic Neue,sans-serif,cursive',
            'dyslexia':'OpenDyslexic,"Atkinson Hyperlegible",Verdana,Tahoma,Arial,sans-serif'
        };
        var GRAY_CSS = {
            gray:null,
            slate:{50:'#f8fafc',100:'#f1f5f9',200:'#e2e8f0',300:'#cbd5e1',400:'#94a3b8',500:'#64748b',600:'#475569',700:'#334155',800:'#1e293b',900:'#0f172a',950:'#020617'},
            zinc:{50:'#fafafa',100:'#f4f4f5',200:'#e4e4e7',300:'#d4d4d8',400:'#a1a1aa',500:'#71717a',600:'#52525b',700:'#3f3f46',800:'#27272a',900:'#18181b',950:'#09090b'},
            neutral:{50:'#fafafa',100:'#f5f5f5',200:'#e5e5e5',300:'#d4d4d4',400:'#a3a3a3',500:'#737373',600:'#525252',700:'#404040',800:'#262626',900:'#171717',950:'#0a0a0a'},
            stone:{50:'#fafaf9',100:'#f5f5f4',200:'#e7e5e4',300:'#d6d3d1',400:'#a8a29e',500:'#78716c',600:'#57534e',700:'#44403c',800:'#292524',900:'#1c1917',950:'#0c0a09'}
        };
        var DEFAULT_GRAYS = {50:'#f9fafb',100:'#f3f4f6',200:'#e5e7eb',300:'#d1d5db',400:'#9ca3af',500:'#6b7280',600:'#4b5563',700:'#374151',800:'#1f2937',900:'#111827',950:'#030712'};
        var root = document.documentElement;
        function applyColor(name) { var c=COLOR_CSS[name]; if(c){root.style.setProperty('--tblr-primary',c.hex);root.style.setProperty('--tblr-primary-rgb',c.rgb);} }
        function applyFont(name) { var stack=FONT_CSS[name]; if(stack) root.style.setProperty('--tblr-body-font-family',stack); document.body.style.letterSpacing=name==='dyslexia'?'.018em':''; document.body.style.wordSpacing=name==='dyslexia'?'.045em':''; }
        function applyBase(name) { var vals=GRAY_CSS[name]||DEFAULT_GRAYS; for(var step in vals) root.style.setProperty('--tblr-gray-'+step,vals[step]); }
        function applyRadius(val) { root.style.setProperty('--tblr-border-radius-scale',val); }
        function applyMode(val) { root.setAttribute('data-bs-theme',val); }
        themeForm.addEventListener('change', function(e) {
            var el=e.target; if(!el.name||el.type!=='radio'||!el.checked) return;
            switch(el.name){case 'theme_mode':applyMode(el.value);break;case 'theme_color':applyColor(el.value);break;case 'theme_font':applyFont(el.value);break;case 'theme_base':applyBase(el.value);break;case 'theme_radius':applyRadius(el.value);break;}
        });

        var access = document.createElement('div');
        access.id = 'theme-accessibility';
        access.innerHTML = '<hr class="my-4"><h3 class="card-title">Display accessibility</h3><p class="card-subtitle">Optional monochrome high-contrast rendering for e-paper and low-color displays.</p><div class="row g-3 mt-1"><div class="col-md-5"><label class="form-check form-switch"><input class="form-check-input" type="checkbox" id="theme-epaper"><span class="form-check-label"><strong>E-paper / monochrome mode</strong><span class="d-block text-secondary small">Removes color dependence and most shadows.</span></span></label></div><div class="col-md-7"><label class="form-label">Contrast <strong id="theme-contrast-value">65</strong>%</label><input type="range" class="form-range" id="theme-contrast" min="0" max="100" step="1" value="65"><div class="form-hint">Controls border strength and secondary-text separation.</div></div></div>';
        themeForm.querySelector('.card-body').appendChild(access);
        var epaper = document.getElementById('theme-epaper');
        var contrast = document.getElementById('theme-contrast');
        var contrastValue = document.getElementById('theme-contrast-value');
        fetch('/api/theme').then(function(r){return r.json();}).then(function(t){epaper.checked=t.epaper==='true';contrast.value=t.contrast||65;contrastValue.textContent=contrast.value;}).catch(function(){});
        contrast.addEventListener('input', function(){ contrastValue.textContent=contrast.value; });

        themeForm.addEventListener('submit', async function(e) {
            if (themeForm.dataset.accessSaved === '1') return;
            e.preventDefault();
            try {
                var r = await fetch('/api/theme/accessibility', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({epaper:epaper.checked, contrast:Number(contrast.value)})});
                if (!r.ok) throw new Error('Accessibility settings could not be saved');
                themeForm.dataset.accessSaved = '1';
                HTMLFormElement.prototype.submit.call(themeForm);
            } catch (error) { window.alert(error.message); }
        });
    }

    var tokenTrigger = document.getElementById('token-modal-trigger');
    if (tokenTrigger) tokenTrigger.click();
})();
