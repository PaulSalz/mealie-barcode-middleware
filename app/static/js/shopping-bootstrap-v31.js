/* v2026.09.23.31 — single-pass Shopping Print startup and observer-free UI fixes. */
(function () {
  'use strict';
  if (window.location.pathname !== '/shopping-print' || window.__b2mShoppingV31Loaded) return;
  window.__b2mShoppingV31Loaded = true;

  function $(id) { return document.getElementById(id); }
  var nativeFetch = window.fetch.bind(window);
  var settingsReady = false;
  var saveTimer = null;
  var overridePayload = null;
  var overridePayloadListId = '';
  var rawCanvas = null;
  var adjustedHeightMm = '';
  var adjustedHeightPx = 0;

  async function json(url, options) {
    var opts = Object.assign({}, options || {});
    opts.headers = Object.assign({Accept:'application/json'}, opts.headers || {});
    opts.cache = 'no-store';
    var response = await nativeFetch(url, opts);
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.error || data.detail || ('HTTP ' + response.status));
    return data;
  }

  function selectedListId() {
    return String(($('shopping-print-list') || {}).value || '').trim();
  }

  function selectedOverrideKey() {
    return String(($('shopping-print-override-item') || {}).value || '').trim();
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
    col.innerHTML = '<label class="form-label">Top margin</label>' +
      '<div class="input-group"><input class="form-control" type="number" min="0" max="20" step="0.1" id="sp-top-margin" value="2.2">' +
      '<span class="input-group-text">mm</span></div>';
    bottomCol.parentElement.insertBefore(col, bottomCol);
    return col.querySelector('input');
  }

  function ensureOverrideControls() {
    var unit = $('shopping-print-override-unit');
    if (!unit) return;
    var col = unit.closest('[class*="col-"]') || unit.parentElement;
    if (!col) return;

    if (!$('shopping-print-override-hide-unit')) {
      var hideUnitLabel = document.createElement('label');
      hideUnitLabel.className = 'form-check form-switch mt-2 mb-0';
      hideUnitLabel.innerHTML = '<input class="form-check-input" type="checkbox" id="shopping-print-override-hide-unit">' +
        '<span class="form-check-label">Hide unit for this item</span>';
      col.appendChild(hideUnitLabel);
    }

    if (!$('shopping-print-override-hide-quantity')) {
      var hideQtyLabel = document.createElement('label');
      hideQtyLabel.className = 'form-check form-switch mt-2 mb-0';
      hideQtyLabel.innerHTML = '<input class="form-check-input" type="checkbox" id="shopping-print-override-hide-quantity">' +
        '<span class="form-check-label">Hide quantity and unit for this item</span>';
      col.appendChild(hideQtyLabel);
    }
  }

  function syncQuantityDependencies() {
    var hideQty = $('shopping-print-override-hide-quantity');
    var hideUnit = $('shopping-print-override-hide-unit');
    var qty = $('shopping-print-override-qty');
    var unit = $('shopping-print-override-unit');
    var quantityHidden = !!(hideQty && hideQty.checked);
    if (hideUnit) {
      if (quantityHidden) hideUnit.checked = true;
      hideUnit.disabled = quantityHidden;
    }
    if (qty) qty.disabled = quantityHidden;
    if (unit) unit.disabled = quantityHidden || !!(hideUnit && hideUnit.checked);
  }

  function ensureHeaderConnect() {
    var source = $('shopping-print-connect');
    var row = document.querySelector('.page-header .col-auto.btn-list');
    if (!source || !row) return null;
    source.classList.add('d-none');
    var button = $('shopping-print-connect-header');
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.id = 'shopping-print-connect-header';
      button.className = 'btn btn-outline-primary';
      var print = $('shopping-print-button');
      if (print) row.insertBefore(button, print);
      else row.appendChild(button);
      button.addEventListener('click', function () {
        source.click();
        window.setTimeout(syncHeaderConnect, 50);
        window.setTimeout(syncHeaderConnect, 1000);
      });
    }
    return button;
  }

  function syncHeaderConnect() {
    var source = $('shopping-print-connect');
    var button = $('shopping-print-connect-header');
    if (!source || !button) return;
    source.classList.add('d-none');
    button.disabled = source.disabled;
    button.innerHTML = source.innerHTML;
    var disconnecting = /disconnect/i.test(source.textContent || '');
    button.classList.toggle('btn-outline-danger', disconnecting);
    button.classList.toggle('btn-outline-primary', !disconnecting);
  }

  function ensureResetButton() {
    if ($('shopping-print-reset-v31')) return;
    var save = $('shopping-print-save-order');
    var host = save && save.parentElement;
    if (!host) return;
    var button = document.createElement('button');
    button.type = 'button';
    button.id = 'shopping-print-reset-v31';
    button.className = 'btn btn-outline-danger me-auto';
    button.innerHTML = '<i class="ti ti-restore icon"></i> Reset list';
    button.title = 'Reset category order/aliases, print-only entries and item overrides. Print settings are kept.';
    host.insertBefore(button, host.firstChild);
    button.addEventListener('click', async function () {
      var listId = selectedListId();
      if (!listId) return;
      if (!window.confirm('Reset this shopping list to its standard print state? Global print settings will be kept.')) return;
      button.disabled = true;
      try {
        await json('/api/shopping-print/reset-list-v30', {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({list_id:listId})
        });
        window.location.reload();
      } catch (error) {
        window.alert('Could not reset shopping list: ' + error.message);
        button.disabled = false;
      }
    });
  }

  function selectedRadio(name, fallback) {
    var input = document.querySelector('input[name="' + name + '"]:checked');
    return input ? input.value : fallback;
  }

  function settingsPayload() {
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

  function settingsStatus(text, tone) {
    var el = $('shopping-print-settings-status');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'form-hint' + (tone ? ' text-' + tone : '');
  }

  async function saveSettings() {
    if (!settingsReady) return;
    settingsStatus('Saving automatically…', 'secondary');
    try {
      var data = await json('/api/shopping-print/settings', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(settingsPayload())
      });
      if (data.settings && $('sp-top-margin')) {
        $('sp-top-margin').value = data.settings.top_margin_mm == null ? $('sp-top-margin').value : data.settings.top_margin_mm;
      }
      settingsStatus('Saved automatically.', 'success');
      window.setTimeout(function () {
        var el = $('shopping-print-settings-status');
        if (el && el.textContent === 'Saved automatically.') el.textContent = '';
      }, 1600);
    } catch (error) {
      settingsStatus(error.message, 'danger');
    }
  }

  function scheduleSettingsSave() {
    if (!settingsReady) return;
    window.clearTimeout(saveTimer);
    settingsStatus('Unsaved changes…', 'yellow');
    saveTimer = window.setTimeout(saveSettings, 450);
  }

  function installAutosave() {
    var saveButton = $('shopping-print-save-settings');
    if (saveButton) saveButton.classList.add('d-none');
    var selector = [
      '#sp-width','#sp-margin','#sp-top-margin','#sp-font','#sp-line-gap','#sp-category-gap','#sp-bottom-margin',
      '#sp-density','#sp-threshold','#sp-dpi','#sp-label-type','#sp-show-items','#sp-show-quantities',
      '#sp-show-item-dividers','#sp-show-category-dividers','input[name="sp-category-divider-style"]',
      'input[name="sp-item-marker-style"]'
    ].join(',');
    document.querySelectorAll(selector).forEach(function (input) {
      if (input.dataset.b2mV31Autosave === '1') return;
      input.dataset.b2mV31Autosave = '1';
      input.addEventListener('input', function () {
        if (input.id === 'sp-top-margin' || input.id === 'sp-margin' || input.id === 'sp-dpi') applyTopMargin();
        scheduleSettingsSave();
      });
      input.addEventListener('change', function () {
        if (input.id === 'sp-top-margin' || input.id === 'sp-margin' || input.id === 'sp-dpi') applyTopMargin();
        scheduleSettingsSave();
      });
    });
  }

  function cloneCanvas(canvas) {
    var copy = document.createElement('canvas');
    copy.width = canvas.width;
    copy.height = canvas.height;
    copy.getContext('2d').drawImage(canvas, 0, 0);
    return copy;
  }

  function applyTopMargin() {
    var canvas = $('shopping-print-canvas');
    if (!canvas || !rawCanvas || !rawCanvas.width || !rawCanvas.height) return;
    var dpi = Math.max(100, Number(($('sp-dpi') || {}).value || 300));
    var desired = Math.max(0, Number(($('sp-top-margin') || {}).value || 0));
    var legacy = Math.max(0, Number(($('sp-margin') || {}).value || 0));
    var delta = Math.round((desired - legacy) * dpi / 25.4);
    var newHeight = Math.max(1, rawCanvas.height + delta);
    canvas.width = rawCanvas.width;
    canvas.height = newHeight;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (delta >= 0) {
      ctx.drawImage(rawCanvas, 0, delta);
    } else {
      var crop = Math.min(rawCanvas.height - 1, -delta);
      ctx.drawImage(rawCanvas, 0, crop, rawCanvas.width, rawCanvas.height - crop, 0, 0, rawCanvas.width, rawCanvas.height - crop);
    }
    adjustedHeightPx = canvas.height;
    adjustedHeightMm = (canvas.height / dpi * 25.4).toFixed(2);
    canvas.dataset.heightMm = adjustedHeightMm;
    var badge = $('shopping-print-paper-size');
    if (badge) {
      var width = Number(($('sp-width') || {}).value || 50);
      badge.textContent = width.toFixed(1).replace('.0','') + ' mm × ' + Number(adjustedHeightMm).toFixed(1) + ' mm';
    }
  }

  function captureRenderedReceipt() {
    var canvas = $('shopping-print-canvas');
    if (!canvas || !canvas.width || !canvas.height || !canvas.dataset.heightMm) return;
    var currentMm = String(canvas.dataset.heightMm || '');
    if (currentMm === adjustedHeightMm && canvas.height === adjustedHeightPx) return;
    rawCanvas = cloneCanvas(canvas);
    applyTopMargin();
  }

  async function loadOverridePayload(force) {
    var listId = selectedListId();
    if (!listId) {
      overridePayload = null;
      overridePayloadListId = '';
      return null;
    }
    if (!force && overridePayload && overridePayloadListId === listId) return overridePayload;
    overridePayload = await json('/api/shopping-print/lists/' + encodeURIComponent(listId) + '?_=' + Date.now());
    overridePayloadListId = listId;
    return overridePayload;
  }

  async function syncOverrideFlags() {
    var key = selectedOverrideKey();
    var hideUnit = $('shopping-print-override-hide-unit');
    var hideQty = $('shopping-print-override-hide-quantity');
    if (!key) {
      if (hideUnit) hideUnit.checked = false;
      if (hideQty) hideQty.checked = false;
      syncQuantityDependencies();
      return;
    }
    try {
      var payload = await loadOverridePayload(true);
      var saved = (payload.item_overrides || []).find(function (row) { return String(row.key || '') === key; }) || {};
      if (hideQty) hideQty.checked = !!saved.hide_quantity;
      if (hideUnit) hideUnit.checked = !!saved.hide_unit || !!saved.hide_quantity;
    } catch (e) {
      if (hideQty) hideQty.checked = false;
      if (hideUnit) hideUnit.checked = false;
    }
    syncQuantityDependencies();
  }

  async function saveOverrideV31(button) {
    var listId = selectedListId();
    var key = selectedOverrideKey();
    if (!listId || !key) return;
    var status = $('shopping-print-override-status');
    button.disabled = true;
    if (status) { status.textContent = 'Saving override…'; status.className = 'form-hint text-secondary'; }
    try {
      var payload = await loadOverridePayload(true);
      var item = (payload.items || []).find(function (row) { return String(row.override_key || '') === key; }) || {};
      var hideQty = !!($('shopping-print-override-hide-quantity') && $('shopping-print-override-hide-quantity').checked);
      var hideUnit = hideQty || !!($('shopping-print-override-hide-unit') && $('shopping-print-override-hide-unit').checked);
      var data = await json('/api/shopping-print/item-overrides-v30', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          list_id:listId,
          key:key,
          name_alias:String(($('shopping-print-override-name') || {}).value || '').trim(),
          quantity_alias:hideQty ? '' : String(($('shopping-print-override-qty') || {}).value || '').trim(),
          unit_alias:hideQty ? '' : String(($('shopping-print-override-unit') || {}).value || '').trim(),
          hide_unit:hideUnit,
          hide_quantity:hideQty,
          source_name:item.original_name || item.name || key,
          source_quantity_text:item.original_quantity_value_text || item.quantity_value_text || '',
          source_unit_text:item.original_unit_text || item.unit_text || ''
        })
      });
      overridePayload = Object.assign({}, payload, {item_overrides:data.item_overrides || []});
      if (status) { status.textContent = 'Override saved.'; status.className = 'form-hint text-success'; }
      var refresh = $('shopping-print-refresh');
      if (refresh) refresh.click();
      window.setTimeout(syncOverrideFlags, 200);
    } catch (error) {
      if (status) { status.textContent = error.message; status.className = 'form-hint text-danger'; }
    } finally {
      button.disabled = false;
    }
  }

  var topMargin = ensureTopMarginControl();
  ensureOverrideControls();
  ensureHeaderConnect();
  ensureResetButton();
  syncQuantityDependencies();
  installAutosave();
  syncHeaderConnect();

  var hideUnit = $('shopping-print-override-hide-unit');
  var hideQty = $('shopping-print-override-hide-quantity');
  if (hideUnit) hideUnit.addEventListener('change', syncQuantityDependencies);
  if (hideQty) hideQty.addEventListener('change', syncQuantityDependencies);

  var overrideSelect = $('shopping-print-override-item');
  if (overrideSelect) overrideSelect.addEventListener('change', function () { window.setTimeout(syncOverrideFlags, 0); });
  var listSelect = $('shopping-print-list');
  if (listSelect) listSelect.addEventListener('change', function () {
    overridePayload = null;
    overridePayloadListId = '';
    window.setTimeout(syncOverrideFlags, 150);
  });
  var refresh = $('shopping-print-refresh');
  if (refresh) refresh.addEventListener('click', function () {
    overridePayload = null;
    overridePayloadListId = '';
    window.setTimeout(syncHeaderConnect, 900);
  });

  // Capture phase replaces the older target listener with the v31 override
  // endpoint, without adding another controller or DOM observer.
  document.addEventListener('click', function (event) {
    var button = event.target && event.target.closest && event.target.closest('#shopping-print-override-save');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    saveOverrideV31(button);
  }, true);

  function acceptBootstrapSettings(data) {
    var settings = data && data.settings || {};
    if (topMargin) topMargin.value = settings.top_margin_mm == null ? '2.2' : String(settings.top_margin_mm);
    settingsReady = true;
    window.setTimeout(syncHeaderConnect, 0);
    window.setTimeout(captureRenderedReceipt, 0);
  }

  // shopping-print-v2 still asks for the legacy bootstrap URL. Redirect only
  // that request to the bounded startup endpoint. No second bootstrap is sent.
  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : '';
    var isBootstrap = false;
    if (url) {
      try {
        var parsed = new URL(url, window.location.href);
        if (parsed.pathname === '/api/shopping-print/bootstrap') {
          parsed.pathname = '/api/shopping-print/bootstrap-v31';
          input = parsed.pathname + parsed.search;
          isBootstrap = true;
        }
      } catch (e) { /* keep original request */ }
    }
    return nativeFetch(input, init).then(function (response) {
      if (isBootstrap) {
        response.clone().json().then(acceptBootstrapSettings).catch(function () { settingsReady = true; });
      }
      return response;
    });
  };

  // Polling here is deliberately low-cost and observer-free. It only mirrors
  // the hidden canonical connect button and notices when shopping-print-v2 has
  // redrawn the receipt canvas. It does not fetch or mutate list state.
  window.setInterval(function () {
    syncHeaderConnect();
    captureRenderedReceipt();
  }, 120);
})();
