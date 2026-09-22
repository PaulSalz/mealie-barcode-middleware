(function () {
  'use strict';

  if (!(window.location.pathname === '/actions/new' || /^\/actions\/[^/]+$/.test(window.location.pathname))) return;
  if (window.__b2mActionV23Loaded) return;
  window.__b2mActionV23Loaded = true;

  const $ = (id) => document.getElementById(id);
  const isNew = window.location.pathname === '/actions/new';
  let selectedPreset = '';
  let idManual = false;
  let urlManual = false;
  let noticeTimer = null;
  let initialWebhook = '';

  function transliterate(value) {
    return String(value || '')
      .replace(/Ä/g,'Ae').replace(/Ö/g,'Oe').replace(/Ü/g,'Ue')
      .replace(/ä/g,'ae').replace(/ö/g,'oe').replace(/ü/g,'ue').replace(/ß/g,'ss')
      .normalize('NFKD').replace(/[\u0300-\u036f]/g,'');
  }

  function actionSlug(name) {
    let value = transliterate(name).toLowerCase().trim()
      .replace(/[^a-z0-9._-]+/g,'_').replace(/_+/g,'_').replace(/^[_-]+|[_-]+$/g,'');
    if (!value) return '';
    if (!value.startsWith('action_')) value = 'action_' + value;
    return value.slice(0, 96);
  }

  function idInput() { return document.querySelector('input[name="action_id"]'); }
  function nameInput() { return document.querySelector('input[name="name"]'); }
  function urlInput() { return document.querySelector('input[name="webhook_url"]'); }
  function typeInput() { return document.querySelector('[name="action_type"]'); }
  function methodInput() { return document.querySelector('[name="method"]'); }
  function executionInput() { return document.querySelector('[name="execution_mode"]'); }

  function currentId() {
    const input = idInput();
    if (input && input.value.trim()) return input.value.trim();
    const disabled = Array.from(document.querySelectorAll('input[disabled]')).find((node) => /^action[_a-z0-9.-]+$/i.test(node.value || ''));
    if (disabled && disabled.value) return disabled.value.trim();
    const match = window.location.pathname.match(/^\/actions\/([^/]+)$/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function webhookPrefix(seed) {
    seed = String(seed || '').trim();
    const match = seed.match(/^(.*\/api\/webhook\/)[^/?#]*/i);
    if (match) return match[1];
    if (/^https?:\/\//i.test(seed)) return seed.replace(/\/+$/,'') + '/api/webhook/';
    return 'http://homeassistant.local:8123/api/webhook/';
  }

  function generatedWebhook(id) {
    return webhookPrefix(initialWebhook) + encodeURIComponent(id || 'action_name');
  }

  function parsePayload() {
    const textarea = $('action-payload-json');
    try {
      const value = JSON.parse((textarea && textarea.value) || '{}');
      return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    } catch (e) { return {}; }
  }

  function writePayload(payload) {
    const textarea = $('action-payload-json');
    if (!textarea) return;
    textarea.value = JSON.stringify(payload, null, 2);
    textarea.dispatchEvent(new Event('change', {bubbles:true}));
    textarea.dispatchEvent(new Event('input', {bubbles:true}));
  }

  function currentName() {
    const input = nameInput();
    return input && input.value.trim() ? input.value.trim() : 'Barcode action';
  }

  function syncPayloadIdentity() {
    const payload = parsePayload();
    if (!Object.prototype.hasOwnProperty.call(payload, 'action_id')) return;
    payload.action_id = currentId();
    if (Object.prototype.hasOwnProperty.call(payload, 'action_name')) payload.action_name = currentName();
    writePayload(payload);
  }

  function presetPayload(name) {
    const payload = parsePayload();
    payload.action_id = currentId();
    payload.action_name = currentName();
    payload.barcode = payload.barcode || '{{ scan.barcode }}';
    if (name === 'light') {
      Object.assign(payload, {kind:'light', entity_id:payload.entity_id || 'light.kitchen', command:'turn_on', brightness_pct:Number(payload.brightness_pct || 70)});
    } else if (name === 'tts') {
      Object.assign(payload, {kind:'tts', tts_entity:payload.tts_entity || 'tts.google_translate_de_de', media_player:payload.media_player || 'media_player.kitchen', message:payload.message || 'Barcode {{ scan.barcode }} scanned', language:payload.language || 'de'});
    } else if (name === 'timer') {
      Object.assign(payload, {kind:'timer', timer:payload.timer || 'timer.kitchen', duration_seconds:payload.duration_seconds || '{{ params.duration_seconds }}'});
    } else if (name === 'automation') {
      Object.assign(payload, {kind:'automation', entity_id:payload.entity_id || 'automation.kitchen_mode', variables:payload.variables || {source:'b2m', barcode:'{{ scan.barcode }}'}});
    } else if (name === 'data') {
      Object.assign(payload, {kind:'data', value:payload.value || '{{ params.value }}', data:payload.data || {source:'barcode'}});
    }
    return payload;
  }

  function yamlQuote(value) { return String(value || '').replace(/'/g, "''"); }
  function webhookId(url) {
    try {
      const parsed = new URL(url, window.location.origin);
      const match = parsed.pathname.match(/\/api\/webhook\/([^/]+)/);
      return match ? decodeURIComponent(match[1]) : currentId() || 'YOUR_WEBHOOK_ID';
    } catch (e) { return currentId() || 'YOUR_WEBHOOK_ID'; }
  }

  function yamlActionBlock(kind) {
    if (kind === 'light') return [
      '  - action: light.turn_on',
      '    target:',
      '      entity_id: "{{ trigger.json.entity_id }}"',
      '    data:',
      '      brightness_pct: "{{ trigger.json.brightness_pct | default(70) | int }}"'
    ].join('\n');
    if (kind === 'tts') return [
      '  - action: tts.speak',
      '    target:',
      '      entity_id: "{{ trigger.json.tts_entity }}"',
      '    data:',
      '      media_player_entity_id: "{{ trigger.json.media_player }}"',
      '      message: "{{ trigger.json.message }}"',
      '      language: "{{ trigger.json.language | default(\'de\') }}"'
    ].join('\n');
    if (kind === 'timer') return [
      '  - action: timer.start',
      '    target:',
      '      entity_id: "{{ trigger.json.timer }}"',
      '    data:',
      '      duration: "{{ trigger.json.duration_seconds | default(600) | int }}"'
    ].join('\n');
    if (kind === 'automation') return [
      '  - action: automation.trigger',
      '    target:',
      '      entity_id: "{{ trigger.json.entity_id }}"',
      '    data:',
      '      skip_condition: false',
      '      variables: "{{ trigger.json.variables | default({}) }}"'
    ].join('\n');
    return [
      '  - event: b2m_action',
      '    event_data:',
      '      action_id: "{{ trigger.json.action_id | default(\'\') }}"',
      '      action_name: "{{ trigger.json.action_name | default(\'\') }}"',
      '      barcode: "{{ trigger.json.barcode | default(\'\') }}"',
      '      value: "{{ trigger.json.value | default(\'\') }}"'
    ].join('\n');
  }

  function updateHaYaml() {
    const area = $('action-ha-yaml');
    if (!area) return;
    const payload = parsePayload();
    const kind = selectedPreset || String(payload.kind || 'data');
    const url = urlInput();
    const id = currentId() || 'action_name';
    area.value = [
      "alias: 'B2M - " + yamlQuote(currentName()) + "'",
      "id: 'b2m_" + yamlQuote(id.replace(/[^A-Za-z0-9_-]/g,'_')) + "'",
      "description: 'Generated from the B2M " + yamlQuote(kind) + " action example.'",
      'triggers:',
      '  - trigger: webhook',
      "    webhook_id: '" + yamlQuote(webhookId(url ? url.value : '')) + "'",
      '    allowed_methods:',
      '      - POST',
      '    local_only: true',
      'conditions: []',
      'actions:',
      yamlActionBlock(kind),
      'mode: single',
      ''
    ].join('\n');
  }

  function syncAdvancedFields() {
    const toggle = $('action-advanced-toggle');
    if (!toggle) return;
    ['action_type','method','execution_mode'].forEach((name) => {
      const field = document.querySelector('[name="' + name + '"]');
      const col = field && field.closest('[class*="col-"]');
      if (col) {
        col.classList.add('action-v23-advanced-request');
        col.classList.toggle('d-none', !toggle.checked);
      }
    });
  }

  function improveBuilderHelp() {
    const help = {
      params: '<strong>Parameters are stored values for this Action.</strong> They are not sent by themselves. Reference them from the payload with <code>{{ params.key }}</code>. Use them for values you want to change later without reprinting the barcode, such as a timer duration or quantity.',
      payload: '<strong>Payload is the actual request data.</strong> B2M resolves templates such as <code>{{ scan.barcode }}</code> and <code>{{ params.duration_seconds }}</code> at scan time, then sends the resulting object as the HTTP body (or query parameters for GET).',
      headers: '<strong>Headers are HTTP metadata, not business data.</strong> Use them for content type, API/version hints or authorization required by the destination. Headers stay in B2M and are never encoded into the printed Action barcode.'
    };
    Object.keys(help).forEach((kind) => {
      const collapse = $('action-v22-' + kind + '-collapse');
      const hint = collapse && collapse.querySelector('.accordion-body > .form-hint');
      if (hint) hint.innerHTML = help[kind];
    });
  }

  function flashPresetNotice(preset) {
    const note = $('action-v22-preset-note');
    if (!note) return;
    clearTimeout(noticeTimer);
    const title = preset ? preset.charAt(0).toUpperCase() + preset.slice(1) : 'Example';
    note.innerHTML = '<strong>' + title + ' example loaded.</strong> Fields and Home Assistant YAML were updated.';
    note.classList.remove('d-none');
    noticeTimer = setTimeout(function () { note.classList.add('d-none'); }, 2200);
  }

  function installIdentityAutomation() {
    const name = nameInput(), id = idInput(), url = urlInput();
    if (!name || !url) return;
    initialWebhook = url.value.trim();

    if (isNew) {
      const type = typeInput(), method = methodInput(), execution = executionInput();
      if (type) type.value = 'homeassistant';
      if (method) method.value = 'POST';
      if (execution) execution.value = 'async';
    }

    function applyFromName() {
      if (!isNew || !id || idManual) return;
      const generated = actionSlug(name.value);
      id.dataset.autoValue = generated;
      id.value = generated;
      if (!urlManual) {
        url.dataset.autoValue = generatedWebhook(generated);
        url.value = url.dataset.autoValue;
      }
      syncPayloadIdentity();
      updateHaYaml();
    }

    name.addEventListener('input', function () {
      applyFromName();
      syncPayloadIdentity();
      updateHaYaml();
    });

    if (id) {
      id.addEventListener('input', function () {
        if (this.value !== (this.dataset.autoValue || '')) idManual = true;
        if (!urlManual) {
          url.dataset.autoValue = generatedWebhook(this.value.trim());
          url.value = url.dataset.autoValue;
        }
        syncPayloadIdentity();
        updateHaYaml();
      });
    }
    url.addEventListener('input', function () {
      if (this.value !== (this.dataset.autoValue || '')) urlManual = true;
      updateHaYaml();
    });

    if (isNew && name.value.trim()) applyFromName();
  }

  function installPresetHooks() {
    document.querySelectorAll('.b2m-action-preset').forEach((button) => {
      if (button.dataset.b2mV23 === '1') return;
      button.dataset.b2mV23 = '1';
      button.addEventListener('click', function () {
        selectedPreset = this.dataset.preset || '';
        setTimeout(function () {
          writePayload(presetPayload(selectedPreset));
          const type = typeInput(), method = methodInput();
          if (type && ['light','tts','timer','automation','data'].includes(selectedPreset)) type.value = 'homeassistant';
          if (method) method.value = 'POST';
          flashPresetNotice(selectedPreset);
          updateHaYaml();
        }, 0);
      });
    });
  }

  function inferPreset() {
    const kind = String(parsePayload().kind || '');
    if (['light','tts','timer','automation','data'].includes(kind)) selectedPreset = kind;
  }

  function install() {
    if (!$('action-v22-builder') || !$('action-advanced-toggle') || !$('action-ha-yaml')) {
      setTimeout(install, 80);
      return;
    }
    inferPreset();
    improveBuilderHelp();
    installIdentityAutomation();
    installPresetHooks();
    const toggle = $('action-advanced-toggle');
    toggle.addEventListener('change', syncAdvancedFields);
    syncAdvancedFields();
    [nameInput(), idInput(), urlInput(), $('action-payload-json')].filter(Boolean).forEach((field) => {
      field.addEventListener('change', function () { setTimeout(updateHaYaml, 0); });
    });
    updateHaYaml();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(install, 0); }, {once:true});
  else setTimeout(install, 0);
})();
