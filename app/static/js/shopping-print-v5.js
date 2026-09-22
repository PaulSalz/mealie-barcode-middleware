(function () {
  'use strict';
  if (window.location.pathname !== '/shopping-print') return;

  function boot() {
    var itemSelect = document.getElementById('shopping-print-override-item');
    var nameInput = document.getElementById('shopping-print-override-name');
    var qtyInput = document.getElementById('shopping-print-override-qty');
    var saveButton = document.getElementById('shopping-print-override-save');
    var status = document.getElementById('shopping-print-override-status');
    var dividerSelect = document.getElementById('sp-category-divider-style');
    var dividerEnabled = document.getElementById('sp-show-category-dividers');

    if (!itemSelect || !nameInput || !qtyInput) return;

    var draft = {key: '', name: '', qty: '', dirty: false};
    var restoring = false;

    function selectedKey() {
      return String(itemSelect.value || '');
    }

    function captureDraft() {
      if (restoring) return;
      draft.key = selectedKey();
      draft.name = nameInput.value;
      draft.qty = qtyInput.value;
      draft.dirty = !!draft.key;
    }

    function clearDraft() {
      draft.key = selectedKey();
      draft.name = nameInput.value;
      draft.qty = qtyInput.value;
      draft.dirty = false;
    }

    function restoreDraft() {
      if (!draft.dirty || !draft.key || selectedKey() !== draft.key) return;
      restoring = true;
      if (nameInput.value !== draft.name) nameInput.value = draft.name;
      if (qtyInput.value !== draft.qty) qtyInput.value = draft.qty;
      restoring = false;
    }

    itemSelect.addEventListener('change', function () {
      /* Changing the selected item intentionally switches editor context. */
      window.setTimeout(clearDraft, 0);
    });
    nameInput.addEventListener('input', captureDraft);
    qtyInput.addEventListener('input', captureDraft);

    if (saveButton) {
      saveButton.addEventListener('click', function () {
        captureDraft();
      }, true);
    }

    /* The main page refreshes from Mealie every 2.5 s and rewrites the input
       values from the saved override. Keep an unsaved draft authoritative while
       its item remains selected. */
    window.setInterval(restoreDraft, 80);

    if (status) {
      new MutationObserver(function () {
        var text = String(status.textContent || '');
        if (/Override saved|Override removed/i.test(text)) {
          window.setTimeout(function () {
            restoreDraft();
            clearDraft();
          }, 120);
        }
      }).observe(status, {childList: true, characterData: true, subtree: true});
    }

    function installDividerButtons() {
      if (!dividerSelect || document.getElementById('b2m-category-divider-buttons')) return;
      dividerSelect.classList.add('d-none');
      dividerSelect.setAttribute('aria-hidden', 'true');

      var group = document.createElement('div');
      group.id = 'b2m-category-divider-buttons';
      group.className = 'form-selectgroup';
      group.innerHTML =
        '<label class="form-selectgroup-item">' +
          '<input type="radio" class="form-selectgroup-input" name="b2m-category-divider-choice" value="solid">' +
          '<span class="form-selectgroup-label"><span class="b2m-divider-sample"></span>Solid</span>' +
        '</label>' +
        '<label class="form-selectgroup-item">' +
          '<input type="radio" class="form-selectgroup-input" name="b2m-category-divider-choice" value="dashed">' +
          '<span class="form-selectgroup-label"><span class="b2m-divider-sample is-dashed"></span>Dashed</span>' +
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

    installDividerButtons();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
