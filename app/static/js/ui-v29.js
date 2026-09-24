/* v2026.09.24.3 — global advanced settings and legacy appearance compatibility. */
(function () {
  'use strict';
  if (window.__b2mUiV29Loaded) return;
  window.__b2mUiV29Loaded = true;

  var root = document.documentElement;
  var CACHE_KEY = 'b2m-global-advanced-v1';
  var advancedEnabled = false;
  var appearanceV35 = !!window.__b2mThemeV35Loaded;

  var PALETTES = {
    gray: {
      50:'#f7f8fa',100:'#eceff3',200:'#d8dde5',300:'#b9c1cc',400:'#8f9aa8',500:'#687483',600:'#4c5765',700:'#37414d',800:'#242c35',900:'#171d24',950:'#0b0f14'
    },
    slate: {
      50:'#f6f8fb',100:'#e8eef6',200:'#d2ddea',300:'#afc0d4',400:'#7f96b0',500:'#5a7390',600:'#405870',700:'#2e4258',800:'#1d2d3e',900:'#111d2a',950:'#08111c'
    },
    zinc: {
      50:'#fafafa',100:'#eeeeef',200:'#d9d9dc',300:'#bdbdc3',400:'#97979f',500:'#707078',600:'#515158',700:'#3a3a40',800:'#25252a',900:'#17171b',950:'#0b0b0e'
    },
    neutral: {
      50:'#fbfbfb',100:'#f0f0f0',200:'#d8d8d8',300:'#b9b9b9',400:'#929292',500:'#6d6d6d',600:'#4f4f4f',700:'#393939',800:'#242424',900:'#151515',950:'#080808'
    },
    stone: {
      50:'#fbf9f6',100:'#f0ebe5',200:'#ddd4ca',300:'#c1b3a4',400:'#9b8977',500:'#796856',600:'#5a4d41',700:'#443a32',800:'#2d2722',900:'#1c1815',950:'#0e0c0a'
    }
  };

  function cachedAdvanced() {
    try { return localStorage.getItem(CACHE_KEY) === '1'; }
    catch (e) { return false; }
  }

  function saveAdvancedCache(enabled) {
    try { localStorage.setItem(CACHE_KEY, enabled ? '1' : '0'); }
    catch (e) {}
  }

  function radiusValue(scale) {
    var map = {'0':0,'0.5':.25,'1':.5,'1.5':.8,'2':1.1};
    var key = String(scale == null ? '1' : scale);
    return Object.prototype.hasOwnProperty.call(map, key) ? map[key] : .5;
  }

  function applyRadius(scale) {
    if (appearanceV35) return;
    var base = radiusValue(scale);
    root.style.setProperty('--tblr-border-radius-scale', String(scale == null ? '1' : scale));
    root.style.setProperty('--tblr-border-radius', base + 'rem');
    root.style.setProperty('--tblr-border-radius-sm', Math.max(0, base * .72) + 'rem');
    root.style.setProperty('--tblr-border-radius-lg', Math.max(0, base * 1.45) + 'rem');
    root.style.setProperty('--tblr-border-radius-xl', Math.max(0, base * 1.9) + 'rem');
  }

  function applyPalette(name) {
    if (appearanceV35) return;
    name = String(name || 'gray').toLowerCase();
    var p = PALETTES[name] || PALETTES.gray;
    root.dataset.b2mBase = name;
    Object.keys(p).forEach(function (step) {
      root.style.setProperty('--tblr-gray-' + step, p[step]);
    });
    if (root.classList.contains('b2m-epaper') || root.classList.contains('b2m-epaper-v9')) return;
    var dark = root.getAttribute('data-bs-theme') === 'dark';
    root.style.setProperty('--tblr-body-bg', dark ? p[950] : p[100]);
    root.style.setProperty('--tblr-bg-surface', dark ? p[900] : p[50]);
    root.style.setProperty('--tblr-bg-surface-secondary', dark ? p[800] : p[200]);
    root.style.setProperty('--tblr-secondary-bg', dark ? p[800] : p[200]);
    root.style.setProperty('--tblr-border-color', dark ? p[700] : p[300]);
    root.style.setProperty('--tblr-secondary-color', dark ? p[400] : p[600]);
    root.style.setProperty('--tblr-body-color', dark ? p[100] : p[900]);
  }

  function syncLegacyAdvancedControls() {
    var settingsToggle = document.getElementById('settings-show-advanced');
    if (settingsToggle && settingsToggle.checked !== advancedEnabled) {
      settingsToggle.checked = advancedEnabled;
      settingsToggle.dispatchEvent(new Event('change', {bubbles: true}));
    }
    var tools = document.getElementById('settings-view-tools');
    if (tools) tools.classList.add('d-none');

    var actionToggle = document.getElementById('action-advanced-toggle');
    if (actionToggle && actionToggle.checked !== advancedEnabled) {
      actionToggle.checked = advancedEnabled;
      actionToggle.dispatchEvent(new Event('change', {bubbles: true}));
    }
    if (actionToggle) {
      var holder = actionToggle.closest('.d-flex.justify-content-end');
      if (holder) holder.classList.add('d-none');
    }
  }

  function applyAdvanced(enabled, announce) {
    advancedEnabled = !!enabled;
    saveAdvancedCache(advancedEnabled);
    root.classList.toggle('b2m-advanced-enabled', advancedEnabled);
    document.querySelectorAll('[data-b2m-global-advanced-toggle]').forEach(function (input) {
      input.checked = advancedEnabled;
    });
    syncLegacyAdvancedControls();
    if (announce) window.dispatchEvent(new CustomEvent('b2m:advanced-change', {detail: {enabled: advancedEnabled}}));
  }

  async function persistAdvanced(enabled) {
    var before = advancedEnabled;
    applyAdvanced(enabled, true);
    try {
      var response = await fetch('/api/appearance-v24', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', Accept: 'application/json'},
        body: JSON.stringify({advanced_settings: !!enabled})
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      var data = await response.json();
      applyAdvanced(!!data.advanced_settings, true);
    } catch (error) {
      applyAdvanced(before, true);
    }
  }

  function advancedSwitchMarkup(id, mobile) {
    if (mobile) {
      return '<label class="nav-link w-100 text-start b2m-global-advanced-menu"><span class="nav-link-icon d-md-none d-lg-inline-block"><i class="ti ti-adjustments-horizontal icon icon-1"></i></span><span class="nav-link-title flex-fill">Advanced settings</span><input type="checkbox" class="form-check-input ms-2" id="' + id + '" data-b2m-global-advanced-toggle></label>';
    }
    return '<label class="dropdown-item d-flex align-items-center gap-2 b2m-global-advanced-menu"><i class="ti ti-adjustments-horizontal icon dropdown-item-icon"></i><span class="flex-fill">Advanced settings</span><input type="checkbox" class="form-check-input ms-auto" id="' + id + '" data-b2m-global-advanced-toggle></label>';
  }

  function installMenuSwitches() {
    if (!document.querySelector('form[action="/logout"]')) return;

    if (!document.getElementById('b2m-global-advanced-toggle')) {
      var logout = document.querySelector('.navbar .dropdown-menu form[action="/logout"]');
      if (logout) {
        var wrap = document.createElement('div');
        wrap.innerHTML = advancedSwitchMarkup('b2m-global-advanced-toggle', false);
        var label = wrap.firstElementChild;
        logout.insertAdjacentElement('beforebegin', label);
      }
    }

    if (!document.getElementById('b2m-global-advanced-toggle-mobile')) {
      var mobileLogout = document.querySelector('#navbar-menu form[action="/logout"]');
      var mobileLi = mobileLogout && mobileLogout.closest('li');
      if (mobileLi) {
        var li = document.createElement('li');
        li.className = 'nav-item d-md-none';
        li.innerHTML = advancedSwitchMarkup('b2m-global-advanced-toggle-mobile', true);
        mobileLi.insertAdjacentElement('beforebegin', li);
      }
    }

    document.querySelectorAll('[data-b2m-global-advanced-toggle]').forEach(function (input) {
      if (input.dataset.b2mBound === '1') return;
      input.dataset.b2mBound = '1';
      input.checked = advancedEnabled;
      input.addEventListener('click', function (event) { event.stopPropagation(); });
      input.addEventListener('change', function (event) {
        event.stopPropagation();
        persistAdvanced(input.checked);
      });
    });
  }

  function installAppearanceListeners() {
    if (appearanceV35 || window.location.pathname !== '/profile/appearance') return;
    var form = document.querySelector('form[action="/profile/appearance"]');
    if (!form) return;
    var base = form.querySelector('[name="theme_base"]');
    var radius = form.querySelector('[name="theme_radius"]');
    if (base) {
      applyPalette(base.value);
      base.addEventListener('input', function () { applyPalette(base.value); });
      base.addEventListener('change', function () { applyPalette(base.value); });
    }
    if (radius) {
      applyRadius(radius.value);
      radius.addEventListener('input', function () { applyRadius(radius.value); });
      radius.addEventListener('change', function () { applyRadius(radius.value); });
    }
  }

  async function loadPreferences() {
    applyAdvanced(cachedAdvanced(), false);
    try {
      var response = await fetch('/api/appearance-v24', {headers: {Accept: 'application/json'}, cache: 'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      var data = await response.json();
      applyAdvanced(!!data.advanced_settings, true);
      if (!appearanceV35 && data.theme) {
        applyPalette(data.theme.base || 'gray');
        applyRadius(data.theme.radius || '1');
      }
    } catch (e) {}
  }

  function boot() {
    applyAdvanced(cachedAdvanced(), false);
    installMenuSwitches();
    installAppearanceListeners();
    syncLegacyAdvancedControls();
    loadPreferences();
    new MutationObserver(function () {
      installMenuSwitches();
      syncLegacyAdvancedControls();
    }).observe(document.body, {childList: true, subtree: true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
