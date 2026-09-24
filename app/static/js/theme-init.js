/* v35 first-paint stabilizer.
   Persisted personal CSS is authoritative. Its machine-readable saved state is
   copied to root data attributes synchronously in <head>, before body paint. */
(function () {
  'use strict';
  var root = document.documentElement;

  try {
    // Remove caches used by the layered v24-v34 implementations. The legacy
    // inline bootstrap in base.html may have read them a few lines earlier, but
    // this script still executes in <head> before the body is parsed/painted.
    ['theme-mode-override','theme-base-override','theme-epaper-override','theme-radius-override'].forEach(function (key) {
      localStorage.removeItem(key);
    });
  } catch (e) {}

  // Keep the persisted personal stylesheet last in the cascade. All structural
  // rules live in global-ui.css; user-theme.css owns the saved values.
  var personal = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(function (link) {
    return String(link.getAttribute('href') || '').indexOf('/user-theme.css') === 0;
  });
  if (personal) document.head.appendChild(personal);

  function saved(name) {
    try {
      return getComputedStyle(root).getPropertyValue('--b2m-saved-' + name).trim();
    } catch (e) {
      return '';
    }
  }

  var mode = saved('mode');
  var base = saved('base');
  var buttonColor = saved('button-color');
  var logoColor = saved('logo-color');
  var radius = saved('radius');
  var font = saved('font');
  var epaper = saved('epaper');
  var contrast = saved('contrast');

  if (mode === 'light' || mode === 'dark') root.setAttribute('data-bs-theme', mode);
  if (base) root.dataset.b2mBase = base;
  if (buttonColor) root.dataset.b2mButtonColor = buttonColor;
  if (logoColor) root.dataset.b2mLogoColor = logoColor;
  if (radius) root.dataset.b2mRadius = radius;
  if (font) root.dataset.b2mFont = font;
  if (epaper === 'true' || epaper === 'false') {
    root.dataset.b2mEpaper = epaper;
    root.classList.toggle('b2m-epaper-v9', epaper === 'true');
    root.classList.toggle('b2m-epaper', epaper === 'true');
  }
  if (contrast) root.dataset.b2mContrast = contrast;
})();
