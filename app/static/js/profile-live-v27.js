(function () {
  'use strict';
  if (window.location.pathname !== '/profile/appearance') return;

  function boot() {
    var root = document.documentElement;
    var form = document.querySelector('form[action="/profile/appearance"]');
    if (!form) return;

    var epaper = form.querySelector('input[name="theme_epaper"]');
    var contrast = document.getElementById('profile-contrast');
    var contrastOut = document.getElementById('profile-contrast-value');
    var userThemeLink = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(function (link) {
      return String(link.getAttribute('href') || '').indexOf('/user-theme.css') === 0;
    });
    var globalThemeLink = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(function (link) {
      return String(link.getAttribute('href') || '').indexOf('/theme.css') === 0;
    });
    var previewStyle = document.createElement('style');
    previewStyle.id = 'b2m-personal-theme-live-preview';
    document.head.appendChild(previewStyle);
    var previewTimer = null;
    var requestId = 0;

    function checkedValue(name, fallback) {
      var checked = form.querySelector('input[name="' + name + '"]:checked');
      if (checked) return checked.value;
      var select = form.querySelector('select[name="' + name + '"]');
      return select ? select.value : fallback;
    }

    function payload() {
      return {
        mode: checkedValue('theme_mode', root.getAttribute('data-bs-theme') || 'light'),
        color: checkedValue('theme_color', 'blue'),
        font: checkedValue('theme_font', 'sans-serif'),
        base: checkedValue('theme_base', 'gray'),
        radius: checkedValue('theme_radius', '1'),
        date_style: checkedValue('theme_date_style', 'medium'),
        epaper: epaper && epaper.checked ? 'true' : 'false',
        contrast: contrast ? String(contrast.value) : '65'
      };
    }

    function radiusValue(scale) {
      var map = {'0':0,'0.5':.25,'1':.5,'1.5':.8,'2':1.1};
      var key = String(scale == null ? '1' : scale);
      return Object.prototype.hasOwnProperty.call(map, key) ? map[key] : .5;
    }

    function applyRadiusOnly() {
      var scale = checkedValue('theme_radius', '1');
      var base = radiusValue(scale);
      root.style.setProperty('--tblr-border-radius-scale', String(scale));
      root.style.setProperty('--tblr-border-radius', base + 'rem');
      root.style.setProperty('--tblr-border-radius-sm', Math.max(0, base * .72) + 'rem');
      root.style.setProperty('--tblr-border-radius-lg', Math.max(0, base * 1.45) + 'rem');
      root.style.setProperty('--tblr-border-radius-xl', Math.max(0, base * 1.9) + 'rem');
    }

    function applyImmediateState() {
      var values = payload();
      root.setAttribute('data-bs-theme', values.mode);
      root.dataset.b2mBase = values.base;
      var mono = values.epaper === 'true';
      root.classList.toggle('b2m-epaper-v9', mono);
      root.classList.toggle('b2m-epaper', mono);
      applyRadiusOnly();
      if (contrastOut && contrast) contrastOut.textContent = contrast.value;
    }

    function setSavedStylesEnabled(enabled) {
      if (userThemeLink) userThemeLink.disabled = !enabled;
      if (globalThemeLink) globalThemeLink.disabled = !enabled;
    }

    async function renderExactPreview(disableSavedImmediately) {
      applyImmediateState();
      if (disableSavedImmediately) setSavedStylesEnabled(false);
      var id = ++requestId;
      try {
        var response = await fetch('/api/appearance-v24/preview', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', Accept: 'text/css'},
          cache: 'no-store',
          body: JSON.stringify(payload())
        });
        if (!response.ok) throw new Error('HTTP ' + response.status);
        var css = await response.text();
        if (id !== requestId) return;
        previewStyle.textContent = css;
        /* The response is the complete effective personal theme. Disabling both
           persisted layers is required for defaults such as gray/epaper=false to
           remove a saved/global override instead of being stacked on top of it. */
        setSavedStylesEnabled(false);
        applyImmediateState();
      } catch (error) {
        if (id !== requestId) return;
        previewStyle.textContent = '';
        setSavedStylesEnabled(true);
        applyImmediateState();
      }
    }

    function schedulePreview(disableSavedImmediately) {
      applyImmediateState();
      clearTimeout(previewTimer);
      previewTimer = window.setTimeout(function () {
        renderExactPreview(disableSavedImmediately);
      }, 25);
    }

    function handleThemeInput(event) {
      if (!event.target.matches('input[name^="theme_"],select[name^="theme_"]')) return;
      /* Radius is a geometry-only preference. Re-rendering the complete theme for
         it used to disable/re-enable the persisted stylesheet and visibly change
         the selected background. Keep it isolated and purely local. */
      if (event.target.name === 'theme_radius') {
        applyRadiusOnly();
        return;
      }
      schedulePreview(true);
    }

    form.addEventListener('input', handleThemeInput);
    form.addEventListener('change', handleThemeInput);

    if (contrast) {
      contrast.addEventListener('input', function () {
        if (contrastOut) contrastOut.textContent = contrast.value;
        schedulePreview(true);
      });
    }
    if (epaper) epaper.addEventListener('change', function () { schedulePreview(true); });

    form.addEventListener('submit', function () {
      var values = payload();
      localStorage.setItem('theme-mode-override', values.mode);
      localStorage.setItem('theme-base-override', values.base);
      localStorage.setItem('theme-epaper-override', values.epaper);
    });

    applyImmediateState();
    renderExactPreview(false);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
