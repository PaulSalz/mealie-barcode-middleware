/* v35 first-paint stabilizer.
   Persisted personal CSS provides the saved values/metadata; global-ui.css is
   the final live authority. Copy the saved state to root attributes
   synchronously in <head>, before body paint. */
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

  // Do not reorder stylesheets here. base.html intentionally loads
  // user-theme.css before global-ui.css, so persisted state is available for
  // first paint while the generated v35 catalog remains the final cascade
  // authority for subsequent live changes.
  function cssValue(property) {
    try {
      return getComputedStyle(root).getPropertyValue(property).trim();
    } catch (e) {
      return '';
    }
  }

  var mode = cssValue('--b2m-saved-mode');
  var base = cssValue('--b2m-saved-base');
  var buttonColor = cssValue('--b2m-saved-button-color');
  var logoColor = cssValue('--b2m-saved-logo-color');
  var radius = cssValue('--b2m-saved-radius');
  var font = cssValue('--b2m-saved-font');
  var epaper = cssValue('--b2m-saved-epaper');
  var contrast = cssValue('--b2m-saved-contrast');

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
