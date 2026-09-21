/* Compatibility guard for the v2 printer settings timer.
 * v3 hides the legacy System printer card. Keep the node alive so the old
 * five-second refresh timer can continue harmlessly until v2 is retired.
 */
(function () {
  'use strict';
  var originalRemove = Element.prototype.remove;
  Element.prototype.remove = function () {
    var params = new URLSearchParams(window.location.search);
    var tab = params.get('tab') || 'mealie';
    if (window.location.pathname === '/settings' && tab === 'system' && this.id === 'b2m-printer-settings-card') {
      this.style.display = 'none';
      this.setAttribute('aria-hidden', 'true');
      return;
    }
    return originalRemove.call(this);
  };
})();
