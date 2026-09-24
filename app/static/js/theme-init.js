/* v35 first-paint stabilizer.
   The server stylesheet is authoritative; no localStorage or async fetch may
   modify appearance before/after paint. */
(function () {
  'use strict';
  var root = document.documentElement;

  try {
    // Remove caches used by the layered v24-v34 implementations. The inline
    // legacy bootstrap in base.html may have read them a few lines earlier;
    // everything below is still in <head>, before body paint, and corrects it.
    ['theme-mode-override','theme-base-override','theme-epaper-override','theme-radius-override'].forEach(function (key) {
      localStorage.removeItem(key);
    });
  } catch (e) {}

  root.classList.remove('b2m-epaper-v9', 'b2m-epaper');
  delete root.dataset.b2mBase;
  delete root.dataset.b2mButtonColor;
  delete root.dataset.b2mLogoColor;
  delete root.dataset.b2mRadius;
  delete root.dataset.b2mFont;
  delete root.dataset.b2mEpaper;

  // global-ui.css contains the structural theme rules. Keep the persisted
  // personal stylesheet last in the cascade without waiting for JavaScript in
  // the body. The link is already loaded; moving it does not create a new theme.
  var personal = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find(function (link) {
    return String(link.getAttribute('href') || '').indexOf('/user-theme.css') === 0;
  });
  if (personal) document.head.appendChild(personal);

  // build_theme_css exposes the persisted mode as a CSS custom property. A
  // synchronous style read here fixes data-bs-theme before the body is parsed,
  // so Tabler's own mode selectors and our surfaces start on the same frame.
  try {
    var saved = getComputedStyle(root).getPropertyValue('--b2m-saved-mode').trim();
    if (saved === 'light' || saved === 'dark') root.setAttribute('data-bs-theme', saved);
  } catch (e) {}
})();
