(function() {
    'use strict';

    var STORAGE_KEY = 'b2m-label-generator-v2';
    var queue = [];
    var entryIdSequence = 1;
    var tabId = (window.crypto && window.crypto.randomUUID)
        ? window.crypto.randomUUID()
        : Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
    var activePane = 'generic';
    var MAX_PREVIEW_CODES = 24;
    var pendingStorageSync = false;
    var $ = function(id) { return document.getElementById(id); };

    function newEntryId() {
        return tabId + ':' + (entryIdSequence++);
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    function asciiOnly(value) {
        return /^[\x20-\x7E]*$/.test(String(value || ''));
    }

    function genericCode(text) {
        return 'GENERIC:' + encodeURIComponent(String(text || '').trim());
    }

    function codeUrl(entry) {
        return '/labels/code.svg?kind=' + encodeURIComponent(entry.kind || 'auto') + '&value=' + encodeURIComponent(entry.code);
    }

    function cleanEntry(entry) {
        return {
            code: String(entry.code || '').trim(),
            label: String(entry.label || entry.code || '').trim(),
            kind: ['auto', 'qr', 'code128'].includes(entry.kind) ? entry.kind : 'auto',
            target_type: entry.target_type || 'custom',
            target_id: entry.target_id || '',
            target_name: entry.target_name || entry.label || '',
            qty: Math.max(1, Math.min(99, Number(entry.qty || 1))),
            _id: entry._id == null || entry._id === '' ? newEntryId() : String(entry._id)
        };
    }

    function storageSettings() {
        var ids = ['label-format','label-page-format','label-size','label-gap','label-padding','label-margin','label-font-size','label-show-text','label-show-border'];
        var values = {};
        ids.forEach(function(id) {
            var el = $(id);
            if (el) values[id] = el.type === 'checkbox' ? el.checked : el.value;
        });
        return values;
    }

    function readStoredState() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            console.warn('Could not read label queue state', e);
            return null;
        }
    }

    function persist(changes) {
        changes = changes || {};
        try {
            var latest = readStoredState() || {};
            var nextState = {
                queue: changes.queue
                    ? queue.map(cleanEntry)
                    : (Array.isArray(latest.queue) ? latest.queue.map(cleanEntry) : queue.map(cleanEntry)),
                settings: changes.settings ? storageSettings() : (latest.settings || storageSettings()),
                pane: changes.pane ? activePane : (latest.pane || activePane),
                writer: tabId,
                updated_at: Date.now()
            };
            localStorage.setItem(STORAGE_KEY, JSON.stringify(nextState));
            queue = nextState.queue;
        } catch (e) {
            console.warn('Could not persist label queue', e);
        }
    }

    function restore() {
        try {
            var state = readStoredState();
            if (!state) return false;
            if (Array.isArray(state.queue)) {
                queue = state.queue.map(cleanEntry).filter(function(e) { return e.code; });
            }
            Object.keys(state.settings || {}).forEach(function(id) {
                var el = $(id);
                if (!el) return;
                if (el.type === 'checkbox') el.checked = !!state.settings[id];
                else el.value = state.settings[id];
            });
            if (state.pane) activePane = state.pane;
            return true;
        } catch (e) {
            console.warn('Could not restore label queue', e);
            return false;
        }
    }

    function refreshQueueFromStorage() {
        var latest = readStoredState();
        if (latest && Array.isArray(latest.queue)) {
            queue = latest.queue.map(cleanEntry).filter(function(e) { return e.code; });
        }
    }

    function syncPageFromStorage() {
        if (!restore()) {
            queue = [];
            activePane = 'generic';
        }
        switchPane(activePane, true);
        updateSettingLabels();
        render();
    }

    function addEntry(entry, deferRender) {
        refreshQueueFromStorage();
        entry = cleanEntry(entry);
        if (!entry.code) return;
        if (entry.kind === 'code128' && !asciiOnly(entry.code)) entry.kind = 'auto';
        var duplicate = queue.find(function(row) {
            return row.code === entry.code && row.target_type === entry.target_type && row.target_id === entry.target_id;
        });
        if (duplicate) {
            duplicate.qty = Math.min(99, duplicate.qty + entry.qty);
        } else {
            entry._id = newEntryId();
            queue.push(entry);
        }
        persist({queue: true});
        if (!deferRender) render();
    }

    function removeEntry(id) {
        refreshQueueFromStorage();
        queue = queue.filter(function(entry) { return entry._id !== String(id); });
        persist({queue: true});
        render();
    }

    function setQty(id, quantity) {
        refreshQueueFromStorage();
        var entry = queue.find(function(row) { return row._id === String(id); });
        if (!entry) return;
        var parsed = Number(quantity);
        entry.qty = Math.max(1, Math.min(99, Number.isFinite(parsed) ? Math.round(parsed) : 1));
        persist({queue: true});
        render();
    }

    function typeBadge(type) {
        var labels = {food: 'Food', recipe: 'Recipe', action: 'Action', generic: 'Generic', custom: 'Custom'};
        return labels[type] || type;
    }

    function renderQueue() {
        var root = $('label-queue');
        var empty = $('label-queue-empty');
        root.innerHTML = '';
        empty.classList.toggle('d-none', queue.length > 0);

        var fragment = document.createDocumentFragment();
        queue.forEach(function(entry) {
            var locked = entry.target_type === 'action';
            var col = document.createElement('div');
            col.className = 'col-12';
            col.innerHTML = '<div class="card label-card"><button class="btn btn-sm btn-icon btn-outline-danger label-remove" type="button" title="Remove"><i class="ti ti-x"></i></button>' +
                '<div class="card-body"><div class="row g-3 align-items-center">' +
                '<div class="col-auto"><img loading="lazy" decoding="async" class="label-code-preview rounded border bg-white p-1" style="width:112px;height:80px;object-fit:contain;cursor:zoom-in" alt="Code preview" src="' + esc(codeUrl(entry)) + '" data-bs-toggle="modal" data-bs-target="#code-preview-modal"></div>' +
                '<div class="col"><div class="row g-2">' +
                '<div class="col-md-6"><label class="form-label small mb-1">Label</label><input class="form-control form-control-sm entry-label" value="' + esc(entry.label) + '"></div>' +
                '<div class="col-md-6"><label class="form-label small mb-1">Code value</label><input class="form-control form-control-sm font-monospace entry-code" value="' + esc(entry.code) + '"' + (locked ? ' readonly' : '') + '></div>' +
                '<div class="col-md-5"><label class="form-label small mb-1">Code style</label><select class="form-select form-select-sm entry-kind"><option value="auto"' + (entry.kind === 'auto' ? ' selected' : '') + '>Auto</option><option value="qr"' + (entry.kind === 'qr' ? ' selected' : '') + '>QR</option><option value="code128"' + (entry.kind === 'code128' ? ' selected' : '') + '>Code 128</option></select></div>' +
                '<div class="col-md-5"><label class="form-label small mb-1">Copies</label><div class="input-group input-group-sm label-copy-actions"><input class="form-control entry-qty" type="number" min="1" max="99" step="1" value="' + entry.qty + '" aria-label="Copies"><button class="btn btn-outline-primary entry-edit" type="button" data-entry-id="' + esc(entry._id) + '" title="Edit label"><i class="ti ti-edit"></i> Edit</button></div></div>' +

                '</div><div class="form-hint entry-hint mt-1">' + (entry.kind === 'auto' ? 'Auto uses Code 128 for short ASCII IDs and QR for longer/Unicode values.' : '') + '</div></div>' +
                '</div></div></div>';

            col.querySelector('.label-remove').addEventListener('click', function() { removeEntry(entry._id); });
            col.querySelector('.entry-qty').addEventListener('change', function() {
                setQty(entry._id, this.value);
            });
            col.querySelector('.entry-edit').addEventListener('click', function() {
                var editor = window.__b2mB21LabelEditor;
                var select = $('b21-entry-select');
                var index = queue.findIndex(function(row) { return String(row._id) === String(entry._id); });
                if (editor && typeof editor.selectQueueEntry === 'function') editor.selectQueueEntry(entry._id);
                else if (select && index >= 0) {
                    select.value = String(index);
                    select.dispatchEvent(new Event('change', {bubbles:true}));
                }
                var output = $('b21-output-b21');
                if (output && !output.disabled && !output.checked) {
                    output.checked = true;
                    output.dispatchEvent(new Event('change', {bubbles:true}));
                }
                requestAnimationFrame(function() {
                    requestAnimationFrame(function() {
                        var stage = $('b21-label-stage');
                        var target = stage && !stage.closest('.d-none') ? stage : $('browser-preview-body');
                        if (target) target.scrollIntoView({behavior:'smooth', block:'center'});
                    });
                });
            });
            col.querySelector('.entry-label').addEventListener('input', function() {
                var entryId = entry._id;
                var value = this.value;
                refreshQueueFromStorage();
                var current = queue.find(function(row) { return row._id === entryId; });
                if (!current) { render(); return; }
                current.label = value;
                current.target_name = current.target_name || value;
                persist({queue: true}); renderPreview();
            });
            col.querySelector('.entry-code').addEventListener('change', function() {
                var entryId = entry._id;
                var value = this.value.trim();
                refreshQueueFromStorage();
                var current = queue.find(function(row) { return row._id === entryId; });
                if (!current) { render(); return; }
                if (!value) { this.value = current.code; return; }
                current.code = value;
                if (current.kind === 'code128' && !asciiOnly(value)) current.kind = 'auto';
                persist({queue: true}); render();
            });
            col.querySelector('.entry-kind').addEventListener('change', function() {
                var entryId = entry._id;
                var selected = this.value;
                refreshQueueFromStorage();
                var current = queue.find(function(row) { return row._id === entryId; });
                if (!current) { render(); return; }
                if (selected === 'code128' && !asciiOnly(current.code)) {
                    current.kind = 'auto';
                } else {
                    current.kind = selected;
                }
                persist({queue: true}); render();
            });
            col.querySelector('.label-code-preview').addEventListener('click', function() {
                $('code-preview-title').textContent = entry.label || 'Code preview';
                $('code-preview-value').textContent = entry.code;
                $('code-preview-large').src = codeUrl(entry);
            });
            fragment.appendChild(col);
        });
        root.appendChild(fragment);

        $('label-count').textContent = '(' + queue.reduce(function(sum, e) { return sum + e.qty; }, 0) + ')';
        $('label-clear').disabled = queue.length === 0;
        $('label-print').disabled = queue.length === 0;
        if ($('label-niim-print')) $('label-niim-print').disabled = queue.length === 0;
    }

    function layout() {
        var size = Number($('label-size').value);
        var format = $('label-format').value;
        var ratio = format.split(':').map(Number);
        var height = size * ratio[1] / ratio[0];
        return {
            width: size,
            height: height,
            gap: Number($('label-gap').value),
            padding: Number($('label-padding').value),
            margin: Number($('label-margin').value),
            font: Number($('label-font-size').value),
            showText: $('label-show-text').checked,
            border: $('label-show-border').checked,
            landscape: ratio[0] > ratio[1]
        };
    }

    function applyVars(element, values, printMode) {
        var p = printMode ? '--label-' : '--preview-';
        var unit = printMode ? 'mm' : 'px';
        var scale = printMode ? 1 : 2.2;
        element.style.setProperty(p + 'width', (values.width * scale) + unit);
        element.style.setProperty(p + 'height', (values.height * scale) + unit);
        element.style.setProperty(p + 'gap', (values.gap * scale) + unit);
        element.style.setProperty(p + 'padding', (values.padding * scale) + unit);
        element.style.setProperty(p + 'margin', (values.margin * scale) + unit);
        element.style.setProperty(p + 'font-size', values.font + (printMode ? 'pt' : 'px'));
        element.style.setProperty(p + 'img-max', values.landscape ? '58%' : 'none');
    }

    function createLabelCell(entry, values, printMode) {
        var cell = document.createElement('div');
        cell.className = (printMode ? 'label-cell' : 'label-preview-cell') + (values.landscape ? ' landscape' : '') + (values.border ? ' has-border' : '');
        var img = document.createElement('img');
        if (!printMode) {
            img.loading = 'lazy';
            img.decoding = 'async';
        }
        img.src = codeUrl(entry);
        img.alt = entry.code;
        img.style.objectFit = 'contain';
        cell.appendChild(img);
        if (values.showText) {
            var text = document.createElement('div');
            text.className = printMode ? 'label-text' : 'label-preview-text';
            text.textContent = entry.label;
            cell.appendChild(text);
        }
        return cell;
    }

    function renderPreview() {
        var values = layout();
        var preview = $('preview-grid');
        preview.innerHTML = '';
        applyVars(preview, values, false);
        var total = queue.reduce(function(sum, entry) { return sum + entry.qty; }, 0);
        var visibleEntries = queue.slice(0, MAX_PREVIEW_CODES);
        var fragment = document.createDocumentFragment();
        visibleEntries.forEach(function(entry) {
            fragment.appendChild(createLabelCell(entry, values, false));
        });
        preview.appendChild(fragment);
        if (!queue.length) preview.innerHTML = '<div class="label-preview-empty text-center text-secondary py-5">Add a code to preview it.</div>';

        var summary = total ? total + ' label' + (total === 1 ? '' : 's') : '';
        if (total > queue.length) summary += ' across ' + queue.length + ' code' + (queue.length === 1 ? '' : 's');
        if (queue.length > MAX_PREVIEW_CODES) {
            summary += ' · showing ' + MAX_PREVIEW_CODES + ' of ' + queue.length + ' code previews; printing includes all labels';
        } else if (total > queue.length) {
            summary += ' · one preview per code';
        }
        if (total) summary += ' · ' + values.width + '×' + Math.round(values.height * 10) / 10 + ' mm';
        $('preview-summary').textContent = summary;
    }

    function renderPrint() {
        var values = layout();
        var grid = $('print-grid');
        grid.innerHTML = '';
        applyVars(grid, values, true);
        queue.forEach(function(entry) {
            for (var n = 0; n < entry.qty; n++) grid.appendChild(createLabelCell(entry, values, true));
        });
        var style = $('dynamic-print-style');
        if (!style) {
            style = document.createElement('style');
            style.id = 'dynamic-print-style';
            document.head.appendChild(style);
        }
        var page = $('label-page-format').value;
        var sizeRule = page === 'auto' ? '' : ' size: ' + page + ';';
        style.textContent = '@media print { @page {' + sizeRule + ' margin: ' + values.margin + 'mm; } }';
    }

    function render() {
        renderQueue();
        renderPreview();
    }

    function switchPane(type, skipPersist) {
        activePane = type;
        document.querySelectorAll('[data-code-type]').forEach(function(button) { button.classList.toggle('active', button.dataset.codeType === type); });
        document.querySelectorAll('.generator-pane').forEach(function(pane) { pane.classList.toggle('d-none', pane.dataset.pane !== type); });
        if (!skipPersist) persist({pane: true});
    }

    function debounce(fn, wait) {
        var timer;
        return function() {
            var args = arguments;
            clearTimeout(timer);
            timer = setTimeout(function() { fn.apply(null, args); }, wait);
        };
    }

    async function fetchJson(url, options) {
        var response = await fetch(url, Object.assign({headers: {'Accept': 'application/json'}}, options || {}));
        var data = await response.json().catch(function() { return {}; });
        if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
        return data;
    }

    function renderSearchResults(root, rows, onSelect, emptyText) {
        root.innerHTML = '';
        if (!rows.length) {
            root.innerHTML = '<div class="list-group-item text-secondary">' + esc(emptyText || 'No matches') + '</div>';
            return;
        }
        rows.forEach(function(row) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
            button.innerHTML = '<span>' + esc(row.name) + '</span>' + (row.id ? '<code class="small ms-2">' + esc(row.id) + '</code>' : '');
            button.addEventListener('click', function() { onSelect(row); });
            root.appendChild(button);
        });
    }

    var searchFood = debounce(async function(value) {
        var root = $('generator-food-results');
        if (!value.trim()) { root.innerHTML = ''; return; }
        try {
            var rows = await fetchJson('/labels/search?q=' + encodeURIComponent(value));
            renderSearchResults(root, rows, function(row) {
                addEntry({code: 'FOOD:' + row.id, label: row.name, kind: 'auto', target_type: 'food', target_id: row.id, target_name: row.name});
            });
        } catch (e) { root.innerHTML = '<div class="text-danger">Search failed</div>'; }
    }, 220);

    var searchRecipe = debounce(async function(value) {
        var root = $('generator-recipe-results');
        if (!value.trim()) { root.innerHTML = ''; return; }
        try {
            var rows = await fetchJson('/recipes-search?q=' + encodeURIComponent(value));
            renderSearchResults(root, rows, function(row) {
                addEntry({code: 'RECIPE:' + row.id, label: row.name, kind: 'auto', target_type: 'recipe', target_id: row.id, target_name: row.name});
            }, 'No matching Mealie recipes');
        } catch (e) { root.innerHTML = '<div class="text-danger">Recipe search failed</div>'; }
    }, 220);

    var searchAction = debounce(async function(value) {
        var root = $('generator-action-results');
        try {
            var rows = await fetchJson('/labels/actions-search?q=' + encodeURIComponent(value || ''));
            renderSearchResults(root, rows, function(row) {
                addEntry({code: row.code, label: row.name, kind: 'auto', target_type: 'action', target_id: row.id, target_name: row.name});
            }, 'No matching actions');
        } catch (e) { root.innerHTML = '<div class="text-danger">Action search failed</div>'; }
    }, 180);

    async function registerQueue() {
        refreshQueueFromStorage();
        render();
        if (!queue.length) return;
        var data = await fetchJson('/labels/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
            body: JSON.stringify({labels: queue.map(function(entry) {
                return {
                    code: entry.code,
                    label: entry.label,
                    symbology: entry.kind,
                    target_type: entry.target_type,
                    target_id: entry.target_id,
                    target_name: entry.target_name
                };
            })})
        });
        if (data.errors && data.errors.length) console.warn('Label registration warnings:', data.errors);
        return data;
    }

    async function registerAndPrint() {
        if (!queue.length) return;
        var button = $('label-print');
        button.disabled = true;
        try {
            await registerQueue();
            renderPrint();
            window.print();
        } catch (error) {
            window.alert('Could not register labels: ' + error.message);
        } finally {
            button.disabled = queue.length === 0;
        }
    }

    function imageFromSvg(svg) {
        return new Promise(function(resolve, reject) {
            var blob = new Blob([svg], {type: 'image/svg+xml'});
            var url = URL.createObjectURL(blob);
            var img = new Image();
            img.onload = function() { URL.revokeObjectURL(url); resolve(img); };
            img.onerror = function() { URL.revokeObjectURL(url); reject(new Error('Could not render code')); };
            img.src = url;
        });
    }

    function drawContain(ctx, img, x, y, w, h) {
        var scale = Math.min(w / img.naturalWidth, h / img.naturalHeight);
        var dw = img.naturalWidth * scale;
        var dh = img.naturalHeight * scale;
        ctx.drawImage(img, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh);
    }

    async function renderEntryPng(entry, values) {
        var dpi = 300;
        var pxPerMm = dpi / 25.4;
        var width = Math.max(64, Math.round(values.width * pxPerMm));
        var height = Math.max(64, Math.round(values.height * pxPerMm));
        var canvas = document.createElement('canvas');
        canvas.width = width; canvas.height = height;
        var ctx = canvas.getContext('2d');
        ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, width, height);
        ctx.fillStyle = '#000';

        var response = await fetch(codeUrl(entry));
        if (!response.ok) throw new Error(await response.text());
        var img = await imageFromSvg(await response.text());
        var padding = Math.max(4, Math.round(values.padding * pxPerMm));
        var textPx = Math.max(16, Math.round(values.font * dpi / 72));

        if (values.showText && values.landscape) {
            var codeW = Math.round(width * 0.62);
            drawContain(ctx, img, padding, padding, codeW - padding * 2, height - padding * 2);
            ctx.font = '600 ' + textPx + 'px sans-serif';
            ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            var tx = codeW + (width - codeW) / 2;
            ctx.fillText(entry.label || entry.code, tx, height / 2, width - codeW - padding * 2);
        } else {
            var textH = values.showText ? textPx * 1.5 : 0;
            drawContain(ctx, img, padding, padding, width - padding * 2, height - padding * 2 - textH);
            if (values.showText) {
                ctx.font = '600 ' + textPx + 'px sans-serif';
                ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
                ctx.fillText(entry.label || entry.code, width / 2, height - padding - textH / 2, width - padding * 2);
            }
        }
        return canvas.toDataURL('image/png').split(',', 2)[1];
    }

    async function printNiim() {
        if (!queue.length || !$('label-niim-print')) return;
        var button = $('label-niim-print');
        var old = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Printing…';
        try {
            await registerQueue();
            var values = layout();
            for (var i = 0; i < queue.length; i++) {
                var entry = queue[i];
                var image = await renderEntryPng(entry, values);
                await fetchJson('/labels/niim-print', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
                    body: JSON.stringify({image_base64: image, width_mm: values.width, height_mm: values.height, quantity: entry.qty})
                });
            }
            button.innerHTML = '<i class="ti ti-check icon"></i> Printed';
            setTimeout(function() { button.innerHTML = old; }, 1800);
        } catch (error) {
            button.innerHTML = old;
            window.alert('B21 Pro print failed: ' + error.message);
        } finally {
            button.disabled = queue.length === 0;
        }
    }

    function updateSettingLabels() {
        $('label-size-value').textContent = $('label-size').value;
        $('label-gap-value').textContent = $('label-gap').value;
        $('label-padding-value').textContent = $('label-padding').value;
        $('label-margin-value').textContent = $('label-margin').value;
    }

    window.addEventListener('storage', function(event) {
        if (event.key !== STORAGE_KEY) return;
        var active = document.activeElement;
        if (active && active.closest && active.closest('#label-queue')) {
            pendingStorageSync = true;
            return;
        }
        syncPageFromStorage();
    });

    document.addEventListener('focusout', function(event) {
        if (!pendingStorageSync || !event.target.closest || !event.target.closest('#label-queue')) return;
        setTimeout(function() {
            var active = document.activeElement;
            if (active && active.closest && active.closest('#label-queue')) return;
            pendingStorageSync = false;
            syncPageFromStorage();
        }, 0);
    });

    document.querySelectorAll('[data-code-type]').forEach(function(button) { button.addEventListener('click', function() { switchPane(button.dataset.codeType); }); });
    $('generic-add').addEventListener('click', function() {
        var text = $('generic-text').value.trim();
        if (text) addEntry({code: genericCode(text), label: text, kind: 'auto', target_type: 'generic'});
    });
    document.querySelectorAll('.generic-example').forEach(function(button) { button.addEventListener('click', function() { addEntry({code: genericCode(button.dataset.value), label: button.dataset.value, kind: 'auto', target_type: 'generic'}); }); });
    $('custom-add').addEventListener('click', function() {
        var code = $('custom-code').value.trim();
        if (code) addEntry({code: code, label: $('custom-label').value.trim() || code, kind: 'auto', target_type: 'custom'});
    });
    $('generator-food-search').addEventListener('input', function() { searchFood(this.value); });
    $('generator-recipe-search').addEventListener('input', function() { searchRecipe(this.value); });
    $('generator-action-search').addEventListener('input', function() { searchAction(this.value); });
    $('generator-action-search').addEventListener('focus', function() { searchAction(this.value); });
    document.querySelectorAll('.recipe-example').forEach(function(button) { button.addEventListener('click', function() { $('generator-recipe-search').value = button.dataset.value; searchRecipe(button.dataset.value); switchPane('recipe'); }); });

    document.querySelectorAll('.queue-kind-all').forEach(function(button) {
        button.addEventListener('click', function() {
            var kind = button.dataset.kind;
            refreshQueueFromStorage();
            queue.forEach(function(entry) { entry.kind = (kind === 'code128' && !asciiOnly(entry.code)) ? 'auto' : kind; });
            persist({queue: true}); render();
        });
    });

    document.querySelectorAll('.label-preset').forEach(function(button) {
        button.addEventListener('click', function() {
            document.querySelectorAll('.label-preset').forEach(function(b) { b.classList.remove('active'); });
            button.classList.add('active');
            $('label-format').value = button.dataset.format;
            $('label-size').value = button.dataset.size;
            $('label-gap').value = button.dataset.gap;
            $('label-padding').value = button.dataset.padding;
            $('label-margin').value = button.dataset.margin;
            $('label-font-size').value = button.dataset.font;
            updateSettingLabels(); persist({settings: true}); renderPreview();
        });
    });

    ['label-size','label-gap','label-padding','label-margin','label-font-size','label-format','label-page-format','label-show-text','label-show-border'].forEach(function(id) {
        $(id).addEventListener('input', function() { updateSettingLabels(); persist({settings: true}); renderPreview(); });
        $(id).addEventListener('change', function() { updateSettingLabels(); persist({settings: true}); renderPreview(); });
    });

    $('label-clear').addEventListener('click', function() { refreshQueueFromStorage(); queue = []; persist({queue: true}); render(); });
    $('label-print').addEventListener('click', registerAndPrint);
    if ($('label-niim-print')) $('label-niim-print').addEventListener('click', printNiim);

    $('quick-action-name').addEventListener('input', function() {
        if ($('quick-action-id').dataset.userEdited === '1') return;
        $('quick-action-id').value = this.value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9._-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 96);
    });
    $('quick-action-id').addEventListener('input', function() { this.dataset.userEdited = '1'; });
    $('quick-action-create').addEventListener('click', async function() {
        var errorBox = $('quick-action-error');
        errorBox.classList.add('d-none');
        try {
            var action = await fetchJson('/labels/actions-create', {
                method: 'POST', headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
                body: JSON.stringify({
                    id: $('quick-action-id').value.trim(), name: $('quick-action-name').value.trim(),
                    webhook_url: $('quick-action-webhook').value.trim(), duration_seconds: Number($('quick-action-duration').value || 0),
                    cooldown_seconds: Number($('quick-action-cooldown').value || 0)
                })
            });
            addEntry({code: action.code, label: action.name, kind: 'auto', target_type: 'action', target_id: action.id, target_name: action.name});
            document.querySelector('#quick-action-modal .btn-close').click();
            $('generator-action-search').value = action.name;
            searchAction(action.name);
        } catch (e) {
            errorBox.textContent = e.message; errorBox.classList.remove('d-none');
        }
    });

    restore();
    switchPane(activePane, true);
    var prefillRaw = $('generator-prefill').dataset.prefill;
    if (prefillRaw && prefillRaw !== 'null') {
        try {
            var prefill = JSON.parse(prefillRaw);
            if (prefill && !queue.some(function(e) { return e.code === prefill.code; })) addEntry(prefill, true);
        } catch (e) { console.warn('Invalid generator prefill', e); }
    }
    updateSettingLabels();
    render();
})();
