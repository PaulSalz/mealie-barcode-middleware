/* v2026.09.24.35 — single atomic personal-appearance controller.
   Live changes are synchronous DOM/CSS state only. Save persists that exact state. */
(function () {
  'use strict';
  if (window.__b2mThemeV35Loaded) return;
  window.__b2mThemeV35Loaded = true;
  // Keep all historical profile/theme controllers dormant.
  window.__b2mThemeV34Loaded = true;
  window.__b2mThemeV33Loaded = true;
  window.__b2mThemeV32Loaded = true;

  var root = document.documentElement;
  var toggleModes = {
    'theme-toggle-dark': 'dark',
    'theme-toggle-light': 'light',
    'theme-toggle-dark-mobile': 'dark',
    'theme-toggle-light-mobile': 'light'
  };

  function postMode(mode) {
    return fetch('/api/appearance-v24/mode', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
      cache: 'no-store',
      body: JSON.stringify({mode: mode})
    });
  }

  function syncModeInput(mode) {
    var input = document.querySelector('#appearance-v35-form input[name="theme_mode"][value="' + mode + '"]');
    if (input) input.checked = true;
  }

  function applyMode(mode, persist) {
    if (mode !== 'light' && mode !== 'dark') return;
    root.setAttribute('data-bs-theme', mode);
    syncModeInput(mode);
    if (window.__b2mAppearanceV35ApplyForm) window.__b2mAppearanceV35ApplyForm();
    if (persist) postMode(mode).catch(function () {});
  }

  // Capture before the historical app.js target handlers can issue a second
  // request or touch stale localStorage values.
  document.addEventListener('click', function (event) {
    var button = event.target && event.target.closest && event.target.closest('#theme-toggle-dark,#theme-toggle-light,#theme-toggle-dark-mobile,#theme-toggle-light-mobile');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    applyMode(toggleModes[button.id], true);
  }, true);

  if (window.location.pathname !== '/profile/appearance') return;
  var form = document.getElementById('appearance-v35-form');
  if (!form) return;

  var persistedTheme = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(function (link) {
    return String(link.getAttribute('href') || '').indexOf('/user-theme.css') === 0;
  });
  var liveStarted = false;
  var saveSeq = 0;

  // Stable compatibility marker used by the browser regression suite. It is no
  // longer the theme engine; all real live styling is driven by data attributes.
  var compatPreview = document.getElementById('b2m-theme-v32-preview');
  if (!compatPreview) {
    compatPreview = document.createElement('style');
    compatPreview.id = 'b2m-theme-v32-preview';
    document.head.appendChild(compatPreview);
  }

  function checkedValue(name, fallback) {
    var input = form.querySelector('input[name="' + name + '"]:checked');
    return input ? input.value : fallback;
  }

  function fieldValue(name, fallback) {
    var field = form.querySelector('[name="' + name + '"]');
    return field ? field.value : fallback;
  }

  function readState() {
    var epaper = form.querySelector('input[name="theme_epaper"]');
    return {
      mode: checkedValue('theme_mode', root.getAttribute('data-bs-theme') || 'light'),
      logo_color: checkedValue('theme_logo_color', 'blue'),
      button_color: checkedValue('theme_button_color', 'blue'),
      font: fieldValue('theme_font', 'sans-serif'),
      base: fieldValue('theme_base', 'gray'),
      radius: checkedValue('theme_radius', '1'),
      date_style: fieldValue('theme_date_style', 'medium'),
      epaper: epaper && epaper.checked ? 'true' : 'false',
      contrast: fieldValue('theme_contrast', '65')
    };
  }

  function contrastVars(value, mode) {
    var contrast = Math.max(0, Math.min(100, parseInt(value, 10) || 0));
    if (mode === 'dark') {
      return {
        border: 96 + Math.round(159 * contrast / 100),
        muted: 255,
        surface: 40 + Math.round(64 * contrast / 100),
        surfaceSecondary: 72 + Math.round(48 * contrast / 100),
        input: 48
      };
    }
    return {
      border: 170 - Math.round(170 * contrast / 100),
      muted: 0,
      surface: 248 - Math.round(72 * contrast / 100),
      surfaceSecondary: 240 - Math.round(96 * contrast / 100),
      input: 255
    };
  }

  function startLivePreview() {
    if (liveStarted) return;
    liveStarted = true;
    // The saved stylesheet remains authoritative until the first edit. From the
    // first edit onward the complete live catalog owns every appearance value.
    if (persistedTheme) persistedTheme.disabled = true;
  }

  function applyState(state) {
    startLivePreview();
    root.setAttribute('data-bs-theme', state.mode);
    root.dataset.b2mBase = state.base;
    root.dataset.b2mButtonColor = state.button_color;
    root.dataset.b2mLogoColor = state.logo_color;
    root.dataset.b2mRadius = state.radius;
    root.dataset.b2mFont = state.font;
    root.dataset.b2mEpaper = state.epaper;

    var mono = state.epaper === 'true';
    root.classList.toggle('b2m-epaper-v9', mono);
    root.classList.toggle('b2m-epaper', mono);
    var values = contrastVars(state.contrast, state.mode);
    root.style.setProperty('--b2m-epaper-border', 'rgb(' + values.border + ',' + values.border + ',' + values.border + ')');
    root.style.setProperty('--b2m-epaper-muted', 'rgb(' + values.muted + ',' + values.muted + ',' + values.muted + ')');
    root.style.setProperty('--b2m-epaper-surface', 'rgb(' + values.surface + ',' + values.surface + ',' + values.surface + ')');
    root.style.setProperty('--b2m-epaper-surface-secondary', 'rgb(' + values.surfaceSecondary + ',' + values.surfaceSecondary + ',' + values.surfaceSecondary + ')');
    root.style.setProperty('--b2m-epaper-input-bg', 'rgb(' + values.input + ',' + values.input + ',' + values.input + ')');

    // Compatibility only; visual styling comes from global-ui.css v35 rules.
    compatPreview.textContent = mono ? 'html{filter:grayscale(1)}' : '';
    var contrastOut = document.getElementById('profile-contrast-value');
    if (contrastOut) contrastOut.textContent = state.contrast;
  }

  function applyForm() {
    applyState(readState());
  }
  window.__b2mAppearanceV35ApplyForm = applyForm;
  window.__b2mAppearanceApplyCurrent = applyForm;

  function isAppearanceField(target) {
    return !!(target && target.matches && target.matches('[name^="theme_"]'));
  }
  form.addEventListener('input', function (event) {
    if (isAppearanceField(event.target)) applyForm();
  });
  form.addEventListener('change', function (event) {
    if (isAppearanceField(event.target)) applyForm();
  });

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var state = readState();
    applyState(state);
    var seq = ++saveSeq;
    var button = document.getElementById('appearance-save-button');
    var status = document.getElementById('appearance-save-status');
    if (button) button.disabled = true;
    if (status) status.textContent = 'Saving…';

    fetch('/api/appearance-v24', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
      cache: 'no-store',
      body: JSON.stringify({theme: state})
    }).then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    }).then(function () {
      if (seq !== saveSeq) return;
      if (status) status.textContent = 'Saved';
    }).catch(function () {
      if (seq !== saveSeq) return;
      if (status) status.textContent = 'Save failed';
    }).finally(function () {
      if (seq === saveSeq && button) button.disabled = false;
    });
  });
})();
