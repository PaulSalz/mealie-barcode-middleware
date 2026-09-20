(function () {
  'use strict';
  const cfg = document.getElementById('item-detail-config');
  if (!cfg) return;
  const itemId = cfg.dataset.itemId;
  let refreshTimer = null;

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  function preview(barcode) {
    document.getElementById('item-code-preview-value').textContent = barcode;
    document.getElementById('item-code-preview-img').src = '/labels/code.svg?kind=auto&value=' + encodeURIComponent(barcode);
  }

  function bindPreviews() {
    document.querySelectorAll('.barcode-preview-trigger').forEach((el) => {
      if (el.dataset.previewBound === '1') return;
      el.dataset.previewBound = '1';
      el.addEventListener('click', () => preview(el.dataset.barcode));
    });
  }

  function renderBarcodes(rows) {
    const root = document.getElementById('item-barcode-stats');
    if (!root) return;
    if (!rows.length) {
      root.innerHTML = '<div class="list-group-item text-secondary">No scan history yet.</div>';
      return;
    }
    root.innerHTML = rows.map((row) =>
      '<div class="list-group-item d-flex align-items-center gap-2">' +
      '<button type="button" class="btn btn-ghost-secondary p-0 font-monospace text-start text-break barcode-preview-trigger" data-barcode="' + esc(row.barcode) + '" data-bs-toggle="modal" data-bs-target="#item-code-preview">' + esc(row.barcode) + '</button>' +
      '<span class="text-secondary small ms-auto" title="' + esc(row.last_scan_absolute) + '">' + esc(row.last_scan) + '</span>' +
      '<span class="badge bg-primary text-primary-fg">' + Number(row.count || 0) + '</span>' +
      '<a class="btn btn-sm btn-icon btn-ghost-secondary" href="/barcodes/' + encodeURIComponent(row.barcode) + '" title="Open barcode"><i class="ti ti-external-link"></i></a>' +
      '</div>'
    ).join('');
    bindPreviews();
  }

  async function refreshStats() {
    try {
      const response = await fetch('/api/items/' + encodeURIComponent(itemId) + '/stats', {headers: {'Accept': 'application/json'}});
      if (!response.ok) return;
      const data = await response.json();
      document.getElementById('item-stat-total').textContent = data.total;
      document.getElementById('item-stat-7').textContent = data.days_7;
      document.getElementById('item-stat-30').textContent = data.days_30;
      const last = document.getElementById('item-stat-last');
      last.textContent = data.last_scan;
      last.title = data.last_scan_absolute || '';
      renderBarcodes(data.by_barcode || []);
    } catch (e) {
      console.debug('Item stats refresh failed', e);
    }
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refreshStats, 120);
  }

  bindPreviews();

  const route = document.getElementById('shopping-route');
  const list = document.getElementById('shopping-list-id');
  if (route && list) {
    const updateListState = () => {
      const enabled = ['default', 'mealie', 'both'].includes(route.value);
      list.disabled = !enabled;
    };
    route.addEventListener('change', updateListState);
    updateListState();
  }

  if (window.EventSource) {
    const events = new EventSource('/events');
    events.addEventListener('scan', scheduleRefresh);
  }
})();
