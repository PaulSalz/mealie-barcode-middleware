(function () {
  'use strict';
  if (window.__b2mUiV23Loaded) return;
  window.__b2mUiV23Loaded = true;

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value == null ? '' : value)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#039;');

  function permissions() {
    return new Set(String(document.body && document.body.dataset.b2mPermissions || '').split(',').map((v) => v.trim()).filter(Boolean));
  }

  function settingsTab() {
    return new URLSearchParams(window.location.search).get('tab') || 'mealie';
  }

  async function json(url, options) {
    const response = await fetch(url, Object.assign({headers:{Accept:'application/json'}}, options || {}));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || data.detail || ('HTTP ' + response.status));
    return data;
  }

  function formatBytes(value) {
    let bytes = Number(value || 0);
    if (!Number.isFinite(bytes) || bytes < 0) bytes = 0;
    const units = ['B','KB','MB','GB','TB'];
    let index = 0;
    while (bytes >= 1024 && index < units.length - 1) { bytes /= 1024; index += 1; }
    return (index === 0 ? bytes.toFixed(0) : bytes >= 100 ? bytes.toFixed(0) : bytes >= 10 ? bytes.toFixed(1) : bytes.toFixed(2)) + ' ' + units[index];
  }

  function enforcePrinterNavigation() {
    if (window.location.pathname !== '/settings') return;
    if (permissions().has('printer_settings')) return;
    document.querySelectorAll('a[href="/settings?tab=printing"],a[href="/settings?tab=printer"]').forEach((node) => node.remove());
  }

  function polishLabelEditor() {
    if (window.location.pathname !== '/labels') return;
    function apply() {
      const align = $('b21-v2-align');
      if (!align) { setTimeout(apply, 100); return; }
      const icons = {
        left: 'ti-layout-align-left',
        hcenter: 'ti-layout-align-center',
        right: 'ti-layout-align-right'
      };
      Object.entries(icons).forEach(([key, icon]) => {
        const node = align.querySelector('[data-align="' + key + '"] i');
        if (node) node.className = 'ti ' + icon;
      });

      // v4 created this wrapper for Frame + Threshold. v22 deliberately moved
      // both controls elsewhere, so keeping the empty heading only wastes space.
      const appearance = $('b21-v4-label-appearance');
      if (appearance) appearance.remove();
    }
    apply();
  }

  function permissionCard(permission, user) {
    const checked = !!(user.permissions && user.permissions[permission.id]);
    return '<label class="b2m-access-permission form-check mb-0">' +
      '<input class="form-check-input" type="checkbox" value="' + esc(permission.id) + '"' + (checked ? ' checked' : '') + (user.is_admin ? ' disabled' : '') + '>' +
      '<span class="form-check-label"><strong><i class="ti ' + esc(permission.icon || 'ti-shield') + ' me-1"></i>' + esc(permission.label) + '</strong><small class="text-secondary">' + esc(permission.description) + '</small></span>' +
    '</label>';
  }

  async function installAccessControl() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'users') return;
    const body = document.querySelector('.col-12.col-md-9 > .card-body');
    if (!body || $('b2m-access-card')) return;
    try {
      const data = await json('/api/settings/access', {cache:'no-store'});
      const card = document.createElement('div');
      card.className = 'card mt-4';
      card.id = 'b2m-access-card';
      card.innerHTML = '<div class="card-header"><div><h3 class="card-title">Access control</h3><p class="card-subtitle">Admin remains the unrestricted superuser. Capabilities below apply to normal users and are enforced server-side, not only hidden in the UI.</p></div></div>' +
        '<div class="card-body"><div id="b2m-access-users"></div></div>';
      body.appendChild(card);
      const root = $('b2m-access-users');
      (data.users || []).forEach((user) => {
        const row = document.createElement('div');
        row.className = 'b2m-access-user';
        row.dataset.userId = user.id;
        row.innerHTML = '<div class="d-flex align-items-center gap-2"><div class="flex-fill"><strong>' + esc(user.username) + '</strong> ' +
          (user.is_admin ? '<span class="badge bg-purple text-purple-fg">Admin · all capabilities</span>' : '<span class="badge bg-secondary-lt">User</span>') +
          '</div>' + (user.is_admin ? '' : '<button class="btn btn-sm btn-primary b2m-access-save" type="button"><i class="ti ti-device-floppy me-1"></i>Save access</button>') + '</div>' +
          '<div class="b2m-access-permissions">' + (data.permissions || []).map((permission) => permissionCard(permission,user)).join('') + '</div>' +
          '<div class="form-hint mt-2 b2m-access-result"></div>';
        root.appendChild(row);
      });

      root.querySelectorAll('.b2m-access-save').forEach((button) => button.addEventListener('click', async function () {
        const row = this.closest('.b2m-access-user');
        const result = row.querySelector('.b2m-access-result');
        const selected = Array.from(row.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value);
        button.disabled = true;
        result.className = 'form-hint mt-2 text-secondary'; result.textContent = 'Saving…';
        try {
          await json('/api/settings/access/' + encodeURIComponent(row.dataset.userId), {method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({permissions:selected})});
          result.className = 'form-hint mt-2 text-success'; result.textContent = 'Permissions saved.';
          setTimeout(() => { result.textContent = ''; }, 2200);
        } catch (error) {
          result.className = 'form-hint mt-2 text-danger'; result.textContent = error.message;
        } finally { button.disabled = false; }
      }));
    } catch (error) {
      // Non-admin users never get the Users tab, so a failed fetch here should
      // stay unobtrusive rather than creating a broken empty panel.
      console.debug('Access matrix unavailable', error);
    }
  }

  async function installStorageMetrics() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'admin') return;
    const body = document.querySelector('.col-12.col-md-9 > .card-body');
    if (!body || $('b2m-storage-card')) return;
    try {
      const data = await json('/api/settings/storage', {cache:'no-store'});
      const card = document.createElement('div');
      card.id = 'b2m-storage-card';
      card.className = 'card mt-3';
      card.innerHTML = '<div class="card-header"><div><h3 class="card-title">System data usage</h3><p class="card-subtitle">Total persistent data next to the SQLite database, including WAL/SHM and other B2M files. This makes long-term growth visible even when the main .db file stays small.</p></div></div>' +
        '<div class="card-body"><div class="b2m-storage-grid">' +
          '<div class="b2m-storage-metric"><small>Total system data</small><strong>' + formatBytes(data.system_size) + '</strong></div>' +
          '<div class="b2m-storage-metric"><small>SQLite database</small><strong>' + formatBytes(data.db_size) + '</strong></div>' +
          '<div class="b2m-storage-metric"><small>SQLite WAL + SHM</small><strong>' + formatBytes(data.db_aux_size) + '</strong></div>' +
          '<div class="b2m-storage-metric"><small>Other persistent files</small><strong>' + formatBytes(data.other_size) + '</strong></div>' +
        '</div><div class="form-hint mt-3"><strong>' + Number(data.file_count || 0) + '</strong> files below <code>' + esc(data.data_path || '') + '</code>. WAL: ' + formatBytes(data.wal_size) + ' · SHM: ' + formatBytes(data.shm_size) + '.</div></div>';
      const firstCard = body.querySelector(':scope > .card.mt-3');
      if (firstCard) body.insertBefore(card, firstCard); else body.appendChild(card);
    } catch (error) {
      console.debug('Storage metrics unavailable', error);
    }
  }

  function labelRainbowOption() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'appearance') return;
    const input = document.querySelector('input[name="theme_color"][value="rainbow"]');
    const label = input && input.closest('label');
    if (label) {
      label.title = 'Rainbow — continuously cycle the primary accent; dashboard brand uses a moving gradient.';
      label.setAttribute('aria-label','Rainbow accent');
    }
  }

  function forbiddenHint() {
    if (window.location.pathname !== '/settings') return;
    if (new URLSearchParams(window.location.search).get('forbidden') !== '1') return;
    const pane = document.querySelector('.col-12.col-md-9');
    if (!pane || $('b2m-forbidden-hint')) return;
    const alert = document.createElement('div');
    alert.id = 'b2m-forbidden-hint';
    alert.className = 'alert alert-warning m-3 mb-0';
    alert.textContent = 'That settings section is not enabled for your user account.';
    pane.insertBefore(alert,pane.firstChild);
  }

  function init() {
    enforcePrinterNavigation();
    polishLabelEditor();
    installAccessControl();
    installStorageMetrics();
    labelRainbowOption();
    forbiddenHint();
    if (window.location.pathname === '/settings') setTimeout(enforcePrinterNavigation, 250);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once:true});
  else init();
})();
