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

  function installDeleteButton() {
    const list = document.querySelector('.page-header .btn-list');
    if (!list || list.querySelector('form[action$="/delete"]') || document.getElementById('item-delete-source')) return;
    const synced = /synced from mealie/i.test(document.querySelector('.page-pretitle')?.textContent || '');
    const button = document.createElement('button');
    button.type = 'button'; button.id = 'item-delete-source'; button.className = 'btn btn-outline-danger';
    button.innerHTML = '<i class="ti ti-trash icon"></i> Delete Item';
    list.appendChild(button);
    button.addEventListener('click', function() {
      const detail = synced
        ? 'This deletes the Food in Mealie first, then removes its B2M targets and mappings. This cannot be undone.'
        : 'This removes the item and its local B2M links.';
      if (!window.showConfirm) return;
      window.showConfirm('Delete this item?', detail, async function() {
        button.disabled = true;
        try {
          const response = await fetch('/api/items/' + encodeURIComponent(itemId), {method:'DELETE', headers:{'Accept':'application/json'}});
          const data = await response.json();
          if (!response.ok || !data.ok) throw new Error(data.error || 'Delete failed');
          window.location.href = '/items';
        } catch (error) {
          button.disabled = false;
          window.alert(error.message);
        }
      }, 'Delete Item');
    });
  }

  function renderBarcodes(rows) {
    const root = document.getElementById('item-barcode-stats');
    if (!root) return;
    if (!rows.length) { root.innerHTML = '<div class="list-group-item text-secondary">No scan history yet.</div>'; return; }
    root.innerHTML = rows.map((row) =>
      '<div class="list-group-item d-flex align-items-center gap-2">' +
      '<button type="button" class="btn btn-ghost-primary p-0 font-monospace text-start text-break barcode-preview-trigger" data-barcode="' + esc(row.barcode) + '" data-bs-toggle="modal" data-bs-target="#item-code-preview">' + esc(row.barcode) + '</button>' +
      '<span class="text-secondary small ms-auto" title="' + esc(row.last_scan_absolute) + '">' + esc(row.last_scan) + '</span>' +
      '<span class="badge bg-primary text-primary-fg">' + Number(row.count || 0) + '</span>' +
      '<a class="btn btn-sm btn-icon btn-ghost-primary" href="/barcodes/' + encodeURIComponent(row.barcode) + '" title="Open barcode"><i class="ti ti-external-link"></i></a>' +
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
    } catch (e) { console.debug('Item recent history refresh failed', e); }
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
      last.textContent = data.last_scan; last.title = data.last_scan_absolute || '';
      renderBarcodes(data.by_barcode || []); await refreshRecentHistory();
    } catch (e) { console.debug('Item stats refresh failed', e); }
  }

  function scheduleRefresh() { clearTimeout(refreshTimer); refreshTimer = setTimeout(refreshStats, 120); }

  function installRoutingChoices() {
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

    let listWrapper = null;
    if (list) {
      list.classList.add('d-none');
      listWrapper = document.createElement('div');
      listWrapper.className = 'b2m-choice-grid b2m-item-list-choices';
      listWrapper.innerHTML = Array.from(list.options).map((option) => {
        const text = option.textContent.trim();
        const isDefault = !option.value || /default/i.test(text);
        return '<label class="b2m-choice-card"><input class="form-check-input me-2" type="radio" name="b2m-item-list-ui" value="' + esc(option.value) + '"' + (option.selected ? ' checked' : '') + '><span><strong>' + esc(text.replace(/^Default configured list$/, 'Default shopping list')) + '</strong><small>' + (isDefault ? 'Use current B2M default' : 'Mealie list') + '</small></span></label>';
      }).join('');
      list.insertAdjacentElement('afterend', listWrapper);
      listWrapper.querySelectorAll('input').forEach((input) => input.addEventListener('change', () => { if (input.checked) list.value = input.value; }));
    }

    function syncRoute() {
      const values = checks.filter((check) => check.checked).map((check) => check.value);
      if (values.includes('mealie') && values.includes('homeassistant')) route.value = 'both';
      else if (values.includes('mealie')) route.value = 'mealie';
      else if (values.includes('homeassistant')) route.value = 'homeassistant';
      else route.value = 'none';
      const mealieEnabled = values.includes('mealie');
      if (listWrapper) {
        listWrapper.classList.toggle('b2m-choice-disabled', !mealieEnabled);
        listWrapper.querySelectorAll('input').forEach((input) => { input.disabled = !mealieEnabled; });
      }
    }
    checks.forEach((check) => check.addEventListener('change', syncRoute));
    syncRoute();
  }

  bindPreviews();
  installDeleteButton();
  installRoutingChoices();

  if (window.EventSource) {
    const events = new EventSource('/events');
    events.addEventListener('scan', scheduleRefresh);
    window.addEventListener('beforeunload', () => events.close());
  }
})();
