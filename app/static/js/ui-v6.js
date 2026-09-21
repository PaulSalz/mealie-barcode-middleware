(function () {
  'use strict';
  if (window.__b2mUiV6Loaded) return;
  window.__b2mUiV6Loaded = true;

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');

  async function fetchJson(url, options) {
    const response = await fetch(url, Object.assign({headers: {Accept: 'application/json'}}, options || {}));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || data.error || ('HTTP ' + response.status));
    return data;
  }

  function settingsTab() {
    return new URLSearchParams(window.location.search).get('tab') || 'mealie';
  }

  async function syncVersionOnce() {
    try {
      const data = await fetchJson('/api/version', {cache: 'no-store'});
      if (!data.version) return;
      document.querySelectorAll('span').forEach((span) => {
        if (/^v20\d\d\./.test(span.textContent.trim())) span.textContent = 'v' + data.version;
      });
    } catch (e) {}
  }

  function installBellPulse() {
    const link = document.querySelector('#notif-dropdown > a');
    if (!link) return;
    let timer = null;
    window.addEventListener('b2m:scan', () => {
      clearTimeout(timer);
      link.classList.remove('b2m-v6-bell-pulse');
      void link.offsetWidth;
      link.classList.add('b2m-v6-bell-pulse');
      timer = setTimeout(() => link.classList.remove('b2m-v6-bell-pulse'), 500);
    });
  }

  function installScannerLinks() {
    if (window.location.pathname === '/') {
      document.querySelectorAll('a[href="/settings?tab=tokens"]').forEach((link) => {
        if (link.textContent.includes('Scanners')) link.href = '/settings?tab=scanning';
      });
    }
    const desktopSettings = document.querySelector('.dropdown-menu a[href="/settings"]');
    if (desktopSettings && !document.getElementById('b2m-v6-scanner-menu')) {
      const link = document.createElement('a');
      link.id = 'b2m-v6-scanner-menu';
      link.className = 'dropdown-item';
      link.href = '/settings?tab=scanning';
      link.innerHTML = '<i class="ti ti-scan icon dropdown-item-icon"></i> Scanner';
      desktopSettings.insertAdjacentElement('beforebegin', link);
    }
    const mobileSettings = document.querySelector('#navbar-menu a[href="/settings"]');
    if (mobileSettings && !document.getElementById('b2m-v6-scanner-mobile')) {
      const li = document.createElement('li');
      li.id = 'b2m-v6-scanner-mobile';
      li.className = 'nav-item d-md-none';
      li.innerHTML = '<a class="nav-link" href="/settings?tab=scanning"><span class="nav-link-icon d-md-none d-lg-inline-block"><i class="ti ti-scan icon icon-1"></i></span><span class="nav-link-title">Scanner</span></a>';
      mobileSettings.closest('li')?.insertAdjacentElement('beforebegin', li);
    }
  }

  function printerInfoHtml(data) {
    const status = data.status || {};
    const info = status.info || {};
    const pi = info.printerInfo || {};
    const meta = info.modelMetadata || {};
    const rows = [
      ['Model', meta.model || info.model || 'B21 Pro'], ['State', status.connected ? 'Connected' : 'Disconnected'],
      ['Serial', pi.serial || info.serial || '—'], ['Address', status.address || pi.mac || info.mac || '—'],
      ['DPI', meta.dpi || status.dpi || '—'], ['Print task', info.detectedPrintTask || status.detected_print_task || status.print_task || '—'],
      ['Firmware', pi.softwareVersion || info.softwareVersion || '—'], ['Hardware', pi.hardwareVersion || info.hardwareVersion || '—'],
      ['Charge', pi.charge == null ? '—' : pi.charge], ['Printed labels', data.labels || 0], ['Jobs', data.jobs || 0],
      ['Failed jobs', data.failed || 0], ['Active jobs', data.active_jobs || 0],
    ];
    return rows.map((row) => '<div class="datagrid-item"><div class="datagrid-title">' + esc(row[0]) + '</div><div class="datagrid-content">' + esc(row[1]) + '</div></div>').join('');
  }

  function installPrinterPanel() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'printing') return;
    const form = document.querySelector('form[action="/settings/configuration"]');
    const body = form && form.querySelector(':scope > .card-body');
    if (!body) return;
    document.getElementById('b2m-printer-runtime-v4')?.remove();
    if (document.getElementById('b2m-printer-runtime-v6')) return;
    const card = document.createElement('div');
    card.id = 'b2m-printer-runtime-v6';
    card.className = 'card mb-3';
    card.innerHTML = '<div class="card-header"><div><h3 class="card-title">Printer status</h3><p class="card-subtitle">Manual connection and current NIIMBOT/niimblue-node statistics.</p></div><div class="card-actions d-flex gap-2 align-items-center"><span id="v6-printer-state" class="badge bg-secondary-lt">Loading…</span><button id="v6-printer-refresh" class="btn btn-outline-secondary btn-sm" type="button"><i class="ti ti-refresh icon"></i> Refresh</button><button id="v6-printer-connect" class="btn btn-outline-primary btn-sm" type="button"><i class="ti ti-bluetooth icon"></i> Connect</button></div></div><div class="card-body"><div class="datagrid" id="v6-printer-datagrid"></div><div id="v6-printer-error" class="form-hint mt-2"></div></div>';
    body.prepend(card);
    async function refresh() {
      const state = $('v6-printer-state'), button = $('v6-printer-connect'), error = $('v6-printer-error');
      try {
        const data = await fetchJson('/labels/b21/stats', {cache: 'no-store'});
        const connected = !!(data.status && data.status.connected);
        state.className = 'badge ' + (connected ? 'bg-green text-green-fg' : 'bg-red-lt text-red');
        state.textContent = connected ? 'Connected' : 'Not connected';
        button.dataset.connected = connected ? '1' : '0';
        button.className = 'btn btn-sm ' + (connected ? 'btn-outline-danger' : 'btn-outline-primary');
        button.innerHTML = connected ? '<i class="ti ti-bluetooth-off icon"></i> Disconnect' : '<i class="ti ti-bluetooth icon"></i> Connect';
        $('v6-printer-datagrid').innerHTML = printerInfoHtml(data);
        error.textContent = data.last_error || '';
        error.className = 'form-hint mt-2' + (data.last_error ? ' text-danger' : '');
      } catch (err) { error.className = 'form-hint mt-2 text-danger'; error.textContent = err.message; }
    }
    $('v6-printer-refresh').addEventListener('click', refresh);
    $('v6-printer-connect').addEventListener('click', async function () {
      const button = this, error = $('v6-printer-error'); button.disabled = true; error.textContent = '';
      try { await fetchJson(button.dataset.connected === '1' ? '/labels/b21/disconnect' : '/labels/b21/connect', {method: 'POST'}); }
      catch (err) { error.className = 'form-hint mt-2 text-danger'; error.textContent = err.message; }
      finally { button.disabled = false; await refresh(); }
    });
    refresh();
  }

  async function refreshDashboardDateTitles() {
    if (window.location.pathname !== '/') return;
    const tbody = $('recent-scans-body'); if (!tbody) return;
    try {
      const data = await fetchJson('/api/dashboard', {cache: 'no-store'});
      const rows = Array.from(tbody.querySelectorAll('tr'));
      (data.recent_items || []).forEach((item, index) => {
        const cell = rows[index] && rows[index].lastElementChild;
        if (cell && item.created_at_absolute) cell.title = item.created_at_absolute;
      });
    } catch (e) {}
  }

  function installDateRefresh() {
    refreshDashboardDateTitles();
    window.addEventListener('pageshow', refreshDashboardDateTitles);
    window.addEventListener('b2m:scan', () => setTimeout(refreshDashboardDateTitles, 650));
  }

  function init() {
    syncVersionOnce(); installBellPulse(); installScannerLinks(); installPrinterPanel(); installDateRefresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
