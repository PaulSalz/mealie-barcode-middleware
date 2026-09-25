(function () {
  'use strict';

  if (!(window.location.pathname === '/actions/new' || /^\/actions\/[^/]+$/.test(window.location.pathname))) return;
  if (window.__b2mActionEditorLoaded) return;
  window.__b2mActionEditorLoaded = true;

  const $ = (id) => document.getElementById(id);
  const field = (name) => document.querySelector('[name="' + name + '"]');
  const esc = (value) => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');

  const PRESETS = {
    light: {
      name: 'Barcode light', icon: 'bulb', title: 'Light', subtitle: 'Toggle a Home Assistant light',
      params: {},
      payload: {kind: 'light', entity_id: 'light.kitchen', command: 'toggle'}
    },
    tts: {
      name: 'Barcode announcement', icon: 'speakerphone', title: 'Text to speech', subtitle: 'Speak a message on a media player',
      params: {},
      payload: {kind: 'tts', tts_entity: 'tts.home_assistant_cloud', media_player: 'media_player.kitchen', message: 'Barcode {{ scan.barcode }} scanned', language: 'de'}
    },
    timer: {
      name: 'Barcode timer', icon: 'clock-play', title: 'Timer', subtitle: 'Start a Home Assistant timer',
      params: {},
      payload: {kind: 'timer', timer: 'timer.kitchen', duration: '00:10:00'}
    },
    automation: {
      name: 'Barcode automation', icon: 'automation', title: 'Automation', subtitle: 'Run a Home Assistant automation',
      params: {},
      payload: {kind: 'automation', entity_id: 'automation.kitchen_mode'}
    },
    notification: {
      name: 'Barcode notification', icon: 'bell-ringing', title: 'Notification', subtitle: 'Show a notification in Home Assistant',
      params: {},
      payload: {kind: 'notification', title: 'B2M scan', message: 'Barcode {{ scan.barcode }} scanned'}
    },
    data: {
      name: 'Custom webhook action', icon: 'braces', title: 'Custom data', subtitle: 'Send a custom payload to a webhook',
      params: {value: 'example'},
      payload: {kind: 'data', value: '{{ params.value }}', data: {source: 'barcode'}}
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

  let programmaticIdentity = false;
  let idOverridden = false;
  let urlOverridden = false;
  let exampleActive = false;
  let activePreset = null;
  let advancedMode = false;

  function dispatch(el) {
    if (!el) return;
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
  }

  function parseObject(textarea) {
    if (!textarea) return {};
    try {
      const value = JSON.parse(textarea.value || '{}');
      return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    } catch (e) {
      return {};
    }
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

  function editorRoot(kind) {
    return $('action-v22-' + kind);
  }

  function textareaFor(kind) {
    if (kind === 'params') return $('action-parameters-json');
    if (kind === 'payload') return $('action-payload-json');
    return field('headers_json');
  }

  function objectFromEditor(root) {
    const out = {};
    root.querySelectorAll('.b2m-kv-row').forEach((row) => {
      const key = row.querySelector('.b2m-kv-key').value.trim();
      if (key) out[key] = valueFromRow(row);
    });
    return out;
  }

  function updatePreview(kind) {
    const root = editorRoot(kind);
    const preview = $('action-v22-' + kind + '-preview');
    if (root && preview) preview.textContent = JSON.stringify(objectFromEditor(root), null, 2);
  }

  function writeTextarea(kind) {
    const root = editorRoot(kind);
    const textarea = textareaFor(kind);
    if (!root || !textarea) return;
    textarea.value = JSON.stringify(objectFromEditor(root), null, 2);
    textarea.dispatchEvent(new Event('input', {bubbles: true}));
    updatePreview(kind);
  }

  function bindKvRow(row, kind) {
    row.querySelector('.b2m-kv-remove').addEventListener('click', function () {
      row.remove();
      writeTextarea(kind);
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
    const root = editorRoot(kind);
    if (!root) return;
    root.innerHTML = '';
    Object.entries(value || {}).forEach(([key, rowValue]) => {
      const row = kvRow(key, rowValue);
      root.appendChild(row);
      bindKvRow(row, kind);
    });
    updatePreview(kind);
  }

  function addRow(kind) {
    const root = editorRoot(kind);
    if (!root) return;
    const row = kvRow('', '', 'text');
    root.appendChild(row);
    bindKvRow(row, kind);
    row.querySelector('.b2m-kv-key').focus();
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

  function buildBuilder() {
    if ($('action-v22-builder')) return;
    const payloadInput = $('action-payload-json');
    const paramsInput = $('action-parameters-json');
    const headersInput = field('headers_json');
    if (!payloadInput || !paramsInput || !headersInput) return;
    const requestCard = payloadInput.closest('.card');
    const row = requestCard && requestCard.querySelector('.card-body > .row');
    if (!row) return;

    const builder = document.createElement('div');
    builder.id = 'action-v22-builder';
    builder.className = 'col-12';
    builder.innerHTML =
      '<div class="b2m-action-builder">' +
        '<div class="d-flex justify-content-between align-items-start gap-3 flex-wrap mb-3"><div><h3 class="h4 mb-1">Choose an example</h3><div class="text-secondary">Choose what should happen when this code is scanned. B2M prepares the action and Home Assistant automation.</div></div></div>' +
        '<div class="b2m-action-preset-grid mb-3">' + Object.entries(PRESETS).map(([key, preset]) =>
          '<button class="b2m-action-preset" type="button" data-preset="' + key + '"><span class="avatar bg-primary-lt text-primary"><i class="ti ti-' + preset.icon + '"></i></span><span><strong>' + esc(preset.title) + '</strong><small>' + esc(preset.subtitle) + '</small></span></button>'
        ).join('') + '</div>' +
        '<div class="alert alert-info py-2 mb-3" id="action-v22-preset-note" role="status">Choose an example, save the action in B2M, then copy the automation below into Home Assistant.</div>' +
        '<div class="accordion" id="action-v22-editor-accordion">' +
          editorSection('params', 'Parameters', 'Parameters are reusable server-side values stored with the Action. They are not sent automatically; reference one in the Payload as {{ params.key }}. Use them for values you may want to change later without printing a new barcode.') +
          editorSection('payload', 'Payload', 'Payload is the actual data B2M sends to the webhook. For POST/PUT/PATCH it becomes the JSON request body; for GET it becomes query parameters. Template values are resolved at scan time.') +
          editorSection('headers', 'Headers', 'Headers are HTTP metadata, not normal action data. Most Home Assistant webhooks need none. Secrets here stay in B2M and are never encoded in the barcode.') +
        '</div>' +
      '</div>';

    markAdvancedField(builder.querySelector('#action-v22-editor-accordion'));
    markAdvancedField(builder.querySelector('[data-preset="data"]'));

    const insertionPoint = Array.from(row.children).find((node) => node.querySelector && node.querySelector('#action-apply-timer')) || payloadInput.closest('[class*="col-"]');
    row.insertBefore(builder, insertionPoint);

    ['params', 'payload', 'headers'].forEach((kind) => {
      renderObjectEditor(kind, parseObject(textareaFor(kind)));
      const add = $('action-v22-' + kind + '-add');
      if (add) add.addEventListener('click', () => addRow(kind));
      const textarea = textareaFor(kind);
      if (textarea) textarea.addEventListener('change', function () {
        renderObjectEditor(kind, parseObject(textarea));
      });
    });

    builder.querySelectorAll('.b2m-action-preset').forEach((button) => {
      button.addEventListener('click', () => applyPreset(button.dataset.preset));
    });

    const timerCol = $('action-apply-timer') && $('action-apply-timer').closest('.col-12');
    const timerSlot = $('action-v22-helper-slot');
    if (timerCol && timerSlot) {
      timerCol.classList.remove('col-12');
      timerSlot.appendChild(timerCol);
      const helperCard = timerCol.querySelector('.card');
      if (helperCard) helperCard.classList.add('mb-0');
    }
  }

  function slug(value) {
    return String(value || '').trim().toLowerCase()
      .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
      .normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9._-]+/g, '_').replace(/^[-_.]+|[-_.]+$/g, '').replace(/_+/g, '_');
  }

  function generatedId(name) {
    const clean = slug(name);
    return clean ? 'action_' + clean : 'action_';
  }

  function webhookPrefix(value) {
    value = String(value || '').trim();
    const match = value.match(/^(.*\/api\/webhook\/)([^/?#]*)/i);
    if (match) return match[1];
    if (/\/api\/webhook\/?$/i.test(value)) return value.replace(/\/?$/, '/');
    return '';
  }

  function payloadRow(key) {
    const root = editorRoot('payload');
    return root && Array.from(root.querySelectorAll('.b2m-kv-row')).find((row) => row.querySelector('.b2m-kv-key')?.value.trim() === key);
  }

  function setPayloadField(key, value, createIfMissing) {
    const row = payloadRow(key);
    const input = row && row.querySelector('.b2m-kv-value');
    if (input) {
      input.value = value;
      input.dispatchEvent(new Event('input', {bubbles: true}));
      return;
    }
    if (!createIfMissing) return;
    const textarea = $('action-payload-json');
    if (!textarea) return;
    const payload = parseObject(textarea);
    payload[key] = value;
    textarea.value = JSON.stringify(payload, null, 2);
    renderObjectEditor('payload', payload);
  }

  function syncPayloadIdentity() {
    const id = field('action_id');
    const name = field('name');
    if (id) setPayloadField('action_id', id.value, exampleActive);
    if (name) setPayloadField('action_name', name.value, exampleActive);
  }

  function syncGeneratedIdentity(force) {
    const name = field('name');
    const id = field('action_id');
    const url = field('webhook_url');
    if (!name) return;
    const nextId = generatedId(name.value);
    programmaticIdentity = true;
    if (id && (force || !idOverridden)) {
      id.value = nextId;
      dispatch(id);
    }
    const activeId = id ? String(id.value || nextId) : nextId;
    if (url && (force || !urlOverridden)) {
      const prefix = webhookPrefix(url.dataset.b2mWebhookSeed || url.value);
      if (prefix) {
        url.value = prefix + encodeURIComponent(activeId);
        dispatch(url);
      }
    }
    programmaticIdentity = false;
    if (exampleActive) syncPayloadIdentity();
  }

  function flashPresetNote(title) {
    const note = $('action-v22-preset-note');
    if (!note) return;
    note.textContent = title + ' example selected. Save the action in B2M, then copy the Home Assistant automation below.';
  }

  function applyPreset(name) {
    const preset = PRESETS[name];
    if (!preset) return;
    activePreset = name;
    exampleActive = true;
    const nameInput = field('name');
    if (nameInput && window.location.pathname === '/actions/new' && (!nameInput.value.trim() || nameInput.dataset.b2mGeneratedDefault === 'true')) {
      nameInput.value = preset.name;
      nameInput.dataset.b2mGeneratedDefault = 'false';
      dispatch(nameInput);
    }
    syncGeneratedIdentity(false);

    const currentId = field('action_id')?.value || generatedId(field('name')?.value || '');
    const currentName = field('name')?.value || '';
    const payload = Object.assign({
      action_id: currentId,
      action_name: currentName,
      barcode: '{{ scan.barcode }}'
    }, JSON.parse(JSON.stringify(preset.payload)));

    const paramsInput = $('action-parameters-json');
    const payloadInput = $('action-payload-json');
    if (paramsInput) paramsInput.value = JSON.stringify(preset.params, null, 2);
    if (payloadInput) payloadInput.value = JSON.stringify(payload, null, 2);
    renderObjectEditor('params', preset.params);
    renderObjectEditor('payload', payload);

    document.querySelectorAll('.b2m-action-preset').forEach((button) => {
      button.classList.toggle('active', button.dataset.preset === name);
    });

    const type = field('action_type');
    const method = field('method');
    const execution = field('execution_mode');
    if (type) { type.value = 'homeassistant'; dispatch(type); }
    if (method) { method.value = 'POST'; dispatch(method); }
    if (execution) { execution.value = 'async'; dispatch(execution); }
    flashPresetNote(preset.title);
    updateHaYaml();
  }

  function addHelp() {
    Object.entries(HELP).forEach(([name, text]) => {
      const input = field(name);
      if (!input) return;
      const wrap = input.closest('[class*="col-"]') || input.parentElement;
      if (!wrap || wrap.querySelector(':scope > .b2m-v22-field-help')) return;
      const hint = document.createElement('div');
      hint.className = 'form-hint b2m-v22-field-help';
      hint.textContent = text;
      wrap.appendChild(hint);
    });
  }

  function polishStats() {
    const rows = Array.from(document.querySelectorAll('.row.row-cards.mb-3'));
    const row = rows.find((item) => item.querySelectorAll('.card.card-sm').length >= 6);
    if (!row) return;
    const look = {
      'Executions': ['scan', 'primary'],
      'Successful': ['circle-check', 'green'],
      'Failed': ['alert-triangle', 'red'],
      'Cooldown ignored': ['clock-pause', 'yellow'],
      'Avg. request': ['gauge', 'blue'],
      'Last execution': ['clock', 'purple']
    };
    row.classList.add('b2m-action-stat-row');
    row.querySelectorAll('.card.card-sm').forEach((card) => {
      const body = card.querySelector('.card-body');
      const value = body && body.querySelector('.font-weight-medium');
      const label = body && body.querySelector('.text-secondary');
      if (!body || !value || !label || card.classList.contains('b2m-stat-card')) return;
      const config = look[label.textContent.trim()] || ['activity', 'secondary'];
      const valueHtml = value.innerHTML;
      const labelText = label.textContent;
      card.classList.add('b2m-stat-card');
      body.innerHTML = '<div class="d-flex align-items-center gap-3"><span class="avatar bg-' + config[1] + '-lt text-' + config[1] + '"><i class="ti ti-' + config[0] + '"></i></span><div class="min-w-0"><div class="font-weight-medium text-truncate">' + valueHtml + '</div><div class="text-secondary">' + esc(labelText) + '</div></div></div>';
    });
  }

  function fieldColumnByName(name) {
    const input = field(name);
    return input ? input.closest('[class*="col-"]') : null;
  }

  function cardByHeading(text) {
    const heading = Array.from(document.querySelectorAll('h3.card-title')).find((el) => el.textContent.trim() === text);
    return heading ? heading.closest('.card') : null;
  }

  function markAdvancedField(element) {
    if (!element) return;
    element.classList.add('action-advanced-field');
    element.classList.toggle('d-none', !advancedMode);
  }

  function hasSimplePreset() {
    return Boolean(activePreset && activePreset !== 'data');
  }

  function applyAdvancedMode() {
    document.querySelectorAll('.action-advanced-field').forEach((element) => {
      element.classList.toggle('d-none', !advancedMode);
    });
    const copyButton = $('action-ha-copy');
    if (copyButton) copyButton.disabled = !hasSimplePreset() && !advancedMode;
    updateHaYaml();
  }

  function setupAdvancedMode() {
    const form = document.querySelector('form[action^="/actions/"]');
    if (!form || $('action-advanced-toggle')) return;
    advancedMode = localStorage.getItem('b2m-action-advanced') === '1';
    const advancedEls = ['action_id', 'aliases', 'description', 'respect_pause', 'parameters_json', 'payload_json', 'headers_json']
      .map(fieldColumnByName).filter(Boolean);
    const webhookUrl = field('webhook_url');
    if (webhookUrl && webhookUrl.value.trim()) advancedEls.push(webhookUrl.closest('[class*="col-"]'));
    ['Execution controls', 'Timeouts'].forEach((title) => {
      const card = cardByHeading(title);
      if (card) advancedEls.push(card);
    });
    advancedEls.forEach(markAdvancedField);

    const holder = document.createElement('div');
    holder.className = 'd-flex justify-content-end align-items-center mb-3';
    holder.innerHTML = '<span class="text-secondary small me-2 b2m-v22-advanced-hint">Show technical settings</span><label class="form-check form-switch mb-0"><input class="form-check-input" type="checkbox" id="action-advanced-toggle"><span class="form-check-label"><i class="ti ti-adjustments-horizontal me-1"></i>Advanced</span></label>';
    form.parentElement.insertBefore(holder, form);
    const toggle = holder.querySelector('input');
    toggle.checked = advancedMode;
    toggle.addEventListener('change', () => {
      advancedMode = toggle.checked;
      localStorage.setItem('b2m-action-advanced', advancedMode ? '1' : '0');
      applyAdvancedMode();
    });
    if (webhookUrl && !webhookUrl.value.trim()) {
      const note = document.createElement('div');
      note.className = 'alert alert-warning py-2 mb-3';
      note.textContent = 'Add the Home Assistant webhook URL in Settings before saving this action.';
      webhookUrl.closest('[class*="col-"]')?.prepend(note);
    }
    applyAdvancedMode();
  }

  function revealAdvancedField(element) {
    if (element) {
      element.classList.add('action-advanced-field');
      element.classList.toggle('d-none', !advancedMode);
    }
  }

  function moveProtocolFieldsToAdvanced() {
    const execHeading = Array.from(document.querySelectorAll('h3.card-title')).find((el) => el.textContent.trim() === 'Execution controls');
    const card = execHeading && execHeading.closest('.card');
    const row = card && card.querySelector('.card-body .row');
    if (!row) return;
    ['action_type', 'method', 'execution_mode'].forEach((name) => {
      const input = field(name);
      const col = input && input.closest('[class*="col-"]');
      if (!col || col.closest('.card') === card) return;
      col.className = 'col-12';
      row.insertBefore(col, row.firstChild);
      revealAdvancedField(col);
    });
  }

  function genericPayload() {
    return {
      action_id: field('action_id')?.value || '{{ action.id }}',
      action_name: field('name')?.value || '{{ action.name }}',
      barcode: '{{ scan.barcode }}',
      params: '{{ params }}'
    };
  }

  function setupTimerHelpers() {
    const paramsInput = $('action-parameters-json');
    const payloadInput = $('action-payload-json');
    const timerButton = $('action-apply-timer');
    const envelopeButton = $('action-preset-envelope');

    if (timerButton && paramsInput && payloadInput) {
      timerButton.addEventListener('click', function () {
        const value = Number.parseFloat($('action-timer-value')?.value);
        const multiplier = Number.parseFloat($('action-timer-unit')?.value);
        if (!Number.isFinite(value) || value < 0 || !Number.isFinite(multiplier)) return;
        const params = parseObject(paramsInput);
        params.duration_seconds = Math.round(value * multiplier * 1000) / 1000;
        paramsInput.value = JSON.stringify(params, null, 2);
        const payload = genericPayload();
        payload.duration_seconds = '{{ params.duration_seconds }}';
        payloadInput.value = JSON.stringify(payload, null, 2);
        renderObjectEditor('params', params);
        renderObjectEditor('payload', payload);
        exampleActive = true;
        updateHaYaml();
      });
    }

    if (envelopeButton && payloadInput) {
      envelopeButton.addEventListener('click', function () {
        const payload = genericPayload();
        payloadInput.value = JSON.stringify(payload, null, 2);
        renderObjectEditor('payload', payload);
        exampleActive = true;
      });
    }
  }

  function yamlQuote(value) {
    return String(value || '').replace(/'/g, "''");
  }

  function webhookId(url) {
    try {
      const parsed = new URL(url, window.location.origin);
      const match = parsed.pathname.match(/\/api\/webhook\/([^/]+)/);
      return match ? decodeURIComponent(match[1]) : 'YOUR_WEBHOOK_ID';
    } catch (e) {
      return 'YOUR_WEBHOOK_ID';
    }
  }

  function currentActionName() {
    const input = field('name');
    return input && input.value.trim() ? input.value.trim() : 'Barcode action';
  }

  function buildHaYaml() {
    const url = field('webhook_url');
    const id = webhookId(url ? url.value : '');
    const payload = parseObject($('action-payload-json'));
    const selectedPreset = activePreset && PRESETS[activePreset] ? activePreset : null;
    let description = 'Runs the selected action when a B2M code is scanned.';
    let action = '';

    if (selectedPreset === 'light') {
      const entity = yamlQuote(payload.entity_id || 'light.kitchen');
      const command = ['turn_on', 'turn_off'].includes(payload.command) ? payload.command : 'toggle';
      description = 'Toggles a Home Assistant light when a B2M code is scanned.';
      action = '  - action: light.' + command + '\n' +
        '    target:\n      entity_id: "{{ trigger.json.entity_id | default(\'' + entity + '\') }}"\n';
      if (command === 'turn_on' && Number.isFinite(Number(payload.brightness_pct))) {
        action += '    data:\n      brightness_pct: "{{ trigger.json.brightness_pct | default(' + Number(payload.brightness_pct) + ') | int }}"\n';
      }
    } else if (selectedPreset === 'tts') {
      const ttsEntity = yamlQuote(payload.tts_entity || 'tts.home_assistant_cloud');
      const player = yamlQuote(payload.media_player || 'media_player.kitchen');
      const language = yamlQuote(payload.language || 'de');
      description = 'Speaks the B2M scan message on a Home Assistant media player.';
      action = '  - action: tts.speak\n' +
        '    target:\n      entity_id: "{{ trigger.json.tts_entity | default(\'' + ttsEntity + '\') }}"\n' +
        '    data:\n      media_player_entity_id: "{{ trigger.json.media_player | default(\'' + player + '\') }}"\n' +
        '      message: "{{ trigger.json.message | default(\'Barcode scanned\') }}"\n' +
        '      language: "{{ trigger.json.language | default(\'' + language + '\') }}"\n';
    } else if (selectedPreset === 'timer') {
      const timer = yamlQuote(payload.timer || 'timer.kitchen');
      const duration = yamlQuote(payload.duration || '00:10:00');
      description = 'Starts a Home Assistant timer when a B2M code is scanned.';
      action = '  - action: timer.start\n' +
        '    target:\n      entity_id: "{{ trigger.json.timer | default(\'' + timer + '\') }}"\n' +
        '    data:\n      duration: "{{ trigger.json.duration | default(\'' + duration + '\') }}"\n';
    } else if (selectedPreset === 'automation') {
      const entity = yamlQuote(payload.entity_id || 'automation.kitchen_mode');
      description = 'Runs a Home Assistant automation when a B2M code is scanned.';
      action = '  - action: automation.trigger\n' +
        '    target:\n      entity_id: "{{ trigger.json.entity_id | default(\'' + entity + '\') }}"\n' +
        '    data:\n      skip_condition: true\n';
    } else if (selectedPreset === 'notification') {
      const title = yamlQuote(payload.title || 'B2M scan');
      description = 'Shows a Home Assistant notification for every scanned code.';
      action = '  - action: persistent_notification.create\n' +
        '    data:\n      title: "{{ trigger.json.title | default(\'' + title + '\') }}"\n' +
        '      message: "{{ trigger.json.message | default(\'Barcode scanned\') }}"\n';
    } else {
      description = 'Emits a b2m_action event for custom Home Assistant automations.';
      action = '  - event: b2m_action\n    event_data:\n' +
        '      action_id: "{{ trigger.json.action_id | default(\'\') }}"\n' +
        '      action_name: "{{ trigger.json.action_name | default(\'\') }}"\n' +
        '      barcode: "{{ trigger.json.barcode | default(\'\') }}"\n' +
        '      duration_seconds: "{{ trigger.json.params.duration_seconds | default(0) }}"\n';
    }

    return "alias: 'B2M - " + yamlQuote(currentActionName()) + "'\n" +
      "description: '" + yamlQuote(description) + "'\n" +
      "triggers:\n  - trigger: webhook\n    webhook_id: '" + yamlQuote(id) + "'\n    allowed_methods:\n      - POST\n    local_only: true\n" +
      "conditions: []\nactions:\n" + action + "mode: queued\nmax: 10\n";
  }

  function updateHaYaml() {
    const textarea = $('action-ha-yaml');
    if (!textarea) return;
    textarea.value = buildHaYaml();
    const copyButton = $('action-ha-copy');
    const url = field('webhook_url');
    const hasWebhookId = webhookId(url ? url.value : '') !== 'YOUR_WEBHOOK_ID';
    if (copyButton) copyButton.disabled = !hasWebhookId || (!hasSimplePreset() && !advancedMode);
    const status = $('action-ha-status');
    if (status) {
      status.textContent = hasWebhookId
        ? (hasSimplePreset() || advancedMode ? 'Save this action in B2M, then add the copied automation in Home Assistant.' : 'Choose an example to prepare an automation.')
        : 'Add the Home Assistant webhook URL in Settings to generate this automation.';
    }
  }

  function setupHaGenerator() {
    const urlInput = field('webhook_url');
    if (!urlInput || $('action-ha-yaml')) return;
    const requestCard = urlInput.closest('.card');
    if (!requestCard) return;
    const card = document.createElement('div');
    card.className = 'card mb-3';
    card.innerHTML = '<div class="card-header"><div><h3 class="card-title"><i class="ti ti-home me-1"></i>Home Assistant automation</h3><p class="card-subtitle">Copy the finished automation and add it in Home Assistant.</p></div><div class="card-actions"><button class="btn btn-primary" type="button" id="action-ha-copy" disabled><i class="ti ti-copy icon"></i>Copy automation</button></div></div><div class="card-body"><p id="action-ha-status" class="mb-0" role="status">Choose an example to prepare an automation.</p><details id="action-ha-yaml-details" class="mt-3"><summary>Show generated YAML</summary><textarea id="action-ha-yaml" class="form-control font-monospace mt-2" rows="16" readonly></textarea></details></div>';
    requestCard.insertAdjacentElement('afterend', card);
    updateHaYaml();
    ['input', 'change'].forEach((eventName) => {
      urlInput.addEventListener(eventName, updateHaYaml);
      const nameInput = field('name');
      if (nameInput) nameInput.addEventListener(eventName, updateHaYaml);
      const payloadInput = $('action-payload-json');
      if (payloadInput) payloadInput.addEventListener(eventName, () => {
        const kind = parseObject(payloadInput).kind;
        activePreset = Object.prototype.hasOwnProperty.call(PRESETS, kind) ? kind : null;
        document.querySelectorAll('.b2m-action-preset').forEach((button) => {
          button.classList.toggle('active', button.dataset.preset === activePreset);
        });
        updateHaYaml();
      });
    });
    $('action-ha-copy').addEventListener('click', async function () {
      const button = $('action-ha-copy');
      const area = $('action-ha-yaml');
      const old = button.innerHTML;
      let copied = false;
      if (window.isSecureContext && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        try {
          await navigator.clipboard.writeText(area.value);
          copied = true;
        } catch (error) {
          copied = false;
        }
      }
      if (!copied) {
        const details = $('action-ha-yaml-details');
        const wasOpen = details.open;
        details.open = true;
        area.focus();
        area.select();
        area.setSelectionRange(0, area.value.length);
        try { copied = document.execCommand('copy'); } catch (error) { copied = false; }
        if (!wasOpen) details.open = false;
      }
      if (copied) {
        button.innerHTML = '<i class="ti ti-check icon"></i>Copied';
        $('action-ha-status').textContent = 'Automation copied. Add it in Home Assistant.';
        setTimeout(() => { button.innerHTML = old; }, 1500);
      } else {
        $('action-ha-status').textContent = 'Copy failed. Open “Show generated YAML” and copy it manually.';
      }
    });
  }

  function setupActionTest() {
    const button = $('action-test');
    const result = $('action-test-result');
    if (!button || !result) return;
    button.addEventListener('click', async function () {
      const actionId = button.dataset.actionId;
      button.disabled = true;
      result.innerHTML = '<div class="alert alert-info">Testing action…</div>';
      try {
        const response = await fetch('/api/actions/' + encodeURIComponent(actionId) + '/test', {method: 'POST', headers: {'Accept': 'application/json'}});
        const data = await response.json();
        if (response.ok && data.status === 'success') {
          result.innerHTML = '<div class="alert alert-success">✓ Webhook delivered' + (data.http_status ? ' — HTTP ' + data.http_status : '') + (data.duration_ms != null ? ' — ' + data.duration_ms + ' ms' : '') + '</div>';
        } else {
          result.innerHTML = '<div class="alert alert-danger">✗ Action failed — ' + esc(data.error || data.status || 'unknown error') + '</div>';
        }
      } catch (error) {
        result.innerHTML = '<div class="alert alert-danger">✗ Action test failed — ' + esc(error.message) + '</div>';
      } finally {
        button.disabled = false;
      }
    });
  }

  function setupIdentity() {
    const name = field('name');
    const id = field('action_id');
    const url = field('webhook_url');
    if (!name || !url) return;
    const isNew = window.location.pathname === '/actions/new';
    url.dataset.b2mWebhookSeed = url.value || '';
    if (!isNew) {
      if (id) idOverridden = true;
      urlOverridden = true;
    }

    if (isNew) {
      const type = field('action_type');
      const method = field('method');
      const execution = field('execution_mode');
      if (type) type.value = 'homeassistant';
      if (method) method.value = 'POST';
      if (execution) execution.value = 'async';
      if (!name.value.trim()) {
        name.value = 'Barcode action';
        name.dataset.b2mGeneratedDefault = 'true';
      }
      syncGeneratedIdentity(false);
    }

    name.addEventListener('input', function () {
      if (name.dataset.b2mGeneratedDefault === 'true' && name.value !== 'Barcode action') {
        name.dataset.b2mGeneratedDefault = 'false';
      }
      if (!programmaticIdentity && isNew) syncGeneratedIdentity(false);
      if (exampleActive) setPayloadField('action_name', name.value, true);
    });

    if (id) {
      id.addEventListener('input', function () {
        if (programmaticIdentity) return;
        idOverridden = true;
        if (exampleActive) setPayloadField('action_id', id.value, true);
        if (!urlOverridden) {
          programmaticIdentity = true;
          const prefix = webhookPrefix(url.dataset.b2mWebhookSeed || url.value);
          if (prefix) {
            url.value = prefix + encodeURIComponent(id.value);
            dispatch(url);
          }
          programmaticIdentity = false;
        }
      });
    }

    url.addEventListener('input', function () {
      if (!programmaticIdentity) urlOverridden = true;
    });
  }

  function install() {
    // Order is deliberate: base layout first, then the visual builder, then move
    // low-level protocol fields into the already-hidden Advanced card.
    polishStats();
    setupAdvancedMode();
    setupHaGenerator();
    addHelp();
    buildBuilder();
    moveProtocolFieldsToAdvanced();
    setupIdentity();
    setupTimerHelpers();
    setupActionTest();

    const payload = parseObject($('action-payload-json'));
    exampleActive = Object.prototype.hasOwnProperty.call(payload, 'action_name');
    activePreset = Object.prototype.hasOwnProperty.call(PRESETS, payload.kind) ? payload.kind : null;
    document.querySelectorAll('.b2m-action-preset').forEach((button) => {
      button.classList.toggle('active', button.dataset.preset === activePreset);
    });
    if (exampleActive) syncPayloadIdentity();
    updateHaYaml();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install, {once: true});
  } else {
    install();
  }
})();
