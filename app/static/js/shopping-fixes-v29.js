/* v2026.09.23.29 — robust print-only entries, unit hiding, printer control and autosaved receipt settings. */
(function () {
  'use strict';
  if (window.location.pathname !== '/shopping-print' || window.__b2mShoppingV29Loaded) return;
  window.__b2mShoppingV29Loaded = true;

  var payloadCache = null;
  var payloadListId = '';
  var settingsSaveTimer = null;
  var settingsBootstrapped = false;

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

  function setSettingsStatus(text, tone) {
    var el = $('shopping-print-settings-status');
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

  function selectedRadio(name, fallback) {
    var input = document.querySelector('input[name="' + name + '"]:checked');
    return input ? input.value : fallback;
  }

  function ensureTopMarginControl() {
    var existing = $('sp-top-margin');
    if (existing) return existing;
    var bottom = $('sp-bottom-margin');
    if (!bottom) return null;
    var bottomCol = bottom.closest('[class*="col-"]');
    if (!bottomCol || !bottomCol.parentElement) return null;
    var col = document.createElement('div');
    col.className = bottomCol.className || 'col-6';
    col.innerHTML = '<label class="form-label">Top margin</label><div class="input-group"><input class="form-control" type="number" min="0" max="20" step="0.1" id="sp-top-margin"><span class="input-group-text">mm</span></div>';
    bottomCol.parentElement.insertBefore(col, bottomCol);
    return col.querySelector('input');
  }

  function receiptSettingsPayload() {
    var marker = selectedRadio('sp-item-marker-style', 'checkbox');
    return {
      paper_width_mm: Number(($('sp-width') || {}).value || 50),
      margin_mm: Number(($('sp-margin') || {}).value || 0),
      top_margin_mm: Number(($('sp-top-margin') || {}).value || 0),
      body_font_mm: Number(($('sp-font') || {}).value || 3),
      line_gap_mm: Number(($('sp-line-gap') || {}).value || 0),
      category_gap_mm: Number(($('sp-category-gap') || {}).value || 0),
      bottom_margin_mm: Number(($('sp-bottom-margin') || {}).value || 0),
      density: Number(($('sp-density') || {}).value || 3),
      threshold: Number(($('sp-threshold') || {}).value || 145),
      dpi: Number(($('sp-dpi') || {}).value || 300),
      label_type: Number(($('sp-label-type') || {}).value || 3),
      show_checkboxes: marker === 'checkbox',
      item_marker_style: marker,
      show_items: !!($('sp-show-items') && $('sp-show-items').checked),
      show_quantities: !!($('sp-show-quantities') && $('sp-show-quantities').checked),
      show_item_dividers: !!($('sp-show-item-dividers') && $('sp-show-item-dividers').checked),
      show_category_dividers: !!($('sp-show-category-dividers') && $('sp-show-category-dividers').checked),
      category_divider_style: selectedRadio('sp-category-divider-style', 'solid')
    };
  }

  function updateTopMarginPreview() {
    var input = $('sp-top-margin');
    var canvas = $('shopping-print-canvas');
    if (!input || !canvas) return;
    var mm = Math.max(0, Number(input.value || 0));
    var dpi = Math.max(100, Number(($('sp-dpi') || {}).value || 300));
    var sourceWidth = Math.max(1, Number(canvas.width || 1));
    var displayWidth = canvas.getBoundingClientRect().width || sourceWidth;
    var cssPixels = Math.round((mm * dpi / 25.4) * (displayWidth / sourceWidth));
    canvas.style.marginTop = cssPixels > 0 ? cssPixels + 'px' : '';

    var badge = $('shopping-print-paper-size');
    if (badge) {
      var match = badge.textContent.match(/^(.*?×\s*)([0-9]+(?:\.[0-9]+)?)(\s*mm)$/);
      var base = Number(canvas.dataset.b2mBaseHeightMm || 0);
      if (!base && match) {
        base = Math.max(0, Number(match[2]) - Number(canvas.dataset.b2mLastTopMarginMm || 0));
        canvas.dataset.b2mBaseHeightMm = String(base);
      }
      if (base) badge.textContent = match ? match[1] + (base + mm).toFixed(1) + match[3] : badge.textContent;
    }
    canvas.dataset.b2mLastTopMarginMm = String(mm);
  }

  function installTopMarginExport() {
    var canvas = $('shopping-print-canvas');
    if (!canvas || canvas.dataset.b2mTopMarginExport === '1') return;
    canvas.dataset.b2mTopMarginExport = '1';
    var nativeToDataURL = canvas.toDataURL.bind(canvas);
    canvas.toDataURL = function () {
      var args = arguments;
      var mm = Math.max(0, Number(($('sp-top-margin') || {}).value || 0));
      var dpi = Math.max(100, Number(($('sp-dpi') || {}).value || 300));
      var topPx = Math.max(0, Math.round(mm * dpi / 25.4));
      if (!topPx) return nativeToDataURL.apply(canvas, args);
      var out = document.createElement('canvas');
      out.width = canvas.width;
      out.height = canvas.height + topPx;
      var ctx = out.getContext('2d');
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, out.width, out.height);
      ctx.drawImage(canvas, 0, topPx);
      canvas.dataset.heightMm = (out.height / dpi * 25.4).toFixed(2);
      return out.toDataURL.apply(out, args);
    };
  }

  async function bootstrapReceiptSettings() {
    var top = ensureTopMarginControl();
    if (!top) return;
    try {
      var data = await json('/api/shopping-print/bootstrap?_=' + Date.now());
      var settings = data.settings || {};
      top.value = settings.top_margin_mm == null ? 2.2 : settings.top_margin_mm;
    } catch (e) {
      if (!top.value) top.value = '2.2';
    }
    settingsBootstrapped = true;
    updateTopMarginPreview();
  }

  async function saveReceiptSettings() {
    if (!settingsBootstrapped) return;
    var saveButton = $('shopping-print-save-settings');
    if (saveButton && saveButton.disabled) return;
    setSettingsStatus('Saving automatically…', 'secondary');
    try {
      var data = await json('/api/shopping-print/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(receiptSettingsPayload())
      });
      if (data.settings && $('sp-top-margin')) $('sp-top-margin').value = data.settings.top_margin_mm;
      setSettingsStatus('Saved automatically.', 'success');
      window.setTimeout(function () {
        var status = $('shopping-print-settings-status');
        if (status && status.textContent === 'Saved automatically.') status.textContent = '';
      }, 1800);
    } catch (error) {
      setSettingsStatus(error.message, 'danger');
    }
  }

  function scheduleReceiptSettingsSave() {
    if (!settingsBootstrapped) return;
    clearTimeout(settingsSaveTimer);
    setSettingsStatus('Unsaved changes…', 'yellow');
    settingsSaveTimer = window.setTimeout(saveReceiptSettings, 450);
  }

  function installReceiptAutosave() {
    var saveButton = $('shopping-print-save-settings');
    if (saveButton) saveButton.classList.add('d-none');
    var footer = saveButton && saveButton.closest('.card-footer');
    if (footer) footer.classList.add('justify-content-end');

    var selector = [
      '#sp-width','#sp-margin','#sp-top-margin','#sp-font','#sp-line-gap','#sp-category-gap','#sp-bottom-margin',
      '#sp-density','#sp-threshold','#sp-dpi','#sp-label-type','#sp-show-items','#sp-show-quantities',
      '#sp-show-item-dividers','#sp-show-category-dividers','input[name="sp-category-divider-style"]',
      'input[name="sp-item-marker-style"]'
    ].join(',');
    document.querySelectorAll(selector).forEach(function (input) {
      if (input.dataset.b2mAutoSaveBound === '1') return;
      input.dataset.b2mAutoSaveBound = '1';
      input.addEventListener('input', function () {
        if (input.id === 'sp-top-margin' || input.id === 'sp-dpi') window.setTimeout(updateTopMarginPreview, 0);
        scheduleReceiptSettingsSave();
      });
      input.addEventListener('change', function () {
        if (input.id === 'sp-top-margin' || input.id === 'sp-dpi') window.setTimeout(updateTopMarginPreview, 0);
        scheduleReceiptSettingsSave();
      });
    });
  }

  function bind() {
    ensureHeaderConnect();
    ensureHideUnitControl();
    installTopMarginExport();
    bootstrapReceiptSettings().then(function () {
      installReceiptAutosave();
      window.setTimeout(updateTopMarginPreview, 150);
    });
    syncHideUnit();

    var canvas = $('shopping-print-canvas');
    if (canvas && canvas.dataset.b2mTopMarginObserved !== '1') {
      canvas.dataset.b2mTopMarginObserved = '1';
      new MutationObserver(function () {
        canvas.dataset.b2mBaseHeightMm = canvas.dataset.heightMm || '';
        window.setTimeout(updateTopMarginPreview, 0);
      }).observe(canvas, {attributes: true, attributeFilter: ['width', 'height', 'data-height-mm']});
    }

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
