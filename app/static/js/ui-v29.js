/* v2026.09.24.1 — global advanced settings only.
   Personal theme rendering is owned by theme-controls-v33.js. */
(function () {
  'use strict';
  if (window.__b2mUiV29Loaded) return;
  window.__b2mUiV29Loaded = true;

  var root = document.documentElement;
  var CACHE_KEY = 'b2m-global-advanced-v1';
  var advancedEnabled = false;

  function cachedAdvanced() {
    try { return localStorage.getItem(CACHE_KEY) === '1'; }
    catch (e) { return false; }
  }

  function saveAdvancedCache(enabled) {
    try { localStorage.setItem(CACHE_KEY, enabled ? '1' : '0'); }
    catch (e) {}
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
        logout.insertAdjacentElement('beforebegin', wrap.firstElementChild);
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

  async function loadPreferences() {
    applyAdvanced(cachedAdvanced(), false);
    try {
      var response = await fetch('/api/appearance-v24', {headers: {Accept: 'application/json'}, cache: 'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      var data = await response.json();
      applyAdvanced(!!data.advanced_settings, true);
    } catch (e) {}
  }

  function boot() {
    applyAdvanced(cachedAdvanced(), false);
    installMenuSwitches();
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
