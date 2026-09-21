(function () {
  'use strict';

  var APP_VERSION = '2026.09.21.2';
  var FONT_STORAGE_KEY = 'b2m-font-size-percent-v3';

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  function applyFontSize(value) {
    var size = Math.max(80, Math.min(120, Number(value) || 100));
    document.documentElement.style.fontSize = size + '%';
    try { localStorage.setItem(FONT_STORAGE_KEY, String(size)); } catch (e) {}
    return size;
  }

  try {
    var cachedFontSize = localStorage.getItem(FONT_STORAGE_KEY);
    if (cachedFontSize) applyFontSize(cachedFontSize);
  } catch (e) {}

  async function json(url, options) {
    var response = await fetch(url, Object.assign({headers: {'Accept': 'application/json'}}, options || {}));
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    return data;
  }

  function updateVersion(version) {
    version = version || APP_VERSION;
    document.documentElement.dataset.appVersion = version;
    if (window.location.pathname !== '/') return;
    var title = document.querySelector('.page-header .page-title');
    if (!title) return;
    var badge = title.querySelector('.text-secondary.small.fw-normal');
    if (badge) badge.textContent = 'v' + version;
  }

  function initBell() {
    var link = document.querySelector('#notif-dropdown > a');
    var badge = document.getElementById('notif-badge');
    if (!link || !badge) return;

    if (!link.querySelector('.b2m-bell-active-icon')) {
      var filled = document.createElement('span');
      filled.className = 'b2m-bell-active-icon';
      filled.setAttribute('aria-hidden', 'true');
      filled.innerHTML = '<svg viewBox="0 0 24 24" focusable="false"><path fill="currentColor" d="M12 2a5 5 0 0 0-5 5v2.6c0 1.8-.62 3.52-1.76 4.9L4 16v2h16v-2l-1.24-1.5A7.7 7.7 0 0 1 17 9.6V7a5 5 0 0 0-5-5Zm-2.4 18a2.5 2.5 0 0 0 4.8 0H9.6Z"/></svg>';
      link.insertBefore(filled, link.firstChild);
    }

    function sync() {
      var active = !badge.classList.contains('d-none') || !!document.querySelector('#notif-dropdown .b2m-scan-received-bell');
      link.classList.toggle('b2m-bell-unread', active);
    }

    new MutationObserver(sync).observe(badge, {attributes: true, attributeFilter: ['class']});
    var list = document.getElementById('notif-list');
    if (list) new MutationObserver(sync).observe(list, {childList: true, subtree: true});
    sync();
  }

  function settingsTab() {
    return new URLSearchParams(window.location.search).get('tab') || 'mealie';
  }

  function installPrinterNav() {
    if (window.location.pathname !== '/settings') return;
    var sidebar = document.querySelector('.col-12.col-md-3 .card-body');
    if (!sidebar || sidebar.querySelector('a[href="/settings?tab=printer"]')) return;
    var groups = Array.from(sidebar.querySelectorAll('h4.subheader'));
    var heading = groups.find(function (node) { return node.textContent.trim() === 'Configuration'; });
    if (!heading) return;
    var list = heading.nextElementSibling;
    if (!list || !list.classList.contains('list-group')) return;
    var link = document.createElement('a');
    link.href = '/settings?tab=printer';
    link.className = 'list-group-item list-group-item-action d-flex align-items-center' + (settingsTab() === 'printer' ? ' active' : '');
    link.innerHTML = '<span class="me-2"><i class="ti ti-printer icon"></i></span>Printer';
    list.appendChild(link);
  }

  function removePrinterFromSystem() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'system') return;
    var right = document.querySelector('.col-12.col-md-9');
    if (!right) return;
    function remove() {
      var card = document.getElementById('b2m-printer-settings-card');
      if (card) card.remove();
    }
    remove();
    new MutationObserver(remove).observe(right, {childList: true, subtree: true});
  }

  function initPrinterPage() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'printer') return;
    var body = document.querySelector('.col-12.col-md-9 form[action="/settings/configuration"] > .card-body');
    if (!body) return;
    body.querySelectorAll('.empty').forEach(function (node) { node.remove(); });
    if (document.getElementById('b2m-printer-settings-card')) return;

    var card = document.createElement('div');
    card.className = 'card mt-3';
    card.id = 'b2m-printer-settings-card';
    card.innerHTML =
      '<div class="card-header"><div><h3 class="card-title">B21 Pro printer</h3><p class="card-subtitle">Connection, detected hardware and print statistics.</p></div>' +
      '<div class="card-actions"><button class="btn btn-outline-primary" id="b2m-settings-printer-connect" type="button"><i class="ti ti-bluetooth icon"></i> Connect</button></div></div>' +
      '<div class="card-body"><div class="row row-cards" id="b2m-printer-stats"><div class="col-12 text-secondary">Loading printer…</div></div>' +
      '<div class="datagrid mt-3" id="b2m-printer-data"></div><div class="form-hint text-danger mt-2" id="b2m-printer-error"></div></div>';
    body.appendChild(card);

    var connect = document.getElementById('b2m-settings-printer-connect');
    var error = document.getElementById('b2m-printer-error');

    async function refresh() {
      try {
        var data = await json('/labels/b21/stats');
        var status = data.status || {};
        var info = status.info || {};
        var meta = info.modelMetadata || {};
        var printer = info.printerInfo || {};
        var stats = [
          ['printer', 'blue', status.connected ? 'Connected' : 'Disconnected', 'Printer'],
          ['tag', 'green', data.labels || 0, 'Labels printed'],
          ['briefcase', 'azure', data.jobs || 0, 'Print jobs'],
          ['alert-triangle', 'red', data.failed || 0, 'Failed jobs']
        ];
        document.getElementById('b2m-printer-stats').innerHTML = stats.map(function (row) {
          return '<div class="col-sm-6 col-lg-3"><div class="card card-sm b2m-settings-stat"><div class="card-body"><div class="row align-items-center"><div class="col-auto"><span class="avatar bg-' + row[1] + '-lt text-' + row[1] + '"><i class="ti ti-' + row[0] + '"></i></span></div><div class="col"><div class="font-weight-medium">' + esc(row[2]) + '</div><div class="text-secondary">' + esc(row[3]) + '</div></div></div></div></div></div>';
        }).join('');

        var rows = [
          ['Model', meta.model || 'B21 Pro'],
          ['Serial', printer.serial || '—'],
          ['Address', status.address || printer.mac || '—'],
          ['Transport', status.transport || '—'],
          ['DPI', meta.dpi || status.dpi || '—'],
          ['Print task', info.detectedPrintTask || status.detected_print_task || status.print_task || '—'],
          ['Firmware', printer.softwareVersion || '—'],
          ['Hardware', printer.hardwareVersion || '—'],
          ['Charge', printer.charge != null ? printer.charge : '—'],
          ['Active jobs', data.active_jobs || 0],
          ['Last print', data.last_print_at || '—']
        ];
        document.getElementById('b2m-printer-data').innerHTML = rows.map(function (row) {
          return '<div class="datagrid-item"><div class="datagrid-title">' + esc(row[0]) + '</div><div class="datagrid-content">' + esc(row[1]) + '</div></div>';
        }).join('');
        error.textContent = data.last_error || status.error || '';
        connect.dataset.connected = status.connected ? '1' : '0';
        connect.className = 'btn ' + (status.connected ? 'btn-outline-danger' : 'btn-outline-primary');
        connect.innerHTML = '<i class="ti ti-' + (status.connected ? 'bluetooth-off' : 'bluetooth') + ' icon"></i> ' + (status.connected ? 'Disconnect' : 'Connect');
      } catch (e) {
        error.textContent = e.message;
      }
    }

    connect.addEventListener('click', async function () {
      connect.disabled = true;
      error.textContent = '';
      try {
        await json(connect.dataset.connected === '1' ? '/labels/b21/disconnect' : '/labels/b21/connect', {method: 'POST'});
      } catch (e) {
        error.textContent = e.message;
      } finally {
        connect.disabled = false;
        refresh();
      }
    });

    refresh();
    window.setInterval(refresh, 5000);
  }

  function initAppearance(preferences) {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'appearance') return;
    var form = document.querySelector('form[action="/settings/theme"]');
    if (!form) return;
    var body = form.querySelector('.card-body');
    if (!body) return;

    function removeLegacyDateControls() {
      body.querySelectorAll('#b2m-date-style').forEach(function (node) { node.remove(); });
    }
    removeLegacyDateControls();
    new MutationObserver(removeLegacyDateControls).observe(body, {childList: true, subtree: true});

    if (document.getElementById('b2m-appearance-v3-top')) return;
    var top = document.createElement('section');
    top.id = 'b2m-appearance-v3-top';
    top.innerHTML =
      '<h3 class="card-title">Date format</h3><p class="card-subtitle">Format used for full timestamps throughout the interface.</p>' +
      '<div class="form-selectgroup mb-4" id="b2m-date-format-v3">' +
        '<label class="form-selectgroup-item"><input class="form-selectgroup-input" type="radio" name="theme_date_style" value="short"><span class="form-selectgroup-label">21.09.26 04:26</span></label>' +
        '<label class="form-selectgroup-item"><input class="form-selectgroup-input" type="radio" name="theme_date_style" value="medium"><span class="form-selectgroup-label">21.09.2026 04:26</span></label>' +
        '<label class="form-selectgroup-item"><input class="form-selectgroup-input" type="radio" name="theme_date_style" value="long"><span class="form-selectgroup-label">21. September 2026, 04:26</span></label>' +
      '</div>' +
      '<h3 class="card-title">Font size</h3><p class="card-subtitle">Scale the complete interface. OpenDyslexic usually reads best around 90–95% if the default feels too large.</p>' +
      '<div class="row g-3 align-items-center mb-4"><div class="col"><input class="form-range" id="b2m-font-size-v3" type="range" min="80" max="120" step="1"></div><div class="col-auto"><strong class="b2m-font-size-value" id="b2m-font-size-value-v3">100%</strong></div></div>' +
      '<div class="form-hint" id="b2m-ui-pref-status"></div>';

    var firstHeading = body.querySelector('h3.card-title');
    if (firstHeading) firstHeading.insertAdjacentElement('beforebegin', top);
    else body.appendChild(top);

    var dateStyle = (preferences && preferences.date_style) || 'medium';
    var dateRadio = top.querySelector('input[name="theme_date_style"][value="' + dateStyle + '"]');
    if (dateRadio) dateRadio.checked = true;
    var fontSize = applyFontSize((preferences && preferences.font_size) || 100);
    var fontRange = document.getElementById('b2m-font-size-v3');
    var fontValue = document.getElementById('b2m-font-size-value-v3');
    var status = document.getElementById('b2m-ui-pref-status');
    fontRange.value = fontSize;
    fontValue.textContent = fontSize + '%';

    async function save(payload) {
      status.className = 'form-hint text-secondary';
      status.textContent = 'Saving…';
      try {
        var result = await json('/api/ui-preferences-v3', {
          method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
        });
        if (result.font_size) applyFontSize(result.font_size);
        status.className = 'form-hint text-success';
        status.textContent = 'Saved.';
      } catch (e) {
        status.className = 'form-hint text-danger';
        status.textContent = e.message;
      }
    }

    top.querySelectorAll('input[name="theme_date_style"]').forEach(function (radio) {
      radio.addEventListener('change', function () {
        if (radio.checked) save({date_style: radio.value});
      });
    });
    fontRange.addEventListener('input', function () {
      var value = applyFontSize(fontRange.value);
      fontValue.textContent = value + '%';
      status.className = 'form-hint text-secondary';
      status.textContent = 'Preview · release the slider to save.';
    });
    fontRange.addEventListener('change', function () {
      save({font_size: Number(fontRange.value)});
    });
    fontRange.addEventListener('dblclick', function () {
      fontRange.value = 100;
      fontRange.dispatchEvent(new Event('input', {bubbles: true}));
      fontRange.dispatchEvent(new Event('change', {bubbles: true}));
    });
  }

  function relocateFrameControls() {
    if (window.location.pathname !== '/labels') return;
    var tries = 0;
    var timer = window.setInterval(function () {
      tries += 1;
      var frame = document.getElementById('b21-v2-frame');
      if (!frame) {
        if (tries > 60) window.clearInterval(timer);
        return;
      }
      var calibration = frame.closest('.b21-section');
      var row = frame.closest('.row');
      if (!calibration || !row) return;
      if (!document.getElementById('b21-v3-label-output')) {
        var section = document.createElement('div');
        section.id = 'b21-v3-label-output';
        section.className = 'b21-section';
        section.innerHTML = '<div class="fw-semibold mb-2">Label appearance</div>';
        calibration.parentNode.insertBefore(section, calibration);
        section.appendChild(row);
      }
      var heading = calibration.querySelector('.fw-semibold');
      if (heading) heading.textContent = 'Calibration';
      window.clearInterval(timer);
    }, 150);
  }

  async function init() {
    updateVersion(APP_VERSION);
    initBell();
    installPrinterNav();
    removePrinterFromSystem();
    initPrinterPage();
    relocateFrameControls();

    var preferences = null;
    try {
      preferences = await json('/api/ui-preferences-v3');
      if (preferences.font_size) applyFontSize(preferences.font_size);
      updateVersion(preferences.version || APP_VERSION);
    } catch (e) {}
    initAppearance(preferences || {font_size: 100, date_style: 'medium'});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
