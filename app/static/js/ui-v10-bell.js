/* v2026.09.21.10: immediate scan-received feedback without another SSE connection. */
(function () {
  'use strict';
  if (window.__b2mBellV10Loaded) return;
  window.__b2mBellV10Loaded = true;

  const NativeEventSource = window.EventSource;
  if (!NativeEventSource) return;

  let pulseTimer = null;

  function pulseBell() {
    const link = document.querySelector('#notif-dropdown > a');
    if (!link) return;

    let bell = link.querySelector('i.ti-bell');
    if (!bell) {
      bell = document.createElement('i');
      bell.className = 'ti ti-bell icon icon-1';
      link.insertBefore(bell, link.firstChild);
    }

    window.clearTimeout(pulseTimer);
    link.classList.remove('b2m-v10-bell-pulse');
    void link.offsetWidth;
    link.classList.add('b2m-v10-bell-pulse');
    pulseTimer = window.setTimeout(function () {
      link.classList.remove('b2m-v10-bell-pulse');
    }, 500);
  }

  function WrappedEventSource(url, options) {
    const source = new NativeEventSource(url, options);
    try {
      const value = String(url || '');
      if (value === '/events' || value.endsWith('/events')) {
        source.addEventListener('scan-start', pulseBell);
      }
    } catch (e) {}
    return source;
  }

  WrappedEventSource.prototype = NativeEventSource.prototype;
  ['CONNECTING', 'OPEN', 'CLOSED'].forEach(function (key) {
    try { WrappedEventSource[key] = NativeEventSource[key]; } catch (e) {}
  });

  window.EventSource = WrappedEventSource;
})();
