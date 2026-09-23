/* v2026.09.24.1 — synchronous, CSP-compatible personal theme controller.
   Theme variables are applied through CSSOM; complex modes use static classes
   from theme-live-v33.css. No preview request or dynamic <style> is used. */
(function () {
  'use strict';
  if (window.__b2mThemeV33Loaded) return;
  window.__b2mThemeV33Loaded = true;
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
  var persistedThemeLink = null;
  var liveActive = false;

  function setStoredMode(mode) {
    try { localStorage.setItem('theme-mode-override', mode); } catch (e) {}
  }

  function setVar(name, value) {
    root.style.setProperty(name, String(value), 'important');
  }

  function clearVar(name) {
    root.style.removeProperty(name);
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

  function ensureLiveOwnership() {
    if (liveActive) return;
    liveActive = true;
    persistedThemeLink = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(function (link) {
      return String(link.getAttribute('href') || '').indexOf('/user-theme.css') === 0;
    }) || null;
    if (persistedThemeLink) persistedThemeLink.disabled = true;
  }

  function applyTheme(theme) {
    ensureLiveOwnership();
    var mode = theme.mode === 'dark' ? 'dark' : 'light';
    var base = PALETTES[theme.base] ? theme.base : 'gray';
    var palette = PALETTES[base];
    var epaper = theme.epaper === 'true';
    var color = COLORS[theme.color] ? theme.color : (theme.color === 'rainbow' ? 'rainbow' : 'blue');
    var font = FONTS[theme.font] ? theme.font : 'sans-serif';
    var radiusKey = Object.prototype.hasOwnProperty.call(RADIUS, String(theme.radius)) ? String(theme.radius) : '1';
    var radius = RADIUS[radiusKey];
    var contrast = Math.max(0, Math.min(100, Number(theme.contrast || 65)));
    if (!Number.isFinite(contrast)) contrast = 65;

    root.setAttribute('data-bs-theme', mode);
    root.dataset.b2mBase = base;
    Object.keys(palette).forEach(function (step) { setVar('--tblr-gray-' + step, palette[step]); });

    if (mode === 'dark') {
      setVar('--tblr-body-color', palette[100]);
      setVar('--tblr-body-bg', palette[950]);
      setVar('--tblr-bg-surface', palette[900]);
      setVar('--tblr-bg-surface-secondary', palette[800]);
      setVar('--tblr-secondary-bg', palette[800]);
      setVar('--tblr-border-color', palette[700]);
      setVar('--tblr-secondary-color', palette[400]);
      setVar('--tblr-light-text-emphasis', palette[100]);
      setVar('--tblr-dark-text-emphasis', palette[300]);
      setVar('--tblr-light-bg-subtle', palette[800]);
    } else {
      setVar('--tblr-body-color', palette[900]);
      setVar('--tblr-body-bg', palette[100]);
      setVar('--tblr-bg-surface', palette[50]);
      setVar('--tblr-bg-surface-secondary', palette[200]);
      setVar('--tblr-secondary-bg', palette[200]);
      setVar('--tblr-border-color', palette[300]);
      setVar('--tblr-secondary-color', palette[600]);
      setVar('--tblr-light-text-emphasis', palette[900]);
      setVar('--tblr-dark-text-emphasis', palette[700]);
      setVar('--tblr-light-bg-subtle', palette[100]);
    }

    setVar('--tblr-body-font-family', FONTS[font]);
    root.classList.toggle('b2m-font-dyslexia-live', font === 'dyslexia');

    setVar('--tblr-border-radius-scale', radiusKey);
    setVar('--tblr-border-radius', radius + 'rem');
    setVar('--tblr-border-radius-sm', Math.max(0, radius * .72) + 'rem');
    setVar('--tblr-border-radius-lg', Math.max(0, radius * 1.45) + 'rem');
    setVar('--tblr-border-radius-xl', Math.max(0, radius * 1.9) + 'rem');

    root.classList.toggle('b2m-epaper-v9', epaper);
    root.classList.toggle('b2m-epaper', epaper);
    root.classList.toggle('b2m-theme-live-epaper', epaper);
    root.classList.toggle('b2m-rainbow-disabled', epaper || color !== 'rainbow');
    root.classList.toggle('b2m-rainbow-active', !epaper && color === 'rainbow');

    if (epaper) {
      var border = Math.max(24, 220 - Math.round(contrast * 1.7));
      var muted = Math.max(0, 112 - Math.round(contrast * .9));
      var surface = Math.max(238, 255 - Math.round(contrast * .12));
      setVar('--b2m-epaper-border', 'rgb(' + border + ',' + border + ',' + border + ')');
      setVar('--b2m-epaper-muted', 'rgb(' + muted + ',' + muted + ',' + muted + ')');
      setVar('--b2m-epaper-surface', 'rgb(' + surface + ',' + surface + ',' + surface + ')');
      setVar('--tblr-primary', '#000');
      setVar('--tblr-primary-rgb', '0,0,0');
      setVar('--tblr-body-color', '#000');
      setVar('--tblr-body-bg', '#fff');
      setVar('--tblr-bg-surface', 'rgb(' + surface + ',' + surface + ',' + surface + ')');
      setVar('--tblr-bg-surface-secondary', 'rgb(' + surface + ',' + surface + ',' + surface + ')');
      setVar('--tblr-secondary-bg', 'rgb(' + surface + ',' + surface + ',' + surface + ')');
      setVar('--tblr-border-color', 'rgb(' + border + ',' + border + ',' + border + ')');
      setVar('--tblr-secondary-color', 'rgb(' + muted + ',' + muted + ',' + muted + ')');
      setVar('--tblr-link-color', '#000');
      setVar('--tblr-link-hover-color', '#000');
    } else {
      clearVar('--b2m-epaper-border');
      clearVar('--b2m-epaper-muted');
      clearVar('--b2m-epaper-surface');
      clearVar('--tblr-link-color');
      clearVar('--tblr-link-hover-color');
      if (color === 'rainbow') {
        clearVar('--tblr-primary');
        clearVar('--tblr-primary-rgb');
      } else {
        setVar('--tblr-primary', COLORS[color].hex);
        setVar('--tblr-primary-rgb', COLORS[color].rgb);
      }
    }

    var out = document.getElementById('profile-contrast-value');
    if (out) out.textContent = String(Math.round(contrast));
    window.dispatchEvent(new CustomEvent('b2m:theme-live-change', {detail:{theme:theme}}));
  }

  var form = window.location.pathname === '/profile/appearance'
    ? document.querySelector('form[action="/profile/appearance"]') : null;

  function renderProfilePreview() {
    if (!form) return;
    applyTheme(formValues(form));
  }

  function syncAppearanceMode(mode) {
    if (!form) return;
    var input = form.querySelector('input[name="theme_mode"][value="' + mode + '"]');
    if (input) input.checked = true;
    renderProfilePreview();
  }

  function applyMode(mode, persist) {
    if (mode !== 'light' && mode !== 'dark') return;
    if (form) syncAppearanceMode(mode);
    else root.setAttribute('data-bs-theme', mode);
    setStoredMode(mode);
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
    }).catch(function () {});
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

  if (!form) return;

  function isThemeField(target) {
    return !!(target && target.matches && target.matches('input[name^="theme_"],select[name^="theme_"]'));
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
})();
