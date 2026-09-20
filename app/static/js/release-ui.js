(function() {
    'use strict';

    var notificationConfig = {toast_seconds: 15, group_window_seconds: 30};
    var toastGroups = new Map();

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    async function jsonFetch(url, options) {
        var response = await fetch(url, options || {headers: {'Accept': 'application/json'}});
        var data = await response.json().catch(function() { return {}; });
        if (!response.ok) throw new Error(data.error || data.detail || ('HTTP ' + response.status));
        return data;
    }

    function currentBarcode() {
        if (!window.location.pathname.startsWith('/barcodes/') || window.location.pathname === '/barcodes/') return null;
        try { return decodeURIComponent(window.location.pathname.slice('/barcodes/'.length)); }
        catch (e) { return null; }
    }

    /* ── Configurable toast lifetime + repeat grouping ───────────────────── */
    async function loadNotificationConfig() {
        try {
            var data = await jsonFetch('/api/settings/notifications');
            notificationConfig.toast_seconds = Number(data.toast_seconds || 15);
            notificationConfig.group_window_seconds = Number(data.group_window_seconds || 30);
        } catch (e) {
            // Non-admin sessions can keep the safe defaults; POST remains admin-only.
        }
    }

    function toastSignature(toast) {
        var title = toast.querySelector('.toast-header strong');
        var body = toast.querySelector('.toast-body');
        return (title ? title.textContent.trim() : '') + '|' + (body ? body.textContent.trim().replace(/\s+/g, ' ') : '');
    }

    function incrementToast(toast, count) {
        var badge = toast.querySelector('.b2m-release-count, .b2m-toast-count');
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'badge bg-secondary-lt ms-2 b2m-release-count';
            var title = toast.querySelector('.toast-header strong');
            if (title) title.insertAdjacentElement('afterend', badge);
        }
        badge.textContent = '×' + count;
    }

    function manageToast(toast) {
        if (!(toast instanceof HTMLElement) || !toast.classList.contains('toast')) return;
        if (!toast.dataset.b2mReleaseManaged) {
            toast.dataset.b2mReleaseManaged = '1';
            var lifetime = Math.max(3, Number(notificationConfig.toast_seconds || 15)) * 1000;
            toast.dataset.b2mKeepUntil = String(Date.now() + lifetime);
            setTimeout(function() {
                if (toast.parentNode && toast.dataset.b2mManual !== '1') toast.remove();
            }, lifetime);
        }

        var signature = toastSignature(toast);
        if (!signature) return;
        var previous = toastGroups.get(signature);
        var now = Date.now();
        var windowMs = Math.max(1, Number(notificationConfig.group_window_seconds || 30)) * 1000;
        if (previous && previous.el && previous.el.isConnected && previous.el !== toast && now - previous.last <= windowMs) {
            previous.count += 1;
            previous.last = now;
            incrementToast(previous.el, previous.count);
            toast.dataset.b2mManual = '1';
            toast.remove();
            return;
        }
        toastGroups.set(signature, {el: toast, count: 1, last: now});
    }

    function installToastManager() {
        var root = document.getElementById('scan-toasts');
        if (!root || !window.MutationObserver) return;
        root.addEventListener('click', function(event) {
            var close = event.target.closest('[data-bs-dismiss="toast"], .btn-close');
            if (close) {
                var toast = close.closest('.toast');
                if (toast) toast.dataset.b2mManual = '1';
            }
        }, true);
        new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) { manageToast(node); });
                mutation.removedNodes.forEach(function(node) {
                    if (!(node instanceof HTMLElement) || !node.classList.contains('toast')) return;
                    if (node.dataset.b2mManual === '1') return;
                    var keepUntil = Number(node.dataset.b2mKeepUntil || 0);
                    // app.js has an older fixed 8 s timer. Reinsert if our configured
                    // lifetime is longer; our own timer removes it at the right time.
                    if (keepUntil > Date.now()) root.prepend(node);
                });
            });
        }).observe(root, {childList: true});
        root.querySelectorAll('.toast').forEach(manageToast);
    }

    /* ── Settings navigation / Notifications ─────────────────────────────── */
    function addSettingsNavLink(tab, label, icon, afterSelector) {
        if (window.location.pathname !== '/settings' || document.querySelector('a[href="/settings?tab=' + tab + '"]')) return;
        var anchor = document.querySelector(afterSelector);
        if (!anchor) return;
        var link = document.createElement('a');
        link.href = '/settings?tab=' + tab;
        link.className = 'list-group-item list-group-item-action d-flex align-items-center' +
            (new URLSearchParams(window.location.search).get('tab') === tab ? ' active' : '');
        link.innerHTML = '<span class="me-2"><i class="ti ' + icon + ' icon"></i></span>' + esc(label);
        anchor.insertAdjacentElement('afterend', link);
    }

    async function renderNotificationSettings() {
        if (window.location.pathname !== '/settings' || new URLSearchParams(window.location.search).get('tab') !== 'notifications') return;
        var pane = document.querySelector('.col-12.col-md-9.d-flex.flex-column');
        if (!pane) return;
        pane.innerHTML = '<div class="card-body"><h2 class="mb-2">Notifications</h2><p class="card-subtitle mb-4">Web UI notification timing and repeat decluttering.</p><div id="release-notification-settings">Loading…</div></div>';
        try {
            var data = await jsonFetch('/api/settings/notifications');
            notificationConfig = data;
            document.getElementById('release-notification-settings').innerHTML =
                '<form id="release-notification-form"><div class="card"><div class="card-header"><div><h3 class="card-title">Display</h3><p class="card-subtitle">Changes apply without restarting B2M.</p></div></div>' +
                '<div class="card-body"><div class="row g-3">' +
                '<div class="col-md-6"><label class="form-label">Notification duration</label><div class="input-group"><input class="form-control" type="number" min="3" max="120" name="toast_seconds" value="' + Number(data.toast_seconds || 15) + '"><span class="input-group-text">seconds</span></div><div class="form-hint">How long a scan toast stays visible.</div></div>' +
                '<div class="col-md-6"><label class="form-label">Repeat grouping window</label><div class="input-group"><input class="form-control" type="number" min="1" max="300" name="group_window_seconds" value="' + Number(data.group_window_seconds || 30) + '"><span class="input-group-text">seconds</span></div><div class="form-hint">Identical scans in this window are combined as ×2, ×3, …</div></div>' +
                '<div class="col-12"><div id="release-notification-result" class="form-hint"></div></div></div></div>' +
                '<div class="card-footer text-end"><button class="btn btn-primary" type="submit"><i class="ti ti-device-floppy icon"></i> Save</button></div></div></form>';
            document.getElementById('release-notification-form').addEventListener('submit', async function(event) {
                event.preventDefault();
                var fd = new FormData(event.currentTarget);
                var result = document.getElementById('release-notification-result');
                try {
                    var saved = await jsonFetch('/api/settings/notifications', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({toast_seconds: Number(fd.get('toast_seconds')), group_window_seconds: Number(fd.get('group_window_seconds'))})
                    });
                    notificationConfig = saved;
                    result.className = 'form-hint text-success';
                    result.textContent = 'Saved.';
                } catch (error) {
                    result.className = 'form-hint text-danger'; result.textContent = error.message;
                }
            });
        } catch (error) {
            document.getElementById('release-notification-settings').innerHTML = '<div class="alert alert-danger">' + esc(error.message) + '</div>';
        }
    }

    /* ── Mealie settings: test + runtime default list ────────────────────── */
    async function renderMealieRuntimeSettings() {
        if (window.location.pathname !== '/settings' || new URLSearchParams(window.location.search).get('tab') !== 'mealie') return;
        var body = document.querySelector('.col-12.col-md-9 .card-body');
        if (!body) return;
        var old = document.getElementById('shopping-lists-card');
        if (old) old.remove(); // old enhancement exposed raw IDs; replace it.
        var existing = document.getElementById('release-mealie-card');
        if (existing) existing.remove();
        var card = document.createElement('div');
        card.id = 'release-mealie-card'; card.className = 'card mt-4';
        card.innerHTML = '<div class="card-header"><div><h3 class="card-title">Connection & shopping lists</h3><p class="card-subtitle">List IDs are discovered automatically from Mealie.</p></div><div class="card-actions"><button type="button" class="btn btn-outline-primary" id="release-test-mealie"><i class="ti ti-plug-connected icon"></i> Test connection</button></div></div><div class="card-body" id="release-mealie-body">Loading…</div>';
        body.appendChild(card);
        try {
            var data = await jsonFetch('/api/shopping-lists?force=true');
            var options = (data.items || []).map(function(row) {
                return '<option value="' + esc(row.id) + '"' + (row.default ? ' selected' : '') + '>' + esc(row.name) + (row.default ? ' · current default' : '') + '</option>';
            }).join('');
            document.getElementById('release-mealie-body').innerHTML =
                '<div class="row g-3 align-items-end"><div class="col-md-8"><label class="form-label">Default shopping list</label><select class="form-select" id="release-default-list">' + options + '</select><div class="form-hint">Used whenever a Food/recipe target says “default”. No list ID needs to be copied into the environment.</div></div><div class="col-md-4"><button type="button" class="btn btn-primary w-100" id="release-save-default-list">Save default</button></div><div class="col-12"><div id="release-mealie-result" class="form-hint"></div></div></div>';
            document.getElementById('release-save-default-list').addEventListener('click', async function() {
                var result = document.getElementById('release-mealie-result');
                try {
                    var selected = document.getElementById('release-default-list').value;
                    var saved = await jsonFetch('/api/settings/default-shopping-list', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({list_id: selected})});
                    result.className = 'form-hint text-success'; result.textContent = 'Default list: ' + saved.default.name;
                    renderMealieRuntimeSettings();
                } catch (error) { result.className = 'form-hint text-danger'; result.textContent = error.message; }
            });
        } catch (error) {
            document.getElementById('release-mealie-body').innerHTML = '<div class="alert alert-danger">' + esc(error.message) + '</div>';
        }
        document.getElementById('release-test-mealie').addEventListener('click', async function() {
            var button = this; var result = document.getElementById('release-mealie-result');
            button.disabled = true;
            try {
                var data = await jsonFetch('/api/settings/test-mealie', {method: 'POST', headers: {'Accept': 'application/json'}});
                result.className = 'form-hint text-success';
                result.textContent = 'Connected · ' + Number(data.shopping_lists || 0) + ' shopping list(s) detected.';
            } catch (error) { result.className = 'form-hint text-danger'; result.textContent = 'Connection failed: ' + error.message; }
            finally { button.disabled = false; }
        });
    }

    /* ── Dashboard shopping list counters ────────────────────────────────── */
    async function renderDashboardLists() {
        if (window.location.pathname !== '/') return;
        try {
            var data = await jsonFetch('/api/shopping-list-stats');
            var items = data.items || [];
            var root = document.getElementById('release-dashboard-lists');
            if (!root) {
                root = document.createElement('div'); root.id = 'release-dashboard-lists'; root.className = 'card mb-3';
                var recent = document.getElementById('recent-scans-card');
                var row = recent && recent.closest('.row');
                if (row) row.insertAdjacentElement('beforebegin', root);
            }
            root.innerHTML = '<div class="card-header"><div><h3 class="card-title">Shopping lists</h3><p class="card-subtitle">Current open items in Mealie.</p></div></div><div class="card-body"><div class="row g-3">' +
                (items.length ? items.map(function(item) {
                    return '<div class="col-sm-6 col-lg-3"><div class="border rounded p-3 h-100"><div class="d-flex align-items-center"><div class="me-auto"><div class="fw-bold">' + esc(item.name) + '</div><div class="text-secondary small">' + (item.default ? 'Default list' : 'Shopping list') + '</div></div>' + (item.default ? '<span class="badge bg-blue-lt">default</span>' : '') + '</div><div class="h1 mb-0 mt-2">' + Number(item.open_items || 0) + '</div><div class="text-secondary small">open · ' + Number(item.total_items || 0) + ' total</div></div></div>';
                }).join('') : '<div class="text-secondary">No shopping lists returned.</div>') + '</div></div>';
        } catch (error) { console.debug('Shopping list stats unavailable', error); }
    }

    /* ── Barcode product/primary target polish ───────────────────────────── */
    function findCard(title) {
        var heading = Array.from(document.querySelectorAll('h3.card-title')).find(function(h) { return h.textContent.trim() === title; });
        return heading ? heading.closest('.card') : null;
    }

    function showInline(form, message, ok) {
        var result = form.querySelector('.b2m-inline-result');
        if (!result) {
            result = document.createElement('span'); result.className = 'b2m-inline-result ms-2 small';
            var button = form.querySelector('button[type="submit"]');
            if (button) button.insertAdjacentElement('afterend', result);
        }
        result.className = 'b2m-inline-result ms-2 small ' + (ok ? 'text-success' : 'text-danger');
        result.textContent = message;
    }

    function setupMetadataAjax(barcode) {
        var form = document.querySelector('form[action$="/metadata"]');
        if (!form || form.dataset.b2mAjax === '1') return;
        form.dataset.b2mAjax = '1';
        var titleInput = form.querySelector('input[name="title"]');
        var brandInput = form.querySelector('input[name="brand"]');
        form.addEventListener('submit', async function(event) {
            event.preventDefault();
            try {
                var data = await jsonFetch('/api/barcodes/' + encodeURIComponent(barcode) + '/metadata', {
                    method: 'PUT', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({title: titleInput ? titleInput.value : '', brand: brandInput ? brandInput.value : ''})
                });
                showInline(form, 'Saved', true);
                var pageTitle = document.querySelector('.page-header h2.page-title');
                if (pageTitle && data.title) pageTitle.textContent = data.title;
            } catch (error) { showInline(form, error.message, false); }
        });

        var footer = form.querySelector('.card-footer');
        if (footer && !document.getElementById('release-lookup-refresh')) {
            var wrap = footer.querySelector('div') || footer;
            var refresh = document.createElement('button');
            refresh.type = 'button'; refresh.id = 'release-lookup-refresh'; refresh.className = 'btn btn-outline-secondary me-2';
            refresh.innerHTML = '<i class="ti ti-refresh icon"></i> Refresh product lookup';
            var clear = document.createElement('button');
            clear.type = 'button'; clear.className = 'btn btn-outline-warning';
            clear.innerHTML = '<i class="ti ti-eraser icon"></i> Refresh + clear overrides';
            wrap.appendChild(refresh); wrap.appendChild(clear);
            async function redo(clearOverrides, button) {
                button.disabled = true;
                try {
                    var data = await jsonFetch('/api/barcode-lookup', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({barcode: barcode, clear_overrides: clearOverrides})});
                    if (clearOverrides) { if (titleInput) titleInput.value = ''; if (brandInput) brandInput.value = ''; }
                    showInline(form, data.found ? 'Lookup refreshed' : 'Lookup refreshed · product not found', true);
                    var pageTitle = document.querySelector('.page-header h2.page-title');
                    if (pageTitle && data.title) pageTitle.textContent = data.title;
                } catch (error) { showInline(form, error.message, false); }
                finally { button.disabled = false; }
            }
            refresh.addEventListener('click', function() { redo(false, refresh); });
            clear.addEventListener('click', function() { redo(true, clear); });
        }
    }

    function polishBarcodeCards() {
        var product = findCard('Product Information');
        if (product) {
            var heading = product.querySelector('h3.card-title');
            if (heading) heading.textContent = 'Product behind this barcode';
            var subtitle = product.querySelector('.card-subtitle');
            if (subtitle) subtitle.textContent = 'Lookup data for the product encoded by this barcode. Manual overrides only change the displayed metadata.';
        }
        ['Create new Mealie Food', 'Link Mealie recipe'].forEach(function(title) {
            var card = findCard(title); if (card) card.classList.add('b2m-option-card');
        });
        var current = findCard('Current target');
        if (current) {
            var form = current.querySelector('form[action$="/mapping-settings"]');
            if (form) {
                var save = form.querySelector('button[type="submit"]'); if (save) save.textContent = 'Save';
                var quantity = form.querySelector('input[name="quantity"]');
                if (quantity && Number(quantity.value) <= 0.001) quantity.value = '';
                var labels = form.querySelectorAll('label.form-label');
                labels.forEach(function(label) {
                    if (label.textContent.trim() === 'Default quantity') label.textContent = 'Quantity';
                    if (label.textContent.trim() === 'Unit') label.textContent = 'Change unit';
                });
            }
        }
    }

    async function setupPrimaryTarget(barcode) {
        var current = findCard('Current target');
        if (!current) return;
        var form = current.querySelector('form[action$="/mapping-settings"]');
        if (!form || form.dataset.b2mAjax === '1') return;
        form.dataset.b2mAjax = '1';
        var data;
        try { data = await jsonFetch('/api/barcode-targets?barcode=' + encodeURIComponent(barcode)); }
        catch (e) { return; }
        var primary = (data.targets || []).find(function(t) { return t.primary; });
        if (!primary) return;
        var quantity = form.querySelector('input[name="quantity"]');
        var unit = form.querySelector('select[name="unit_id"]');
        if (quantity) quantity.value = primary.quantity == null ? '' : primary.quantity;
        if (unit && !primary.unit_id && primary.preferred_unit && primary.preferred_unit.id) {
            unit.value = primary.preferred_unit.id;
            var hint = document.createElement('div'); hint.className = 'form-hint text-secondary b2m-unit-inferred';
            hint.textContent = 'Current unit inferred from an open Mealie shopping item: ' + primary.preferred_unit.name;
            unit.insertAdjacentElement('afterend', hint);
        }
        function updateWarning() {
            var old = form.querySelector('.b2m-unit-warning'); if (old) old.remove();
            if (!unit || !primary.preferred_unit || !unit.value || unit.value === primary.preferred_unit.id) return;
            var warning = document.createElement('div'); warning.className = 'alert alert-warning py-2 mt-2 mb-0 b2m-unit-warning';
            warning.innerHTML = '<i class="ti ti-alert-triangle icon"></i> Selected unit differs from the unit currently used for this Food in an open Mealie shopping item (<strong>' + esc(primary.preferred_unit.name) + '</strong>).';
            unit.closest('.row, .mb-3, form').appendChild(warning);
        }
        if (unit) { unit.addEventListener('change', updateWarning); updateWarning(); }

        var summary = document.createElement('div'); summary.className = 'small mt-3 border-top pt-2'; summary.id = 'release-primary-summary';
        function renderSummary() {
            var q = quantity ? quantity.value.trim() : '';
            var unitText = unit && unit.value ? unit.options[unit.selectedIndex].text : 'none';
            summary.innerHTML = 'Quantity: <strong>' + (q || 'none') + '</strong>' + (primary.target_type === 'food' ? ' · Unit: <strong>' + esc(unitText) + '</strong>' : '');
        }
        form.appendChild(summary); renderSummary();
        if (quantity) quantity.addEventListener('input', renderSummary);
        if (unit) unit.addEventListener('change', renderSummary);

        form.addEventListener('submit', async function(event) {
            event.preventDefault();
            var list = form.querySelector('select[name="shopping_list_id"]');
            var scale = form.querySelector('input[name="recipe_scale"]');
            try {
                var saved = await jsonFetch('/api/barcodes/' + encodeURIComponent(barcode) + '/primary-target', {
                    method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
                        quantity: quantity && quantity.value.trim() ? Number(quantity.value.replace(',', '.')) : null,
                        unit_id: unit ? unit.value || null : null,
                        recipe_scale: scale ? Number(scale.value.replace(',', '.')) : null,
                        shopping_list_id: list ? list.value || null : null
                    })
                });
                primary = saved.target || primary;
                if (quantity) quantity.value = primary.quantity == null ? '' : primary.quantity;
                showInline(form, 'Saved', true); renderSummary(); updateWarning();
                renderBarcodeTargets(barcode);
            } catch (error) { showInline(form, error.message, false); }
        });
    }

    /* ── Extra barcode targets ───────────────────────────────────────────── */
    function routeLabel(target) {
        if (target.destination_type === 'mealie') return target.shopping_list_name ? 'Mealie · ' + target.shopping_list_name : 'Mealie';
        if (target.destination_type === 'homeassistant') return 'Home Assistant';
        if (target.destination_type === 'webhook') return 'Webhook';
        return 'Inherit item route';
    }

    async function renderBarcodeTargets(barcode) {
        var data;
        try { data = await jsonFetch('/api/barcode-targets?barcode=' + encodeURIComponent(barcode)); }
        catch (e) { return; }
        var primary = (data.targets || []).find(function(t) { return t.primary; });
        var extras = (data.targets || []).filter(function(t) { return !t.primary; });
        var current = findCard('Current target');
        if (!current) return;
        var host = document.getElementById('release-extra-targets');
        if (!host) {
            host = document.createElement('div'); host.id = 'release-extra-targets'; host.className = 'card mb-3';
            var row = current.closest('.row.row-cards.mb-3');
            if (row) row.insertAdjacentElement('afterend', host); else current.insertAdjacentElement('afterend', host);
        }
        var listHtml = extras.length ? extras.map(function(t) {
            var qty = t.target_type === 'food' ? (t.quantity == null ? 'none' : t.quantity) : '×' + (t.recipe_scale || 1);
            return '<div class="list-group-item"><div class="d-flex align-items-center gap-2"><span class="avatar avatar-sm bg-' + (t.target_type === 'food' ? 'blue' : 'purple') + '-lt"><i class="ti ti-' + (t.target_type === 'food' ? 'apple' : 'receipt') + '"></i></span><div class="me-auto min-w-0"><div class="fw-bold text-truncate">' + esc(t.target_name) + '</div><div class="text-secondary small">' + esc(routeLabel(t)) + ' · quantity/scale <strong>' + esc(qty) + '</strong></div></div><button type="button" class="btn btn-sm btn-outline-danger b2m-target-delete" data-id="' + t.id + '"><i class="ti ti-trash"></i></button></div></div>';
        }).join('') : '<div class="list-group-item text-secondary">No additional targets. The primary target above is the only thing triggered by this barcode.</div>';
        host.innerHTML = '<div class="card-header"><div><h3 class="card-title">Additional targets & destinations</h3><p class="card-subtitle">One scan can add multiple Foods/recipes to different Mealie lists or send them to different endpoints.</p></div><div class="card-actions"><button type="button" class="btn btn-primary" id="release-add-target-toggle"><i class="ti ti-plus icon"></i> Add target</button></div></div><div class="list-group list-group-flush">' + listHtml + '</div><div class="card-body d-none" id="release-target-editor"></div>';
        host.querySelectorAll('.b2m-target-delete').forEach(function(button) {
            button.addEventListener('click', async function() {
                button.disabled = true;
                try { await jsonFetch('/api/barcode-targets/' + button.dataset.id, {method: 'DELETE'}); await renderBarcodeTargets(barcode); }
                catch (error) { button.disabled = false; }
            });
        });
        document.getElementById('release-add-target-toggle').addEventListener('click', function() {
            var editor = document.getElementById('release-target-editor');
            editor.classList.toggle('d-none');
            if (!editor.classList.contains('d-none')) renderTargetEditor(editor, barcode, data, primary);
        });
    }

    function renderTargetEditor(editor, barcode, data, primary) {
        var lists = data.shopping_lists || [];
        var units = data.units || [];
        editor.innerHTML = '<form id="release-target-form"><div class="row g-3">' +
            '<div class="col-md-3"><label class="form-label">Thing</label><select class="form-select" id="release-target-type"><option value="food">Food</option><option value="recipe">Recipe</option></select></div>' +
            '<div class="col-md-9"><label class="form-label">Search</label><input class="form-control" id="release-target-search" autocomplete="off" placeholder="Food name…"><div class="list-group mt-1" id="release-target-results"></div><input type="hidden" id="release-target-id"><input type="hidden" id="release-target-name"><div class="form-hint" id="release-target-selected">No target selected.</div></div>' +
            '<div class="col-md-4"><label class="form-label">Destination</label><select class="form-select" id="release-target-destination"><option value="mealie">Mealie shopping list</option><option value="homeassistant">Home Assistant</option><option value="webhook">Custom webhook</option><option value="inherit">Inherit Food route</option></select></div>' +
            '<div class="col-md-8" id="release-target-list-wrap"><label class="form-label">Shopping list</label><select class="form-select" id="release-target-list"><option value="">Default list</option>' + lists.map(function(l) { return '<option value="' + esc(l.id) + '">' + esc(l.name) + (String(l.id) === String(data.default_list_id) ? ' · default' : '') + '</option>'; }).join('') + '</select></div>' +
            '<div class="col-12 d-none" id="release-target-webhook-wrap"><label class="form-label">Webhook endpoint</label><input class="form-control" id="release-target-webhook" placeholder="https://…"></div>' +
            '<div class="col-md-6" id="release-target-quantity-wrap"><label class="form-label">Quantity</label><input class="form-control" id="release-target-quantity" inputmode="decimal" placeholder="none"></div>' +
            '<div class="col-md-6" id="release-target-unit-wrap"><label class="form-label">Unit</label><select class="form-select" id="release-target-unit"><option value="">No unit</option>' + units.map(function(u) { return '<option value="' + esc(u.id) + '">' + esc(u.name) + '</option>'; }).join('') + '</select></div>' +
            '<div class="col-md-6 d-none" id="release-target-scale-wrap"><label class="form-label">Recipe scale</label><input class="form-control" type="number" min="0.001" step="0.1" id="release-target-scale" value="1"></div>' +
            '<div class="col-12"><div class="form-hint" id="release-target-error"></div></div></div><div class="mt-3 text-end"><button class="btn btn-primary" type="submit">Add target</button></div></form>';
        var type = document.getElementById('release-target-type');
        var search = document.getElementById('release-target-search');
        var results = document.getElementById('release-target-results');
        var destination = document.getElementById('release-target-destination');
        var timer = null;
        function updateFields() {
            var isFood = type.value === 'food';
            document.getElementById('release-target-quantity-wrap').classList.toggle('d-none', !isFood);
            document.getElementById('release-target-unit-wrap').classList.toggle('d-none', !isFood);
            document.getElementById('release-target-scale-wrap').classList.toggle('d-none', isFood);
            document.getElementById('release-target-list-wrap').classList.toggle('d-none', destination.value !== 'mealie');
            document.getElementById('release-target-webhook-wrap').classList.toggle('d-none', destination.value !== 'webhook');
            search.placeholder = isFood ? 'Food name…' : 'Recipe name…';
        }
        type.addEventListener('change', function() { search.value = ''; results.innerHTML = ''; document.getElementById('release-target-id').value = ''; updateFields(); });
        destination.addEventListener('change', updateFields); updateFields();
        search.addEventListener('input', function() {
            clearTimeout(timer); var q = search.value.trim(); if (q.length < 2) { results.innerHTML = ''; return; }
            timer = setTimeout(async function() {
                try {
                    var response = type.value === 'food'
                        ? await jsonFetch('/api/foods/search?q=' + encodeURIComponent(q) + '&limit=6')
                        : {items: await jsonFetch('/recipes-search?q=' + encodeURIComponent(q))};
                    var rows = response.items || [];
                    results.innerHTML = rows.slice(0, 6).map(function(row) {
                        return '<button type="button" class="list-group-item list-group-item-action release-target-pick" data-id="' + esc(row.id) + '" data-name="' + esc(row.name) + '">' + esc(row.name) + (row.score != null ? '<span class="badge bg-secondary-lt ms-2">' + (row.exact ? 'Exact' : row.score + '%') + '</span>' : '') + '</button>';
                    }).join('');
                    results.querySelectorAll('.release-target-pick').forEach(function(button) {
                        button.addEventListener('click', function() {
                            document.getElementById('release-target-id').value = button.dataset.id;
                            document.getElementById('release-target-name').value = button.dataset.name;
                            document.getElementById('release-target-selected').innerHTML = 'Selected: <strong>' + esc(button.dataset.name) + '</strong>';
                            results.innerHTML = '';
                        });
                    });
                } catch (e) { results.innerHTML = '<div class="list-group-item text-danger">Search failed</div>'; }
            }, 180);
        });
        document.getElementById('release-target-form').addEventListener('submit', async function(event) {
            event.preventDefault(); var error = document.getElementById('release-target-error');
            var id = document.getElementById('release-target-id').value;
            if (!id) { error.className = 'form-hint text-danger'; error.textContent = 'Select a Food or recipe first.'; return; }
            var quantity = document.getElementById('release-target-quantity').value.trim();
            try {
                await jsonFetch('/api/barcode-targets', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
                    barcode: barcode, target_type: type.value, target_id: id, target_name: document.getElementById('release-target-name').value,
                    quantity: quantity ? Number(quantity.replace(',', '.')) : null,
                    unit_id: document.getElementById('release-target-unit').value || null,
                    recipe_scale: Number(document.getElementById('release-target-scale').value || 1),
                    destination_type: destination.value,
                    shopping_list_id: document.getElementById('release-target-list').value || null,
                    endpoint_url: document.getElementById('release-target-webhook').value.trim() || null,
                    enabled: true
                })});
                await renderBarcodeTargets(barcode);
            } catch (e) { error.className = 'form-hint text-danger'; error.textContent = e.message; }
        });
    }

    /* ── Activity badges after app.js live refresh ───────────────────────── */
    function normalizeActivityBadges() {
        var root = document.getElementById('activity-tbody'); if (!root) return;
        var map = {
            resolved: ['green', 'Linked'], action_queued: ['purple', 'Action queued'], action_triggered: ['green', 'Action triggered'],
            action_ignored: ['secondary', 'Action cooldown'], action_paused: ['azure', 'Action paused'], action_disabled: ['red', 'Action disabled'],
            partial: ['orange', 'Partial']
        };
        root.querySelectorAll('.sort-status .badge').forEach(function(badge) {
            var key = badge.textContent.trim().toLowerCase().replace(/\s+/g, '_');
            var spec = map[key]; if (!spec) return;
            badge.className = 'badge bg-' + spec[0] + (spec[0] === 'secondary' ? '-lt' : ' text-' + spec[0] + '-fg');
            badge.textContent = spec[1];
        });
    }

    function observeActivity() {
        var root = document.getElementById('activity-tbody'); if (!root || !window.MutationObserver) return;
        normalizeActivityBadges(); new MutationObserver(normalizeActivityBadges).observe(root, {childList: true, subtree: true});
    }

    /* ── Bootstrap ───────────────────────────────────────────────────────── */
    document.addEventListener('DOMContentLoaded', async function() {
        await loadNotificationConfig();
        installToastManager();
        addSettingsNavLink('notifications', 'Notifications', 'ti-bell-cog', 'a[href="/settings?tab=scanning"]');
        renderNotificationSettings();
        setTimeout(renderMealieRuntimeSettings, 80); // run after legacy enhancement card
        renderDashboardLists();
        observeActivity();

        var barcode = currentBarcode();
        if (barcode) {
            polishBarcodeCards();
            setupMetadataAjax(barcode);
            setupPrimaryTarget(barcode);
            renderBarcodeTargets(barcode);
            // The previous release injected a single-destination summary. The new
            // multi-target card supersedes it.
            setTimeout(function() { var old = document.getElementById('barcode-destination-summary'); if (old) old.remove(); }, 150);
        }

        window.addEventListener('b2m:scan', function(event) {
            renderDashboardLists();
            normalizeActivityBadges();
            if (barcode && event.detail && event.detail.barcode === barcode) {
                setTimeout(function() { setupPrimaryTarget(barcode); renderBarcodeTargets(barcode); }, 300);
            }
        });
    });
})();
