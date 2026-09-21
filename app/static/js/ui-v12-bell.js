/* v2026.09.21.21: stable notification bell with direct early scanner SSE. */
(function () {
  'use strict';
  if (window.__b2mBellV12Loaded) return;
  window.__b2mBellV12Loaded = true;

  let flashTimer = null;
  let lastBarcode = '';
  let lastReceivedAt = 0;
  let receivedSource = null;

  function createStableBell() {
    const icon = document.createElement('span');
    icon.className = 'b2m-stable-bell icon icon-1';
    icon.setAttribute('aria-hidden', 'true');
    icon.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
        '<path d="M10 5a2 2 0 0 1 4 0a7 7 0 0 1 4 6v3a4 4 0 0 0 2 3H4a4 4 0 0 0 2-3v-3a7 7 0 0 1 4-6"/>' +
        '<path d="M9 17v1a3 3 0 0 0 6 0v-1"/>' +
      '</svg>';
    return icon;
  }

  function ensureBell() {
    const link = document.querySelector('#notif-dropdown > a');
    if (!link) return null;

    link.classList.add('nav-link');
    link.classList.remove('px-0');

    // Legacy UI layers used ti-bell / ti-bell-filled as mutable state. Keep
    // those nodes out of the visible control; the stable SVG is the only bell.
    link.querySelectorAll(
      'i.ti-bell,i.ti-bell-filled,.b2m-v4-bell-filled,.b2m-bell-active-icon'
    ).forEach(function (node) {
      node.remove();
    });

    let bell = link.querySelector('.b2m-stable-bell');
    if (!bell) {
      bell = createStableBell();
      link.insertBefore(bell, link.firstChild);
    }
    return link;
  }

  function flashBell() {
    const link = ensureBell();
    if (!link) return;

    window.clearTimeout(flashTimer);
    link.classList.remove(
      'b2m-v6-bell-pulse',
      'b2m-v9-bell-pulse',
      'b2m-v10-bell-pulse',
      'b2m-bell-flash',
      'b2m-v12-bell-flash'
    );

    void link.offsetWidth;
    link.classList.add('b2m-v12-bell-flash');
    flashTimer = window.setTimeout(function () {
      link.classList.remove('b2m-v12-bell-flash');
    }, 500);
  }

  function markUnreadImmediately() {
    const badge = document.getElementById('notif-badge');
    if (badge) badge.classList.remove('d-none');
    if (window.refreshNotifications) {
      window.refreshNotifications();
    } else {
      window.setTimeout(function () {
        if (window.refreshNotifications) window.refreshNotifications();
      }, 40);
    }
  }

  function handleReceivedData(data) {
    data = data || {};
    const barcode = String(data.barcode || '');
    const now = Date.now();

    if (barcode && barcode === lastBarcode && now - lastReceivedAt < 120) return;
    lastBarcode = barcode;
    lastReceivedAt = now;

    flashBell();
    markUnreadImmediately();
    window.dispatchEvent(new CustomEvent('b2m:scanner-received', {detail: data}));
  }

  function onReceived(event) {
    let data = {};
    try { data = JSON.parse(event.data || '{}'); } catch (e) {}
    handleReceivedData(data);
  }

  function connectReceivedSource() {
    if (!window.EventSource || receivedSource) return;
    receivedSource = new EventSource('/events');
    receivedSource.addEventListener('received', onReceived);
  }

  // Final scan is only a fallback for a short SSE reconnect race. It must not
  // create a second flash after a normal early `received` event.
  window.addEventListener('b2m:scan', function (event) {
    if (Date.now() - lastReceivedAt < 1200) return;
    handleReceivedData((event && event.detail) || {});
  });

  window.addEventListener('beforeunload', function () {
    if (receivedSource) receivedSource.close();
  });

  function init() {
    ensureBell();
    connectReceivedSource();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, {once: true});
  } else {
    init();
  }
})();
