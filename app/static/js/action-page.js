(function() {
    'use strict';
    var button = document.getElementById('action-test');
    var result = document.getElementById('action-test-result');
    if (!button || !result) return;

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
})();
