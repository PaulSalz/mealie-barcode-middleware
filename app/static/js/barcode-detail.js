(function() {
    'use strict';

    var form = document.getElementById('barcode-metadata-form');
    var status = document.getElementById('metadata-save-status');

    async function saveMetadata(event) {
        var submitter = event.submitter;
        if (submitter && submitter.getAttribute('formaction')) return;
        event.preventDefault();
        if (!form) return;
        if (status) {
            status.className = 'form-hint text-secondary';
            status.textContent = 'Saving…';
        }
        try {
            var response = await fetch(form.action, {
                method: 'POST',
                headers: {'X-Requested-With': 'fetch', 'Accept': 'application/json'},
                body: new FormData(form)
            });
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Save failed');
            var title = document.getElementById('displayed-title');
            var brand = document.getElementById('displayed-brand');
            if (title) title.textContent = data.title || '—';
            if (brand) brand.textContent = data.brand || '—';
            if (status) {
                status.className = 'form-hint text-success';
                status.textContent = 'Saved.';
                setTimeout(function() { status.textContent = ''; }, 2500);
            }
        } catch (error) {
            if (status) {
                status.className = 'form-hint text-danger';
                status.textContent = error.message;
            }
        }
    }

    if (form) form.addEventListener('submit', saveMetadata);

    // Enter inside either override field now uses the AJAX save above instead of a
    // page navigation. Textareas are not present in this form, so no exception needed.
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
})();
