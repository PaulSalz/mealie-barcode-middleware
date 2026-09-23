/* v2026.09.23.31 — single-pass Shopping Print bootstrap without the legacy v29 controller. */
(function () {
  'use strict';
  if (window.location.pathname !== '/shopping-print' || window.__b2mShoppingV31Loaded) return;
  window.__b2mShoppingV31Loaded = true;

  function $(id) { return document.getElementById(id); }

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

  function ensureHideUnitControl() {
    var existing = $('shopping-print-override-hide-unit');
    if (existing) return existing;
    var unit = $('shopping-print-override-unit');
    if (!unit) return null;
    var col = unit.closest('[class*="col-"]') || unit.parentElement;
    if (!col) return null;
    var label = document.createElement('label');
    label.className = 'form-check form-switch mt-2 mb-0';
    label.innerHTML = '<input class="form-check-input" type="checkbox" id="shopping-print-override-hide-unit">' +
      '<span class="form-check-label">Hide unit for this item</span>';
    col.appendChild(label);
    return label.querySelector('input');
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
      var disconnecting = /disconnect/i.test(source.textContent || '');
      button.classList.toggle('btn-outline-danger', disconnecting);
      button.classList.toggle('btn-outline-primary', !disconnecting);
    }
    sync();
    if (source.dataset.b2mV31Observed !== '1') {
      source.dataset.b2mV31Observed = '1';
      new MutationObserver(sync).observe(source, {attributes:true, childList:true, subtree:true});
    }
  }

  var topMargin = ensureTopMarginControl();
  ensureHideUnitControl();
  ensureHeaderConnect();

  var settingsReady = false;
  var saveTimer = null;

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
      var response = await window.fetch('/api/shopping-print/settings', {
        method:'POST',
        headers:{'Content-Type':'application/json','Accept':'application/json'},
        body:JSON.stringify(settingsPayload())
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(data.error || data.detail || ('HTTP ' + response.status));
      if (data.settings && topMargin) topMargin.value = data.settings.top_margin_mm == null ? topMargin.value : data.settings.top_margin_mm;
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
      input.addEventListener('input', scheduleSettingsSave);
      input.addEventListener('change', scheduleSettingsSave);
    });
  }
  installAutosave();

  function acceptBootstrapSettings(data) {
    var settings = data && data.settings || {};
    if (topMargin) topMargin.value = settings.top_margin_mm == null ? '2.2' : String(settings.top_margin_mm);
    settingsReady = true;
  }

  // shopping-print-v2 asks for the legacy bootstrap URL. Redirect only that
  // request to a fast bootstrap that never performs /info or RFID calls. The
  // response shape stays identical, so the canonical page controller remains
  // unchanged while page startup is no longer coupled to printer diagnostics.
  var nativeFetch = window.fetch.bind(window);
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
        response.clone().json().then(acceptBootstrapSettings).catch(function () {
          settingsReady = true;
        });
      }
      return response;
    });
  };
})();
