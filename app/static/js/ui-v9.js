(function () {
  'use strict';
  if (window.__b2mUiV9Loaded) return;
  window.__b2mUiV9Loaded = true;

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');

  function settingsTab() {
    return new URLSearchParams(window.location.search).get('tab') || 'mealie';
  }

  async function json(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs || 12000);
    try {
      const response = await fetch(url, Object.assign({headers: {Accept: 'application/json'}, signal: controller.signal}, options || {}));
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || data.error || ('HTTP ' + response.status));
      return data;
    } catch (error) {
      if (error && error.name === 'AbortError') throw new Error('Request timed out');
      throw error;
    } finally {
      window.clearTimeout(timer);
    }
  }

  function normalizePrinterNav() {
    if (window.location.pathname !== '/settings') return;
    const tab = settingsTab();
    if (tab === 'printer') {
      window.location.replace('/settings?tab=printing');
      return;
    }
    const sidebar = document.querySelector('.col-12.col-md-3 .card-body');
    if (!sidebar) return;
    sidebar.querySelectorAll('a[href="/settings?tab=printing"],a[href="/settings?tab=printer"]').forEach((link) => link.remove());
    const heading = Array.from(sidebar.querySelectorAll('h4.subheader')).find((node) => node.textContent.trim() === 'Integrations');
    const list = heading && heading.nextElementSibling;
    if (!list || !list.classList.contains('list-group')) return;
    const link = document.createElement('a');
    link.href = '/settings?tab=printing';
    link.className = 'list-group-item list-group-item-action d-flex align-items-center' + (tab === 'printing' ? ' active' : '');
    link.innerHTML = '<span class="me-2"><i class="ti ti-printer icon"></i></span>Printer';
    list.appendChild(link);
  }

  function cleanupDuplicateDateControls() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'appearance') return;
    document.getElementById('b2m-v7-date-style')?.remove();
    const box = document.getElementById('b2m-v4-date-style');
    if (box) {
      const subtitle = box.previousElementSibling;
      const heading = subtitle && subtitle.previousElementSibling;
      box.remove();
      if (subtitle && subtitle.matches('p.card-subtitle') && /date|timestamp/i.test(subtitle.textContent)) subtitle.remove();
      if (heading && heading.matches('h3.card-title') && /date/i.test(heading.textContent)) heading.remove();
    }
  }

  function installBellBehavior() {
    const link = document.querySelector('#notif-dropdown > a');
    if (!link) return;
    let outline = link.querySelector('i.ti-bell');
    if (!outline) {
      outline = document.createElement('i');
      outline.className = 'ti ti-bell icon icon-1';
      link.insertBefore(outline, link.firstChild);
    }
    link.querySelectorAll('.b2m-v4-bell-filled,.b2m-bell-active-icon').forEach((node) => node.setAttribute('aria-hidden', 'true'));
    let timer = null;
    window.addEventListener('b2m:scan', () => {
      window.clearTimeout(timer);
      link.classList.remove('b2m-v9-bell-pulse');
      void link.offsetWidth;
      link.classList.add('b2m-v9-bell-pulse');
      timer = window.setTimeout(() => link.classList.remove('b2m-v9-bell-pulse'), 500);
    });
  }

  function setEpaperClass(enabled) {
    document.documentElement.classList.toggle('b2m-epaper-v9', !!enabled);
  }

  function installEpaperFix() {
    json('/api/theme', {cache: 'no-store'}, 5000).then((theme) => setEpaperClass(theme.epaper === 'true')).catch(() => {});
    document.addEventListener('change', (event) => {
      if (event.target && event.target.id === 'theme-epaper') setEpaperClass(event.target.checked);
    }, true);
  }

  function printerStatsHtml(data) {
    const status = data.status || {};
    const rows = [
      ['printer', status.connected ? 'green' : 'red', status.connected ? 'Connected' : 'Disconnected', 'Printer'],
      ['tag', 'green', Number(data.labels || 0), 'Labels printed'],
      ['briefcase', 'azure', Number(data.jobs || 0), 'Print jobs'],
      ['alert-triangle', Number(data.failed || 0) ? 'red' : 'secondary', Number(data.failed || 0), 'Failed jobs'],
    ];
    return rows.map((row) => '<div class="col-sm-6 col-xl-3"><div class="card card-sm"><div class="card-body"><div class="d-flex align-items-center gap-3"><span class="avatar bg-' + row[1] + '-lt text-' + row[1] + '"><i class="ti ti-' + row[0] + '"></i></span><div><div class="h3 mb-0">' + esc(row[2]) + '</div><div class="text-secondary small">' + esc(row[3]) + '</div></div></div></div></div></div>').join('');
  }

  function printerDataHtml(data) {
    const status = data.status || {};
    const info = status.info || {};
    const printer = info.printerInfo || {};
    const meta = info.modelMetadata || {};
    const rows = [
      ['Model', meta.model || info.model || 'B21 Pro'],
      ['Serial', printer.serial || info.serial || '—'],
      ['Address', status.address || printer.mac || info.mac || '—'],
      ['Transport', status.transport || '—'],
      ['DPI', meta.dpi || status.dpi || '—'],
      ['Print task', info.detectedPrintTask || status.detected_print_task || status.print_task || '—'],
      ['Firmware', printer.softwareVersion || info.softwareVersion || '—'],
      ['Hardware', printer.hardwareVersion || info.hardwareVersion || '—'],
      ['Charge (raw)', printer.charge == null ? '—' : printer.charge],
      ['Active jobs', data.active_jobs || 0],
      ['Last print', data.last_print_at || '—'],
    ];
    return rows.map((row) => '<div class="datagrid-item"><div class="datagrid-title">' + esc(row[0]) + '</div><div class="datagrid-content">' + esc(row[1]) + '</div></div>').join('');
  }

  function configFormHtml(config) {
    const c = config || {};
    const selected = (value, expected) => String(value || '') === expected ? ' selected' : '';
    return '<form id="v9-printer-config-form"><div class="row g-3">' +
      '<div class="col-12"><label class="form-label">niimblue-node URL</label><input class="form-control" name="url" value="' + esc(c.url || '') + '" placeholder="http://127.0.0.1:5000"></div>' +
      '<div class="col-md-4"><label class="form-label">Transport</label><select class="form-select" name="transport"><option value="ble"' + selected(c.transport, 'ble') + '>BLE</option><option value="serial"' + selected(c.transport, 'serial') + '>Serial</option></select></div>' +
      '<div class="col-md-8"><label class="form-label">Printer address</label><input class="form-control font-monospace" name="address" value="' + esc(c.address || '') + '"></div>' +
      '<div class="col-md-6"><label class="form-label">Print task</label><input class="form-control font-monospace" name="print_task" value="' + esc(c.print_task || 'D110M_V4') + '"></div>' +
      '<div class="col-md-6"><label class="form-label">Direction</label><select class="form-select" name="print_direction">' + ['top','left','right','bottom'].map((value) => '<option value="' + value + '"' + selected(c.print_direction, value) + '>' + value + '</option>').join('') + '</select></div>' +
      '<div class="col-md-3"><label class="form-label">Density</label><input class="form-control" type="number" min="1" max="5" name="density" value="' + esc(c.density || 3) + '"></div>' +
      '<div class="col-md-3"><label class="form-label">Label type</label><input class="form-control" type="number" min="1" name="label_type" value="' + esc(c.label_type || 1) + '"></div>' +
      '<div class="col-md-3"><label class="form-label">DPI</label><input class="form-control" type="number" min="100" name="dpi" value="' + esc(c.dpi || 300) + '"></div>' +
      '<div class="col-md-3"><label class="form-label">Max width (mm)</label><input class="form-control" type="number" min="1" step="0.1" name="max_label_width_mm" value="' + esc(c.max_label_width_mm || 50) + '"></div>' +
      '<div class="col-md-4"><label class="form-label">Timeout (s)</label><input class="form-control" type="number" min="1" step="0.1" name="timeout" value="' + esc(c.timeout || 30) + '"></div>' +
      '<div class="col-12 d-flex align-items-center justify-content-end gap-2"><span id="v9-printer-config-result" class="form-hint me-auto"></span><button class="btn btn-primary" type="submit"><i class="ti ti-device-floppy icon"></i> Save</button></div>' +
      '</div></form>';
  }

  async function renderPrinterPage() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'printing') return;
    const pane = document.querySelector('.col-12.col-md-9.d-flex.flex-column');
    if (!pane) return;
    pane.innerHTML = '<div class="card-body"><h2 class="mb-2">Printer</h2><p class="card-subtitle mb-4">Connection, print statistics and runtime configuration for niimblue-node and the NIIMBOT B21 Pro.</p>' +
      '<div class="card mb-3" id="v9-printer-runtime"><div class="card-header"><div><h3 class="card-title">Printer connection</h3><p class="card-subtitle">BLE connection is manual.</p></div><div class="card-actions d-flex align-items-center gap-2"><span class="badge bg-secondary-lt" id="v9-printer-state">Loading…</span><button class="btn btn-outline-secondary btn-sm" id="v9-printer-refresh" type="button"><i class="ti ti-refresh icon"></i> Refresh</button><button class="btn btn-outline-primary btn-sm" id="v9-printer-connect" type="button"><i class="ti ti-bluetooth icon"></i> Connect</button></div></div><div class="card-body"><div class="row row-cards mb-3" id="v9-printer-stats"></div><div class="datagrid" id="v9-printer-data"></div><div class="form-hint mt-3" id="v9-printer-error"></div></div></div>' +
      '<div class="card"><div class="card-header"><div><h3 class="card-title">Runtime configuration</h3><p class="card-subtitle">Changes apply to the next printer request without restarting B2M.</p></div></div><div class="card-body" id="v9-printer-config"><div class="text-secondary">Loading…</div></div></div></div>';

    let lastActionError = '';
    async function refreshStats(preserveError) {
      try {
        const data = await json('/labels/b21/stats', {cache: 'no-store'}, 8000);
        const status = data.status || {};
        const connected = !!status.connected;
        $('v9-printer-state').className = 'badge ' + (connected ? 'bg-green text-green-fg' : 'bg-red-lt text-red');
        $('v9-printer-state').textContent = connected ? 'Connected' : 'Not connected';
        $('v9-printer-stats').innerHTML = printerStatsHtml(data);
        $('v9-printer-data').innerHTML = printerDataHtml(data);
        const button = $('v9-printer-connect');
        button.dataset.connected = connected ? '1' : '0';
        button.className = 'btn btn-sm ' + (connected ? 'btn-outline-danger' : 'btn-outline-primary');
        button.innerHTML = connected ? '<i class="ti ti-bluetooth-off icon"></i> Disconnect' : '<i class="ti ti-bluetooth icon"></i> Connect';
        const message = lastActionError || data.last_error || status.error || '';
        const error = $('v9-printer-error');
        error.className = 'form-hint mt-3' + (message ? ' text-danger' : ' text-secondary');
        error.textContent = message || 'Printer service reachable.';
        if (!preserveError) lastActionError = '';
      } catch (error) {
        $('v9-printer-state').className = 'badge bg-red-lt text-red';
        $('v9-printer-state').textContent = 'Status failed';
        $('v9-printer-error').className = 'form-hint mt-3 text-danger';
        $('v9-printer-error').textContent = lastActionError || error.message;
      }
    }

    async function loadConfig() {
      try {
        const data = await json('/api/settings/niim', {cache: 'no-store'}, 8000);
        $('v9-printer-config').innerHTML = configFormHtml(data.config || {});
        $('v9-printer-config-form').addEventListener('submit', async (event) => {
          event.preventDefault();
          const result = $('v9-printer-config-result');
          const payload = {};
          new FormData(event.currentTarget).forEach((value, key) => { payload[key] = value; });
          result.className = 'form-hint me-auto text-secondary'; result.textContent = 'Saving…';
          try {
            await json('/api/settings/niim', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)}, 12000);
            result.className = 'form-hint me-auto text-success'; result.textContent = 'Saved.';
            await refreshStats(false);
          } catch (error) {
            result.className = 'form-hint me-auto text-danger'; result.textContent = error.message;
          }
        });
      } catch (error) {
        $('v9-printer-config').innerHTML = '<div class="alert alert-danger mb-0">' + esc(error.message) + '</div>';
      }
    }

    $('v9-printer-refresh').addEventListener('click', () => { lastActionError = ''; refreshStats(false); });
    $('v9-printer-connect').addEventListener('click', async function () {
      const button = this;
      const disconnecting = button.dataset.connected === '1';
      lastActionError = '';
      button.disabled = true;
      button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>' + (disconnecting ? 'Disconnecting…' : 'Connecting…');
      try {
        await json(disconnecting ? '/labels/b21/disconnect' : '/labels/b21/connect', {method: 'POST'}, 24000);
      } catch (error) {
        lastActionError = error.message;
      } finally {
        button.disabled = false;
        await refreshStats(!!lastActionError);
      }
    });

    await Promise.allSettled([refreshStats(false), loadConfig()]);
  }

  function init() {
    normalizePrinterNav();
    cleanupDuplicateDateControls();
    installBellBehavior();
    installEpaperFix();
    window.setTimeout(() => {
      normalizePrinterNav();
      cleanupDuplicateDateControls();
      renderPrinterPage();
    }, 80);
    [300, 800, 1600].forEach((delay) => window.setTimeout(() => {
      normalizePrinterNav();
      cleanupDuplicateDateControls();
    }, delay));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();