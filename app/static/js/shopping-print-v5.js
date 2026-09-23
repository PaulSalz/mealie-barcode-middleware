(function () {
  'use strict';
  if (window.location.pathname !== '/shopping-print') return;

  function boot() {
    var itemSelect = document.getElementById('shopping-print-override-item');
    var nameInput = document.getElementById('shopping-print-override-name');
    var qtyInput = document.getElementById('shopping-print-override-qty');
    var saveButton = document.getElementById('shopping-print-override-save');
    var status = document.getElementById('shopping-print-override-status');
    var overrideList = document.getElementById('shopping-print-overrides-list');
    var listSelect = document.getElementById('shopping-print-list');
    var dividerSelect = document.getElementById('sp-category-divider-style');
    var dividerEnabled = document.getElementById('sp-show-category-dividers');
    var localAdd = document.getElementById('shopping-print-local-add');
    var localEntries = document.getElementById('shopping-print-local-entries');
    var localSave = document.getElementById('shopping-print-save-local');

    if (!itemSelect || !nameInput || !qtyInput) return;

    /* Add a dedicated unit override without changing Mealie data. */
    var qtyCol = qtyInput.closest('[class*="col-sm-"]');
    var nameCol = nameInput.closest('[class*="col-sm-"]');
    var unitInput = document.getElementById('shopping-print-override-unit');
    if (!unitInput && qtyCol && qtyCol.parentElement) {
      if (nameCol) nameCol.className = 'col-sm-6';
      qtyCol.className = 'col-sm-3';
      var unitCol = document.createElement('div');
      unitCol.className = 'col-sm-3';
      unitCol.innerHTML =
        '<label class="form-label" for="shopping-print-override-unit">Printed unit</label>' +
        '<input class="form-control" id="shopping-print-override-unit" maxlength="60" placeholder="Keep unit">';
      qtyCol.insertAdjacentElement('afterend', unitCol);
      unitInput = document.getElementById('shopping-print-override-unit');
    }

    var draft = {key: '', name: '', qty: '', unit: '', dirty: false};
    var restoring = false;
    var valueDescriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    var nativeFetch = window.fetch.bind(window);
    var latestPayload = null;
    var overrideRefreshId = 0;

    function selectedKey() {
      return String(itemSelect.value || '');
    }

    function setOverrideStatus(text, tone) {
      if (!status) return;
      status.textContent = text || '';
      status.className = 'form-hint' + (tone ? ' text-' + tone : '');
    }

    function guardProgrammaticValue(input) {
      if (!input || !valueDescriptor || !valueDescriptor.get || !valueDescriptor.set) return;
      Object.defineProperty(input, 'value', {
        configurable: true,
        enumerable: valueDescriptor.enumerable,
        get: function () { return valueDescriptor.get.call(this); },
        set: function (value) {
          if (!restoring && draft.dirty && draft.key && selectedKey() === draft.key) return;
          valueDescriptor.set.call(this, value);
        }
      });
    }

    guardProgrammaticValue(nameInput);
    guardProgrammaticValue(qtyInput);
    guardProgrammaticValue(unitInput);

    function rawSet(input, value) {
      if (!input) return;
      if (!valueDescriptor || !valueDescriptor.set) {
        input.value = value;
        return;
      }
      valueDescriptor.set.call(input, value);
    }

    function captureDraft(markStatus) {
      if (restoring) return;
      draft.key = selectedKey();
      draft.name = nameInput.value;
      draft.qty = qtyInput.value;
      draft.unit = unitInput ? unitInput.value : '';
      draft.dirty = !!draft.key;
      if (markStatus && draft.key) setOverrideStatus('Unsaved override changes.', 'yellow');
    }

    function clearDraft() {
      draft.key = selectedKey();
      draft.name = nameInput.value;
      draft.qty = qtyInput.value;
      draft.unit = unitInput ? unitInput.value : '';
      draft.dirty = false;
    }

    function restoreDraft() {
      if (!draft.dirty || !draft.key || selectedKey() !== draft.key) return;
      restoring = true;
      if (nameInput.value !== draft.name) rawSet(nameInput, draft.name);
      if (qtyInput.value !== draft.qty) rawSet(qtyInput, draft.qty);
      if (unitInput && unitInput.value !== draft.unit) rawSet(unitInput, draft.unit);
      restoring = false;
    }

    function currentOverride() {
      if (!latestPayload) return null;
      var key = selectedKey();
      return (latestPayload.item_overrides || []).find(function (row) {
        return String(row.key || '') === key;
      }) || null;
    }

    function currentItem() {
      if (!latestPayload) return null;
      var key = selectedKey();
      return (latestPayload.items || []).find(function (row) {
        return String(row.override_key || '') === key;
      }) || null;
    }

    function renderOverrideMetadata() {
      if (!latestPayload) return;
      var saved = currentOverride();
      if (unitInput && (!draft.dirty || draft.key !== selectedKey())) {
        restoring = true;
        rawSet(unitInput, saved ? (saved.unit_alias || '') : '');
        restoring = false;
      }

      if (!overrideList) return;
      var byKey = {};
      (latestPayload.item_overrides || []).forEach(function (row) { byKey[String(row.key)] = row; });
      overrideList.querySelectorAll('[data-override-key]').forEach(function (node) {
        var row = byKey[String(node.dataset.overrideKey || '')];
        if (!row) return;
        var parts = [];
        if (row.name_alias) parts.push('name → ' + row.name_alias);
        if (row.quantity_alias) parts.push('quantity → ' + row.quantity_alias);
        if (row.unit_alias) parts.push('unit → ' + row.unit_alias);
        if (!row.active) parts.push('currently not open');
        var meta = node.querySelector('.text-secondary.small');
        if (meta) meta.textContent = parts.join(' · ');
      });
    }

    async function refreshOverrideData() {
      if (!listSelect || !listSelect.value) return;
      var id = ++overrideRefreshId;
      try {
        var response = await nativeFetch('/api/shopping-print/lists/' + encodeURIComponent(listSelect.value) + '?_=' + Date.now(), {
          headers: {Accept: 'application/json', 'Cache-Control': 'no-cache'},
          cache: 'no-store'
        });
        if (!response.ok) return;
        var data = await response.json();
        if (id !== overrideRefreshId) return;
        latestPayload = data;
        renderOverrideMetadata();
      } catch (error) {}
    }

    itemSelect.addEventListener('change', function () {
      draft = {key: selectedKey(), name: '', qty: '', unit: '', dirty: false};
      setOverrideStatus('', '');
      window.setTimeout(function () {
        clearDraft();
        refreshOverrideData();
      }, 0);
    });
    nameInput.addEventListener('input', function () { captureDraft(true); });
    qtyInput.addEventListener('input', function () { captureDraft(true); });
    if (unitInput) unitInput.addEventListener('input', function () { captureDraft(true); });

    if (saveButton) {
      saveButton.addEventListener('click', function () { captureDraft(false); }, true);
    }

    /* Add the unit field to the existing save request. The main shopping-print
       code remains the single owner of save/reload/status behavior. */
    window.fetch = function (input, init) {
      var url = typeof input === 'string' ? input : (input && input.url) || '';
      if (url === '/api/shopping-print/item-overrides' && init && String(init.method || 'GET').toUpperCase() === 'POST') {
        try {
          var body = JSON.parse(init.body || '{}');
          var item = currentItem();
          body.unit_alias = unitInput ? unitInput.value : '';
          body.source_unit_text = item ? (item.original_unit_text || '') : '';
          init = Object.assign({}, init, {body: JSON.stringify(body)});
        } catch (error) {}
      }
      return nativeFetch(input, init);
    };

    /* The main page refreshes from Mealie every 2.5 s and rewrites the editor.
       Reject those writes while the user has an unsaved draft. */
    window.setInterval(restoreDraft, 80);

    if (status) {
      new MutationObserver(function () {
        var text = String(status.textContent || '');
        if (/Override saved|Override removed/i.test(text)) {
          if (unitInput && unitInput.value.trim() && /Override removed/i.test(text)) {
            setOverrideStatus('Override saved for this shopping list.', 'success');
          }
          window.setTimeout(function () {
            clearDraft();
            refreshOverrideData();
          }, 120);
        }
      }).observe(status, {childList: true, characterData: true, subtree: true});
    }

    if (overrideList) {
      new MutationObserver(function () {
        renderOverrideMetadata();
      }).observe(overrideList, {childList: true, subtree: true});
    }

    /* Keep print-only entries durable immediately. Add/remove still updates the
       main in-memory state first; this listener then uses the existing Save path. */
    function scheduleLocalSave() {
      if (!localSave) return;
      window.setTimeout(function () {
        if (!localSave.disabled) localSave.click();
      }, 40);
    }
    if (localAdd) localAdd.addEventListener('click', scheduleLocalSave);
    if (localEntries) {
      localEntries.addEventListener('click', function (event) {
        if (event.target.closest('[data-local-remove]')) scheduleLocalSave();
      });
    }

    function installDividerButtons() {
      if (!dividerSelect || document.getElementById('b2m-category-divider-buttons')) return;
      dividerSelect.classList.add('d-none');
      dividerSelect.setAttribute('aria-hidden', 'true');

      var group = document.createElement('div');
      group.id = 'b2m-category-divider-buttons';
      group.className = 'form-selectgroup d-flex flex-row flex-nowrap gap-2';
      group.innerHTML =
        '<label class="form-selectgroup-item flex-fill">' +
          '<input type="radio" class="form-selectgroup-input" name="b2m-category-divider-choice" value="solid">' +
          '<span class="form-selectgroup-label text-center"><span class="b2m-divider-sample"></span>Solid</span>' +
        '</label>' +
        '<label class="form-selectgroup-item flex-fill">' +
          '<input type="radio" class="form-selectgroup-input" name="b2m-category-divider-choice" value="dashed">' +
          '<span class="form-selectgroup-label text-center"><span class="b2m-divider-sample is-dashed"></span>Dashed</span>' +
        '</label>';
      dividerSelect.insertAdjacentElement('afterend', group);

      function syncFromSelect() {
        var wanted = dividerSelect.value === 'dashed' ? 'dashed' : 'solid';
        var radio = group.querySelector('input[value="' + wanted + '"]');
        if (radio && !radio.checked) radio.checked = true;
        var disabled = !!dividerSelect.disabled || !!(dividerEnabled && !dividerEnabled.checked);
        group.classList.toggle('opacity-50', disabled);
        group.querySelectorAll('input').forEach(function (input) { input.disabled = disabled; });
      }

      group.addEventListener('change', function (event) {
        var radio = event.target.closest('input[name="b2m-category-divider-choice"]');
        if (!radio || !radio.checked) return;
        dividerSelect.value = radio.value;
        dividerSelect.dispatchEvent(new Event('change', {bubbles: true}));
        syncFromSelect();
      });

      dividerSelect.addEventListener('change', syncFromSelect);
      if (dividerEnabled) dividerEnabled.addEventListener('change', function () { window.setTimeout(syncFromSelect, 0); });
      new MutationObserver(syncFromSelect).observe(dividerSelect, {attributes: true, attributeFilter: ['disabled']});
      window.setInterval(syncFromSelect, 350);
      syncFromSelect();
    }

    function installNamedLabelTypes() {
      var field = document.getElementById('sp-label-type');
      if (!field || field.tagName === 'SELECT') return;
      var current = String(field.value || '3');
      var select = document.createElement('select');
      select.className = 'form-select';
      select.id = 'sp-label-type';
      select.innerHTML = [
        ['1', 'Gap / die-cut'],
        ['2', 'Black mark'],
        ['3', 'Continuous'],
        ['4', 'Perforated'],
        ['5', 'Transparent'],
        ['6', 'PVC tag'],
        ['10', 'Black mark + gap'],
        ['11', 'Heat-shrink tube']
      ].map(function (row) {
        return '<option value="' + row[0] + '">' + row[1] + '</option>';
      }).join('');
      select.value = current;
      field.replaceWith(select);
    }

    installDividerButtons();
    installNamedLabelTypes();
    refreshOverrideData();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
