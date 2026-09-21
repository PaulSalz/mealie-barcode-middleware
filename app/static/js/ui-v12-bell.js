/* v2026.09.21.12: bell feedback is driven by the physical scanner receipt event. */
(function () {
  'use strict';
  if (window.__b2mBellV12Loaded) return;
  window.__b2mBellV12Loaded = true;

  const NativeEventSource = window.EventSource;
  if (!NativeEventSource) return;

  let flashTimer = null;
  let lastBarcode = '';
  let lastReceivedAt = 0;

  function ensureBell() {
    const link = document.querySelector('#notif-dropdown > a');
    if (!link) return null;
    let bell = link.querySelector('i.ti-bell');
    if (!bell) {
      bell = document.createElement('i');
      bell.className = 'ti ti-bell icon icon-1';
      link.insertBefore(bell, link.firstChild);
    }
    link.querySelectorAll('.b2m-v4-bell-filled,.b2m-bell-active-icon').forEach(function (node) {
      node.remove();
    });
    return link;
  }

  function flashBell() {
    const link = ensureBell();
    if (!link) return;
    window.clearTimeout(flashTimer);
    link.classList.remove('b2m-v6-bell-pulse', 'b2m-v9-bell-pulse', 'b2m-v10-bell-pulse', 'b2m-bell-flash', 'b2m-v12-bell-flash');
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

  function onReceived(event) {
    let data = {};
    try { data = JSON.parse(event.data || '{}'); } catch (e) {}
    const barcode = String(data.barcode || '');
    const now = Date.now();

    // Some pages currently have two /events subscribers. De-duplicate the same
    // physical scanner receipt so the 500 ms animation is not restarted twice.
    if (barcode && barcode === lastBarcode && now - lastReceivedAt < 120) return;
    lastBarcode = barcode;
    lastReceivedAt = now;

    flashBell();
    markUnreadImmediately();
    window.dispatchEvent(new CustomEvent('b2m:scanner-received', {detail: data}));
  }

  function WrappedEventSource(url, options) {
    const source = new NativeEventSource(url, options);
    try {
      const value = String(url || '');
      if (value === '/events' || value.endsWith('/events')) {
        // This is emitted by /scanner/received, i.e. the same moment as the
        // already-fast dashboard scanner feedback. Do not wait for /scan.
        source.addEventListener('received', onReceived);
      }
    } catch (e) {}
    return source;
  }

  WrappedEventSource.prototype = NativeEventSource.prototype;
  ['CONNECTING', 'OPEN', 'CLOSED'].forEach(function (key) {
    try { WrappedEventSource[key] = NativeEventSource[key]; } catch (e) {}
  });
  window.EventSource = WrappedEventSource;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureBell, {once: true});
  } else {
    ensureBell();
  }
})();
