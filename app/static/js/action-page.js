(function() {
    'use strict';

    var button = document.getElementById('action-test');
    var result = document.getElementById('action-test-result');
    if (button && result) {
        button.addEventListener('click', async function() {
            var actionId = button.dataset.actionId;
            button.disabled = true;
            result.innerHTML = '<div class="alert alert-info">Testing action…</div>';
            try {
                var response = await fetch('/api/actions/' + encodeURIComponent(actionId) + '/test', {
                    method: 'POST',
                    headers: {'Accept': 'application/json'}
                });
                var data = await response.json();
                if (response.ok && data.status === 'success') {
                    result.innerHTML = '<div class="alert alert-success">✓ Webhook delivered' +
                        (data.http_status ? ' — HTTP ' + data.http_status : '') +
                        (data.duration_ms != null ? ' — ' + data.duration_ms + ' ms' : '') + '</div>';
                } else {
                    result.innerHTML = '<div class="alert alert-danger">✗ Action failed — ' +
                        (data.error || data.status || 'unknown error') + '</div>';
                }
            } catch (error) {
                result.innerHTML = '<div class="alert alert-danger">✗ Action test failed — ' + error.message + '</div>';
            } finally {
                button.disabled = false;
            }
        });
    }

    var paramsInput = document.getElementById('action-parameters-json');
    var payloadInput = document.getElementById('action-payload-json');
    var timerButton = document.getElementById('action-apply-timer');
    var envelopeButton = document.getElementById('action-preset-envelope');

    function genericPayload() {
        return {
            action_id: '{{ action.id }}',
            action_name: '{{ action.name }}',
            barcode: '{{ scan.barcode }}',
            params: '{{ params }}'
        };
    }

    if (timerButton && paramsInput && payloadInput) {
        timerButton.addEventListener('click', function() {
            var valueInput = document.getElementById('action-timer-value');
            var unitInput = document.getElementById('action-timer-unit');
            var value = Number.parseFloat(valueInput.value);
            var multiplier = Number.parseFloat(unitInput.value);
            if (!Number.isFinite(value) || value < 0 || !Number.isFinite(multiplier)) return;

            var params = {};
            try { params = JSON.parse(paramsInput.value || '{}'); } catch (error) { params = {}; }
            params.duration_seconds = Math.round(value * multiplier * 1000) / 1000;
            paramsInput.value = JSON.stringify(params, null, 2);

            var payload = genericPayload();
            payload.duration_seconds = '{{ params.duration_seconds }}';
            payloadInput.value = JSON.stringify(payload, null, 2);
        });
    }

    if (envelopeButton && payloadInput) {
        envelopeButton.addEventListener('click', function() {
            payloadInput.value = JSON.stringify(genericPayload(), null, 2);
        });
    }
})();
