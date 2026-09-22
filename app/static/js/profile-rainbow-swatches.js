(function () {
  'use strict';
  if (window.location.pathname !== '/profile/appearance') return;

  var COLORS = ['blue','azure','indigo','purple','pink','red','orange','yellow','lime','green','teal','cyan'];

  function install() {
    var select = document.getElementById('b2m-v24-rainbow-buttons-select');
    if (!select || document.getElementById('b2m-rainbow-button-swatches')) return false;

    select.classList.add('d-none');
    select.setAttribute('aria-hidden', 'true');

    var row = document.createElement('div');
    row.id = 'b2m-rainbow-button-swatches';
    row.className = 'row g-2';

    var options = ['smooth'].concat(COLORS);
    row.innerHTML = options.map(function (value) {
      var title = value === 'smooth' ? 'Smooth rainbow' : 'Fixed ' + value.charAt(0).toUpperCase() + value.slice(1);
      var swatchClass = value === 'smooth' ? 'b2m-rainbow-swatch' : 'bg-' + value;
      return '<div class="col-auto"><label class="form-colorinput" title="' + title + '">' +
        '<input type="radio" name="b2m-rainbow-button-swatch" value="' + value + '" class="form-colorinput-input"' + (select.value === value ? ' checked' : '') + '>' +
        '<span class="form-colorinput-color ' + swatchClass + '"></span>' +
        '</label></div>';
    }).join('');

    select.insertAdjacentElement('afterend', row);

    function syncDisabled() {
      var disabled = !!select.disabled;
      row.classList.toggle('opacity-50', disabled);
      row.querySelectorAll('input').forEach(function (input) { input.disabled = disabled; });
    }

    row.addEventListener('change', function (event) {
      var input = event.target.closest('input[name="b2m-rainbow-button-swatch"]');
      if (!input) return;
      select.value = input.value;
      select.dispatchEvent(new Event('change', {bubbles: true}));
      syncDisabled();
    });

    var observer = new MutationObserver(syncDisabled);
    observer.observe(select, {attributes: true, attributeFilter: ['disabled']});
    document.querySelectorAll('input[name="theme_color"],input[name="theme_epaper"]').forEach(function (input) {
      input.addEventListener('change', function () { window.setTimeout(syncDisabled, 0); });
    });
    syncDisabled();
    return true;
  }

  function boot() {
    if (install()) return;
    var attempts = 0;
    var timer = window.setInterval(function () {
      attempts += 1;
      if (install() || attempts > 40) window.clearInterval(timer);
    }, 50);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
