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
      el.classList.remove('btn-ghost-secondary');
      el.classList.add('btn-ghost-primary', 'text-primary');
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
      '<button type="button" class="btn btn-ghost-primary text-primary p-0 font-monospace text-start text-break barcode-preview-trigger" data-barcode="' + esc(row.barcode) + '" data-bs-toggle="modal" data-bs-target="#item-code-preview">' + esc(row.barcode) + '</button>' +
      '<span class="text-secondary small ms-auto" title="' + esc(row.last_scan_absolute) + '">' + esc(row.last_scan) + '</span>' +
      '<span class="badge bg-primary text-primary-fg">' + Number(row.count || 0) + '</span>' +
      '<a class="btn btn-sm btn-icon btn-ghost-secondary" href="/barcodes/' + encodeURIComponent(row.barcode) + '" title="Open barcode"><i class="ti ti-external-link"></i></a>' +
      '</div>'
    ).join('');
    bindPreviews();
  }

  function cardByTitle(root, title) {
    const heading = Array.from(root.querySelectorAll('h3.card-title')).find((el) => el.textContent.trim().toLowerCase() === title.toLowerCase());
    return heading ? heading.closest('.card') : null;
  }

  async function refreshRecentHistory() {
    try {
      const response = await fetch(window.location.pathname + '?live=1', {headers: {'Accept': 'text/html'}});
      if (!response.ok) return;
      const fresh = new DOMParser().parseFromString(await response.text(), 'text/html');
      const currentCard = cardByTitle(document, 'Recent scans');
      const freshCard = cardByTitle(fresh, 'Recent scans');
      if (currentCard && freshCard) currentCard.replaceWith(freshCard);
    } catch (e) {
      console.debug('Item recent history refresh failed', e);
    }
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
      await refreshRecentHistory();
    } catch (e) {
      console.debug('Item stats refresh failed', e);
    }
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refreshStats, 120);
  }

  function installRouteCheckboxes() {
    const route = document.getElementById('shopping-route');
    const list = document.getElementById('shopping-list-id');
    if (!route) return;

    route.classList.add('d-none');
    const wrapper = document.createElement('div');
    wrapper.className = 'b2m-choice-grid b2m-item-route-choices';
    wrapper.innerHTML =
      '<label class="b2m-choice-card"><input class="form-check-input me-2" type="checkbox" value="mealie"><span><strong>Mealie</strong><small>Shopping list</small></span></label>' +
      '<label class="b2m-choice-card"><input class="form-check-input me-2" type="checkbox" value="homeassistant"><span><strong>Home Assistant</strong><small>Webhook event</small></span></label>';
    route.insertAdjacentElement('afterend', wrapper);

    const checks = Array.from(wrapper.querySelectorAll('input[type="checkbox"]'));
    if (route.value === 'both') checks.forEach((check) => { check.checked = true; });
    else if (route.value === 'mealie' || route.value === 'default') checks.find((check) => check.value === 'mealie').checked = true;
    else if (route.value === 'homeassistant') checks.find((check) => check.value === 'homeassistant').checked = true;

    function syncRoute() {
      const values = checks.filter((check) => check.checked).map((check) => check.value);
      if (values.includes('mealie') && values.includes('homeassistant')) route.value = 'both';
      else if (values.includes('mealie')) route.value = 'mealie';
      else if (values.includes('homeassistant')) route.value = 'homeassistant';
      else route.value = 'none';
      if (list) list.disabled = !values.includes('mealie');
    }
    checks.forEach((check) => check.addEventListener('change', syncRoute));
    syncRoute();
  }

  bindPreviews();
  installRouteCheckboxes();

  if (window.EventSource) {
    const events = new EventSource('/events');
    events.addEventListener('scan', scheduleRefresh);
    window.addEventListener('beforeunload', () => events.close());
  }
})();
