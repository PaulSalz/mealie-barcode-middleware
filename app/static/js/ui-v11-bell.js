/* v2026.09.21.11: single notification-bell controller and instant local scan feedback. */
(function () {
  'use strict';
  if (window.__b2mBellV11Loaded) return;
  window.__b2mBellV11Loaded = true;

  const NativeEventSource = window.EventSource;
  if (!NativeEventSource) return;

  let pulseTimer = null;
  let lastPulseAt = 0;

  function bellLink() {
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

  function pulseBell() {
    const link = bellLink();
    if (!link) return;
    lastPulseAt = Date.now();
    window.clearTimeout(pulseTimer);
    link.classList.remove('b2m-v6-bell-pulse', 'b2m-v9-bell-pulse', 'b2m-v10-bell-pulse', 'b2m-bell-flash');
    void link.offsetWidth;
    link.classList.add('b2m-bell-flash');
    pulseTimer = window.setTimeout(function () {
      link.classList.remove('b2m-bell-flash');
    }, 500);
  }

  function pendingToastFor(barcode) {
    return Array.from(document.querySelectorAll('.b2m-scan-received')).find(function (toast) {
      return toast.dataset.barcode === String(barcode || '');
    }) || null;
  }

  function showReceivedToast(data) {
    const container = document.getElementById('scan-toasts');
    if (!container) return;
    const barcode = String(data.barcode || '');
    const item = String(data.item || barcode || 'Scan');
    let toast = pendingToastFor(barcode);
    if (toast) {
      const count = Number(toast.dataset.count || '1') + 1;
      toast.dataset.count = String(count);
      const badge = toast.querySelector('.b2m-received-count');
      if (badge) badge.textContent = '×' + count;
      return;
    }

    toast = document.createElement('div');
    toast.className = 'toast show b2m-scan-received';
    toast.dataset.barcode = barcode;
    toast.dataset.count = '1';
    toast.setAttribute('role', 'status');
    toast.setAttribute('data-bs-autohide', 'false');
    const secondary = item !== barcode && barcode ? ' <span class="text-secondary">(' + escapeHtml(barcode) + ')</span>' : '';
    toast.innerHTML =
      '<div class="toast-header">' +
        '<span class="avatar avatar-xs me-2 bg-primary"><i class="ti ti-scan icon-sm text-white"></i></span>' +
        '<strong class="me-auto">Scan received</strong>' +
        '<span class="badge bg-secondary-lt ms-2 b2m-received-count">×1</span>' +
        '<button type="button" class="ms-2 btn-close" data-bs-dismiss="toast"></button>' +
      '</div>' +
      '<div class="toast-body">' + escapeHtml(item) + secondary + ' <span class="text-secondary">· processing…</span></div>';
    container.prepend(toast);

    window.setTimeout(function () {
      if (toast.isConnected && toast.classList.contains('b2m-scan-received')) toast.remove();
    }, 15000);
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function onScanReceived(event) {
    let data = {};
    try { data = JSON.parse(event.data || '{}'); } catch (e) {}

    // scan-start normally pulsed a few milliseconds earlier. Keep this fallback
    // for reconnect races without creating a second visible pulse.
    if (Date.now() - lastPulseAt > 1000) pulseBell();

    showReceivedToast(data);
    if (window.refreshNotifications) {
      window.refreshNotifications();
    } else {
      window.setTimeout(function () {
        if (window.refreshNotifications) window.refreshNotifications();
      }, 50);
    }
  }

  function WrappedEventSource(url, options) {
    const source = new NativeEventSource(url, options);
    try {
      const value = String(url || '');
      if (value === '/events' || value.endsWith('/events')) {
        source.addEventListener('scan-start', pulseBell);
        source.addEventListener('scan-received', onScanReceived);
      }
    } catch (e) {}
    return source;
  }

  WrappedEventSource.prototype = NativeEventSource.prototype;
  ['CONNECTING', 'OPEN', 'CLOSED'].forEach(function (key) {
    try { WrappedEventSource[key] = NativeEventSource[key]; } catch (e) {}
  });
  window.EventSource = WrappedEventSource;

  // The final scan event is still handled by app.js. Once it has rendered the
  // final toast, remove only our temporary "processing" toast for that barcode.
  window.addEventListener('b2m:scan', function (event) {
    const detail = event.detail || {};
    const toast = pendingToastFor(detail.barcode);
    if (toast) toast.remove();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bellLink, {once: true});
  } else {
    bellLink();
  }
})();
