(function() {
    'use strict';

    var queue = [];
    var nextId = 1;
    var $ = function(id) { return document.getElementById(id); };

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    function currentSymbology() {
        return $('label-symbology').value;
    }

    function validateCode(code, kind) {
        if (!code) return 'Code cannot be empty.';
        if (kind === 'ean13' && !/^\d{12,13}$/.test(code)) return 'EAN-13 requires exactly 12 or 13 digits.';
        if (kind === 'upca' && !/^\d{11,12}$/.test(code)) return 'UPC-A requires exactly 11 or 12 digits.';
        return '';
    }

    function codeUrl(entry) {
        return '/labels/code.svg?kind=' + encodeURIComponent(entry.kind) + '&value=' + encodeURIComponent(entry.code);
    }

    function addEntry(entry) {
        entry.code = String(entry.code || '').trim();
        entry.label = String(entry.label || entry.code).trim();
        entry.kind = entry.kind || currentSymbology();
        entry.target_type = entry.target_type || 'custom';
        entry.target_id = entry.target_id || '';
        entry.target_name = entry.target_name || entry.label;
        entry.qty = Number(entry.qty || 1);
        var error = validateCode(entry.code, entry.kind);
        if (error) {
            window.alert(error + ' Choose QR or Code 128 for alphanumeric IDs.');
            return;
        }
        entry._id = nextId++;
        queue.push(entry);
        render();
    }

    function removeEntry(id) {
        queue = queue.filter(function(entry) { return entry._id !== id; });
        render();
    }

    function updateQty(id, delta) {
        var entry = queue.find(function(row) { return row._id === id; });
        if (!entry) return;
        entry.qty = Math.max(1, Math.min(99, entry.qty + delta));
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
        queue.forEach(function(entry) {
            var col = document.createElement('div');
            col.className = 'col-md-6';
            col.innerHTML = '<div class="card label-card h-100"><button class="btn btn-sm btn-icon btn-outline-danger label-remove" type="button" title="Remove"><i class="ti ti-x"></i></button>' +
                '<div class="card-body d-flex gap-3 align-items-center"><img class="label-qr-preview" alt="Code preview" src="' + esc(codeUrl(entry)) + '">' +
                '<div class="min-w-0 flex-fill"><div class="fw-bold text-truncate">' + esc(entry.label) + '</div><code class="small d-block text-truncate">' + esc(entry.code) + '</code>' +
                '<div class="mt-2"><span class="badge bg-blue-lt me-1">' + esc(typeBadge(entry.target_type)) + '</span><span class="badge bg-muted-lt">' + esc(entry.kind.toUpperCase()) + '</span></div>' +
                '<div class="mt-2 label-qty"><button type="button" data-delta="-1">−</button><span>' + entry.qty + '</span><button type="button" data-delta="1">+</button></div></div></div></div>';
            col.querySelector('.label-remove').addEventListener('click', function() { removeEntry(entry._id); });
            col.querySelectorAll('[data-delta]').forEach(function(button) {
                button.addEventListener('click', function() { updateQty(entry._id, Number(button.dataset.delta)); });
            });
            root.appendChild(col);
        });
        $('label-count').textContent = '(' + queue.reduce(function(sum, e) { return sum + e.qty; }, 0) + ')';
        $('label-clear').disabled = queue.length === 0;
        $('label-print').disabled = queue.length === 0;
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
        element.style.setProperty(p + 'img-max', values.landscape ? '50%' : 'none');
    }

    function createLabelCell(entry, values, printMode) {
        var cell = document.createElement('div');
        cell.className = (printMode ? 'label-cell' : 'label-preview-cell') + (values.landscape ? ' landscape' : '') + (values.border ? ' has-border' : '');
        var img = document.createElement('img');
        img.src = codeUrl(entry);
        img.alt = entry.code;
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
        var total = 0;
        queue.forEach(function(entry) {
            for (var n = 0; n < entry.qty; n++) {
                preview.appendChild(createLabelCell(entry, values, false));
                total++;
            }
        });
        if (!queue.length) preview.innerHTML = '<div class="label-preview-empty text-center text-secondary py-5">Add a code to preview it.</div>';
        $('preview-summary').textContent = total ? total + ' label' + (total === 1 ? '' : 's') + ' · ' + values.width + '×' + Math.round(values.height * 10) / 10 + ' mm' : '';
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
        style.textContent = '@media print { @page { margin: ' + values.margin + 'mm; } }';
    }

    function render() {
        renderQueue();
        renderPreview();
    }

    function switchPane(type) {
        document.querySelectorAll('[data-code-type]').forEach(function(button) { button.classList.toggle('active', button.dataset.codeType === type); });
        document.querySelectorAll('.generator-pane').forEach(function(pane) { pane.classList.toggle('d-none', pane.dataset.pane !== type); });
    }

    function debounce(fn, wait) {
        var timer;
        return function() {
            var args = arguments;
            clearTimeout(timer);
            timer = setTimeout(function() { fn.apply(null, args); }, wait);
        };
    }

    async function fetchJson(url) {
        var response = await fetch(url, {headers: {'Accept': 'application/json'}});
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
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
                addEntry({code: 'FOOD:' + row.id, label: row.name, target_type: 'food', target_id: row.id, target_name: row.name});
            });
        } catch (e) { root.innerHTML = '<div class="text-danger">Search failed</div>'; }
    }, 220);

    var searchRecipe = debounce(async function(value) {
        var root = $('generator-recipe-results');
        if (!value.trim()) { root.innerHTML = ''; return; }
        try {
            var rows = await fetchJson('/recipes-search?q=' + encodeURIComponent(value));
            renderSearchResults(root, rows, function(row) {
                addEntry({code: 'RECIPE:' + row.id, label: row.name, target_type: 'recipe', target_id: row.id, target_name: row.name});
            }, 'No matching Mealie recipes');
        } catch (e) { root.innerHTML = '<div class="text-danger">Recipe search failed</div>'; }
    }, 220);

    var searchAction = debounce(async function(value) {
        var root = $('generator-action-results');
        try {
            var rows = await fetchJson('/labels/actions-search?q=' + encodeURIComponent(value || ''));
            renderSearchResults(root, rows, function(row) {
                addEntry({code: row.code, label: row.name, target_type: 'action', target_id: row.id, target_name: row.name});
            }, 'No matching actions');
        } catch (e) { root.innerHTML = '<div class="text-danger">Action search failed</div>'; }
    }, 180);

    async function registerAndPrint() {
        if (!queue.length) return;
        var button = $('label-print');
        button.disabled = true;
        try {
            var response = await fetch('/labels/register', {
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
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
            if (data.errors && data.errors.length) {
                window.alert('Registered with warnings:\n' + data.errors.join('\n'));
            }
            renderPrint();
            window.print();
        } catch (error) {
            window.alert('Could not register labels: ' + error.message);
        } finally {
            button.disabled = queue.length === 0;
        }
    }

    document.querySelectorAll('[data-code-type]').forEach(function(button) { button.addEventListener('click', function() { switchPane(button.dataset.codeType); }); });
    $('generic-add').addEventListener('click', function() {
        var text = $('generic-text').value.trim();
        if (text) addEntry({code: 'GENERIC:' + text, label: text, target_type: 'generic'});
    });
    document.querySelectorAll('.generic-example').forEach(function(button) { button.addEventListener('click', function() { addEntry({code: 'GENERIC:' + button.dataset.value, label: button.dataset.value, target_type: 'generic'}); }); });
    $('custom-add').addEventListener('click', function() {
        var code = $('custom-code').value.trim();
        if (code) addEntry({code: code, label: $('custom-label').value.trim() || code, target_type: 'custom'});
    });
    $('generator-food-search').addEventListener('input', function() { searchFood(this.value); });
    $('generator-recipe-search').addEventListener('input', function() { searchRecipe(this.value); });
    $('generator-action-search').addEventListener('input', function() { searchAction(this.value); });
    $('generator-action-search').addEventListener('focus', function() { searchAction(this.value); });
    document.querySelectorAll('.recipe-example').forEach(function(button) { button.addEventListener('click', function() { $('generator-recipe-search').value = button.dataset.value; searchRecipe(button.dataset.value); switchPane('recipe'); }); });

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
            updateSettingLabels();
            renderPreview();
        });
    });

    function updateSettingLabels() {
        $('label-size-value').textContent = $('label-size').value;
        $('label-gap-value').textContent = $('label-gap').value;
        $('label-padding-value').textContent = $('label-padding').value;
        $('label-margin-value').textContent = $('label-margin').value;
    }

    ['label-size','label-gap','label-padding','label-margin','label-font-size','label-format','label-show-text','label-show-border'].forEach(function(id) {
        $(id).addEventListener('input', function() { updateSettingLabels(); renderPreview(); });
        $(id).addEventListener('change', function() { updateSettingLabels(); renderPreview(); });
    });

    $('label-clear').addEventListener('click', function() { queue = []; render(); });
    $('label-print').addEventListener('click', registerAndPrint);

    var prefillRaw = $('generator-prefill').dataset.prefill;
    if (prefillRaw && prefillRaw !== 'null') {
        try {
            var prefill = JSON.parse(prefillRaw);
            if (prefill) addEntry(prefill);
        } catch (e) { console.warn('Invalid generator prefill', e); }
    }
    updateSettingLabels();
    render();
})();
