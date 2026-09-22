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
    var base = form.querySelector('select[name="theme_base"]');
    var userThemeLink = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(function (link) {
      return String(link.getAttribute('href') || '').indexOf('/user-theme.css') === 0;
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

    function applyImmediateState() {
      var values = payload();
      root.setAttribute('data-bs-theme', values.mode);
      root.dataset.b2mBase = values.base;
      root.classList.toggle('b2m-epaper-v9', values.epaper === 'true');
      if (contrastOut && contrast) contrastOut.textContent = contrast.value;
    }

    async function renderExactPreview(disableSavedImmediately) {
      applyImmediateState();
      if (disableSavedImmediately && userThemeLink) userThemeLink.disabled = true;
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
        if (userThemeLink) userThemeLink.disabled = true;
      } catch (error) {
        if (userThemeLink) userThemeLink.disabled = false;
      }
    }

    function schedulePreview(disableSavedImmediately) {
      applyImmediateState();
      clearTimeout(previewTimer);
      previewTimer = window.setTimeout(function () {
        renderExactPreview(disableSavedImmediately);
      }, 45);
    }

    form.addEventListener('input', function (event) {
      if (!event.target.matches('input[name^="theme_"],select[name^="theme_"]')) return;
      schedulePreview(true);
    });
    form.addEventListener('change', function (event) {
      if (!event.target.matches('input[name^="theme_"],select[name^="theme_"]')) return;
      schedulePreview(true);
    });

    /* Cache only values that are actually being submitted. Unsaved previews do not
       leak to the next page when the user navigates away without saving. */
    form.addEventListener('submit', function () {
      var values = payload();
      localStorage.setItem('theme-mode-override', values.mode);
      localStorage.setItem('theme-base-override', values.base);
    });

    applyImmediateState();
    renderExactPreview(false);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
