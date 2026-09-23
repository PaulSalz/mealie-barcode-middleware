(function() {
    'use strict';

    var QUEUE_KEY = 'b2m-label-generator-v2';
    var OUTPUT_KEY = 'b2m-label-output-mode-v1';
    var DESIGN_KEY = 'b2m-b21-design-v1';
    var PROFILE_KEY = 'b2m-b21-profile-v1';
    var configured = (document.getElementById('generator-config') || {}).dataset?.niimConfigured === '1';
    var $ = function(id) { return document.getElementById(id); };

    var state = {
        mode: localStorage.getItem(OUTPUT_KEY) || 'browser',
        status: {configured: configured, connected: false},
        profiles: [],
        bindings: {},
        profileId: localStorage.getItem(PROFILE_KEY) || '50x30',
        rfid: null,
        activeIndex: 0,
        designs: loadDesigns(),
        pollTimer: null
    };

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    function loadDesigns() {
        try { return JSON.parse(localStorage.getItem(DESIGN_KEY) || '{}') || {}; }
        catch (e) { return {}; }
    }

    function defaultDesign() {
        return {
            preset: 'stacked',
            frame: true,
            frameInsetMm: 1.0,
            frameWidthMm: 0.35,
            showCode: true,
            showLabel: true,
            showValue: false,
            codeX: 50,
            codeY: 42,
            codeW: 86,
            codeH: 58,
            codeRotation: 0,
            textX: 50,
            textY: 82,
            textW: 88,
            textSizePt: 14,
            textRotation: 0,
            valueX: 50,
            valueY: 94,
            valueW: 90,
            valueSizePt: 7,
            valueRotation: 0,
            threshold: 128
        };
    }

    function design() {
        if (!state.designs[state.profileId]) state.designs[state.profileId] = defaultDesign();
        return state.designs[state.profileId];
    }

    function saveDesign() {
        try { localStorage.setItem(DESIGN_KEY, JSON.stringify(state.designs)); } catch (e) {}
    }

    function readQueue() {
        try {
            var data = JSON.parse(localStorage.getItem(QUEUE_KEY) || '{}');
            return Array.isArray(data.queue) ? data.queue : [];
        } catch (e) { return []; }
    }

    function profile() {
        return state.profiles.find(function(row) { return row.id === state.profileId; }) || state.profiles[0] || {
            id: '50x30', name: '50 × 30 mm', width_mm: 50, height_mm: 30, dpi: 300, density: 3, label_type: 1
        };
    }

    function codeUrl(entry) {
        return '/labels/code.svg?kind=' + encodeURIComponent(entry.kind || 'auto') + '&value=' + encodeURIComponent(entry.code || '');
    }

    async function fetchJson(url, options) {
        var response = await fetch(url, Object.assign({headers: {'Accept': 'application/json'}}, options || {}));
        var data = await response.json().catch(function() { return {}; });
        if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
        return data;
    }

    function installStyles() {
        var style = document.createElement('style');
        style.id = 'b21-designer-styles';
        style.textContent = `
            .b21-output-card .b2m-choice-card { min-height: 68px; }
            .b21-connection-bar { border-top: 1px solid var(--tblr-border-color); margin-top: 1rem; padding-top: 1rem; }
            .b21-status-dot { width:.65rem;height:.65rem;border-radius:50%;display:inline-block;background:var(--tblr-secondary);box-shadow:0 0 0 .2rem rgba(98,105,118,.12); }
            .b21-status-dot.connected { background:var(--tblr-success);box-shadow:0 0 0 .2rem rgba(var(--tblr-success-rgb),.12); }
            .b21-status-dot.error { background:var(--tblr-danger);box-shadow:0 0 0 .2rem rgba(var(--tblr-danger-rgb),.12); }
            .b21-label-shell { display:flex;justify-content:center;align-items:center;min-height:320px;padding:1.25rem;border:1px solid var(--tblr-border-color);border-radius:var(--tblr-border-radius);background:var(--tblr-bg-surface-secondary);overflow:auto; }
            .b21-label-stage { position:relative;width:min(100%,760px);background:#fff;color:#111;box-shadow:0 4px 18px rgba(0,0,0,.14);overflow:hidden;touch-action:none;user-select:none; }
            .b21-label-frame { position:absolute;pointer-events:none;border-style:solid;border-color:#111;box-sizing:border-box; }
            .b21-element { position:absolute;transform:translate(-50%,-50%);cursor:move;touch-action:none; }
            .b21-code { object-fit:contain;max-width:none;max-height:none; }
            .b21-text,.b21-value { display:flex;align-items:center;justify-content:center;text-align:center;line-height:1.08;overflow:hidden;overflow-wrap:anywhere;font-family:Inter,DejaVu Sans,sans-serif; }
            .b21-value { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
            .b21-label-stage .b21-element:hover { outline:1px dashed rgba(var(--tblr-primary-rgb),.65);outline-offset:2px; }
            .b21-control-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.75rem; }
            .b21-control-grid .form-range { min-width:0; }
            .b21-section { border-top:1px solid var(--tblr-border-color);padding-top:1rem;margin-top:1rem; }
            .b21-rfid-badge { max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
            .b21-preview-meta { display:flex;gap:.5rem;flex-wrap:wrap;align-items:center; }
            .b21-profile-actions { display:flex;gap:.4rem;flex-wrap:wrap; }
            .b21-profile-editor { background:var(--tblr-bg-surface-secondary);border:1px solid var(--tblr-border-color);border-radius:var(--tblr-border-radius);padding:.75rem; }
            @media (max-width: 767.98px) { .b21-control-grid { grid-template-columns:1fr; } .b21-label-shell{min-height:230px;padding:.75rem;} }
        `;
        document.head.appendChild(style);
    }

    function buildUi() {
        var previewPage = $('preview-page');
        var layoutControl = $('label-format');
        if (!previewPage || !layoutControl || $('b21-output-card')) return;

        var previewCard = previewPage.closest('.card');
        var layoutCard = layoutControl.closest('.card');
        var row = previewCard.closest('.row.row-cards');
        var browserPreviewBody = previewPage.closest('.card-body');
        var browserLayoutBody = layoutControl.closest('.card-body');
        browserPreviewBody.id = 'browser-preview-body';
        browserLayoutBody.id = 'browser-layout-body';

        var output = document.createElement('div');
        output.id = 'b21-output-card';
        output.className = 'card mb-3 d-print-none b21-output-card';
        output.innerHTML = `
            <div class="card-header"><div><h3 class="card-title">Output</h3><p class="card-subtitle">Choose the normal browser sheet or the B21 Pro label roll.</p></div></div>
            <div class="card-body">
                <div class="b2m-choice-grid" id="b21-output-grid">
                    <label class="b2m-choice-card"><input class="form-check-input me-2" type="radio" name="label-output" value="browser"><span><strong>Browser print</strong><small>Sheet/page layout</small></span></label>
                    <label class="b2m-choice-card${configured ? '' : ' b2m-choice-disabled'}"><input class="form-check-input me-2" type="radio" name="label-output" value="b21"${configured ? '' : ' disabled'}><span><strong>B21 Pro</strong><small>niimblue-node · physical label preview</small></span></label>
                </div>
                <div class="b21-connection-bar d-none" id="b21-connection-bar">
                    <div class="d-flex align-items-center gap-3 flex-wrap">
                        <span class="b21-status-dot" id="b21-status-dot"></span>
                        <div class="flex-fill min-w-0"><div class="fw-semibold" id="b21-status-title">Not connected</div><div class="text-secondary small" id="b21-status-detail">Connection is manual.</div></div>
                        <button class="btn btn-outline-primary" type="button" id="b21-connect-button"><i class="ti ti-bluetooth icon"></i> Connect</button>
                    </div>
                </div>
            </div>`;
        row.parentNode.insertBefore(output, row);

        var b21Preview = document.createElement('div');
        b21Preview.id = 'b21-preview-body';
        b21Preview.className = 'card-body p-3 d-none';
        b21Preview.innerHTML = `
            <div class="d-flex gap-2 align-items-center flex-wrap mb-3">
                <div class="flex-fill"><label class="form-label mb-1">Preview label</label><select class="form-select" id="b21-entry-select"></select></div>
                <div class="b21-preview-meta pt-3" id="b21-preview-meta"></div>
            </div>
            <div class="b21-label-shell"><div class="b21-label-stage" id="b21-label-stage"></div></div>
            <div class="text-secondary small mt-2">Drag code/text directly on the label or use the precise position controls.</div>`;
        browserPreviewBody.parentNode.appendChild(b21Preview);

        var b21Controls = document.createElement('div');
        b21Controls.id = 'b21-layout-body';
        b21Controls.className = 'card-body d-none';
        b21Controls.innerHTML = controlsHtml();
        browserLayoutBody.parentNode.appendChild(b21Controls);

        output.querySelectorAll('input[name="label-output"]').forEach(function(input) {
            input.checked = input.value === state.mode;
            input.addEventListener('change', function() { if (input.checked) setMode(input.value); });
        });

        cloneNiimButton();
        bindControls();
        setMode(state.mode === 'b21' && configured ? 'b21' : 'browser');
    }

    function controlsHtml() {
        return `
            <div>
                <label class="form-label">Roll profile</label>
                <select class="form-select" id="b21-profile-select"></select>
                <div class="b21-profile-actions mt-2">
                    <button class="btn btn-sm btn-outline-primary" type="button" id="b21-new-profile"><i class="ti ti-plus"></i> New</button>
                    <button class="btn btn-sm btn-outline-secondary" type="button" id="b21-edit-profile"><i class="ti ti-adjustments"></i> Edit</button>
                    <button class="btn btn-sm btn-outline-danger" type="button" id="b21-delete-profile"><i class="ti ti-trash"></i></button>
                </div>
                <div class="b21-profile-editor mt-2 d-none" id="b21-profile-editor">
                    <div class="row g-2">
                        <div class="col-12"><label class="form-label">Profile name</label><input class="form-control" id="b21-profile-name"></div>
                        <div class="col-6"><label class="form-label">Width (mm)</label><input class="form-control" type="number" min="5" max="100" step="0.1" id="b21-profile-width"></div>
                        <div class="col-6"><label class="form-label">Height (mm)</label><input class="form-control" type="number" min="5" max="200" step="0.1" id="b21-profile-height"></div>
                        <div class="col-4"><label class="form-label">DPI</label><input class="form-control" type="number" min="100" max="1200" step="1" id="b21-profile-dpi"></div>
                        <div class="col-4"><label class="form-label">Density</label><input class="form-control" type="number" min="1" max="5" step="1" id="b21-profile-density"></div>
                        <div class="col-4"><label class="form-label">Label type</label><input class="form-control" type="number" min="1" step="1" id="b21-profile-label-type"></div>
                    </div>
                    <div class="text-end mt-2"><button class="btn btn-sm btn-primary" type="button" id="b21-save-profile"><i class="ti ti-device-floppy"></i> Save profile</button></div>
                </div>
            </div>
            <div class="b21-section">
                <div class="d-flex align-items-center justify-content-between gap-2"><label class="form-label mb-0">RFID roll</label><button class="btn btn-sm btn-outline-secondary" type="button" id="b21-read-rfid"><i class="ti ti-refresh"></i> Read</button></div>
                <div class="mt-2" id="b21-rfid-state"><span class="text-secondary small">Connect the printer to read the roll.</span></div>
            </div>
            <div class="b21-section">
                <label class="form-label">Layout preset</label>
                <div class="b2m-choice-grid" id="b21-preset-grid">
                    <label class="b2m-choice-card"><input class="form-check-input me-2" type="radio" name="b21-preset" value="stacked"><span><strong>Stacked</strong><small>Code above text</small></span></label>
                    <label class="b2m-choice-card"><input class="form-check-input me-2" type="radio" name="b21-preset" value="left"><span><strong>Code left</strong><small>Text on the right</small></span></label>
                    <label class="b2m-choice-card"><input class="form-check-input me-2" type="radio" name="b21-preset" value="right"><span><strong>Code right</strong><small>Text on the left</small></span></label>
                    <label class="b2m-choice-card"><input class="form-check-input me-2" type="radio" name="b21-preset" value="code"><span><strong>Code only</strong><small>No label text</small></span></label>
                    <label class="b2m-choice-card"><input class="form-check-input me-2" type="radio" name="b21-preset" value="text"><span><strong>Text only</strong><small>No barcode/QR</small></span></label>
                </div>
            </div>
            <div class="b21-section">
                <div class="row g-2">
                    <div class="col-6"><label class="form-check form-switch"><input class="form-check-input b21-design" type="checkbox" id="b21-show-frame" data-key="frame"><span class="form-check-label">Frame</span></label></div>
                    <div class="col-6"><label class="form-check form-switch"><input class="form-check-input b21-design" type="checkbox" id="b21-show-code" data-key="showCode"><span class="form-check-label">Code</span></label></div>
                    <div class="col-6"><label class="form-check form-switch"><input class="form-check-input b21-design" type="checkbox" id="b21-show-label" data-key="showLabel"><span class="form-check-label">Label text</span></label></div>
                    <div class="col-6"><label class="form-check form-switch"><input class="form-check-input b21-design" type="checkbox" id="b21-show-value" data-key="showValue"><span class="form-check-label">Raw code text</span></label></div>
                </div>
            </div>
            <div class="b21-section">
                <div class="fw-semibold mb-2">Code geometry</div>
                <div class="b21-control-grid">
                    ${rangeControl('Code X','b21-code-x','codeX',0,100,1,'%')}
                    ${rangeControl('Code Y','b21-code-y','codeY',0,100,1,'%')}
                    ${rangeControl('Code width','b21-code-w','codeW',10,100,1,'%')}
                    ${rangeControl('Code height','b21-code-h','codeH',10,100,1,'%')}
                </div>
                <label class="form-label mt-2">Code rotation</label><select class="form-select b21-design" id="b21-code-rotation" data-key="codeRotation"><option>0</option><option>90</option><option>180</option><option>270</option></select>
            </div>
            <div class="b21-section">
                <div class="fw-semibold mb-2">Label text</div>
                <div class="b21-control-grid">
                    ${rangeControl('Text X','b21-text-x','textX',0,100,1,'%')}
                    ${rangeControl('Text Y','b21-text-y','textY',0,100,1,'%')}
                    ${rangeControl('Text width','b21-text-w','textW',10,100,1,'%')}
                    ${rangeControl('Text size','b21-text-size','textSizePt',6,36,1,' pt')}
                </div>
                <label class="form-label mt-2">Text rotation</label><select class="form-select b21-design" id="b21-text-rotation" data-key="textRotation"><option>0</option><option>90</option><option>180</option><option>270</option></select>
            </div>
            <div class="b21-section">
                <div class="fw-semibold mb-2">Frame & output</div>
                <div class="b21-control-grid">
                    ${rangeControl('Frame inset','b21-frame-inset','frameInsetMm',0,5,.1,' mm')}
                    ${rangeControl('Frame width','b21-frame-width','frameWidthMm',.1,2,.05,' mm')}
                    ${rangeControl('Threshold','b21-threshold','threshold',1,255,1,'')}
                </div>
            </div>`;
    }

    function rangeControl(label, id, key, min, max, step, unit) {
        return '<div><label class="form-label">' + label + ': <strong id="' + id + '-value"></strong>' + unit + '</label><input class="form-range b21-design" type="range" id="' + id + '" data-key="' + key + '" min="' + min + '" max="' + max + '" step="' + step + '"></div>';
    }

    function cloneNiimButton() {
        var button = $('label-niim-print');
        if (!button) return;
        var clone = button.cloneNode(true);
        button.parentNode.replaceChild(clone, button);
        clone.innerHTML = '<i class="ti ti-printer icon"></i> Print B21';
        clone.addEventListener('click', printQueue);
    }

    function bindControls() {
        $('b21-connect-button').addEventListener('click', toggleConnection);
        $('b21-profile-select').addEventListener('change', function() {
            state.profileId = this.value;
            localStorage.setItem(PROFILE_KEY, state.profileId);
            syncControls(); renderB21Preview();
        });
        $('b21-new-profile').addEventListener('click', function() {
            var p = profile();
            var currentDesign = Object.assign({}, design());
            state.profileId = 'custom-' + Date.now();
            state.profiles.push({id: state.profileId, name: 'Custom label', width_mm: p.width_mm, height_mm: p.height_mm, dpi: p.dpi, density: p.density, label_type: p.label_type});
            state.designs[state.profileId] = currentDesign;
            saveDesign();
            renderProfileSelect(); showProfileEditor(true); syncControls(); renderB21Preview();
        });
        $('b21-edit-profile').addEventListener('click', function() { showProfileEditor(); });
        $('b21-save-profile').addEventListener('click', saveProfile);
        $('b21-delete-profile').addEventListener('click', deleteProfile);
        $('b21-read-rfid').addEventListener('click', readRfid);
        $('b21-entry-select').addEventListener('change', function() { state.activeIndex = Number(this.value || 0); renderB21Preview(); });

        document.querySelectorAll('input[name="b21-preset"]').forEach(function(input) {
            input.addEventListener('change', function() { if (input.checked) applyPreset(input.value); });
        });
        document.querySelectorAll('.b21-design').forEach(function(input) {
            var eventName = input.type === 'range' ? 'input' : 'change';
            input.addEventListener(eventName, function() {
                var d = design();
                var key = input.dataset.key;
                d[key] = input.type === 'checkbox' ? input.checked : Number(input.value);
                d.preset = 'custom';
                saveDesign(); updateRangeLabels(); renderB21Preview();
            });
        });
    }

    function setMode(mode) {
        state.mode = mode === 'b21' && configured ? 'b21' : 'browser';
        localStorage.setItem(OUTPUT_KEY, state.mode);
        var browser = state.mode === 'browser';
        $('browser-preview-body').classList.toggle('d-none', !browser);
        $('browser-layout-body').classList.toggle('d-none', !browser);
        $('b21-preview-body').classList.toggle('d-none', browser);
        $('b21-layout-body').classList.toggle('d-none', browser);
        $('b21-connection-bar').classList.toggle('d-none', browser);
        var browserBtn = $('label-print');
        var b21Btn = $('label-niim-print');
        if (browserBtn) browserBtn.classList.toggle('d-none', !browser);
        if (b21Btn) b21Btn.classList.toggle('d-none', browser);
        var previewCard = $('preview-page').closest('.card');
        var title = previewCard.querySelector('.card-title');
        var subtitle = previewCard.querySelector('.card-subtitle');
        if (title) title.textContent = browser ? 'Preview' : 'B21 label preview';
        if (subtitle) subtitle.textContent = browser ? 'Click a code in the queue for a large scannable preview.' : 'Physical roll proportions. Drag code and text to position them.';
        var layoutCard = $('label-format').closest('.card');
        var layoutTitle = layoutCard.querySelector('.card-title');
        var layoutSubtitle = layoutCard.querySelector('.card-subtitle');
        if (layoutTitle) layoutTitle.textContent = browser ? 'Print layout' : 'B21 label setup';
        if (layoutSubtitle) layoutSubtitle.textContent = browser ? 'Physical label/page settings. Code type is configured in the queue.' : 'Roll profile, RFID binding and label element geometry.';
        document.querySelectorAll('input[name="label-output"]').forEach(function(input) { input.checked = input.value === state.mode; });
        if (!browser) {
            refreshStatus(); loadProfiles(); syncQueueSelector(); renderB21Preview(); startPolling();
        } else stopPolling();
    }

    function startPolling() {
        stopPolling();
        state.pollTimer = window.setInterval(refreshStatus, 3000);
    }
    function stopPolling() { if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; } }

    async function refreshStatus() {
        if (!configured) return;
        try { state.status = await fetchJson('/labels/b21/status'); }
        catch (e) { state.status = {configured: true, connected: false, error: e.message}; }
        renderStatus();
    }

    function renderStatus() {
        var dot = $('b21-status-dot');
        var title = $('b21-status-title');
        var detail = $('b21-status-detail');
        var button = $('b21-connect-button');
        if (!dot || !button) return;
        dot.className = 'b21-status-dot' + (state.status.connected ? ' connected' : (state.status.error ? ' error' : ''));
        if (state.status.connected) {
            var meta = state.status.info && state.status.info.modelMetadata || {};
            title.textContent = 'Connected';
            detail.textContent = (meta.model || 'B21 Pro') + ' · ' + (meta.dpi || state.status.dpi || 300) + ' dpi · manual connection';
            button.className = 'btn btn-outline-danger';
            button.innerHTML = '<i class="ti ti-bluetooth-off icon"></i> Disconnect';
        } else {
            title.textContent = state.status.error ? 'Printer unavailable' : 'Not connected';
            detail.textContent = state.status.error || 'Connection is manual. B2M will not auto-connect before printing.';
            button.className = 'btn btn-outline-primary';
            button.innerHTML = '<i class="ti ti-bluetooth icon"></i> Connect';
        }
        updatePrintButton();
        $('b21-read-rfid').disabled = !state.status.connected;
    }

    async function toggleConnection() {
        var button = $('b21-connect-button');
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>' + (state.status.connected ? 'Disconnecting…' : 'Connecting…');
        try {
            state.status = await fetchJson(state.status.connected ? '/labels/b21/disconnect' : '/labels/b21/connect', {method: 'POST'});
            renderStatus();
            if (state.status.connected) await readRfid(true); else { state.rfid = null; renderRfid(); }
        } catch (e) {
            state.status = {configured: true, connected: false, error: e.message};
            renderStatus();
        } finally { button.disabled = false; }
    }

    async function loadProfiles() {
        try {
            var data = await fetchJson('/labels/b21/profiles');
            state.profiles = data.profiles || [];
            state.bindings = data.rfid_bindings || {};
            if (!state.profiles.some(function(row) { return row.id === state.profileId; }) && state.profiles.length) state.profileId = state.profiles[0].id;
            renderProfileSelect(); syncControls(); renderB21Preview();
        } catch (e) {
            console.warn('Could not load B21 profiles', e);
        }
    }

    function renderProfileSelect() {
        var select = $('b21-profile-select'); if (!select) return;
        select.innerHTML = state.profiles.map(function(row) {
            return '<option value="' + esc(row.id) + '"' + (row.id === state.profileId ? ' selected' : '') + '>' + esc(row.name) + ' · ' + row.width_mm + '×' + row.height_mm + ' mm</option>';
        }).join('');
        localStorage.setItem(PROFILE_KEY, state.profileId);
    }

    function showProfileEditor(forceOpen) {
        var editor = $('b21-profile-editor');
        var show = forceOpen === true || editor.classList.contains('d-none');
        editor.classList.toggle('d-none', !show);
        if (show) populateProfileEditor();
    }

    function populateProfileEditor() {
        var p = profile();
        $('b21-profile-name').value = p.name || '';
        $('b21-profile-width').value = p.width_mm;
        $('b21-profile-height').value = p.height_mm;
        $('b21-profile-dpi').value = p.dpi || 300;
        $('b21-profile-density').value = p.density || 3;
        $('b21-profile-label-type').value = p.label_type || 1;
    }

    async function saveProfile() {
        var payload = {
            id: state.profileId,
            name: $('b21-profile-name').value.trim(),
            width_mm: Number($('b21-profile-width').value),
            height_mm: Number($('b21-profile-height').value),
            dpi: Number($('b21-profile-dpi').value),
            density: Number($('b21-profile-density').value),
            label_type: Number($('b21-profile-label-type').value)
        };
        try {
            var data = await fetchJson('/labels/b21/profiles', {method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'}, body:JSON.stringify(payload)});
            state.profiles = data.profiles || state.profiles;
            $('b21-profile-editor').classList.add('d-none');
            renderProfileSelect(); syncControls(); renderB21Preview();
        } catch (e) { window.alert('Could not save roll profile: ' + e.message); }
    }

    async function deleteProfile() {
        if (state.profiles.length <= 1) return window.alert('At least one roll profile is required.');
        var p = profile();
        if (!window.confirm('Delete roll profile "' + p.name + '"?')) return;
        try {
            var data = await fetchJson('/labels/b21/profiles/' + encodeURIComponent(p.id), {method:'DELETE'});
            state.profiles = data.profiles || [];
            state.bindings = data.rfid_bindings || {};
            delete state.designs[state.profileId]; saveDesign();
            state.profileId = state.profiles[0].id;
            renderProfileSelect(); syncControls(); renderB21Preview(); renderRfid();
        } catch (e) { window.alert('Could not delete roll profile: ' + e.message); }
    }

    async function readRfid(silent) {
        if (!state.status.connected) return;
        var root = $('b21-rfid-state');
        if (!silent) root.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Reading roll…';
        try {
            state.rfid = await fetchJson('/labels/b21/rfid');
            if (state.rfid.profile_id && state.profiles.some(function(row) { return row.id === state.rfid.profile_id; })) {
                state.profileId = state.rfid.profile_id;
                renderProfileSelect(); syncControls(); renderB21Preview();
            }
            renderRfid();
        } catch (e) { root.innerHTML = '<span class="text-danger small">' + esc(e.message) + '</span>'; }
    }

    function renderRfid() {
        var root = $('b21-rfid-state'); if (!root) return;
        if (!state.status.connected) { root.innerHTML = '<span class="text-secondary small">Connect the printer to read the roll.</span>'; return; }
        if (!state.rfid) { root.innerHTML = '<span class="text-secondary small">Roll not read yet.</span>'; return; }
        var paper = state.rfid.paperRfidInfo || {};
        if (!paper.tagPresent) { root.innerHTML = '<span class="badge bg-secondary-lt">No RFID</span> <span class="text-secondary small">Choose a profile manually.</span>'; return; }
        var barcode = String(paper.barCode || '');
        var bound = state.rfid.profile_id;
        var p = state.profiles.find(function(row) { return row.id === bound; });
        root.innerHTML = '<div class="d-flex align-items-center gap-2 flex-wrap"><span class="badge bg-blue-lt b21-rfid-badge">RFID ' + esc(barcode || paper.uuid || 'detected') + '</span>' +
            (p ? '<span class="text-success small"><i class="ti ti-link"></i> ' + esc(p.name) + '</span>' : '<span class="text-warning small">Not assigned to a profile</span>') +
            '<button class="btn btn-sm btn-outline-primary ms-auto" type="button" id="b21-bind-rfid">Bind to current profile</button></div>';
        $('b21-bind-rfid').addEventListener('click', bindRfid);
    }

    async function bindRfid() {
        var paper = state.rfid && state.rfid.paperRfidInfo || {};
        var barcode = String(paper.barCode || '');
        if (!barcode) return window.alert('This roll does not expose an RFID barcode.');
        try {
            await fetchJson('/labels/b21/rfid-bind', {method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'}, body:JSON.stringify({barcode:barcode, profile_id:state.profileId})});
            state.rfid.profile_id = state.profileId;
            state.bindings[barcode] = state.profileId;
            renderRfid();
        } catch (e) { window.alert('Could not bind RFID roll: ' + e.message); }
    }

    function applyPreset(name) {
        var d = design();
        var presets = {
            stacked: {showCode:true,showLabel:true,codeX:50,codeY:42,codeW:86,codeH:58,codeRotation:0,textX:50,textY:82,textW:88,textSizePt:14,textRotation:0},
            left: {showCode:true,showLabel:true,codeX:29,codeY:50,codeW:52,codeH:82,codeRotation:0,textX:75,textY:50,textW:42,textSizePt:14,textRotation:0},
            right: {showCode:true,showLabel:true,codeX:71,codeY:50,codeW:52,codeH:82,codeRotation:0,textX:25,textY:50,textW:42,textSizePt:14,textRotation:0},
            code: {showCode:true,showLabel:false,codeX:50,codeY:50,codeW:92,codeH:86,codeRotation:0},
            text: {showCode:false,showLabel:true,textX:50,textY:50,textW:90,textSizePt:20,textRotation:0}
        };
        Object.assign(d, presets[name] || {}, {preset:name});
        saveDesign(); syncControls(); renderB21Preview();
    }

    function syncControls() {
        var d = design();
        document.querySelectorAll('.b21-design').forEach(function(input) {
            var key = input.dataset.key;
            if (!(key in d)) return;
            if (input.type === 'checkbox') input.checked = !!d[key]; else input.value = d[key];
        });
        document.querySelectorAll('input[name="b21-preset"]').forEach(function(input) { input.checked = input.value === d.preset; });
        updateRangeLabels(); populateProfileEditor(); renderProfileSelect(); renderRfid();
    }

    function updateRangeLabels() {
        document.querySelectorAll('input[type="range"].b21-design').forEach(function(input) {
            var value = $(input.id + '-value'); if (value) value.textContent = input.value;
        });
    }

    function syncQueueSelector() {
        var queue = readQueue();
        var select = $('b21-entry-select'); if (!select) return;
        if (state.activeIndex >= queue.length) state.activeIndex = Math.max(0, queue.length - 1);
        select.innerHTML = queue.length ? queue.map(function(entry, index) {
            return '<option value="' + index + '"' + (index === state.activeIndex ? ' selected' : '') + '>' + esc(entry.label || entry.code || ('Label ' + (index + 1))) + '</option>';
        }).join('') : '<option value="0">No labels in queue</option>';
        select.disabled = !queue.length;
        updatePrintButton();
    }

    function renderB21Preview() {
        if (!$('b21-label-stage')) return;
        syncQueueSelector();
        var queue = readQueue();
        var p = profile();
        var d = design();
        var stage = $('b21-label-stage');
        stage.style.aspectRatio = p.width_mm + ' / ' + p.height_mm;
        stage.innerHTML = '';
        $('b21-preview-meta').innerHTML = '<span class="badge bg-blue-lt">' + esc(p.name) + '</span><span class="badge bg-secondary-lt">' + p.width_mm + '×' + p.height_mm + ' mm</span><span class="badge bg-secondary-lt">' + (p.dpi || 300) + ' dpi</span>';
        if (!queue.length) {
            stage.innerHTML = '<div class="position-absolute top-50 start-50 translate-middle text-secondary">Add a code to the queue.</div>';
            return;
        }
        var entry = queue[state.activeIndex] || queue[0];
        if (d.frame) {
            var frame = document.createElement('div');
            frame.className = 'b21-label-frame';
            stage.appendChild(frame);
            requestAnimationFrame(function() {
                var pxPerMm = stage.clientWidth / p.width_mm;
                frame.style.inset = (d.frameInsetMm * pxPerMm) + 'px';
                frame.style.borderWidth = Math.max(1, d.frameWidthMm * pxPerMm) + 'px';
            });
        }
        if (d.showCode) {
            var img = document.createElement('img');
            img.className = 'b21-element b21-code'; img.dataset.element = 'code'; img.src = codeUrl(entry); img.alt = entry.code || '';
            applyElementStyle(img, d.codeX, d.codeY, d.codeW, d.codeH, d.codeRotation); stage.appendChild(img); makeDraggable(img, 'codeX', 'codeY');
        }
        if (d.showLabel) {
            var text = document.createElement('div');
            text.className = 'b21-element b21-text'; text.dataset.element = 'text'; text.textContent = entry.label || entry.code || '';
            applyElementStyle(text, d.textX, d.textY, d.textW, 28, d.textRotation); stage.appendChild(text); makeDraggable(text, 'textX', 'textY');
            requestAnimationFrame(function() { text.style.fontSize = physicalFontPx(stage, p, d.textSizePt) + 'px'; });
        }
        if (d.showValue) {
            var value = document.createElement('div');
            value.className = 'b21-element b21-value'; value.dataset.element = 'value'; value.textContent = entry.code || '';
            applyElementStyle(value, d.valueX, d.valueY, d.valueW, 18, d.valueRotation); stage.appendChild(value); makeDraggable(value, 'valueX', 'valueY');
            requestAnimationFrame(function() { value.style.fontSize = physicalFontPx(stage, p, d.valueSizePt) + 'px'; });
        }
    }

    function physicalFontPx(stage, p, pt) {
        return Math.max(7, (Number(pt) * 25.4 / 72) * (stage.clientWidth / p.width_mm));
    }

    function applyElementStyle(el, x, y, w, h, rotation) {
        el.style.left = x + '%'; el.style.top = y + '%'; el.style.width = w + '%'; el.style.height = h + '%';
        el.style.transform = 'translate(-50%,-50%) rotate(' + Number(rotation || 0) + 'deg)';
    }

    function makeDraggable(el, keyX, keyY) {
        el.addEventListener('pointerdown', function(event) {
            event.preventDefault(); el.setPointerCapture(event.pointerId);
            function move(e) {
                var rect = $('b21-label-stage').getBoundingClientRect();
                var d = design();
                d[keyX] = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
                d[keyY] = Math.max(0, Math.min(100, ((e.clientY - rect.top) / rect.height) * 100));
                el.style.left = d[keyX] + '%';
                el.style.top = d[keyY] + '%';
                saveDesign(); syncPositionInputs(keyX, keyY);
            }
            function end(e) {
                try { el.releasePointerCapture(e.pointerId); } catch (ignore) {}
                el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', end); el.removeEventListener('pointercancel', end);
                renderB21Preview();
            }
            el.addEventListener('pointermove', move); el.addEventListener('pointerup', end); el.addEventListener('pointercancel', end);
        });
    }

    function syncPositionInputs(keyX, keyY) {
        document.querySelectorAll('.b21-design').forEach(function(input) {
            if (input.dataset.key === keyX || input.dataset.key === keyY) input.value = design()[input.dataset.key];
        });
        updateRangeLabels();
    }

    function updatePrintButton() {
        var button = $('label-niim-print'); if (!button) return;
        button.disabled = !readQueue().length || !state.status.connected;
        button.title = !state.status.connected ? 'Connect B21 Pro first' : '';
    }

    async function registerQueue(queue) {
        await fetchJson('/labels/register', {
            method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'},
            body:JSON.stringify({labels:queue.map(function(entry){return {code:entry.code,label:entry.label,symbology:entry.kind,target_type:entry.target_type,target_id:entry.target_id,target_name:entry.target_name};})})
        });
    }

    function imageFromSvg(svg) {
        return new Promise(function(resolve, reject) {
            var blob = new Blob([svg], {type:'image/svg+xml'}), url = URL.createObjectURL(blob), img = new Image();
            img.onload = function(){URL.revokeObjectURL(url);resolve(img);}; img.onerror=function(){URL.revokeObjectURL(url);reject(new Error('Could not render code'));}; img.src=url;
        });
    }

    function drawContain(ctx, img, x, y, w, h) {
        var scale = Math.min(w / img.naturalWidth, h / img.naturalHeight);
        var dw = img.naturalWidth * scale, dh = img.naturalHeight * scale;
        ctx.drawImage(img, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
    }

    async function renderPng(entry) {
        var p = profile(), d = design(), pxPerMm = p.dpi / 25.4;
        var width = Math.max(8, Math.round(p.width_mm * pxPerMm)), height = Math.max(8, Math.round(p.height_mm * pxPerMm));
        var canvas = document.createElement('canvas'); canvas.width=width;canvas.height=height;
        var ctx = canvas.getContext('2d'); ctx.fillStyle='#fff';ctx.fillRect(0,0,width,height);ctx.fillStyle='#000';ctx.strokeStyle='#000';
        if (d.frame) {
            var inset = d.frameInsetMm * pxPerMm, line = Math.max(1, d.frameWidthMm * pxPerMm);
            ctx.lineWidth=line; ctx.strokeRect(inset+line/2,inset+line/2,width-2*inset-line,height-2*inset-line);
        }
        if (d.showCode) {
            var response = await fetch(codeUrl(entry)); if(!response.ok) throw new Error(await response.text());
            var img = await imageFromSvg(await response.text());
            drawRotatedImage(ctx,img,width*d.codeX/100,height*d.codeY/100,width*d.codeW/100,height*d.codeH/100,d.codeRotation);
        }
        if (d.showLabel) drawText(ctx,entry.label||entry.code||'',width*d.textX/100,height*d.textY/100,width*d.textW/100,d.textSizePt*p.dpi/72,d.textRotation,false);
        if (d.showValue) drawText(ctx,entry.code||'',width*d.valueX/100,height*d.valueY/100,width*d.valueW/100,d.valueSizePt*p.dpi/72,d.valueRotation,true);
        return canvas.toDataURL('image/png').split(',',2)[1];
    }

    function drawRotatedImage(ctx,img,cx,cy,w,h,rotation) {
        ctx.save();ctx.translate(cx,cy);ctx.rotate(Number(rotation||0)*Math.PI/180);drawContain(ctx,img,-w/2,-h/2,w,h);ctx.restore();
    }

    function drawText(ctx,text,cx,cy,maxWidth,fontPx,rotation,mono) {
        ctx.save();ctx.translate(cx,cy);ctx.rotate(Number(rotation||0)*Math.PI/180);ctx.fillStyle='#000';ctx.textAlign='center';ctx.textBaseline='middle';ctx.font=(mono?'500 ':'600 ')+Math.max(8,fontPx)+'px '+(mono?'monospace':'sans-serif');
        var words=String(text||'').split(/\s+/), lines=[],line='';
        words.forEach(function(word){var candidate=line?line+' '+word:word;if(ctx.measureText(candidate).width<=maxWidth||!line)line=candidate;else{lines.push(line);line=word;}});if(line)lines.push(line);lines=lines.slice(0,3);
        var lineH=fontPx*1.08,start=-(lines.length-1)*lineH/2;lines.forEach(function(row,index){ctx.fillText(row,0,start+index*lineH,maxWidth);});ctx.restore();
    }

    async function printQueue() {
        var queue = readQueue(), button = $('label-niim-print');
        if (!queue.length) return;
        await refreshStatus();
        if (!state.status.connected) return window.alert('B21 Pro is not connected. Connect it first.');
        var old = button.innerHTML; button.disabled=true;button.innerHTML='<span class="spinner-border spinner-border-sm me-2"></span>Printing…';
        try {
            await registerQueue(queue);
            var p=profile(), d=design();
            for(var i=0;i<queue.length;i++) {
                var image=await renderPng(queue[i]);
                await fetchJson('/labels/b21/print',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({image_base64:image,width_mm:p.width_mm,height_mm:p.height_mm,quantity:queue[i].qty||1,density:p.density,label_type:p.label_type,dpi:p.dpi,threshold:d.threshold})});
            }
            button.className='btn btn-success';button.innerHTML='<i class="ti ti-check icon"></i> Printed';setTimeout(function(){button.className='btn btn-outline-primary';button.innerHTML=old;updatePrintButton();},1800);
        } catch(e) { button.className='btn btn-outline-danger';button.innerHTML='<i class="ti ti-alert-triangle icon"></i> Failed';window.alert('B21 Pro print failed: '+e.message);setTimeout(function(){button.className='btn btn-outline-primary';button.innerHTML=old;updatePrintButton();},2200); }
    }

    function watchQueue() {
        var root=$('label-queue'), count=$('label-count'); if(!root)return;
        var observer=new MutationObserver(function(){syncQueueSelector();if(state.mode==='b21')renderB21Preview();});
        observer.observe(root,{childList:true,subtree:true,characterData:true});
        if(count) new MutationObserver(function(){syncQueueSelector();updatePrintButton();}).observe(count,{childList:true,subtree:true,characterData:true});
    }

    installStyles();
    buildUi();
    watchQueue();
    loadProfiles();
    refreshStatus();
})();
