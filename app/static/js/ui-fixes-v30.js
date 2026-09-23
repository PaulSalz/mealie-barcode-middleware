/* v2026.09.23.30 — isolate radius from background and stabilize personal theme preview. */
(function () {
  'use strict';
  if (window.location.pathname !== '/profile/appearance' || window.__b2mAppearanceV30Loaded) return;
  window.__b2mAppearanceV30Loaded = true;

  var root = document.documentElement;
  var form = document.querySelector('form[action="/profile/appearance"]');
  if (!form) return;
  var timer = null;
  var requestId = 0;
  var preview = document.createElement('style');
  preview.id = 'b2m-appearance-v30-preview';
  document.head.appendChild(preview);
  var userTheme = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(function (link) {
    return String(link.getAttribute('href') || '').indexOf('/user-theme.css') === 0;
  });

  function value(name, fallback) {
    var checked = form.querySelector('input[name="' + name + '"]:checked');
    if (checked) return checked.value;
    var field = form.querySelector('[name="' + name + '"]');
    return field ? field.value : fallback;
  }

  function payload() {
    var epaper = form.querySelector('input[name="theme_epaper"]');
    var contrast = form.querySelector('[name="theme_contrast"]');
    return {
      mode:value('theme_mode', root.getAttribute('data-bs-theme') || 'light'),
      color:value('theme_color', 'blue'),
      font:value('theme_font', 'sans-serif'),
      base:value('theme_base', 'gray'),
      radius:value('theme_radius', '1'),
      date_style:value('theme_date_style', 'medium'),
      epaper:epaper && epaper.checked ? 'true' : 'false',
      contrast:contrast ? String(contrast.value) : '65'
    };
  }

  function radiusRem(scale) {
    var map = {'0':0,'0.5':.25,'1':.5,'1.5':.8,'2':1.1};
    return Object.prototype.hasOwnProperty.call(map, String(scale)) ? map[String(scale)] : .5;
  }

  function applyRadius() {
    var scale = value('theme_radius', '1');
    var base = radiusRem(scale);
    root.style.setProperty('--tblr-border-radius-scale', scale);
    root.style.setProperty('--tblr-border-radius', base + 'rem');
    root.style.setProperty('--tblr-border-radius-sm', (base * .72) + 'rem');
    root.style.setProperty('--tblr-border-radius-lg', (base * 1.45) + 'rem');
    root.style.setProperty('--tblr-border-radius-xl', (base * 1.9) + 'rem');
  }

  async function renderFullPreview() {
    var id = ++requestId;
    try {
      var response = await fetch('/api/appearance-v24/preview', {
        method:'POST', headers:{'Content-Type':'application/json',Accept:'text/css'}, cache:'no-store',
        body:JSON.stringify(payload())
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      var css = await response.text();
      if (id !== requestId) return;
      preview.textContent = css;
      if (userTheme) userTheme.disabled = true;
      var p = payload();
      root.setAttribute('data-bs-theme', p.mode);
      root.dataset.b2mBase = p.base;
      root.classList.toggle('b2m-epaper-v9', p.epaper === 'true');
      root.classList.toggle('b2m-epaper', p.epaper === 'true');
      applyRadius();
    } catch (e) {
      if (id !== requestId) return;
      if (userTheme) userTheme.disabled = false;
      preview.textContent = '';
    }
  }

  function scheduleFullPreview() {
    clearTimeout(timer);
    timer = window.setTimeout(renderFullPreview, 30);
  }

  /* Capture radius before older target/bubble listeners. Radius changes only
     geometry; they must never trigger a full stylesheet swap/background change. */
  function interceptRadius(event) {
    if (!event.target || event.target.name !== 'theme_radius') return;
    event.stopPropagation();
    applyRadius();
  }
  form.addEventListener('input', interceptRadius, true);
  form.addEventListener('change', interceptRadius, true);

  form.addEventListener('input', function (event) {
    if (!event.target.matches('input[name^="theme_"],select[name^="theme_"],input[name="theme_contrast"]')) return;
    if (event.target.name === 'theme_radius') return;
    scheduleFullPreview();
  });
  form.addEventListener('change', function (event) {
    if (!event.target.matches('input[name^="theme_"],select[name^="theme_"],input[name="theme_contrast"]')) return;
    if (event.target.name === 'theme_radius') return;
    scheduleFullPreview();
  });

  form.addEventListener('submit', function () {
    var p = payload();
    try {
      localStorage.setItem('theme-mode-override', p.mode);
      localStorage.setItem('theme-base-override', p.base);
      localStorage.setItem('theme-epaper-override', p.epaper);
    } catch (e) {}
  });

  applyRadius();
})();
