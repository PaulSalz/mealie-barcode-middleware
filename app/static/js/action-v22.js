(function () {
  'use strict';

  if (!(window.location.pathname === '/actions/new' || /^\/actions\/[^/]+$/.test(window.location.pathname))) return;
  if (window.__b2mActionV22Loaded) return;
  window.__b2mActionV22Loaded = true;

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');

  const PRESETS = {
    light: {
      icon: 'bulb', title: 'Light', subtitle: 'Toggle or set a Home Assistant light',
      params: {},
      payload: {
        action_id: '{{ action.id }}', barcode: '{{ scan.barcode }}', kind: 'light',
        entity_id: 'light.kitchen', command: 'toggle', brightness_pct: 70
      }
    },
    tts: {
      icon: 'speakerphone', title: 'TTS', subtitle: 'Speak a message on a media player',
      params: {},
      payload: {
        action_id: '{{ action.id }}', barcode: '{{ scan.barcode }}', kind: 'tts',
        media_player: 'media_player.kitchen', message: 'Barcode {{ scan.barcode }} scanned', language: 'de'
      }
    },
    timer: {
      icon: 'clock-play', title: 'Timer', subtitle: 'Send a reusable duration parameter',
      params: {duration_seconds: 600},
      payload: {
        action_id: '{{ action.id }}', barcode: '{{ scan.barcode }}', kind: 'timer',
        timer: 'timer.kitchen', duration_seconds: '{{ params.duration_seconds }}'
      }
    },
    automation: {
      icon: 'automation', title: 'Automation', subtitle: 'Trigger a HA automation with variables',
      params: {},
      payload: {
        action_id: '{{ action.id }}', barcode: '{{ scan.barcode }}', kind: 'automation',
        entity_id: 'automation.kitchen_mode', variables: {source: 'b2m', barcode: '{{ scan.barcode }}'}
      }
    },
    data: {
      icon: 'braces', title: 'Data', subtitle: 'Pass structured data to any webhook',
      params: {value: 'example'},
      payload: {
        action_id: '{{ action.id }}', action_name: '{{ action.name }}', barcode: '{{ scan.barcode }}',
        kind: 'data', value: '{{ params.value }}', data: {source: 'barcode'}
      }
    }
  };

  const HELP = {
    action_id: 'Stable ID encoded in printed labels as ACTION:<id>. Keep it short and do not reuse an ID for a different purpose.',
    name: 'Human-readable name shown in B2M. It does not change an already printed Action code.',
    aliases: 'Previous Action IDs that should still resolve to this action. Useful after renaming or migrating printed labels.',
    description: 'Optional note describing what the action is intended to do.',
    action_type: 'Webhook is generic. Home Assistant webhook marks the action as HA-oriented; delivery is still an HTTP request to the configured URL.',
    method: 'HTTP method used for the request. POST is the usual choice for webhooks and Home Assistant.',
    execution_mode: 'Async returns to the scanner immediately and executes in the background. Sync waits for the remote response before the scan finishes.',
    webhook_url: 'Destination URL. For Home Assistant this is normally the full /api/webhook/<id> URL. Treat webhook URLs as secrets.',
    cooldown_seconds: 'Minimum time after a successful/started execution before another scan of this action is accepted. Repeated scans inside the window are counted as Cooldown ignored.',
    retries: 'Number of additional attempts after the first request fails. 0 means one request only.',
    retry_delay: 'Delay before the first retry. Later delays can grow using the backoff factor.',
    backoff_factor: 'Multiplier for retry delays. Example: 0.5 s with factor 2 becomes 0.5 s, 1 s, 2 s, …',
    retry_policy: 'Defines which failures are safe to retry. For toggle-style actions, Never avoids accidentally executing a request twice.',
    connect_timeout: 'Maximum time to establish the TCP/TLS connection to the destination.',
    read_timeout: 'Maximum time B2M waits for response data after the request has been sent. This is usually the timeout you increase for a slow webhook.',
    write_timeout: 'Maximum time allowed to send the request body to the destination.',
    pool_timeout: 'Maximum time to wait for a free HTTP connection from the connection pool before failing.',
    enabled: 'Disabled actions keep their printed code valid but do not execute.',
    respect_pause: 'When enabled, Scan & Link pause mode also suppresses this action.'
  };

  function parseObject(textarea) {
    if (!textarea) return {};
    try {
      const value = JSON.parse(textarea.value || '{}');
      return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    } catch (e) { return {}; }
  }

  function inferType(value) {
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number') return 'number';
    if (value && typeof value === 'object') return 'json';
    if (typeof value === 'string' && /\{\{\s*[^}]+\s*\}\}/.test(value)) return 'template';
    return 'text';
  }

  function displayValue(value, type) {
    if (type === 'json') {
      try { return JSON.stringify(value); } catch (e) { return '{}'; }
    }
    if (type === 'boolean') return value ? 'true' : 'false';
    return String(value == null ? '' : value);
  }

  function valueFromRow(row) {
    const type = row.querySelector('.b2m-kv-type').value;
    const input = row.querySelector('.b2m-kv-value');
    const raw = input ? input.value : '';
    if (type === 'number') {
      const value = Number(raw);
      return Number.isFinite(value) ? value : 0;
    }
    if (type === 'boolean') return raw === 'true';
    if (type === 'json') {
      try { return JSON.parse(raw || '{}'); } catch (e) { return raw; }
    }
    return raw;
  }

  function kvRow(key, value, type) {
    type = type || inferType(value);
    const row = document.createElement('div');
    row.className = 'b2m-kv-row';
    row.innerHTML =
      '<input class="form-control form-control-sm b2m-kv-key" placeholder="key" value="' + esc(key) + '">' +
      '<select class="form-select form-select-sm b2m-kv-type" aria-label="Value type">' +
        [['text','Text'],['number','Number'],['boolean','Boolean'],['template','Template'],['json','JSON object']]
          .map((entry) => '<option value="' + entry[0] + '"' + (entry[0] === type ? ' selected' : '') + '>' + entry[1] + '</option>').join('') +
      '</select>' +
      (type === 'boolean'
        ? '<select class="form-select form-select-sm b2m-kv-value"><option value="true"' + (value === true ? ' selected' : '') + '>true</option><option value="false"' + (value !== true ? ' selected' : '') + '>false</option></select>'
        : '<input class="form-control form-control-sm b2m-kv-value font-monospace" placeholder="value" value="' + esc(displayValue(value, type)) + '">') +
      '<button class="btn btn-sm btn-outline-danger b2m-kv-remove" type="button" title="Remove"><i class="ti ti-x"></i></button>';
    return row;
  }

  function objectFromEditor(root) {
    const out = {};
    root.querySelectorAll('.b2m-kv-row').forEach((row) => {
      const key = row.querySelector('.b2m-kv-key').value.trim();
      if (!key) return;
      out[key] = valueFromRow(row);
    });
    return out;
  }

  function updatePreview(kind) {
    const root = $('action-v22-' + kind);
    const preview = $('action-v22-' + kind + '-preview');
    if (!root || !preview) return;
    preview.textContent = JSON.stringify(objectFromEditor(root), null, 2);
  }

  function writeTextarea(kind) {
    const root = $('action-v22-' + kind);
    const textarea = kind === 'params' ? $('action-parameters-json') : kind === 'payload' ? $('action-payload-json') : document.querySelector('[name="headers_json"]');
    if (!root || !textarea) return;
    textarea.value = JSON.stringify(objectFromEditor(root), null, 2);
    textarea.dispatchEvent(new Event('input', {bubbles: true}));
    updatePreview(kind);
  }

  function bindKvRow(row, kind) {
    row.querySelector('.b2m-kv-remove').addEventListener('click', function () {
      row.remove(); writeTextarea(kind);
    });
    row.addEventListener('input', function () { writeTextarea(kind); });
    row.addEventListener('change', function (event) {
      if (event.target.classList.contains('b2m-kv-type')) {
        const key = row.querySelector('.b2m-kv-key').value;
        const oldValue = valueFromRow(row);
        const replacement = kvRow(key, oldValue, event.target.value);
        row.replaceWith(replacement);
        bindKvRow(replacement, kind);
      }
      writeTextarea(kind);
    });
  }

  function renderObjectEditor(kind, value) {
    const root = $('action-v22-' + kind);
    if (!root) return;
    root.innerHTML = '';
    Object.entries(value || {}).forEach(([key, rowValue]) => {
      const row = kvRow(key, rowValue);
      root.appendChild(row); bindKvRow(row, kind);
    });
    updatePreview(kind);
  }

  function addRow(kind) {
    const root = $('action-v22-' + kind);
    if (!root) return;
    const row = kvRow('', '', 'text');
    root.appendChild(row); bindKvRow(row, kind);
    row.querySelector('.b2m-kv-key').focus();
  }

  function applyPreset(name) {
    const preset = PRESETS[name];
    if (!preset) return;
    const paramsInput = $('action-parameters-json');
    const payloadInput = $('action-payload-json');
    if (paramsInput) paramsInput.value = JSON.stringify(preset.params, null, 2);
    if (payloadInput) payloadInput.value = JSON.stringify(preset.payload, null, 2);
    renderObjectEditor('params', preset.params);
    renderObjectEditor('payload', preset.payload);
    document.querySelectorAll('.b2m-action-preset').forEach((button) => button.classList.toggle('active', button.dataset.preset === name));
    const note = $('action-v22-preset-note');
    if (note) note.innerHTML = '<strong>' + esc(preset.title) + ' example loaded.</strong> Edit the fields below; B2M will serialize them to JSON automatically.';
    const actionType = document.querySelector('[name="action_type"]');
    if (actionType && ['light','tts','timer','automation'].includes(name)) actionType.value = 'homeassistant';
    ['params','payload'].forEach(writeTextarea);
  }

  function addHelp() {
    Object.entries(HELP).forEach(([name, text]) => {
      const field = document.querySelector('[name="' + name + '"]');
      if (!field) return;
      const wrap = field.closest('[class*="col-"]') || field.parentElement;
      if (!wrap || wrap.querySelector(':scope > .b2m-v22-field-help')) return;
      const hint = document.createElement('div');
      hint.className = 'form-hint b2m-v22-field-help';
      hint.textContent = text;
      wrap.appendChild(hint);
    });
  }

  function equalizeStats() {
    const rows = Array.from(document.querySelectorAll('.row.row-cards.mb-3'));
    const row = rows.find((item) => item.querySelectorAll('.b2m-stat-card,.card.card-sm').length >= 6);
    if (row) row.classList.add('b2m-action-stat-row');
  }

  function buildBuilder() {
    if ($('action-v22-builder')) return;
    const payloadInput = $('action-payload-json');
    const paramsInput = $('action-parameters-json');
    const headersInput = document.querySelector('[name="headers_json"]');
    if (!payloadInput || !paramsInput || !headersInput) return;
    const requestCard = payloadInput.closest('.card');
    const row = requestCard && requestCard.querySelector('.card-body > .row');
    if (!row) return;

    const builder = document.createElement('div');
    builder.id = 'action-v22-builder';
    builder.className = 'col-12';
    builder.innerHTML =
      '<div class="b2m-action-builder">' +
        '<div class="d-flex justify-content-between align-items-start gap-3 flex-wrap mb-3"><div><h3 class="h4 mb-1">Request builder</h3><div class="text-secondary">Start from an example or build parameters, payload and headers without writing JSON by hand.</div></div><span class="badge bg-primary-lt text-primary">JSON generated automatically</span></div>' +
        '<div class="b2m-action-preset-grid mb-3">' + Object.entries(PRESETS).map(([key, preset]) =>
          '<button class="b2m-action-preset" type="button" data-preset="' + key + '"><span class="avatar bg-primary-lt text-primary"><i class="ti ti-' + preset.icon + '"></i></span><span><strong>' + esc(preset.title) + '</strong><small>' + esc(preset.subtitle) + '</small></span></button>'
        ).join('') + '</div>' +
        '<div class="alert alert-info py-2 mb-3" id="action-v22-preset-note"><strong>Examples are editable.</strong> For Home Assistant, your webhook automation decides what <code>kind</code>, <code>entity_id</code>, <code>command</code> and the other fields do.</div>' +
        '<div class="accordion" id="action-v22-editor-accordion">' +
          editorSection('params', 'Parameters', 'Reusable values referenced as {{ params.key }}. Good for durations, quantities and values you may change later without reprinting a code.') +
          editorSection('payload', 'Payload', 'JSON body sent to POST/PUT/PATCH requests. Templates are resolved when the barcode is scanned.') +
          editorSection('headers', 'Headers', 'Optional HTTP headers such as Content-Type or Authorization. Do not put secrets into printed codes; headers stay only in B2M.') +
        '</div>' +
      '</div>';

    row.insertBefore(builder, Array.from(row.children).find((node) => node.querySelector && node.querySelector('#action-apply-timer')) || payloadInput.closest('[class*="col-"]'));

    ['params','payload','headers'].forEach((kind) => {
      const value = kind === 'params' ? parseObject(paramsInput) : kind === 'payload' ? parseObject(payloadInput) : parseObject(headersInput);
      renderObjectEditor(kind, value);
      const add = $('action-v22-' + kind + '-add');
      if (add) add.addEventListener('click', () => addRow(kind));
    });

    builder.querySelectorAll('.b2m-action-preset').forEach((button) => button.addEventListener('click', () => applyPreset(button.dataset.preset)));

    const timerCol = $('action-apply-timer') && $('action-apply-timer').closest('.col-12');
    const timerSlot = $('action-v22-helper-slot');
    if (timerCol && timerSlot) {
      timerCol.classList.remove('col-12');
      timerSlot.appendChild(timerCol);
      timerCol.querySelector('.card')?.classList.add('mb-0');
      $('action-apply-timer').addEventListener('click', function () {
        setTimeout(function () {
          renderObjectEditor('params', parseObject(paramsInput));
          renderObjectEditor('payload', parseObject(payloadInput));
        }, 0);
      });
      $('action-preset-envelope')?.addEventListener('click', function () {
        setTimeout(function () { renderObjectEditor('payload', parseObject(payloadInput)); }, 0);
      });
    }
  }

  function editorSection(kind, title, help) {
    return '<div class="accordion-item">' +
      '<h2 class="accordion-header"><button class="accordion-button' + (kind === 'payload' ? '' : ' collapsed') + '" type="button" data-bs-toggle="collapse" data-bs-target="#action-v22-' + kind + '-collapse">' + title + '</button></h2>' +
      '<div id="action-v22-' + kind + '-collapse" class="accordion-collapse collapse' + (kind === 'payload' ? ' show' : '') + '" data-bs-parent="#action-v22-editor-accordion"><div class="accordion-body">' +
        '<div class="form-hint mb-2">' + help + '</div>' +
        '<div class="b2m-kv-editor" id="action-v22-' + kind + '"></div>' +
        '<div class="d-flex justify-content-between align-items-center mt-2 gap-2"><button class="btn btn-sm btn-outline-primary" type="button" id="action-v22-' + kind + '-add"><i class="ti ti-plus"></i> Add field</button><button class="btn btn-sm btn-ghost-secondary" type="button" data-bs-toggle="collapse" data-bs-target="#action-v22-' + kind + '-preview-wrap"><i class="ti ti-code"></i> Preview JSON</button></div>' +
        '<div class="collapse mt-2" id="action-v22-' + kind + '-preview-wrap"><pre class="b2m-action-json-preview mb-0" id="action-v22-' + kind + '-preview"></pre></div>' +
        (kind === 'params' ? '<div id="action-v22-helper-slot" class="mt-3"></div>' : '') +
      '</div></div></div>';
  }

  function polishAdvancedToggle() {
    const toggle = $('action-advanced-toggle');
    if (!toggle) return;
    const label = toggle.closest('label');
    const text = label && label.querySelector('.form-check-label');
    if (text) text.innerHTML = '<i class="ti ti-adjustments-horizontal me-1"></i>Advanced / raw JSON';
    if (label && !label.parentElement.querySelector('.b2m-v22-advanced-hint')) {
      const hint = document.createElement('span');
      hint.className = 'text-secondary small me-2 b2m-v22-advanced-hint';
      hint.textContent = 'Retries, network timeouts and raw JSON';
      label.parentElement.insertBefore(hint, label);
    }
  }

  function syncExternalJsonChanges() {
    const mapping = [
      [$('action-parameters-json'), 'params'],
      [$('action-payload-json'), 'payload'],
      [document.querySelector('[name="headers_json"]'), 'headers']
    ];
    mapping.forEach(([textarea, kind]) => {
      if (!textarea) return;
      textarea.addEventListener('change', function () { renderObjectEditor(kind, parseObject(textarea)); });
    });
  }

  function install() {
    addHelp();
    equalizeStats();
    buildBuilder();
    polishAdvancedToggle();
    syncExternalJsonChanges();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(install, 0), {once: true});
  else setTimeout(install, 0);
})();
