/* Keep the long-lived preview style id stable for browser integrations/tests. */
(function () {
  'use strict';
  if (window.location.pathname !== '/profile/appearance') return;
  var preview = document.getElementById('b2m-theme-v34-preview');
  if (preview) preview.id = 'b2m-theme-v32-preview';
})();
