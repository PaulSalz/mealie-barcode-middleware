/* v2026.09.24.34 — canonical, synchronous personal-theme controller. */
(function () {
  'use strict';
  if (window.__b2mThemeV34Loaded) return;
  window.__b2mThemeV34Loaded = true;
  window.__b2mThemeV33Loaded = true;
  window.__b2mThemeV32Loaded = true; // keep legacy profile scripts dormant

  var root = document.documentElement;
  var mutationVersion = Number(window.__b2mThemeMutationVersion || 0);

  /* These keys powered an older first-paint cache. The server now renders the
     signed-in user's effective theme before CSS, so stale browser state must
     never override another account or an already-saved personal preference. */
  try {
    localStorage.removeItem('theme-mode-override');
    localStorage.removeItem('theme-base-override');
    localStorage.removeItem('theme-epaper-override');
  } catch (e) {}

  function markMutation() {
    mutationVersion += 1;
    window.__b2mThemeMutationVersion = mutationVersion;
    return mutationVersion;
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
    markMutation();
    root.setAttribute('data-bs-theme', mode);
    syncAppearanceMode(mode);
    window.dispatchEvent(new CustomEvent('b2m:theme-mode-change', {detail:{mode:mode}}));
    if (!persist) return;
    var version = mutationVersion;
    fetch('/api/appearance-v24/mode', {
      method:'POST',
      headers:{'Content-Type':'application/json', Accept:'application/json'},
      cache:'no-store',
      body:JSON.stringify({mode:mode})
    }).then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    }).then(function (data) {
      if (version !== mutationVersion) return;
      var saved = data && data.theme && data.theme.mode;
      if (saved === 'light' || saved === 'dark') root.setAttribute('data-bs-theme', saved);
    }).catch(function () {
      /* The click is optimistic by design. Do not visually roll it back. */
    });
  }

  var toggleModes = {
    'theme-toggle-dark':'dark',
    'theme-toggle-light':'light',
    'theme-toggle-dark-mobile':'dark',
    'theme-toggle-light-mobile':'light'
  };

  /* Capture at document level so old target listeners cannot issue a second
     theme request. This handler is the single navbar authority. */
  document.addEventListener('click', function (event) {
    var button = event.target && event.target.closest && event.target.closest('#theme-toggle-dark,#theme-toggle-light,#theme-toggle-dark-mobile,#theme-toggle-light-mobile');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    applyMode(toggleModes[button.id], true);
  }, true);

  if (window.location.pathname !== '/profile/appearance') return;

  var form = document.querySelector('form[action="/profile/appearance"]');
  var configNode = document.getElementById('b2m-theme-runtime-config');
  if (!form || !configNode) return;

  var config;
  try { config = JSON.parse(configNode.textContent || '{}'); } catch (e) { config = {}; }
  var defaults = config.defaults || {};
  var colors = config.colors || {};
  var fonts = config.fonts || {};
  var grays = config.grays || {};
  var radii = config.radius_rem || {};

  var preview = document.createElement('style');
  preview.id = 'b2m-theme-v34-preview';
  document.head.appendChild(preview);

  var persistedTheme = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(function (link) {
    return String(link.getAttribute('href') || '').indexOf('/user-theme.css') === 0;
  });
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
      mode:fieldValue('theme_mode', defaults.mode || 'light'),
      color:fieldValue('theme_color', defaults.color || 'blue'),
      font:fieldValue('theme_font', defaults.font || 'sans-serif'),
      base:fieldValue('theme_base', defaults.base || 'gray'),
      radius:fieldValue('theme_radius', defaults.radius || '1'),
      date_style:fieldValue('theme_date_style', defaults.date_style || 'medium'),
      epaper:epaper && epaper.checked ? 'true' : 'false',
      contrast:contrast ? String(contrast.value) : String(defaults.contrast || '65')
    };
  }

  function cssNumber(value) {
    var number = Number(value);
    return Number.isFinite(number) ? String(Number(number.toFixed(6))) : '0';
  }

  function buildThemeCss(state) {
    var props = [];
    var lightProps = [];
    var darkProps = [];
    var rules = [];

    if (state.color === 'rainbow') {
      rules.push('@keyframes b2m-rainbow-accent{0%,100%{--tblr-primary:#d63939;--tblr-primary-rgb:214,57,57}16%{--tblr-primary:#f76707;--tblr-primary-rgb:247,103,7}33%{--tblr-primary:#f59f00;--tblr-primary-rgb:245,159,0}50%{--tblr-primary:#2fb344;--tblr-primary-rgb:47,179,68}66%{--tblr-primary:#17a2b8;--tblr-primary-rgb:23,162,184}83%{--tblr-primary:#ae3ec9;--tblr-primary-rgb:174,62,201}}');
      rules.push(':root{animation:b2m-rainbow-accent 14s linear infinite}');
      rules.push('@keyframes b2m-rainbow-brand-move{0%{background-position:0% 50%}100%{background-position:200% 50%}}');
      rules.push('.b2m-brand-text{background:linear-gradient(90deg,#d63939,#f76707,#f59f00,#2fb344,#17a2b8,#4263eb,#ae3ec9,#d63939);background-size:200% 100%;background-clip:text;-webkit-background-clip:text;color:transparent!important;-webkit-text-fill-color:transparent;animation:b2m-rainbow-brand-move 12s linear infinite}');
    } else if (state.color !== (defaults.color || 'blue') && colors[state.color]) {
      props.push('--tblr-primary:' + colors[state.color].hex, '--tblr-primary-rgb:' + colors[state.color].rgb);
    }

    if (state.font !== (defaults.font || 'sans-serif') && fonts[state.font]) {
      props.push('--tblr-body-font-family:' + fonts[state.font]);
    }
    if (state.font === 'dyslexia') {
      rules.push('body{letter-spacing:.018em;word-spacing:.045em;line-height:1.55}');
      rules.push('input,select,textarea,button{letter-spacing:.012em}');
    }

    var gray = state.base !== (defaults.base || 'gray') ? grays[state.base] : null;
    if (gray) {
      Object.keys(gray).forEach(function (step) { props.push('--tblr-gray-' + step + ':' + gray[step]); });
      lightProps.push(
        '--tblr-body-color:' + gray['900'], '--tblr-body-bg:' + gray['100'],
        '--tblr-bg-surface:' + gray['50'], '--tblr-bg-surface-secondary:' + gray['100'],
        '--tblr-bg-surface-tertiary:' + gray['300'], '--tblr-bg-surface-dark:' + gray['900'],
        '--tblr-border-color:' + gray['200'], '--tblr-secondary-bg:' + gray['200'],
        '--tblr-secondary-color:' + gray['600'], '--tblr-light-text-emphasis:' + gray['900'],
        '--tblr-dark-text-emphasis:' + gray['700'], '--tblr-light-bg-subtle:' + gray['100']
      );
      darkProps.push(
        '--tblr-body-color:' + gray['200'], '--tblr-body-bg:' + gray['950'],
        '--tblr-bg-surface:' + gray['900'], '--tblr-bg-surface-secondary:' + gray['800'],
        '--tblr-bg-surface-tertiary:' + gray['700'], '--tblr-bg-surface-dark:' + gray['950'],
        '--tblr-border-color:' + gray['800'], '--tblr-secondary-bg:' + gray['800'],
        '--tblr-secondary-color:' + gray['400'], '--tblr-light-text-emphasis:' + gray['100'],
        '--tblr-dark-text-emphasis:' + gray['300'], '--tblr-light-bg-subtle:' + gray['800']
      );
    }

    var radiusKey = Object.prototype.hasOwnProperty.call(radii, state.radius) ? state.radius : (defaults.radius || '1');
    var radius = Number(radii[radiusKey]);
    if (!Number.isFinite(radius)) radius = 0.5;
    props.push(
      '--tblr-border-radius-scale:' + radiusKey,
      '--tblr-border-radius:' + cssNumber(radius) + 'rem',
      '--tblr-border-radius-sm:' + cssNumber(Math.max(0, radius * 0.72)) + 'rem',
      '--tblr-border-radius-lg:' + cssNumber(Math.max(0, radius * 1.45)) + 'rem',
      '--tblr-border-radius-xl:' + cssNumber(Math.max(0, radius * 1.9)) + 'rem',
      '--tblr-border-radius-xxl:' + cssNumber(Math.max(0, radius * 2.5)) + 'rem'
    );

    if (state.epaper === 'true') {
      var contrast = Math.max(0, Math.min(100, Math.round(Number(state.contrast) || 0)));
      var border = Math.max(24, 220 - Math.round(contrast * 1.7));
      var muted = Math.max(0, 112 - Math.round(contrast * 0.9));
      var surface = Math.max(238, 255 - Math.round(contrast * 0.12));
      var mono = [
        '--tblr-primary:#000', '--tblr-primary-rgb:0,0,0', '--tblr-body-color:#000', '--tblr-body-bg:#fff',
        '--tblr-bg-surface:rgb(' + surface + ',' + surface + ',' + surface + ')',
        '--tblr-bg-surface-secondary:#fff', '--tblr-bg-surface-tertiary:#e5e5e5', '--tblr-bg-surface-dark:#000',
        '--tblr-border-color:rgb(' + border + ',' + border + ',' + border + ')',
        '--tblr-secondary-bg:rgb(' + surface + ',' + surface + ',' + surface + ')',
        '--tblr-secondary-color:rgb(' + muted + ',' + muted + ',' + muted + ')', '--tblr-link-color:#000', '--tblr-link-hover-color:#000'
      ];
      props = props.concat(mono);
      lightProps = lightProps.concat(mono);
      darkProps = darkProps.concat(mono);
      rules.push('html{filter:grayscale(1)}');
      rules.push('body,.page,.page-wrapper{background:#fff!important;color:#000!important}');
      rules.push('.card,.dropdown-menu,.modal-content,.navbar,.list-group-item,.form-control,.form-select{background:rgb(' + surface + ',' + surface + ',' + surface + ')!important;color:#000!important;box-shadow:none!important}');
      rules.push('.card,.dropdown-menu,.modal-content,.navbar,.list-group-item,.form-control,.form-select,.btn{border-color:rgb(' + border + ',' + border + ',' + border + ')!important}');
      rules.push('.text-secondary,.form-hint,.card-subtitle{color:rgb(' + muted + ',' + muted + ',' + muted + ')!important}');
      rules.push('[class*="bg-"][class*="-lt"]{background:#fff!important;color:#000!important;border:1px solid #000!important}');
      rules.push('.badge{border:1px solid currentColor!important}');
    }

    var parts = [];
    if (props.length) parts.push(':root{' + props.join(';') + '}');
    if (lightProps.length) parts.push('[data-bs-theme=light]{' + lightProps.join(';') + '}');
    if (darkProps.length) parts.push('[data-bs-theme=dark]{' + darkProps.join(';') + '}');
    return parts.concat(rules).join('');
  }

  function applyMarkers(state) {
    root.setAttribute('data-bs-theme', state.mode);
    root.dataset.b2mBase = state.base;
    root.dataset.b2mRadius = state.radius;
    var mono = state.epaper === 'true';
    root.classList.toggle('b2m-epaper-v9', mono);
    root.classList.toggle('b2m-epaper', mono);
    var contrastOut = document.getElementById('profile-contrast-value');
    if (contrastOut) contrastOut.textContent = state.contrast;
  }

  function renderPreview() {
    var state = values();
    markMutation();
    applyMarkers(state);
    /* Install the complete replacement first, then disable the saved sheet.
       Both operations happen in the same event turn, so there is no intermediate
       default/persisted frame. */
    preview.textContent = buildThemeCss(state);
    if (persistedTheme) persistedTheme.disabled = true;
    previewActive = true;
  }

  function isThemeField(target) {
    return !!(target && target.matches && target.matches('input[name^="theme_"],select[name^="theme_"],input[name="theme_contrast"]'));
  }

  form.addEventListener('input', function (event) {
    if (!isThemeField(event.target)) return;
    renderPreview();
  });
  form.addEventListener('change', function (event) {
    if (!isThemeField(event.target)) return;
    renderPreview();
  });

  window.addEventListener('b2m:theme-mode-change', function () {
    renderPreview();
  });

  /* Save only persists. The visual state is already exact before submission. */
  form.addEventListener('submit', function () {
    markMutation();
    if (previewActive) applyMarkers(values());
  });

  /* Saved /user-theme.css is render-blocking and already owns the initial look.
     Only mirror semantic markers here; do not replace or recompute its CSS. */
  applyMarkers(values());
})();
