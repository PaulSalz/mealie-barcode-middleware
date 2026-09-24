/* v2026.09.24.34 — one synchronous personal-theme controller; Save only persists. */
(function () {
  'use strict';
  if (window.__b2mThemeV34Loaded) return;
  window.__b2mThemeV34Loaded = true;
  window.__b2mThemeV33Loaded = true;
  window.__b2mThemeV32Loaded = true;

  var root = document.documentElement;
  var mutationVersion = Number(window.__b2mThemeMutationVersion || 0);

  var COLORS = {
    blue:['#066fd1','6,111,209'], azure:['#4299e1','66,153,225'], indigo:['#4263eb','66,99,235'],
    purple:['#ae3ec9','174,62,201'], pink:['#d6336c','214,51,108'], red:['#d63939','214,57,57'],
    orange:['#f76707','247,103,7'], yellow:['#f59f00','245,159,0'], lime:['#74b816','116,184,22'],
    green:['#2fb344','47,179,68'], teal:['#0ca678','12,166,120'], cyan:['#17a2b8','23,162,184']
  };
  var GRAYS = {
    slate:{50:'#f8fafc',100:'#f1f5f9',200:'#e2e8f0',300:'#cbd5e1',400:'#94a3b8',500:'#64748b',600:'#475569',700:'#334155',800:'#1e293b',900:'#0f172a',950:'#020617'},
    zinc:{50:'#fafafa',100:'#f4f4f5',200:'#e4e4e7',300:'#d4d4d8',400:'#a1a1aa',500:'#71717a',600:'#52525b',700:'#3f3f46',800:'#27272a',900:'#18181b',950:'#09090b'},
    neutral:{50:'#fafafa',100:'#f5f5f5',200:'#e5e5e5',300:'#d4d4d4',400:'#a3a3a3',500:'#737373',600:'#525252',700:'#404040',800:'#262626',900:'#171717',950:'#0a0a0a'},
    stone:{50:'#fafaf9',100:'#f5f5f4',200:'#e7e5e4',300:'#d6d3d1',400:'#a8a29e',500:'#78716c',600:'#57534e',700:'#44403c',800:'#292524',900:'#1c1917',950:'#0c0a09'}
  };
  var FONTS = {
    serif:'Georgia,Times New Roman,times,serif',
    monospace:'Monaco,Consolas,Liberation Mono,Courier New,monospace',
    comic:'Comic Sans MS,Comic Sans,Chalkboard SE,Comic Neue,sans-serif,cursive',
    dyslexia:'OpenDyslexic,"Atkinson Hyperlegible",Verdana,Tahoma,Arial,sans-serif'
  };
  var RADIUS = {'0':0,'0.5':.25,'1':.5,'1.5':.8,'2':1.1};

  function markMutation() {
    mutationVersion += 1;
    window.__b2mThemeMutationVersion = mutationVersion;
    return mutationVersion;
  }

  function setStoredMode(mode) {
    try { localStorage.setItem('theme-mode-override', mode); } catch (e) {}
  }

  function syncAppearanceMode(mode) {
    if (window.location.pathname !== '/profile/appearance') return;
    var input = document.querySelector('form[action="/profile/appearance"] input[name="theme_mode"][value="' + mode + '"]');
    if (input && !input.checked) input.checked = true;
  }

  function applyMode(mode, persist) {
    if (mode !== 'light' && mode !== 'dark') return;
    markMutation();
    root.setAttribute('data-bs-theme', mode);
    setStoredMode(mode);
    syncAppearanceMode(mode);
    if (window.__b2mAppearanceApplyCurrent) window.__b2mAppearanceApplyCurrent();
    if (!persist) return;
    var version = mutationVersion;
    fetch('/api/appearance-v24/mode', {
      method:'POST', headers:{'Content-Type':'application/json',Accept:'application/json'}, cache:'no-store',
      body:JSON.stringify({mode:mode})
    }).then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    }).then(function (data) {
      if (version !== mutationVersion) return;
      var saved = data && data.theme && data.theme.mode;
      if (saved === 'light' || saved === 'dark') {
        root.setAttribute('data-bs-theme', saved);
        setStoredMode(saved);
      }
    }).catch(function () {});
  }

  var toggleModes = {
    'theme-toggle-dark':'dark','theme-toggle-light':'light',
    'theme-toggle-dark-mobile':'dark','theme-toggle-light-mobile':'light'
  };
  document.addEventListener('click', function (event) {
    var button = event.target && event.target.closest && event.target.closest('#theme-toggle-dark,#theme-toggle-light,#theme-toggle-dark-mobile,#theme-toggle-light-mobile');
    if (!button) return;
    event.preventDefault(); event.stopPropagation(); event.stopImmediatePropagation();
    applyMode(toggleModes[button.id], true);
  }, true);

  if (window.location.pathname !== '/profile/appearance') return;
  var form = document.querySelector('form[action="/profile/appearance"]');
  if (!form) return;

  var preview = document.createElement('style');
  preview.id = 'b2m-theme-v34-preview';
  document.head.appendChild(preview);
  var persistedTheme = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(function (link) {
    return String(link.getAttribute('href') || '').indexOf('/user-theme.css') === 0;
  });
  var requestId = 0;
  var previewAbort = null;
  var previewFrame = 0;

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
      color:fieldValue('theme_color','blue'), font:fieldValue('theme_font','sans-serif'),
      base:fieldValue('theme_base','gray'), radius:fieldValue('theme_radius','1'),
      date_style:fieldValue('theme_date_style','medium'),
      epaper:epaper && epaper.checked ? 'true' : 'false',
      contrast:contrast ? String(contrast.value) : '65'
    };
  }

  function buildImmediateCss(state) {
    var props = [], dark = [], extra = [], color = state.color;
    if (color === 'rainbow') {
      extra.push('@keyframes b2m-rainbow-accent{0%,100%{--tblr-primary:#d63939;--tblr-primary-rgb:214,57,57}16%{--tblr-primary:#f76707;--tblr-primary-rgb:247,103,7}33%{--tblr-primary:#f59f00;--tblr-primary-rgb:245,159,0}50%{--tblr-primary:#2fb344;--tblr-primary-rgb:47,179,68}66%{--tblr-primary:#17a2b8;--tblr-primary-rgb:23,162,184}83%{--tblr-primary:#ae3ec9;--tblr-primary-rgb:174,62,201}}');
      extra.push(':root{animation:b2m-rainbow-accent 14s linear infinite}');
    } else if (color !== 'blue' && COLORS[color]) {
      props.push('--tblr-primary:' + COLORS[color][0], '--tblr-primary-rgb:' + COLORS[color][1]);
    }
    if (state.font !== 'sans-serif' && FONTS[state.font]) props.push('--tblr-body-font-family:' + FONTS[state.font]);
    if (state.font === 'dyslexia') extra.push('body{letter-spacing:.018em;word-spacing:.045em;line-height:1.55}input,select,textarea,button{letter-spacing:.012em}');

    var grays = GRAYS[state.base];
    if (grays) {
      Object.keys(grays).forEach(function (step) { props.push('--tblr-gray-' + step + ':' + grays[step]); });
      dark.push('--tblr-body-color:' + grays[200], '--tblr-body-bg:' + grays[900], '--tblr-secondary-bg:' + grays[800],
        '--tblr-light-text-emphasis:' + grays[100], '--tblr-dark-text-emphasis:' + grays[300], '--tblr-light-bg-subtle:' + grays[800]);
    }

    var r = Object.prototype.hasOwnProperty.call(RADIUS,state.radius) ? RADIUS[state.radius] : .5;
    props.push('--tblr-border-radius-scale:' + state.radius, '--tblr-border-radius:' + r + 'rem',
      '--tblr-border-radius-sm:' + Math.max(0,r*.72) + 'rem', '--tblr-border-radius-lg:' + Math.max(0,r*1.45) + 'rem',
      '--tblr-border-radius-xl:' + Math.max(0,r*1.9) + 'rem');

    if (state.epaper === 'true') {
      var contrast = Math.max(0,Math.min(100,parseInt(state.contrast,10)||0));
      var border = Math.max(24,220-Math.round(contrast*1.7));
      var muted = Math.max(0,112-Math.round(contrast*.9));
      var surface = Math.max(238,255-Math.round(contrast*.12));
      var mono = ['--tblr-primary:#000','--tblr-primary-rgb:0,0,0','--tblr-body-color:#000','--tblr-body-bg:#fff',
        '--tblr-bg-surface:rgb('+surface+','+surface+','+surface+')','--tblr-border-color:rgb('+border+','+border+','+border+')',
        '--tblr-secondary-color:rgb('+muted+','+muted+','+muted+')','--tblr-link-color:#000','--tblr-link-hover-color:#000'];
      props = props.concat(mono); dark = dark.concat(mono);
      extra.push('html{filter:grayscale(1)}body,.page,.page-wrapper{background:#fff!important;color:#000!important}');
      extra.push('.card,.dropdown-menu,.modal-content,.navbar,.list-group-item{box-shadow:none!important}');
      extra.push('.card,.dropdown-menu,.modal-content,.navbar,.list-group-item,.form-control,.form-select,.btn{border-color:rgb('+border+','+border+','+border+')!important}');
      extra.push('.text-secondary,.form-hint,.card-subtitle{color:rgb('+muted+','+muted+','+muted+')!important}');
      extra.push('[class*="bg-"][class*="-lt"]{background:#fff!important;color:#000!important;border:1px solid #000!important}.badge{border:1px solid currentColor!important}');
    }
    return ':root{' + props.join(';') + '}' + (dark.length ? '[data-bs-theme=dark]{' + dark.join(';') + '}' : '') + extra.join('');
  }

  function applyStateNow(state) {
    root.setAttribute('data-bs-theme', state.mode);
    root.dataset.b2mBase = state.base;
    var mono = state.epaper === 'true';
    root.classList.toggle('b2m-epaper-v9', mono);
    root.classList.toggle('b2m-epaper', mono);
    preview.textContent = buildImmediateCss(state);
    if (persistedTheme) persistedTheme.disabled = true;
    var out = document.getElementById('profile-contrast-value');
    if (out) out.textContent = state.contrast;
  }

  async function confirmWithServer(state) {
    var id = ++requestId, version = mutationVersion;
    if (previewAbort) previewAbort.abort();
    previewAbort = new AbortController();
    try {
      var response = await fetch('/api/appearance-v24/preview', {
        method:'POST', headers:{'Content-Type':'application/json',Accept:'text/css'}, cache:'no-store', signal:previewAbort.signal,
        body:JSON.stringify(state)
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      var css = await response.text();
      if (id !== requestId || version !== mutationVersion) return;
      /* Server CSS is authoritative, but radius variables remain explicit so first/live/save are identical. */
      preview.textContent = css + buildImmediateCss(state).match(/:root\{[^}]*--tblr-border-radius-scale:[^}]*\}/)[0];
    } catch (error) {
      if (error && error.name === 'AbortError') return;
      /* Keep the synchronous complete preview. Never roll back visually. */
    }
  }

  function applyCurrent() {
    var state = values();
    markMutation();
    applyStateNow(state);
    window.cancelAnimationFrame(previewFrame);
    previewFrame = window.requestAnimationFrame(function () { confirmWithServer(state); });
  }
  window.__b2mAppearanceApplyCurrent = applyCurrent;

  function isThemeField(target) {
    return !!(target && target.matches && target.matches('input[name^="theme_"],select[name^="theme_"],input[name="theme_contrast"]'));
  }
  form.addEventListener('input', function (event) { if (isThemeField(event.target)) applyCurrent(); });
  form.addEventListener('change', function (event) { if (isThemeField(event.target)) applyCurrent(); });

  form.addEventListener('submit', function () {
    var state = values();
    try {
      localStorage.setItem('theme-mode-override', state.mode);
      localStorage.setItem('theme-base-override', state.base);
      localStorage.setItem('theme-epaper-override', state.epaper);
      localStorage.setItem('theme-radius-override', state.radius);
    } catch (e) {}
  });

  /* Saved state is already represented by /user-theme.css. Do not disable it until the first real edit. */
})();
