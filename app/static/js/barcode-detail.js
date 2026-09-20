(function() {
    'use strict';

    var form = document.getElementById('barcode-metadata-form');
    var status = document.getElementById('metadata-save-status');
    var barcode = '';
    try { barcode = decodeURIComponent(window.location.pathname.substring('/barcodes/'.length)); } catch (e) {}

    async function saveMetadata(event) {
        var submitter = event.submitter;
        if (submitter && submitter.getAttribute('formaction')) return;
        event.preventDefault();
        if (!form) return;
        if (status) { status.className = 'form-hint text-secondary'; status.textContent = 'Saving…'; }
        try {
            var response = await fetch(form.action, {
                method: 'POST', headers: {'X-Requested-With': 'fetch', 'Accept': 'application/json'}, body: new FormData(form)
            });
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Save failed');
            var title = document.getElementById('displayed-title');
            var brand = document.getElementById('displayed-brand');
            if (title) title.textContent = data.title || '—';
            if (brand) brand.textContent = data.brand || '—';
            if (status) {
                status.className = 'form-hint text-success'; status.textContent = 'Saved.';
                setTimeout(function() { status.textContent = ''; }, 2500);
            }
        } catch (error) {
            if (status) { status.className = 'form-hint text-danger'; status.textContent = error.message; }
        }
    }

    if (form) form.addEventListener('submit', saveMetadata);
    if (form) form.querySelectorAll('input[name="title"], input[name="brand"]').forEach(function(input) {
        input.addEventListener('keydown', function(event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                if (form.requestSubmit) form.requestSubmit();
                else form.dispatchEvent(new Event('submit', {cancelable: true, bubbles: true}));
            }
        });
    });

    document.querySelectorAll('.target-unit-select').forEach(function(select) {
        select.addEventListener('change', function() {
            var defaultId = select.dataset.itemUnit || '';
            var existing = select.parentElement.querySelector('.b2m-unit-live-warning');
            if (existing) existing.remove();
            var selected = select.value === '__item_default__' ? defaultId : select.value;
            if (defaultId && selected && selected !== defaultId) {
                var warning = document.createElement('div');
                warning.className = 'form-hint text-warning b2m-unit-live-warning';
                warning.innerHTML = '<i class="ti ti-alert-triangle"></i> Selected unit differs from the item default.';
                select.insertAdjacentElement('afterend', warning);
            }
        });
    });

    function installRouteChoices(select) {
        if (!select || select.dataset.checkboxUi === '1') return;
        select.dataset.checkboxUi = '1';
        var original = select.value || 'none';
        select.classList.add('d-none');
        var allowInherit = Array.from(select.options).some(function(option) { return option.value === 'inherit'; });
        var box = document.createElement('div');
        box.className = 'b2m-choice-grid b2m-route-choice-grid';
        var entries = [];
        if (allowInherit) entries.push(['inherit', 'Inherit', 'Use item/default route']);
        entries.push(['mealie', 'Mealie', 'Shopping list']);
        entries.push(['homeassistant', 'Home Assistant', 'Webhook event']);
        box.innerHTML = entries.map(function(entry) {
            return '<label class="b2m-choice-card"><input class="form-check-input me-2" type="checkbox" value="' + entry[0] + '"><span><strong>' + entry[1] + '</strong><small>' + entry[2] + '</small></span></label>';
        }).join('');
        select.insertAdjacentElement('afterend', box);
        var checks = Array.from(box.querySelectorAll('input[type="checkbox"]'));
        function check(value, state) { var el = checks.find(function(row) { return row.value === value; }); if (el) el.checked = state; }
        if (original === 'inherit' && allowInherit) check('inherit', true);
        else if (original === 'both') { check('mealie', true); check('homeassistant', true); }
        else if (original === 'mealie') check('mealie', true);
        else if (original === 'homeassistant') check('homeassistant', true);

        function sync(changed) {
            if (changed && changed.value === 'inherit' && changed.checked) {
                checks.forEach(function(row) { if (row !== changed) row.checked = false; });
            } else if (changed && changed.value !== 'inherit' && changed.checked) {
                check('inherit', false);
            }
            var values = checks.filter(function(row) { return row.checked; }).map(function(row) { return row.value; });
            if (values.includes('inherit')) select.value = 'inherit';
            else if (values.includes('mealie') && values.includes('homeassistant')) select.value = 'both';
            else if (values.includes('mealie')) select.value = 'mealie';
            else if (values.includes('homeassistant')) select.value = 'homeassistant';
            else select.value = 'none';
            updateListChoiceState(select.closest('form'));
        }
        checks.forEach(function(row) { row.addEventListener('change', function() { sync(row); }); });
        sync();
    }

    function installListChoices(select) {
        if (!select || select.dataset.checkboxUi === '1') return;
        select.dataset.checkboxUi = '1';
        select.classList.add('d-none');
        var box = document.createElement('div');
        box.className = 'b2m-choice-grid b2m-list-choice-grid';
        box.innerHTML = Array.from(select.options).map(function(option) {
            var text = option.textContent.replace(/ · default$/, '');
            var isDefault = / · default$/.test(option.textContent);
            return '<label class="b2m-choice-card"><input class="form-check-input me-2" type="checkbox" value="' + option.value.replace(/"/g, '&quot;') + '"' + (option.selected ? ' checked' : '') + '><span><strong>' + text.replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</strong>' + (isDefault ? '<small><span class="badge bg-blue-lt">default</span></small>' : '<small>Mealie list</small>') + '</span></label>';
        }).join('');
        select.insertAdjacentElement('afterend', box);
        var hint = select.parentElement.querySelector('.form-hint');
        if (hint && hint.textContent.includes('Ctrl/Cmd')) hint.textContent = 'Select any number of lists. No selection = current default list.';
        box.querySelectorAll('input[type="checkbox"]').forEach(function(check) {
            check.addEventListener('change', function() {
                Array.from(select.options).forEach(function(option) { if (option.value === check.value) option.selected = check.checked; });
            });
        });
    }

    function updateListChoiceState(targetForm) {
        if (!targetForm) return;
        var route = targetForm.querySelector('select[name="route"]');
        var listBox = targetForm.querySelector('.b2m-list-choice-grid');
        if (!route || !listBox) return;
        var enabled = route.value === 'mealie' || route.value === 'both' || route.value === 'inherit';
        listBox.classList.toggle('b2m-choice-disabled', !enabled);
        listBox.querySelectorAll('input').forEach(function(input) { input.disabled = !enabled; });
    }

    document.querySelectorAll('select[name="route"]').forEach(installRouteChoices);
    document.querySelectorAll('select[multiple][name="shopping_list_ids"]').forEach(installListChoices);
    document.querySelectorAll('select[name="route"]').forEach(function(select) { updateListChoiceState(select.closest('form')); });

    function styleTargetCards() {
        document.querySelectorAll('form[action*="/targets/"]:not([action$="/delete"])').forEach(function(targetForm) {
            var wrapper = targetForm.parentElement;
            if (!wrapper || wrapper.classList.contains('b2m-target-card')) return;
            wrapper.classList.add('b2m-target-card', targetForm.querySelector('.target-unit-select') ? 'b2m-target-food' : 'b2m-target-recipe');
            var heading = wrapper.querySelector(':scope > .d-flex');
            if (heading) heading.classList.add('b2m-target-heading');
            targetForm.classList.add('b2m-target-body');
            var remove = wrapper.querySelector('form[action$="/delete"] button');
            if (remove) {
                remove.className = 'btn btn-icon btn-outline-danger b2m-target-remove';
                remove.title = 'Remove target';
            }
            wrapper.querySelectorAll('.text-secondary.small').forEach(function(el) {
                el.textContent = el.textContent.replace(/ · target #\d+/, '');
            });
        });
    }
    styleTargetCards();

    function installClearAll() {
        var title = Array.from(document.querySelectorAll('h3.card-title')).find(function(el) { return el.textContent.trim().startsWith('Current targets'); });
        if (!title || !barcode) return;
        var header = title.closest('.card-header');
        if (!header || header.querySelector('.b2m-clear-targets')) return;
        var actions = document.createElement('div');
        actions.className = 'card-actions';
        actions.innerHTML = '<form method="post" action="/barcodes/' + encodeURIComponent(barcode) + '/unmap" data-confirm="Clear all targets for this barcode?"><button type="submit" class="btn btn-sm btn-outline-danger b2m-clear-targets"><i class="ti ti-trash icon"></i> Clear all</button></form>';
        header.appendChild(actions);
    }
    installClearAll();

    function installTestSend() {
        if (!barcode || !document.querySelector('form[action*="/targets/"]:not([action$="/delete"])')) return;
        var list = document.querySelector('.page-header .btn-list');
        if (!list || document.getElementById('barcode-test-send')) return;
        var button = document.createElement('button');
        button.type = 'button'; button.id = 'barcode-test-send'; button.className = 'btn btn-outline-primary';
        button.innerHTML = '<i class="ti ti-send icon"></i> Test send';
        list.insertBefore(button, list.firstChild);
        button.addEventListener('click', async function() {
            var old = button.innerHTML; button.disabled = true;
            button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Sending…';
            try {
                var response = await fetch('/api/barcodes/' + encodeURIComponent(barcode) + '/test-route', {method: 'POST', headers: {'Accept': 'application/json'}});
                var data = await response.json();
                if (!response.ok || !data.ok) throw new Error(data.error || data.result || 'Test send failed');
                button.className = 'btn btn-success'; button.innerHTML = '<i class="ti ti-check icon"></i> Sent';
                setTimeout(function() { button.className = 'btn btn-outline-primary'; button.innerHTML = old; button.disabled = false; }, 2200);
            } catch (error) {
                button.className = 'btn btn-outline-danger'; button.innerHTML = '<i class="ti ti-alert-triangle icon"></i> ' + error.message;
                setTimeout(function() { button.className = 'btn btn-outline-primary'; button.innerHTML = old; button.disabled = false; }, 3500);
            }
        });
    }
    installTestSend();

    function polishRecipePicker() {
        var selected = document.getElementById('recipe-selected-name');
        if (selected) selected.classList.add('fw-bold', 'fs-3');
        var results = document.getElementById('recipe-search-results');
        if (!results) return;
        function clean() {
            results.querySelectorAll('code').forEach(function(code) { code.remove(); });
            results.querySelectorAll('.list-group-item').forEach(function(row) {
                var name = row.querySelector('span'); if (name) name.classList.add('fw-semibold');
            });
        }
        clean(); new MutationObserver(clean).observe(results, {childList: true, subtree: true});
    }
    polishRecipePicker();
})();
