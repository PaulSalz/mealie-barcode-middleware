/* v2026.09.23.32 — one personal-theme controller for navbar and Appearance live preview. */
(function () {
  'use strict';
  if (window.__b2mThemeV32Loaded) return;
  window.__b2mThemeV32Loaded = true;

  var root = document.documentElement;

  function setStoredMode(mode) {
    try { localStorage.setItem('theme-mode-override', mode); } catch (e) {}
  }

  function syncAppearanceMode(mode) {
    if (window.location.pathname !== '/profile/appearance') return;
    var input = document.querySelector('form[action="/profile/appearance"] input[name="theme_mode"][value="' + mode + '"]');
    if (input && !input.checked) {
      input.checked = true;
      input.dispatchEvent(new Event('change', {bubbles:true}));
    }
  }

  function applyMode(mode, persist) {
    if (mode !== 'light' && mode !== 'dark') return;
    root.setAttribute('data-bs-theme', mode);
    setStoredMode(mode);
    syncAppearanceMode(mode);
    window.dispatchEvent(new CustomEvent('b2m:theme-mode-change', {detail:{mode:mode}}));
    if (!persist) return;
    fetch('/api/appearance-v24/mode', {
      method:'POST',
      headers:{'Content-Type':'application/json', Accept:'application/json'},
      cache:'no-store',
      body:JSON.stringify({mode:mode})
    }).then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    }).then(function (data) {
      var saved = data && data.theme && data.theme.mode;
      if (saved === 'light' || saved === 'dark') {
        root.setAttribute('data-bs-theme', saved);
        setStoredMode(saved);
      }
    }).catch(function () {
      /* Keep the immediate local mode even if persistence is temporarily unavailable. */
    });
  }

  [
    ['theme-toggle-dark','dark'],
    ['theme-toggle-light','light'],
    ['theme-toggle-dark-mobile','dark'],
    ['theme-toggle-light-mobile','light']
  ].forEach(function (pair) {
    var button = document.getElementById(pair[0]);
    if (!button) return;
    button.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopImmediatePropagation();
      applyMode(pair[1], true);
    }, true);
  });

  if (window.location.pathname !== '/profile/appearance') return;

  var form = document.querySelector('form[action="/profile/appearance"]');
  if (!form) return;

  var preview = document.createElement('style');
  preview.id = 'b2m-theme-v32-preview';
  document.head.appendChild(preview);

  var persistedTheme = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(function (link) {
    return String(link.getAttribute('href') || '').indexOf('/user-theme.css') === 0;
  });
  var timer = null;
  var requestId = 0;
  var previewActive = false;

  function fieldValue(name, fallback) {
    var checked = form.querySelector('input[name="' + name + '"]:checked');
    if (checked) return checked.value;
    var field = form.querySelector('[name="' + name + '"]');
    return field ? field.value : fallback;
  }

  function values() {
    var epaper = form.querySelector('input[name="theme_epaper"]');
    var contrast = form.querySelector('[name="theme_contrast"]');
    return {
      mode:fieldValue('theme_mode', root.getAttribute('data-bs-theme') || 'light'),
      color:fieldValue('theme_color', 'blue'),
      font:fieldValue('theme_font', 'sans-serif'),
      base:fieldValue('theme_base', 'gray'),
      radius:fieldValue('theme_radius', '1'),
      date_style:fieldValue('theme_date_style', 'medium'),
      epaper:epaper && epaper.checked ? 'true' : 'false',
      contrast:contrast ? String(contrast.value) : '65'
    };
  }

  function radiusRem(scale) {
    var map = {'0':0,'0.5':.25,'1':.5,'1.5':.8,'2':1.1};
    var key = String(scale == null ? '1' : scale);
    return Object.prototype.hasOwnProperty.call(map, key) ? map[key] : .5;
  }

  function applyImmediate(state) {
    root.setAttribute('data-bs-theme', state.mode);
    root.dataset.b2mBase = state.base;
    var mono = state.epaper === 'true';
    root.classList.toggle('b2m-epaper-v9', mono);
    root.classList.toggle('b2m-epaper', mono);

    var radius = radiusRem(state.radius);
    root.style.setProperty('--tblr-border-radius-scale', String(state.radius));
    root.style.setProperty('--tblr-border-radius', radius + 'rem');
    root.style.setProperty('--tblr-border-radius-sm', Math.max(0, radius * .72) + 'rem');
    root.style.setProperty('--tblr-border-radius-lg', Math.max(0, radius * 1.45) + 'rem');
    root.style.setProperty('--tblr-border-radius-xl', Math.max(0, radius * 1.9) + 'rem');

    var contrastOut = document.getElementById('profile-contrast-value');
    if (contrastOut) contrastOut.textContent = state.contrast;
  }

  async function renderPreview() {
    var id = ++requestId;
    var state = values();
    applyImmediate(state);
    try {
      var response = await fetch('/api/appearance-v24/preview', {
        method:'POST',
        headers:{'Content-Type':'application/json', Accept:'text/css'},
        cache:'no-store',
        body:JSON.stringify(state)
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      var css = await response.text();
      if (id !== requestId) return;
      preview.textContent = css;
      previewActive = true;
      if (persistedTheme) persistedTheme.disabled = true;
      applyImmediate(state);
    } catch (error) {
      if (id !== requestId) return;
      preview.textContent = '';
      previewActive = false;
      if (persistedTheme) persistedTheme.disabled = false;
      applyImmediate(state);
    }
  }

  function schedulePreview() {
    var state = values();
    applyImmediate(state);
    window.clearTimeout(timer);
    timer = window.setTimeout(renderPreview, 25);
  }

  function isThemeField(target) {
    return !!(target && target.matches && target.matches('input[name^="theme_"],select[name^="theme_"],input[name="theme_contrast"]'));
  }

  form.addEventListener('input', function (event) {
    if (!isThemeField(event.target)) return;
    schedulePreview();
  });
  form.addEventListener('change', function (event) {
    if (!isThemeField(event.target)) return;
    schedulePreview();
  });

  window.addEventListener('b2m:theme-mode-change', function () {
    if (previewActive) schedulePreview();
    else applyImmediate(values());
  });

  form.addEventListener('submit', function () {
    var state = values();
    try {
      localStorage.setItem('theme-mode-override', state.mode);
      localStorage.setItem('theme-base-override', state.base);
      localStorage.setItem('theme-epaper-override', state.epaper);
    } catch (e) {}
  });

  /* The persisted stylesheet already represents the saved state. Do not perform
     a second asynchronous preview on load; only start previewing after input. */
  applyImmediate(values());
})();
