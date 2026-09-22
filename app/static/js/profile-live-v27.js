(function () {
  'use strict';
  if (window.location.pathname !== '/profile/appearance') return;

  var root = document.documentElement;
  var form = document.querySelector('form[action="/profile/appearance"]');
  var epaper = form && form.querySelector('input[name="theme_epaper"]');
  var contrast = document.getElementById('profile-contrast');
  var contrastOut = document.getElementById('profile-contrast-value');
  var base = form && form.querySelector('select[name="theme_base"]');

  if (!form) return;

  function applyEpaperPreview() {
    var enabled = !!(epaper && epaper.checked);
    var value = contrast ? Math.max(0, Math.min(100, Number(contrast.value || 65))) : 65;
    var border = Math.max(24, 220 - Math.round(value * 1.7));
    var muted = Math.max(0, 112 - Math.round(value * .9));
    var surface = Math.max(238, 255 - Math.round(value * .12));

    root.classList.toggle('b2m-epaper-live', enabled);
    root.classList.toggle('b2m-epaper-v9', enabled);
    root.style.setProperty('--b2m-live-epaper-border', 'rgb(' + border + ',' + border + ',' + border + ')');
    root.style.setProperty('--b2m-live-epaper-muted', 'rgb(' + muted + ',' + muted + ',' + muted + ')');
    root.style.setProperty('--b2m-live-epaper-surface', 'rgb(' + surface + ',' + surface + ',' + surface + ')');
    if (contrastOut && contrast) contrastOut.textContent = contrast.value;
  }

  function applyBasePreview() {
    if (!base) return;
    root.dataset.b2mBase = base.value || 'gray';
  }

  form.querySelectorAll('input[name="theme_mode"]').forEach(function (input) {
    input.addEventListener('change', function () {
      if (this.checked) root.setAttribute('data-bs-theme', this.value);
      applyEpaperPreview();
    });
  });

  if (epaper) epaper.addEventListener('change', applyEpaperPreview);
  if (contrast) contrast.addEventListener('input', applyEpaperPreview);
  if (base) {
    base.addEventListener('input', applyBasePreview);
    base.addEventListener('change', applyBasePreview);
  }

  /* Cache only values that are actually being submitted. Unsaved previews do not
     leak to the next page when the user navigates away without saving. */
  form.addEventListener('submit', function () {
    var selectedMode = form.querySelector('input[name="theme_mode"]:checked');
    if (selectedMode) localStorage.setItem('theme-mode-override', selectedMode.value);
    if (base) localStorage.setItem('theme-base-override', base.value || 'gray');
  });

  applyBasePreview();
  applyEpaperPreview();
})();
