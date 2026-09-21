(function () {
  'use strict';
  if (window.__b2mUiV7Loaded) return;
  window.__b2mUiV7Loaded = true;

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

  async function fetchJsonTimeout(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs || 15000);
    try {
      return await fetchJson(url, Object.assign({}, options || {}, {signal: controller.signal}));
    } catch (error) {
      if (error && error.name === 'AbortError') throw new Error('Request timed out');
      throw error;
    } finally {
      clearTimeout(timer);
    }
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

  function installPrinterTabLink() {
    if (window.location.pathname !== '/settings') return;
    if (settingsTab() === 'printer') {
      window.location.replace('/settings?tab=printing');
      return;
    }
    if (document.querySelector('a[href="/settings?tab=printing"]')) return;
    const system = document.querySelector('a[href="/settings?tab=system"]');
    if (!system) return;
    const link = document.createElement('a');
    link.href = '/settings?tab=printing';
    link.className = 'list-group-item list-group-item-action d-flex align-items-center' + (settingsTab() === 'printing' ? ' active' : '');
    link.innerHTML = '<span class="me-2"><i class="ti ti-printer icon"></i></span>Printer';
    system.insertAdjacentElement('beforebegin', link);
  }

  function printerInfoHtml(data) {
    const status = data.status || {};
    const info = status.info || {};
    const pi = info.printerInfo || {};
    const meta = info.modelMetadata || {};
    const rows = [
      ['Model', meta.model || info.model || 'B21 Pro'],
      ['State', status.connected ? 'Connected' : 'Disconnected'],
      ['Serial', pi.serial || info.serial || '—'],
      ['Address', status.address || pi.mac || info.mac || '—'],
      ['Transport', status.transport || '—'],
      ['DPI', meta.dpi || status.dpi || '—'],
      ['Print task', info.detectedPrintTask || status.detected_print_task || status.print_task || '—'],
      ['Firmware', pi.softwareVersion || info.softwareVersion || '—'],
      ['Hardware', pi.hardwareVersion || info.hardwareVersion || '—'],
      ['Charge (raw)', pi.charge == null ? '—' : pi.charge],
      ['Active jobs', data.active_jobs || 0],
      ['Last print', data.last_print_at || '—'],
    ];
    return rows.map((row) => '<div class="datagrid-item"><div class="datagrid-title">' + esc(row[0]) + '</div><div class="datagrid-content">' + esc(row[1]) + '</div></div>').join('');
  }

  function printerStatsHtml(data) {
    const status = data.status || {};
    const rows = [
      ['printer', status.connected ? 'green' : 'secondary', status.connected ? 'Connected' : 'Disconnected', 'Printer'],
      ['tag', 'green', Number(data.labels || 0), 'Labels printed'],
      ['briefcase', 'azure', Number(data.jobs || 0), 'Print jobs'],
      ['alert-triangle', Number(data.failed || 0) ? 'red' : 'secondary', Number(data.failed || 0), 'Failed jobs'],
    ];
    return rows.map((row) => '<div class="col-sm-6 col-xl-3"><div class="card card-sm b2m-v7-printer-stat"><div class="card-body"><div class="d-flex align-items-center gap-3"><span class="avatar bg-' + row[1] + '-lt text-' + row[1] + '"><i class="ti ti-' + row[0] + '"></i></span><div><div class="h3 mb-0">' + esc(row[2]) + '</div><div class="text-secondary small">' + esc(row[3]) + '</div></div></div></div></div></div>').join('');
  }

  function installPrinterPanel() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'printing') return;
    const form = document.querySelector('form[action="/settings/configuration"]');
    const body = form && form.querySelector(':scope > .card-body');
    if (!body) return;

    body.querySelector(':scope > .empty')?.remove();
    document.getElementById('b2m-printer-runtime-v4')?.remove();
    document.getElementById('b2m-printer-runtime-v6')?.remove();
    const heading = body.querySelector(':scope > h2');
    if (heading) heading.textContent = 'Printer';
    const subtitle = body.querySelector(':scope > .card-subtitle');
    if (subtitle) subtitle.textContent = 'Connection, statistics and runtime state for niimblue-node and the NIIMBOT B21 Pro.';

    if (document.getElementById('b2m-printer-runtime-v7')) return;
    const card = document.createElement('div');
    card.id = 'b2m-printer-runtime-v7';
    card.className = 'mt-3';
    card.innerHTML =
      '<div class="card mb-3"><div class="card-header"><div><h3 class="card-title">Printer connection</h3><p class="card-subtitle">Manual BLE connection. The button is always released again after success, failure or timeout.</p></div><div class="card-actions d-flex gap-2 align-items-center"><span id="v7-printer-state" class="badge bg-secondary-lt">Loading…</span><button id="v7-printer-refresh" class="btn btn-outline-secondary btn-sm" type="button"><i class="ti ti-refresh icon"></i> Refresh</button><button id="v7-printer-connect" class="btn btn-outline-primary btn-sm" type="button"><i class="ti ti-bluetooth icon"></i> Connect</button></div></div><div class="card-body"><div class="row row-cards mb-3" id="v7-printer-stats"></div><div class="datagrid" id="v7-printer-datagrid"></div><div id="v7-printer-error" class="form-hint mt-3"></div></div></div>';
    body.appendChild(card);

    let actionError = '';
    async function refresh(options) {
      const preserveError = !!(options && options.preserveError);
      const state = $('v7-printer-state'), button = $('v7-printer-connect'), error = $('v7-printer-error');
      try {
        const data = await fetchJsonTimeout('/labels/b21/stats', {cache: 'no-store'}, 8000);
        const status = data.status || {};
        const connected = !!status.connected;
        state.className = 'badge ' + (connected ? 'bg-green text-green-fg' : 'bg-red-lt text-red');
        state.textContent = connected ? 'Connected' : 'Not connected';
        button.dataset.connected = connected ? '1' : '0';
        button.className = 'btn btn-sm ' + (connected ? 'btn-outline-danger' : 'btn-outline-primary');
        button.innerHTML = connected ? '<i class="ti ti-bluetooth-off icon"></i> Disconnect' : '<i class="ti ti-bluetooth icon"></i> Connect';
        $('v7-printer-stats').innerHTML = printerStatsHtml(data);
        $('v7-printer-datagrid').innerHTML = printerInfoHtml(data);
        const backendError = data.last_error || status.error || status.info_error || '';
        if (!preserveError) actionError = '';
        const shownError = actionError || backendError;
        error.className = 'form-hint mt-3' + (shownError ? ' text-danger' : ' text-secondary');
        error.textContent = shownError || 'niimblue-node reachable.';
      } catch (err) {
        if (!preserveError) actionError = err.message;
        error.className = 'form-hint mt-3 text-danger';
        error.textContent = actionError || err.message;
        state.className = 'badge bg-red-lt text-red';
        state.textContent = 'Status failed';
      }
    }

    $('v7-printer-refresh').addEventListener('click', () => { actionError = ''; refresh(); });
    $('v7-printer-connect').addEventListener('click', async function () {
      const button = this, error = $('v7-printer-error');
      const disconnecting = button.dataset.connected === '1';
      actionError = '';
      button.disabled = true;
      button.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>' + (disconnecting ? 'Disconnecting…' : 'Connecting…');
      error.className = 'form-hint mt-3 text-secondary';
      error.textContent = disconnecting ? 'Disconnecting printer…' : 'Connecting printer…';
      let failed = false;
      try {
        await fetchJsonTimeout(disconnecting ? '/labels/b21/disconnect' : '/labels/b21/connect', {method: 'POST'}, 24000);
      } catch (err) {
        failed = true;
        actionError = err.message;
        error.className = 'form-hint mt-3 text-danger';
        error.textContent = actionError;
      } finally {
        // Never make UI recovery depend on a follow-up network request.
        button.disabled = false;
        refresh({preserveError: failed});
      }
    });
    refresh();
  }

  function removeLegacyDateControl() {
    const box = document.getElementById('b2m-v4-date-style');
    if (!box) return;
    const heading = box.previousElementSibling && box.previousElementSibling.previousElementSibling;
    const subtitle = box.previousElementSibling;
    box.remove();
    if (subtitle && subtitle.tagName === 'P' && /Format used for absolute dates/i.test(subtitle.textContent)) subtitle.remove();
    if (heading && heading.tagName === 'H3' && heading.textContent.trim() === 'Date format') heading.remove();
  }

  function installDateFormatControl() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'appearance') return;
    let tries = 0;
    function install() {
      removeLegacyDateControl();
      const form = document.querySelector('form[action="/settings/theme"]');
      const body = form && form.querySelector('.card-body');
      const anchor = document.getElementById('b2m-appearance-v4') || document.getElementById('theme-accessibility');
      if (!form || !body || !anchor) {
        if (tries++ < 50) setTimeout(install, 80);
        return;
      }
      if ($('b2m-v7-date-style')) return;
      const section = document.createElement('section');
      section.id = 'b2m-v7-date-style';
      section.className = 'mt-4';
      section.innerHTML = '<h3 class="card-title">Date format</h3><p class="card-subtitle">Format used for absolute dates and timestamp tooltips across the server-rendered UI.</p><div class="form-selectgroup">' +
        [['short','Short · 21.09.26 14:30'],['medium','Medium · 21.09.2026 14:30'],['long','Long · 21. September 2026, 14:30']]
          .map((row) => '<label class="form-selectgroup-item"><input class="form-selectgroup-input" type="radio" name="b2m_v7_date_style" value="' + row[0] + '"><span class="form-selectgroup-label">' + row[1] + '</span></label>').join('') +
        '</div><div class="form-hint mt-2" id="b2m-v7-date-status"></div>';
      anchor.insertAdjacentElement('afterend', section);
      const status = $('b2m-v7-date-status');
      fetchJson('/api/theme', {cache: 'no-store'}).then((theme) => {
        const current = String(theme.date_style || 'medium');
        const radio = section.querySelector('input[value="' + CSS.escape(current) + '"]');
        if (radio) radio.checked = true;
      }).catch((error) => {status.className='form-hint mt-2 text-danger';status.textContent=error.message;});
      section.querySelectorAll('input[name="b2m_v7_date_style"]').forEach((radio) => {
        radio.addEventListener('change', async () => {
          if (!radio.checked) return;
          status.className = 'form-hint mt-2 text-secondary'; status.textContent = 'Saving…';
          try {
            const data = await fetchJson('/api/theme/preferences', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date_style:radio.value})});
            const saved = data.theme && data.theme.date_style;
            if (saved !== radio.value) throw new Error('Date format was not persisted');
            status.className = 'form-hint mt-2 text-success'; status.textContent = 'Saved · ' + radio.value;
          } catch (error) {
            status.className = 'form-hint mt-2 text-danger'; status.textContent = error.message;
          }
        });
      });
      // v4 can finish its delayed install after us; clean its duplicate a few
      // finite times without adding another permanent MutationObserver.
      [100, 300, 700, 1400].forEach((delay) => setTimeout(removeLegacyDateControl, delay));
    }
    install();
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
    syncVersionOnce();
    installBellPulse();
    installScannerLinks();
    installPrinterTabLink();
    installPrinterPanel();
    installDateFormatControl();
    installDateRefresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
