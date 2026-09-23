/* v2026.09.23.29 — robust print-only entries, unit hiding and header printer control. */
(function () {
  'use strict';
  if (window.location.pathname !== '/shopping-print' || window.__b2mShoppingV29Loaded) return;
  window.__b2mShoppingV29Loaded = true;

  var payloadCache = null;
  var payloadListId = '';

  function $(id) { return document.getElementById(id); }

  async function json(url, options) {
    var opts = Object.assign({}, options || {});
    opts.headers = Object.assign({Accept: 'application/json'}, opts.headers || {});
    opts.cache = 'no-store';
    var response = await fetch(url, opts);
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.error || data.detail || ('HTTP ' + response.status));
    return data;
  }

  function listId() {
    return String(($('shopping-print-list') || {}).value || '').trim();
  }

  function localComment() {
    return String(($('shopping-print-local-comment') || {}).value || '');
  }

  function setStatus(text, tone) {
    var el = $('shopping-print-local-status');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'form-hint' + (tone ? ' text-' + tone : '');
  }

  function setOverrideStatus(text, tone) {
    var el = $('shopping-print-override-status');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'form-hint' + (tone ? ' text-' + tone : '');
  }

  async function refreshPayload(force) {
    var id = listId();
    if (!id) return null;
    if (!force && payloadCache && payloadListId === id) return payloadCache;
    payloadCache = await json('/api/shopping-print/lists/' + encodeURIComponent(id) + '?_=' + Date.now());
    payloadListId = id;
    return payloadCache;
  }

  function selectedOverride(payload) {
    var select = $('shopping-print-override-item');
    var key = String((select || {}).value || '');
    if (!payload || !key) return {key: key, item: null, override: null};
    var item = (payload.items || []).find(function (row) { return String(row.override_key || '') === key; }) || null;
    var override = (payload.item_overrides || []).find(function (row) { return String(row.key || '') === key; }) || null;
    return {key: key, item: item, override: override};
  }

  function ensureHideUnitControl() {
    if ($('shopping-print-override-hide-unit')) return $('shopping-print-override-hide-unit');
    var unit = $('shopping-print-override-unit');
    if (!unit) return null;
    var col = unit.closest('[class*="col-"]') || unit.parentElement;
    var label = document.createElement('label');
    label.className = 'form-check form-switch mt-2 mb-0';
    label.innerHTML = '<input class="form-check-input" type="checkbox" id="shopping-print-override-hide-unit"><span class="form-check-label">Hide unit for this item</span>';
    col.appendChild(label);
    var toggle = label.querySelector('input');
    toggle.addEventListener('change', function () {
      unit.disabled = toggle.checked;
      setOverrideStatus('Unsaved override changes.', 'yellow');
    });
    return toggle;
  }

  async function syncHideUnit() {
    var toggle = ensureHideUnitControl();
    var unit = $('shopping-print-override-unit');
    if (!toggle || !unit) return;
    try {
      var payload = await refreshPayload(true);
      var selected = selectedOverride(payload);
      toggle.checked = !!(selected.override && selected.override.hide_unit);
      toggle.disabled = !selected.key;
      unit.disabled = toggle.checked;
    } catch (e) {
      toggle.disabled = true;
    }
  }

  function ensureHeaderConnect() {
    var source = $('shopping-print-connect');
    var row = document.querySelector('.page-header .col-auto.btn-list');
    if (!source || !row) return;
    var button = $('shopping-print-connect-header');
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.id = 'shopping-print-connect-header';
      button.className = 'btn btn-outline-primary';
      var print = $('shopping-print-button');
      if (print) row.insertBefore(button, print);
      else row.appendChild(button);
      button.addEventListener('click', function () { source.click(); });
    }
    function sync() {
      button.disabled = source.disabled;
      button.innerHTML = source.innerHTML;
      button.classList.toggle('btn-outline-danger', source.classList.contains('btn-outline-danger'));
      button.classList.toggle('btn-outline-primary', !source.classList.contains('btn-outline-danger'));
    }
    sync();
    if (source.dataset.b2mV29Observed !== '1') {
      source.dataset.b2mV29Observed = '1';
      new MutationObserver(sync).observe(source, {attributes: true, childList: true, subtree: true});
    }
  }

  async function saveLocalEntries(entries) {
    return json('/api/shopping-print/local-content', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        list_id: listId(),
        comment: localComment(),
        entries: entries
      })
    });
  }

  async function addLocalEntry(button) {
    var id = listId();
    var name = String(($('shopping-print-local-name') || {}).value || '').trim();
    if (!id) return;
    if (!name) {
      setStatus('Enter a name for the print-only entry.', 'danger');
      $('shopping-print-local-name') && $('shopping-print-local-name').focus();
      return;
    }
    button.disabled = true;
    setStatus('Saving new entry…', 'secondary');
    try {
      var payload = await refreshPayload(true);
      var entries = (payload.local_entries || []).map(function (entry) { return Object.assign({}, entry); });
      entries.push({
        name: name,
        quantity_text: String(($('shopping-print-local-qty') || {}).value || '').trim(),
        category: String(($('shopping-print-local-category') || {}).value || '').trim() || 'Extra'
      });
      await saveLocalEntries(entries);
      window.location.reload();
    } catch (error) {
      setStatus(error.message, 'danger');
      button.disabled = false;
    }
  }

  async function removeLocalEntry(button, row) {
    var id = listId();
    if (!id) return;
    button.disabled = true;
    setStatus('Removing entry…', 'secondary');
    try {
      var payload = await refreshPayload(true);
      var index = Number(row.dataset.localIndex);
      var entry = (payload.local_entries || [])[index];
      if (!entry || !entry.id) throw new Error('Print-only entry could not be resolved. Refresh the page and try again.');
      var entries = (payload.local_entries || []).filter(function (candidate) {
        return String(candidate.id || '') !== String(entry.id);
      }).map(function (candidate) { return Object.assign({}, candidate); });
      await saveLocalEntries(entries);
      window.location.reload();
    } catch (error) {
      setStatus(error.message, 'danger');
      button.disabled = false;
    }
  }

  async function saveOverride(button) {
    var id = listId();
    var select = $('shopping-print-override-item');
    var key = String((select || {}).value || '');
    if (!id || !key) return;
    button.disabled = true;
    setOverrideStatus('Saving override…', 'secondary');
    try {
      var payload = await refreshPayload(true);
      var selected = selectedOverride(payload);
      if (!selected.item) throw new Error('Shopping-list item could not be resolved.');
      var hide = $('shopping-print-override-hide-unit');
      var data = await json('/api/shopping-print/item-overrides', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          list_id: id,
          key: key,
          name_alias: String(($('shopping-print-override-name') || {}).value || '').trim(),
          quantity_alias: String(($('shopping-print-override-qty') || {}).value || '').trim(),
          unit_alias: String(($('shopping-print-override-unit') || {}).value || '').trim(),
          hide_unit: !!(hide && hide.checked),
          source_name: selected.item.original_name || selected.item.name || '',
          source_quantity_text: selected.item.original_quantity_value_text || selected.item.quantity_value_text || '',
          source_unit_text: selected.item.original_unit_text || selected.item.unit_text || ''
        })
      });
      payloadCache = Object.assign({}, payloadCache || {}, {item_overrides: data.item_overrides || []});
      await syncHideUnit();
      setOverrideStatus('Override saved for this shopping-list item.', 'success');
      var refresh = $('shopping-print-refresh');
      if (refresh) refresh.click();
    } catch (error) {
      setOverrideStatus(error.message, 'danger');
    } finally {
      button.disabled = false;
    }
  }

  function bind() {
    ensureHeaderConnect();
    ensureHideUnitControl();
    syncHideUnit();

    var list = $('shopping-print-list');
    if (list && list.dataset.b2mV29Bound !== '1') {
      list.dataset.b2mV29Bound = '1';
      list.addEventListener('change', function () {
        payloadCache = null;
        payloadListId = '';
        window.setTimeout(syncHideUnit, 80);
      });
    }
    var override = $('shopping-print-override-item');
    if (override && override.dataset.b2mV29Bound !== '1') {
      override.dataset.b2mV29Bound = '1';
      override.addEventListener('change', function () { window.setTimeout(syncHideUnit, 0); });
    }
  }

  document.addEventListener('click', function (event) {
    var add = event.target && event.target.closest && event.target.closest('#shopping-print-local-add');
    if (add) {
      event.preventDefault();
      event.stopImmediatePropagation();
      addLocalEntry(add);
      return;
    }

    var remove = event.target && event.target.closest && event.target.closest('[data-local-remove]');
    if (remove) {
      var row = remove.closest('[data-local-index]');
      if (!row) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      removeLocalEntry(remove, row);
      return;
    }

    var save = event.target && event.target.closest && event.target.closest('#shopping-print-override-save');
    if (save) {
      event.preventDefault();
      event.stopImmediatePropagation();
      saveOverride(save);
    }
  }, true);

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, {once: true});
  else bind();
})();
