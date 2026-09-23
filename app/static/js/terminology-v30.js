/* v2026.09.23.30 — consistent appearance terminology. */
(function () {
  'use strict';
  function rename() {
    document.querySelectorAll('label.form-label,h3.card-title').forEach(function (node) {
      var text = String(node.textContent || '').trim();
      if (text === 'Neutral palette' || text === 'Gray shade') node.textContent = 'Background';
    });
    document.querySelectorAll('.card-subtitle').forEach(function (node) {
      if (String(node.textContent || '').trim() === 'The neutral gray tone used for backgrounds and borders.') {
        node.textContent = 'Choose the neutral background tone used for surfaces and borders.';
      }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', rename, {once:true});
  else rename();
})();
