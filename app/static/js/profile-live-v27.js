/* Legacy compatibility entrypoint. Personal Appearance live preview is handled by theme-controls-v32.js. */
(function () {
  'use strict';
  if (window.location.pathname !== '/profile/appearance') return;
  if (window.__b2mThemeV32Loaded) return;
})();
