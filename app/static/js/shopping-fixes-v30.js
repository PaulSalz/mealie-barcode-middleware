/* v2026.09.23.30 — exact receipt top margin, stable drafts, quantity hide and list reset. */
(function () {
  'use strict';
  if (window.location.pathname !== '/shopping-print' || window.__b2mShoppingV30Loaded) return;
  window.__b2mShoppingV30Loaded = true;

  function $(id) { return document.getElementById(id); }
  async function json(url, options) {
    var response = await fetch(url, Object.assign({headers:{Accept:'application/json'}, cache:'no-store'}, options || {}));
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.error || data.detail || ('HTTP ' + response.status));
    return data;
  }

  var aliasDrafts = Object.create(null);
  var rawCanvas = null;
  var adjustedHeightMm = '';
  var applyingCanvas = false;
  var overrideCache = [];

  function selectedListId() { return String(($('shopping-print-list') || {}).value || ''); }
  function selectedOverrideKey() { return String(($('shopping-print-override-item') || {}).value || ''); }

  function hideSecondaryConnect() {
    var source = $('shopping-print-connect');
    if (source) source.classList.add('d-none');
  }

  function ensureQuantityHide() {
    var unit = $('shopping-print-override-hide-unit');
    if (!unit || $('shopping-print-override-hide-quantity')) return;
    var holder = unit.closest('.form-check') || unit.parentElement;
    if (!holder || !holder.parentElement) return;
    var label = document.createElement('label');
    label.className = 'form-check form-switch mt-2';
    label.innerHTML = '<input class="form-check-input" type="checkbox" id="shopping-print-override-hide-quantity">' +
      '<span class="form-check-label">Hide quantity and unit for this item</span>';
    holder.parentElement.insertBefore(label, holder);
  }

  function ensureV30OverrideSave() {
    var old = $('shopping-print-override-save');
    if (!old || $('shopping-print-override-save-v30')) return;
    old.classList.add('d-none');
    var button = document.createElement('button');
    button.type = 'button';
    button.id = 'shopping-print-override-save-v30';
    button.className = old.className.replace(/\bd-none\b/g, '').trim() || 'btn btn-primary';
    button.innerHTML = old.innerHTML || '<i class="ti ti-device-floppy icon"></i> Save override';
    old.insertAdjacentElement('afterend', button);
    button.addEventListener('click', saveOverrideV30);
  }

  async function loadOverrideCache() {
    var listId = selectedListId();
    if (!listId) { overrideCache = []; return; }
    try {
      var data = await json('/api/shopping-print/lists/' + encodeURIComponent(listId) + '?_=' + Date.now());
      overrideCache = Array.isArray(data.item_overrides) ? data.item_overrides : [];
    } catch (e) { overrideCache = []; }
  }

  function syncOverrideFlags() {
    var key = selectedOverrideKey();
    var saved = overrideCache.find(function (row) { return String(row.key) === key; }) || {};
    var hideUnit = $('shopping-print-override-hide-unit');
    var hideQty = $('shopping-print-override-hide-quantity');
    if (hideQty) hideQty.checked = !!saved.hide_quantity;
    if (hideUnit) hideUnit.checked = !!saved.hide_unit || !!saved.hide_quantity;
    syncQuantityDependencies();
  }

  function syncQuantityDependencies() {
    var hideQty = $('shopping-print-override-hide-quantity');
    var hideUnit = $('shopping-print-override-hide-unit');
    var qty = $('shopping-print-override-qty');
    var unit = $('shopping-print-override-unit');
    var hidden = !!(hideQty && hideQty.checked);
    if (hideUnit) {
      if (hidden) hideUnit.checked = true;
      hideUnit.disabled = hidden;
    }
    if (qty) qty.disabled = hidden;
    if (unit) unit.disabled = hidden || !!(hideUnit && hideUnit.checked);
  }

  async function saveOverrideV30() {
    var listId = selectedListId();
    var key = selectedOverrideKey();
    if (!listId || !key) return;
    var select = $('shopping-print-override-item');
    var optionText = select && select.options[select.selectedIndex] ? select.options[select.selectedIndex].textContent : key;
    var current = overrideCache.find(function (row) { return String(row.key) === key; }) || {};
    var button = $('shopping-print-override-save-v30');
    var status = $('shopping-print-override-status');
    if (button) button.disabled = true;
    if (status) { status.textContent = 'Saving override…'; status.className = 'form-hint text-secondary'; }
    try {
      var hideQty = !!($('shopping-print-override-hide-quantity') && $('shopping-print-override-hide-quantity').checked);
      var data = await json('/api/shopping-print/item-overrides-v30', {
        method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'},
        body:JSON.stringify({
          list_id:listId,
          key:key,
          name_alias:String(($('shopping-print-override-name') || {}).value || '').trim(),
          quantity_alias:hideQty ? '' : String(($('shopping-print-override-qty') || {}).value || '').trim(),
          unit_alias:hideQty ? '' : String(($('shopping-print-override-unit') || {}).value || '').trim(),
          hide_unit:hideQty || !!($('shopping-print-override-hide-unit') && $('shopping-print-override-hide-unit').checked),
          hide_quantity:hideQty,
          source_name:current.source_name || optionText,
          source_quantity_text:current.source_quantity_text || '',
          source_unit_text:current.source_unit_text || ''
        })
      });
      overrideCache = Array.isArray(data.item_overrides) ? data.item_overrides : overrideCache;
      if (status) { status.textContent = 'Override saved.'; status.className = 'form-hint text-success'; }
      var refresh = $('shopping-print-refresh');
      if (refresh) refresh.click();
      window.setTimeout(syncOverrideFlags, 150);
    } catch (error) {
      if (status) { status.textContent = error.message; status.className = 'form-hint text-danger'; }
    } finally {
      if (button) button.disabled = false;
    }
  }

  function aliasKeyForInput(input) {
    var row = input && input.closest('.shopping-print-category-row');
    var original = row && row.querySelector('.shopping-print-category-original');
    return String(original && original.textContent || '').trim().toLowerCase();
  }

  function restoreAliasDrafts() {
    document.querySelectorAll('.shopping-print-category-alias').forEach(function (input) {
      var key = aliasKeyForInput(input);
      if (key && Object.prototype.hasOwnProperty.call(aliasDrafts, key) && input.value !== aliasDrafts[key]) {
        input.value = aliasDrafts[key];
      }
    });
  }

  function installAliasDraftProtection() {
    var order = $('shopping-print-category-order');
    if (!order || order.dataset.b2mV30Drafts === '1') return;
    order.dataset.b2mV30Drafts = '1';
    order.addEventListener('input', function (event) {
      var input = event.target.closest('.shopping-print-category-alias');
      if (!input) return;
      var key = aliasKeyForInput(input);
      if (key) aliasDrafts[key] = input.value;
    });
    new MutationObserver(function () { window.requestAnimationFrame(restoreAliasDrafts); })
      .observe(order, {childList:true, subtree:true});

    var save = $('shopping-print-save-order');
    if (save) save.addEventListener('click', function () {
      restoreAliasDrafts();
      document.querySelectorAll('.shopping-print-category-alias').forEach(function (input) {
        input.dispatchEvent(new Event('input', {bubbles:true}));
      });
    }, true);

    var status = $('shopping-print-order-status');
    if (status) new MutationObserver(function () {
      if (/saved globally/i.test(status.textContent || '')) aliasDrafts = Object.create(null);
    }).observe(status, {childList:true, characterData:true, subtree:true});
  }

  function cloneRawCanvas(canvas) {
    var copy = document.createElement('canvas');
    copy.width = canvas.width;
    copy.height = canvas.height;
    copy.getContext('2d').drawImage(canvas, 0, 0);
    return copy;
  }

  function captureRawReceipt() {
    var canvas = $('shopping-print-canvas');
    if (!canvas || applyingCanvas || !canvas.width || !canvas.height) return;
    var currentMm = String(canvas.dataset.heightMm || '');
    if (currentMm && currentMm === adjustedHeightMm) return;
    rawCanvas = cloneRawCanvas(canvas);
    rawCanvas.dataset.heightMm = currentMm;
    applyExactTopMargin();
  }

  function applyExactTopMargin() {
    var canvas = $('shopping-print-canvas');
    if (!canvas || !rawCanvas || applyingCanvas) return;
    applyingCanvas = true;
    try {
      var dpi = Math.max(100, Number(($('sp-dpi') || {}).value || 300));
      var desiredTopMm = Math.max(0, Number(($('sp-top-margin') || {}).value || 0));
      // shopping-print-v2 historically used the side margin as its top margin.
      // Replace that blank area instead of adding another margin on top of it.
      var legacyTopMm = Math.max(0, Number(($('sp-margin') || {}).value || 0));
      var deltaPx = Math.round((desiredTopMm - legacyTopMm) * dpi / 25.4);
      var newHeight = Math.max(1, rawCanvas.height + deltaPx);
      canvas.width = rawCanvas.width;
      canvas.height = newHeight;
      var ctx = canvas.getContext('2d');
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      if (deltaPx >= 0) {
        ctx.drawImage(rawCanvas, 0, deltaPx);
      } else {
        var crop = Math.min(rawCanvas.height - 1, -deltaPx);
        ctx.drawImage(rawCanvas, 0, crop, rawCanvas.width, rawCanvas.height - crop, 0, 0, rawCanvas.width, rawCanvas.height - crop);
      }
      var heightMm = canvas.height / dpi * 25.4;
      adjustedHeightMm = heightMm.toFixed(2);
      canvas.dataset.heightMm = adjustedHeightMm;
      canvas.style.marginTop = '';
      canvas.style.paddingTop = '';
      canvas.style.borderTop = '';
      canvas.toDataURL = function () {
        return HTMLCanvasElement.prototype.toDataURL.apply(canvas, arguments);
      };
      var badge = $('shopping-print-paper-size');
      if (badge) {
        var width = Number(($('sp-width') || {}).value || 50);
        badge.textContent = width.toFixed(1).replace('.0','') + ' mm × ' + heightMm.toFixed(1) + ' mm';
      }
    } finally {
      applyingCanvas = false;
    }
  }

  function installExactTopMargin() {
    var canvas = $('shopping-print-canvas');
    if (!canvas || canvas.dataset.b2mV30Top === '1') return;
    canvas.dataset.b2mV30Top = '1';
    // v29 wrapped toDataURL and added a second top margin only at print time.
    // v30 modifies the real preview canvas instead, so export and preview match.
    canvas.toDataURL = function () { return HTMLCanvasElement.prototype.toDataURL.apply(canvas, arguments); };
    canvas.style.marginTop = '';
    rawCanvas = cloneRawCanvas(canvas);
    rawCanvas.dataset.heightMm = String(canvas.dataset.heightMm || '');
    applyExactTopMargin();

    new MutationObserver(function (mutations) {
      // Never observe style here: clearing the legacy v29 CSS margin from a
      // style observer schedules another style mutation and can starve the
      // shopping-list loader in an endless MutationObserver microtask loop.
      if (canvas.style.marginTop) canvas.style.marginTop = '';
      var external = mutations.some(function (m) {
        return m.attributeName === 'data-height-mm' && String(canvas.dataset.heightMm || '') !== adjustedHeightMm;
      });
      if (external) window.setTimeout(captureRawReceipt, 0);
    }).observe(canvas, {attributes:true, attributeFilter:['width','height','data-height-mm']});

    ['sp-top-margin','sp-margin','sp-dpi'].forEach(function (id) {
      var input = $(id);
      if (!input) return;
      ['input','change'].forEach(function (name) {
        input.addEventListener(name, function () { window.setTimeout(applyExactTopMargin, 30); });
      });
    });
  }

  function ensureResetButton() {
    if ($('shopping-print-reset-v30')) return;
    var saveOrder = $('shopping-print-save-order');
    var host = saveOrder && saveOrder.parentElement;
    if (!host) return;
    var button = document.createElement('button');
    button.type = 'button';
    button.id = 'shopping-print-reset-v30';
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
          method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'},
          body:JSON.stringify({list_id:listId})
        });
        aliasDrafts = Object.create(null);
        window.location.reload();
      } catch (error) {
        window.alert('Could not reset shopping list: ' + error.message);
        button.disabled = false;
      }
    });
  }

  function bindOverrideControls() {
    ensureQuantityHide();
    ensureV30OverrideSave();
    var select = $('shopping-print-override-item');
    var hideUnit = $('shopping-print-override-hide-unit');
    var hideQty = $('shopping-print-override-hide-quantity');
    if (select && select.dataset.b2mV30Flags !== '1') {
      select.dataset.b2mV30Flags = '1';
      select.addEventListener('change', function () { window.setTimeout(syncOverrideFlags, 0); });
    }
    if (hideUnit) hideUnit.addEventListener('change', syncQuantityDependencies);
    if (hideQty) hideQty.addEventListener('change', syncQuantityDependencies);
    loadOverrideCache().then(syncOverrideFlags);
  }

  function boot() {
    hideSecondaryConnect();
    installAliasDraftProtection();
    installExactTopMargin();
    ensureResetButton();
    bindOverrideControls();

    var list = $('shopping-print-list');
    if (list) list.addEventListener('change', function () {
      aliasDrafts = Object.create(null);
      window.setTimeout(function () { loadOverrideCache().then(syncOverrideFlags); }, 100);
    });

    // The v29 code may rebuild a few controls after initial load.
    new MutationObserver(function () {
      hideSecondaryConnect();
      ensureQuantityHide();
      ensureV30OverrideSave();
      ensureResetButton();
      restoreAliasDrafts();
    }).observe(document.body, {childList:true, subtree:true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { window.setTimeout(boot, 80); }, {once:true});
  else window.setTimeout(boot, 80);
})();
