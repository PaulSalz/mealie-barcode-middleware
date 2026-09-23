/* v2026.09.24.1 — synchronous personal theme controller.
   Appearance preview is rendered entirely in the browser; no preview request is
   allowed in the interaction path. */
(function () {
  'use strict';
  if (window.__b2mThemeV33Loaded) return;
  window.__b2mThemeV33Loaded = true;
  /* Compatibility guard for older profile helpers that only know the v32 flag. */
  window.__b2mThemeV32Loaded = true;

  var root = document.documentElement;
  var COLORS = {
    blue:{hex:'#066fd1',rgb:'6,111,209'}, azure:{hex:'#4299e1',rgb:'66,153,225'},
    indigo:{hex:'#4263eb',rgb:'66,99,235'}, purple:{hex:'#ae3ec9',rgb:'174,62,201'},
    pink:{hex:'#d6336c',rgb:'214,51,108'}, red:{hex:'#d63939',rgb:'214,57,57'},
    orange:{hex:'#f76707',rgb:'247,103,7'}, yellow:{hex:'#f59f00',rgb:'245,159,0'},
    lime:{hex:'#74b816',rgb:'116,184,22'}, green:{hex:'#2fb344',rgb:'47,179,68'},
    teal:{hex:'#0ca678',rgb:'12,166,120'}, cyan:{hex:'#17a2b8',rgb:'23,162,184'}
  };
  var FONTS = {
    'sans-serif':'"Inter Var",Inter,-apple-system,BlinkMacSystemFont,San Francisco,Segoe UI,Roboto,Helvetica Neue,sans-serif',
    serif:'Georgia,Times New Roman,times,serif',
    monospace:'Monaco,Consolas,Liberation Mono,Courier New,monospace',
    comic:'Comic Sans MS,Comic Sans,Chalkboard SE,Comic Neue,sans-serif,cursive',
    dyslexia:'OpenDyslexic,"Atkinson Hyperlegible",Verdana,Tahoma,Arial,sans-serif'
  };
  var PALETTES = {
    gray:{50:'#f7f8fa',100:'#eceff3',200:'#d8dde5',300:'#b9c1cc',400:'#8f9aa8',500:'#687483',600:'#4c5765',700:'#37414d',800:'#242c35',900:'#171d24',950:'#0b0f14'},
    slate:{50:'#f6f8fb',100:'#e8eef6',200:'#d2ddea',300:'#afc0d4',400:'#7f96b0',500:'#5a7390',600:'#405870',700:'#2e4258',800:'#1d2d3e',900:'#111d2a',950:'#08111c'},
    zinc:{50:'#fafafa',100:'#eeeeef',200:'#d9d9dc',300:'#bdbdc3',400:'#97979f',500:'#707078',600:'#515158',700:'#3a3a40',800:'#25252a',900:'#17171b',950:'#0b0b0e'},
    neutral:{50:'#fbfbfb',100:'#f0f0f0',200:'#d8d8d8',300:'#b9b9b9',400:'#929292',500:'#6d6d6d',600:'#4f4f4f',700:'#393939',800:'#242424',900:'#151515',950:'#080808'},
    stone:{50:'#fbf9f6',100:'#f0ebe5',200:'#ddd4ca',300:'#c1b3a4',400:'#9b8977',500:'#796856',600:'#5a4d41',700:'#443a32',800:'#2d2722',900:'#1c1815',950:'#0e0c0a'}
  };
  var RADIUS = {'0':0,'0.5':.25,'1':.5,'1.5':.8,'2':1.1};

  function setStoredMode(mode) {
    try { localStorage.setItem('theme-mode-override', mode); } catch (e) {}
  }

  function declarations(values, important) {
    return values.map(function (value) { return value + (important ? '!important' : ''); }).join(';');
  }

  function buildThemeCss(theme, important) {
    var props = [];
    var dark = [];
    var extra = [];
    var epaper = theme.epaper === 'true';
    var color = theme.color || 'blue';

    if (color === 'rainbow' && !epaper) {
      extra.push('@keyframes b2m-rainbow-accent{0%,100%{--tblr-primary:#d63939;--tblr-primary-rgb:214,57,57}16%{--tblr-primary:#f76707;--tblr-primary-rgb:247,103,7}33%{--tblr-primary:#f59f00;--tblr-primary-rgb:245,159,0}50%{--tblr-primary:#2fb344;--tblr-primary-rgb:47,179,68}66%{--tblr-primary:#17a2b8;--tblr-primary-rgb:23,162,184}83%{--tblr-primary:#ae3ec9;--tblr-primary-rgb:174,62,201}}');
      extra.push(':root{animation:b2m-rainbow-accent 14s linear infinite}');
      extra.push('@keyframes b2m-rainbow-brand-move{0%{background-position:0% 50%}100%{background-position:200% 50%}}');
      extra.push('.b2m-brand-text{background:linear-gradient(90deg,#d63939,#f76707,#f59f00,#2fb344,#17a2b8,#4263eb,#ae3ec9,#d63939);background-size:200% 100%;background-clip:text;-webkit-background-clip:text;color:transparent!important;-webkit-text-fill-color:transparent;animation:b2m-rainbow-brand-move 12s linear infinite}');
    } else if (color !== 'blue' && COLORS[color]) {
      props.push('--tblr-primary:' + COLORS[color].hex, '--tblr-primary-rgb:' + COLORS[color].rgb);
    }

    var font = theme.font || 'sans-serif';
    if (font !== 'sans-serif' && FONTS[font]) props.push('--tblr-body-font-family:' + FONTS[font]);
    if (font === 'dyslexia') {
      extra.push('body{letter-spacing:.018em;word-spacing:.045em;line-height:1.55}');
      extra.push('input,select,textarea,button{letter-spacing:.012em}');
    }

    var base = PALETTES[theme.base] ? theme.base : 'gray';
    var p = PALETTES[base];
    Object.keys(p).forEach(function (step) { props.push('--tblr-gray-' + step + ':' + p[step]); });
    props.push(
      '--tblr-body-color:' + p[900],
      '--tblr-body-bg:' + p[100],
      '--tblr-bg-surface:' + p[50],
      '--tblr-bg-surface-secondary:' + p[200],
      '--tblr-secondary-bg:' + p[200],
      '--tblr-border-color:' + p[300],
      '--tblr-secondary-color:' + p[600]
    );
    dark.push(
      '--tblr-body-color:' + p[100],
      '--tblr-body-bg:' + p[950],
      '--tblr-bg-surface:' + p[900],
      '--tblr-bg-surface-secondary:' + p[800],
      '--tblr-secondary-bg:' + p[800],
      '--tblr-border-color:' + p[700],
      '--tblr-secondary-color:' + p[400],
      '--tblr-light-text-emphasis:' + p[100],
      '--tblr-dark-text-emphasis:' + p[300],
      '--tblr-light-bg-subtle:' + p[800]
    );

    var radiusKey = Object.prototype.hasOwnProperty.call(RADIUS, String(theme.radius)) ? String(theme.radius) : '1';
    var radius = RADIUS[radiusKey];
    props.push(
      '--tblr-border-radius-scale:' + radiusKey,
      '--tblr-border-radius:' + radius + 'rem',
      '--tblr-border-radius-sm:' + Math.max(0, radius * .72) + 'rem',
      '--tblr-border-radius-lg:' + Math.max(0, radius * 1.45) + 'rem',
      '--tblr-border-radius-xl:' + Math.max(0, radius * 1.9) + 'rem'
    );

    var contrast = Math.max(0, Math.min(100, Number(theme.contrast || 65)));
    if (!Number.isFinite(contrast)) contrast = 65;
    if (epaper) {
      var border = Math.max(24, 220 - Math.round(contrast * 1.7));
      var muted = Math.max(0, 112 - Math.round(contrast * .9));
      var surface = Math.max(238, 255 - Math.round(contrast * .12));
      var mono = [
        '--tblr-primary:#000','--tblr-primary-rgb:0,0,0','--tblr-body-color:#000','--tblr-body-bg:#fff',
        '--tblr-bg-surface:rgb(' + surface + ',' + surface + ',' + surface + ')',
        '--tblr-bg-surface-secondary:rgb(' + surface + ',' + surface + ',' + surface + ')',
        '--tblr-secondary-bg:rgb(' + surface + ',' + surface + ',' + surface + ')',
        '--tblr-border-color:rgb(' + border + ',' + border + ',' + border + ')',
        '--tblr-secondary-color:rgb(' + muted + ',' + muted + ',' + muted + ')',
        '--tblr-link-color:#000','--tblr-link-hover-color:#000'
      ];
      props = props.concat(mono);
      dark = dark.concat(mono);
      extra.push('html{filter:grayscale(1)}');
      extra.push('body,.page,.page-wrapper{background:#fff!important;color:#000!important}');
      extra.push('.card,.dropdown-menu,.modal-content,.navbar,.list-group-item{box-shadow:none!important}');
      extra.push('.card,.dropdown-menu,.modal-content,.navbar,.list-group-item,.form-control,.form-select,.btn{border-color:rgb(' + border + ',' + border + ',' + border + ')!important}');
      extra.push('.text-secondary,.form-hint,.card-subtitle{color:rgb(' + muted + ',' + muted + ',' + muted + ')!important}');
      extra.push('[class*="bg-"][class*="-lt"]{background:#fff!important;color:#000!important;border:1px solid #000!important}');
      extra.push('.badge{border:1px solid currentColor!important}');
    }

    var parts = [];
    if (props.length) parts.push(':root{' + declarations(props, important) + '}');
    if (dark.length) parts.push('[data-bs-theme=dark]{' + declarations(dark, important) + '}');
    return parts.concat(extra).join('');
  }

  function fieldValue(form, name, fallback) {
    var checked = form.querySelector('input[name="' + name + '"]:checked');
    if (checked) return checked.value;
    var field = form.querySelector('[name="' + name + '"]');
    return field ? field.value : fallback;
  }

  function formValues(form) {
    var epaper = form.querySelector('input[name="theme_epaper"]');
    var contrast = form.querySelector('[name="theme_contrast"]');
    return {
      mode:fieldValue(form, 'theme_mode', root.getAttribute('data-bs-theme') || 'light'),
      color:fieldValue(form, 'theme_color', 'blue'),
      font:fieldValue(form, 'theme_font', 'sans-serif'),
      base:fieldValue(form, 'theme_base', root.dataset.b2mBase || 'gray'),
      radius:fieldValue(form, 'theme_radius', '1'),
      date_style:fieldValue(form, 'theme_date_style', 'medium'),
      epaper:epaper && epaper.checked ? 'true' : 'false',
      contrast:contrast ? String(contrast.value) : '65'
    };
  }

  function applyMarkers(theme) {
    root.setAttribute('data-bs-theme', theme.mode === 'dark' ? 'dark' : 'light');
    root.dataset.b2mBase = PALETTES[theme.base] ? theme.base : 'gray';
    var mono = theme.epaper === 'true';
    root.classList.toggle('b2m-epaper-v9', mono);
    root.classList.toggle('b2m-epaper', mono);
    root.classList.toggle('b2m-rainbow-disabled', mono || theme.color !== 'rainbow');
    root.classList.toggle('b2m-rainbow-active', !mono && theme.color === 'rainbow');
  }

  var form = window.location.pathname === '/profile/appearance'
    ? document.querySelector('form[action="/profile/appearance"]') : null;
  var preview = null;
  var persistedTheme = null;
  var previewActive = false;

  function ensurePreview() {
    if (!form) return null;
    if (!preview) {
      preview = document.createElement('style');
      preview.id = 'b2m-theme-v33-preview';
      document.head.appendChild(preview);
    }
    if (!persistedTheme) {
      persistedTheme = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(function (link) {
        return String(link.getAttribute('href') || '').indexOf('/user-theme.css') === 0;
      }) || null;
    }
    if (!previewActive) {
      previewActive = true;
      if (persistedTheme) persistedTheme.disabled = true;
    }
    return preview;
  }

  function renderProfilePreview() {
    if (!form) return;
    var theme = formValues(form);
    applyMarkers(theme);
    var style = ensurePreview();
    if (style) style.textContent = buildThemeCss(theme, true);
    var out = document.getElementById('profile-contrast-value');
    if (out) out.textContent = theme.contrast;
    window.dispatchEvent(new CustomEvent('b2m:theme-live-change', {detail:{theme:theme}}));
  }

  function syncAppearanceMode(mode) {
    if (!form) return;
    var input = form.querySelector('input[name="theme_mode"][value="' + mode + '"]');
    if (input) input.checked = true;
    renderProfilePreview();
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
      if (saved === 'light' || saved === 'dark') setStoredMode(saved);
    }).catch(function () {
      /* The immediate mode remains applied; a later click/save can retry persistence. */
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
      /* app.js still contains a compatibility handler; this controller owns the
         event and prevents that legacy global-theme write from running. */
      event.stopImmediatePropagation();
      applyMode(pair[1], true);
    }, true);
  });

  if (!form) return;

  function isThemeField(target) {
    return !!(target && target.matches && target.matches('input[name^="theme_"],select[name^="theme_"],input[name="theme_contrast"]'));
  }

  form.addEventListener('input', function (event) {
    if (isThemeField(event.target)) renderProfilePreview();
  });
  form.addEventListener('change', function (event) {
    if (isThemeField(event.target)) renderProfilePreview();
  });

  form.addEventListener('submit', function () {
    var theme = formValues(form);
    try {
      localStorage.setItem('theme-mode-override', theme.mode);
      localStorage.setItem('theme-base-override', theme.base);
      localStorage.setItem('theme-epaper-override', theme.epaper);
    } catch (e) {}
  });

  /* The render-blocking user-theme.css is already the saved state. Only add
     marker classes synchronously; do not issue a preview request or replace CSS. */
  applyMarkers(formValues(form));
})();
