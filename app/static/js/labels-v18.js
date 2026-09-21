(function () {
  'use strict';

  if (window.location.pathname !== '/labels') return;
  if (window.__b2mLabelsV18Loaded) return;
  window.__b2mLabelsV18Loaded = true;

  const QUEUE_KEY = 'b2m-label-generator-v2';
  const ENTRY_KEY = 'b2m-b21-entry-settings-v3';
  const PROFILE_KEY = 'b2m-b21-profile-v1';
  const $ = (id) => document.getElementById(id);

  let serverCalibrations = {};
  let hydratingCalibration = false;
  let calibrationSaveTimer = null;
  let registerTimer = null;
  let profileRestoreToken = 0;

  function loadJson(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || '') || fallback; }
    catch (e) { return fallback; }
  }

  function saveJson(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, Object.assign({headers: {'Accept': 'application/json'}}, options || {}));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    return data;
  }

  function queueRows() {
    const state = loadJson(QUEUE_KEY, {});
    return Array.isArray(state.queue) ? state.queue : [];
  }

  function selectedProfileId() {
    const select = $('b21-profile-select');
    return String((select && select.value) || localStorage.getItem(PROFILE_KEY) || '50x30');
  }

  function calibrationFor(profileId) {
    const row = serverCalibrations[String(profileId)] || {};
    return {
      xMm: Number(row.xMm || row.x_mm || 0),
      yMm: Number(row.yMm || row.y_mm || 0)
    };
  }

  function applyCalibration(profileId) {
    const x = $('b21-v2-cal-x');
    const y = $('b21-v2-cal-y');
    if (!x || !y) return;
    const cal = calibrationFor(profileId);
    hydratingCalibration = true;
    try {
      x.value = String(cal.xMm);
      y.value = String(cal.yMm);
      x.dispatchEvent(new Event('input', {bubbles: true}));
      y.dispatchEvent(new Event('input', {bubbles: true}));
    } finally {
      hydratingCalibration = false;
    }
  }

  async function loadServerCalibration() {
    try {
      const data = await fetchJson('/labels/b21/calibration', {cache: 'no-store'});
      serverCalibrations = data.calibrations || {};
      applyCalibration(selectedProfileId());
    } catch (e) {
      console.warn('Could not load server calibration', e);
    }
  }

  function persistCalibrationSoon() {
    if (hydratingCalibration) return;
    clearTimeout(calibrationSaveTimer);
    calibrationSaveTimer = setTimeout(async function () {
      const profileId = selectedProfileId();
      const x = Number(($('b21-v2-cal-x') || {}).value || 0);
      const y = Number(($('b21-v2-cal-y') || {}).value || 0);
      serverCalibrations[profileId] = {xMm: x, yMm: y};
      try {
        await fetchJson('/labels/b21/calibration', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
          body: JSON.stringify({profile_id: profileId, x_mm: x, y_mm: y})
        });
      } catch (e) {
        console.warn('Could not save server calibration', e);
      }
    }, 180);
  }

  function installCalibrationPersistence() {
    const x = $('b21-v2-cal-x');
    const y = $('b21-v2-cal-y');
    const profile = $('b21-profile-select');
    if (!x || !y || !profile || x.dataset.b2mV18Calibration === '1') return false;
    x.dataset.b2mV18Calibration = '1';
    x.addEventListener('input', persistCalibrationSoon);
    y.addEventListener('input', persistCalibrationSoon);
    profile.addEventListener('change', function () {
      setTimeout(function () { applyCalibration(profile.value); }, 0);
    });
    loadServerCalibration();
    return true;
  }

  function currentEntryState() {
    const queue = queueRows();
    const index = Number(($('b21-entry-select') || {}).value || 0);
    const entry = queue[index] || queue[0];
    if (!entry) return null;
    const key = String(entry._id != null ? entry._id : (entry.code || 'entry-' + index));
    const states = loadJson(ENTRY_KEY, {});
    return {states: states, key: key, state: states[key], entry: entry, index: index};
  }

  function selectedElementState() {
    const data = currentEntryState();
    const select = $('b21-v2-element-select');
    if (!data || !data.state || !Array.isArray(data.state.elements) || !select) return null;
    const element = data.state.elements.find((row) => String(row.id) === String(select.value));
    return element ? Object.assign(data, {element: element}) : null;
  }

  function applyTextAlignment() {
    const data = currentEntryState();
    if (!data || !data.state || !Array.isArray(data.state.elements)) return;
    data.state.elements.forEach(function (element) {
      const node = document.querySelector('#b21-label-stage [data-element-id="' + CSS.escape(String(element.id)) + '"]');
      if (!node || element.type !== 'text') return;
      const centered = element.textAlign === 'center';
      node.classList.toggle('b21-v18-text-centered', centered);
      if (centered) {
        node.style.display = 'flex';
        node.style.alignItems = 'center';
        node.style.justifyContent = 'center';
        node.style.textAlign = 'center';
      }
    });
    const button = $('b21-v18-text-center');
    const selected = selectedElementState();
    if (button) {
      button.disabled = !selected || selected.element.type !== 'text';
      button.classList.toggle('active', !!(selected && selected.element.textAlign === 'center'));
    }
  }

  function centerSelectedText() {
    const data = selectedElementState();
    if (!data || data.element.type !== 'text') return;
    data.element.textAlign = 'center';
    data.states[data.key] = data.state;
    saveJson(ENTRY_KEY, data.states);
    applyTextAlignment();
  }

  function installTextCenterControl() {
    const row = $('b21-v2-align');
    if (!row || $('b21-v18-text-center')) return false;
    const button = document.createElement('button');
    button.id = 'b21-v18-text-center';
    button.type = 'button';
    button.className = 'btn btn-outline-secondary';
    button.title = 'Center text inside field';
    button.setAttribute('aria-label', 'Center text inside field');
    button.innerHTML = '<i class="ti ti-align-center"></i>';
    button.addEventListener('click', function (event) {
      event.preventDefault();
      centerSelectedText();
    });
    row.appendChild(button);
    const select = $('b21-v2-element-select');
    if (select) select.addEventListener('change', function () { setTimeout(applyTextAlignment, 0); });
    const stage = $('b21-label-stage');
    if (stage) new MutationObserver(function () { applyTextAlignment(); }).observe(stage, {childList: true, subtree: true});
    applyTextAlignment();
    return true;
  }

  function referenceHref(entry) {
    const id = String(entry && entry.target_id || '').trim();
    if (!id) return '';
    if (entry.target_type === 'food') return '/items/' + encodeURIComponent(id);
    if (entry.target_type === 'recipe') return '/recipes/' + encodeURIComponent(id);
    if (entry.target_type === 'action') return '/actions/' + encodeURIComponent(id);
    return '';
  }

  function referenceLabel(entry) {
    if (entry.target_type === 'food') return 'Open Food';
    if (entry.target_type === 'recipe') return 'Open Recipe';
    if (entry.target_type === 'action') return 'Open Action';
    return 'Open target';
  }

  function decorateQueueReferences() {
    const root = $('label-queue');
    if (!root) return;
    const rows = queueRows();
    const cards = Array.from(root.querySelectorAll('.label-card'));
    cards.forEach(function (card, index) {
      const entry = rows[index];
      const href = referenceHref(entry);
      const existing = card.querySelector('.b21-v18-reference-link');
      if (!href) {
        if (existing) existing.remove();
        return;
      }
      const codeInput = card.querySelector('.entry-code');
      const wrap = codeInput && codeInput.closest('.col-md-6');
      if (!wrap) return;
      let link = existing;
      if (!link) {
        link = document.createElement('a');
        link.className = 'form-hint mt-1 d-inline-flex align-items-center gap-1 b21-v18-reference-link';
        link.innerHTML = '<i class="ti ti-external-link"></i><span></span>';
        wrap.appendChild(link);
      }
      link.href = href;
      link.querySelector('span').textContent = referenceLabel(entry);
    });
  }

  async function registerQueueNow() {
    const rows = queueRows();
    if (!rows.length) return;
    try {
      await fetchJson('/labels/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: JSON.stringify({labels: rows.map(function (entry) {
          return {
            code: entry.code,
            label: entry.label,
            target_type: entry.target_type,
            target_id: entry.target_id,
            target_name: entry.target_name
          };
        })})
      });
    } catch (e) {
      console.warn('Could not pre-register label queue', e);
    }
  }

  function queueChanged() {
    decorateQueueReferences();
    clearTimeout(registerTimer);
    registerTimer = setTimeout(registerQueueNow, 250);
  }

  function restoreProfile(profileId, token) {
    if (token !== profileRestoreToken) return;
    const select = $('b21-profile-select');
    if (!select || !profileId || !Array.from(select.options).some((option) => option.value === profileId)) return;
    if (select.value === profileId) return;
    select.value = profileId;
    localStorage.setItem(PROFILE_KEY, profileId);
    select.dispatchEvent(new Event('change', {bubbles: true}));
  }

  function installProfileLock() {
    document.addEventListener('click', function (event) {
      const button = event.target && event.target.closest && event.target.closest('#b21-connect-button');
      if (!button) return;
      const isDisconnect = /disconnect/i.test(button.textContent || '');
      if (isDisconnect) return;
      const select = $('b21-profile-select');
      const profileId = select && select.value;
      if (!profileId) return;
      const token = ++profileRestoreToken;
      [250, 600, 1100, 1800].forEach(function (delay) {
        setTimeout(function () { restoreProfile(profileId, token); }, delay);
      });
    }, true);
    return true;
  }

  function installQueueObserver() {
    const root = $('label-queue');
    if (!root || root.dataset.b2mV18Observed === '1') return false;
    root.dataset.b2mV18Observed = '1';
    new MutationObserver(function () { queueChanged(); }).observe(root, {childList: true, subtree: true});
    queueChanged();
    return true;
  }

  function install() {
    const ready = $('label-queue') && $('b21-profile-select') && $('b21-layout-body');
    if (!ready) {
      setTimeout(install, 100);
      return;
    }
    installCalibrationPersistence();
    installTextCenterControl();
    installQueueObserver();
    installProfileLock();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install, {once: true});
  } else {
    install();
  }
})();
