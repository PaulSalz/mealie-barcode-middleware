(function() {
    'use strict';

    function addHaWebhookTestButton() {
        var input = document.getElementById('setting_ha_webhook_url');
        if (!input || document.getElementById('ha-webhook-test')) return;

        var row = input.closest('.row.g-2') || input.parentElement;
        if (!row) return;

        var wrapper = document.createElement('div');
        wrapper.className = 'col-auto d-flex align-items-start';
        wrapper.innerHTML = '<button type="button" class="btn btn-outline-primary" id="ha-webhook-test">' +
            '<i class="ti ti-send icon"></i> Test webhook</button>';
        row.appendChild(wrapper);

        var result = document.createElement('div');
        result.id = 'ha-webhook-test-result';
        result.className = 'form-hint mt-2';
        row.parentElement.appendChild(result);

        wrapper.querySelector('button').addEventListener('click', async function() {
            var button = this;
            button.disabled = true;
            result.className = 'form-hint mt-2 text-secondary';
            result.textContent = 'Sending test webhook…';
            try {
                var response = await fetch('/api/settings/test-ha-webhook', {
                    method: 'POST',
                    headers: {'Accept': 'application/json'}
                });
                var data = await response.json();
                if (response.ok && data.ok) {
                    result.className = 'form-hint mt-2 text-success';
                    result.textContent = '✓ Delivered — HTTP ' + data.status + ' — ' + data.duration_ms + ' ms';
                } else {
                    result.className = 'form-hint mt-2 text-danger';
                    result.textContent = '✗ Failed — ' + (data.error || ('HTTP ' + data.status));
                }
            } catch (error) {
                result.className = 'form-hint mt-2 text-danger';
                result.textContent = '✗ Failed — ' + error.message;
            } finally {
                button.disabled = false;
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        addHaWebhookTestButton();
    });
})();
