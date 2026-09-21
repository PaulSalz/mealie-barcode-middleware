/* v2026.09.21.20: one stable notification-bell glyph and early scanner feedback. */
(function () {
  'use strict';
  if (window.__b2mBellV12Loaded) return;
  window.__b2mBellV12Loaded = true;

  const NativeEventSource = window.EventSource;
  if (!NativeEventSource) return;

  let flashTimer = null;
  let lastBarcode = '';
  let lastReceivedAt = 0;

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

    // Match the neighbouring three-dots control: plain Tabler nav-link sizing.
    // The visible glyph deliberately does not carry ti-bell/ti-bell-filled,
    // because legacy observers used those classes as mutable state and could
    // temporarily replace the icon while a scan was being processed.
    link.classList.add('nav-link');
    link.classList.remove('px-0');

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

  function onReceived(event) {
    let data = {};
    try { data = JSON.parse(event.data || '{}'); } catch (e) {}
    const barcode = String(data.barcode || '');
    const now = Date.now();

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
