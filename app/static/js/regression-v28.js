/* v2026.09.23.28: focused regression repairs after the frontend audit cleanup. */
(function () {
  'use strict';

  var root = document.documentElement;
  var appearanceV35 = !!window.__b2mThemeV35Loaded;

  function normaliseText(value) {
    return String(value == null ? '' : value).trim().replace(/\s+/g, ' ').toLocaleLowerCase();
  }

  function forceEnglishOnly() {
    document.querySelectorAll('[data-ui-language]').forEach(function (node) { node.remove(); });
    document.querySelectorAll('.dropdown-header').forEach(function (node) {
      if (/^(language|sprache)$/i.test(node.textContent.trim())) {
        var previous = node.previousElementSibling;
        var next = node.nextElementSibling;
        node.remove();
        if (previous && previous.classList.contains('dropdown-divider')) previous.remove();
        if (next && next.classList.contains('dropdown-divider')) next.remove();
      }
    });

    if ((root.getAttribute('lang') || 'en').toLowerCase().split('-', 1)[0] === 'en') return;
    fetch('/api/ui-language', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
      body: JSON.stringify({language: 'en'})
    }).then(function (response) {
      if (response.ok) window.location.reload();
    }).catch(function () {});
  }

  function removeSettingsSearch() {
    if (window.location.pathname !== '/settings') return;
    var search = document.getElementById('settings-search');
    if (search) {
      search.value = '';
      var column = search.closest('.col-md');
      if (column) column.remove();
      else search.remove();
    }
    var searchState = document.getElementById('settings-search-state');
    if (searchState) searchState.remove();
    var tools = document.getElementById('settings-view-tools');
    if (tools) {
      var row = tools.querySelector('.row');
      if (row) row.classList.add('justify-content-end');
    }
  }

  function radiusScaleFromPage() {
    var value = getComputedStyle(root).getPropertyValue('--tblr-border-radius-scale').trim();
    var parsed = Number(value || '1');
    return Number.isFinite(parsed) ? Math.max(0, Math.min(2, parsed)) : 1;
  }

  function applyRadius(scale) {
    if (appearanceV35) return;
    scale = Number(scale);
    if (!Number.isFinite(scale)) scale = radiusScaleFromPage();
    scale = Math.max(0, Math.min(2, scale));
    root.style.setProperty('--tblr-border-radius-scale', String(scale));
    root.style.setProperty('--tblr-border-radius', (0.25 * scale).toFixed(3).replace(/0+$/, '').replace(/\.$/, '') + 'rem');
    root.style.setProperty('--tblr-border-radius-sm', (0.2 * scale).toFixed(3).replace(/0+$/, '').replace(/\.$/, '') + 'rem');
    root.style.setProperty('--tblr-border-radius-lg', (0.4 * scale).toFixed(3).replace(/0+$/, '').replace(/\.$/, '') + 'rem');
    root.style.setProperty('--tblr-border-radius-xl', (0.5 * scale).toFixed(3).replace(/0+$/, '').replace(/\.$/, '') + 'rem');
  }

  function gray(step) {
    return getComputedStyle(root).getPropertyValue('--tblr-gray-' + step).trim();
  }

  function applyNeutralSurfaces() {
    if (appearanceV35) return;
    if (root.classList.contains('b2m-epaper') || root.classList.contains('b2m-epaper-v9')) return;
    var g50 = gray(50), g100 = gray(100), g200 = gray(200), g400 = gray(400), g600 = gray(600), g700 = gray(700), g800 = gray(800), g900 = gray(900);
    if (!g50 || !g200 || !g800 || !g900) return;
    var dark = root.getAttribute('data-bs-theme') === 'dark';
    root.style.setProperty('--tblr-body-bg', dark ? g900 : g50);
    root.style.setProperty('--tblr-bg-surface-secondary', dark ? g800 : (g100 || g50));
    root.style.setProperty('--tblr-secondary-bg', dark ? g800 : (g100 || g50));
    root.style.setProperty('--tblr-border-color', dark ? (g700 || g800) : g200);
    root.style.setProperty('--tblr-secondary-color', dark ? (g400 || g200) : (g600 || g700));
  }

  function installAppearanceRepairs() {
    if (appearanceV35) return;
    applyRadius(radiusScaleFromPage());
    applyNeutralSurfaces();

    if (window.location.pathname !== '/profile/appearance') return;
    var form = document.querySelector('form[action="/profile/appearance"]');
    if (!form) return;
    var radius = form.querySelector('[name="theme_radius"]');
    if (radius) {
      radius.addEventListener('input', function () { applyRadius(radius.value); });
      radius.addEventListener('change', function () { applyRadius(radius.value); });
      applyRadius(radius.value);
    }
    function delayedPaletteSync() {
      [60, 180, 420].forEach(function (delay) { window.setTimeout(applyNeutralSurfaces, delay); });
    }
    form.addEventListener('input', delayedPaletteSync);
    form.addEventListener('change', delayedPaletteSync);
  }

  function syncItemsServerSort() {
    if (window.location.pathname !== '/items') return;
    var cfg = document.getElementById('items-page-config');
    if (!cfg) return;
    var mapping = {
      name: 'sort-name',
      category: 'sort-category',
      updated: 'sort-updated',
      last_scan: 'sort-last-scan',
      scans: 'sort-scans',
      barcodes: 'sort-mappings'
    };
    var key = mapping[cfg.dataset.sort || 'name'] || 'sort-name';
    var button = document.querySelector('#items-table .table-sort[data-sort="' + key + '"]');
    if (!button) return;
    var wantAsc = (cfg.dataset.order || 'asc') !== 'desc';
    if (!button.classList.contains('active')) button.click();
    var isAsc = button.classList.contains('asc');
    if (isAsc !== wantAsc) button.click();
  }

  function canonicalShoppingCategory(value) {
    var target = normaliseText(value);
    if (!target) return '';
    var rows = document.querySelectorAll('.shopping-print-category-row');
    for (var i = 0; i < rows.length; i += 1) {
      var originalNode = rows[i].querySelector('.shopping-print-category-original');
      var aliasNode = rows[i].querySelector('.shopping-print-category-alias');
      var original = originalNode ? originalNode.textContent.trim() : '';
      var alias = aliasNode ? aliasNode.value.trim() : '';
      if (normaliseText(original) === target || (alias && normaliseText(alias) === target)) return original;
    }
    return String(value || '').trim().replace(/\s+/g, ' ');
  }

  function installShoppingCategoryRepair() {
    if (window.location.pathname !== '/shopping-print') return;
    document.addEventListener('click', function (event) {
      var button = event.target && event.target.closest && event.target.closest('#shopping-print-local-add');
      if (!button) return;
      var input = document.getElementById('shopping-print-local-category');
      if (!input) return;
      input.value = canonicalShoppingCategory(input.value) || 'Extra';
    }, true);
  }

  function boot() {
    forceEnglishOnly();
    removeSettingsSearch();
    installAppearanceRepairs();
    syncItemsServerSort();
    installShoppingCategoryRepair();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
