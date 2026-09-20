(function() {
    'use strict';

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    var button = document.getElementById('action-test');
    var result = document.getElementById('action-test-result');
    if (button && result) {
        button.addEventListener('click', async function() {
            var actionId = button.dataset.actionId;
            button.disabled = true;
            result.innerHTML = '<div class="alert alert-info">Testing action…</div>';
            try {
                var response = await fetch('/api/actions/' + encodeURIComponent(actionId) + '/test', {
                    method: 'POST', headers: {'Accept': 'application/json'}
                });
                var data = await response.json();
                if (response.ok && data.status === 'success') {
                    result.innerHTML = '<div class="alert alert-success">✓ Webhook delivered' +
                        (data.http_status ? ' — HTTP ' + data.http_status : '') +
                        (data.duration_ms != null ? ' — ' + data.duration_ms + ' ms' : '') + '</div>';
                } else {
                    result.innerHTML = '<div class="alert alert-danger">✗ Action failed — ' +
                        esc(data.error || data.status || 'unknown error') + '</div>';
                }
            } catch (error) {
                result.innerHTML = '<div class="alert alert-danger">✗ Action test failed — ' + esc(error.message) + '</div>';
            } finally { button.disabled = false; }
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
            updateHaYaml();
        });
    }

    if (envelopeButton && payloadInput) {
        envelopeButton.addEventListener('click', function() {
            payloadInput.value = JSON.stringify(genericPayload(), null, 2);
        });
    }

    function fieldColumnByName(name) {
        var field = document.querySelector('[name="' + name + '"]');
        return field ? field.closest('[class*="col-"]') : null;
    }

    function cardByHeading(text) {
        var heading = Array.from(document.querySelectorAll('h3.card-title')).find(function(el) {
            return el.textContent.trim() === text;
        });
        return heading ? heading.closest('.card') : null;
    }

    function setupAdvancedMode() {
        var form = document.querySelector('form[action^="/actions/"]');
        if (!form || document.getElementById('action-advanced-toggle')) return;
        var rawFields = ['parameters_json', 'payload_json', 'headers_json'];
        var advancedEls = rawFields.map(fieldColumnByName).filter(Boolean);
        ['Execution controls', 'Timeouts'].forEach(function(title) {
            var card = cardByHeading(title);
            if (card) advancedEls.push(card);
        });
        advancedEls.forEach(function(el) { el.classList.add('action-advanced-field'); });

        var holder = document.createElement('div');
        holder.className = 'd-flex justify-content-end align-items-center mb-3';
        holder.innerHTML = '<label class="form-check form-switch mb-0"><input class="form-check-input" type="checkbox" id="action-advanced-toggle"><span class="form-check-label"><i class="ti ti-adjustments-horizontal me-1"></i>Advanced</span></label>';
        form.parentElement.insertBefore(holder, form);
        var toggle = holder.querySelector('input');
        toggle.checked = localStorage.getItem('b2m-action-advanced') === '1';

        function apply() {
            advancedEls.forEach(function(el) { el.classList.toggle('d-none', !toggle.checked); });
            localStorage.setItem('b2m-action-advanced', toggle.checked ? '1' : '0');
        }
        toggle.addEventListener('change', apply);
        apply();
    }

    function yamlQuote(value) {
        return String(value || '').replace(/'/g, "''");
    }

    function webhookId(url) {
        try {
            var u = new URL(url, window.location.origin);
            var match = u.pathname.match(/\/api\/webhook\/([^/]+)/);
            return match ? decodeURIComponent(match[1]) : 'YOUR_WEBHOOK_ID';
        } catch (e) { return 'YOUR_WEBHOOK_ID'; }
    }

    function currentActionName() {
        var input = document.querySelector('input[name="name"]');
        return input && input.value.trim() ? input.value.trim() : 'Barcode action';
    }

    function buildHaYaml() {
        var url = document.querySelector('input[name="webhook_url"]');
        var id = webhookId(url ? url.value : '');
        return "alias: 'B2M - " + yamlQuote(currentActionName()) + "'\n" +
            "description: 'Receives this B2M Action webhook and emits a Home Assistant event.'\n" +
            "triggers:\n" +
            "  - trigger: webhook\n" +
            "    webhook_id: '" + yamlQuote(id) + "'\n" +
            "    allowed_methods:\n" +
            "      - POST\n" +
            "    local_only: true\n" +
            "conditions: []\n" +
            "actions:\n" +
            "  - event: b2m_action\n" +
            "    event_data:\n" +
            "      action_id: \"{{ trigger.json.action_id | default('') }}\"\n" +
            "      action_name: \"{{ trigger.json.action_name | default('') }}\"\n" +
            "      barcode: \"{{ trigger.json.barcode | default('') }}\"\n" +
            "      duration_seconds: \"{{ trigger.json.params.duration_seconds | default(0) }}\"\n" +
            "mode: single\n";
    }

    function updateHaYaml() {
        var textarea = document.getElementById('action-ha-yaml');
        if (textarea) textarea.value = buildHaYaml();
    }

    function setupHaGenerator() {
        var urlInput = document.querySelector('input[name="webhook_url"]');
        if (!urlInput || document.getElementById('action-ha-yaml')) return;
        var requestCard = urlInput.closest('.card');
        if (!requestCard) return;
        var card = document.createElement('div');
        card.className = 'card mb-3';
        card.innerHTML = '<div class="card-header"><div><h3 class="card-title"><i class="ti ti-home me-1"></i>Home Assistant automation</h3><p class="card-subtitle">Ready-to-paste webhook trigger. It emits <code>b2m_action</code>; attach another automation to that event or replace the action block directly.</p></div><div class="card-actions"><button class="btn btn-sm btn-outline-primary" type="button" id="action-ha-copy"><i class="ti ti-copy icon"></i>Copy YAML</button></div></div><div class="card-body"><textarea id="action-ha-yaml" class="form-control font-monospace" rows="16" readonly></textarea><div class="form-hint mt-2">The webhook ID is derived from the configured Home Assistant webhook URL. Keep webhook URLs private.</div></div>';
        requestCard.insertAdjacentElement('afterend', card);
        updateHaYaml();
        ['input', 'change'].forEach(function(evt) {
            urlInput.addEventListener(evt, updateHaYaml);
            var nameInput = document.querySelector('input[name="name"]');
            if (nameInput) nameInput.addEventListener(evt, updateHaYaml);
        });
        document.getElementById('action-ha-copy').addEventListener('click', function() {
            var area = document.getElementById('action-ha-yaml');
            navigator.clipboard.writeText(area.value).then(function() {
                var btn = document.getElementById('action-ha-copy');
                var old = btn.innerHTML;
                btn.innerHTML = '<i class="ti ti-check icon"></i>Copied';
                setTimeout(function() { btn.innerHTML = old; }, 1500);
            }).catch(function() { area.select(); document.execCommand('copy'); });
        });
    }

    setupAdvancedMode();
    setupHaGenerator();
})();
