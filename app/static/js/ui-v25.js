(function () {
  'use strict';
  if (window.__b2mUiV25Loaded) return;
  window.__b2mUiV25Loaded = true;

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  function formatUptime(value) {
    var total = Math.max(0, Math.floor(Number(value) || 0));
    if (total < 60) return total + ' sec';

    var minutes = Math.floor(total / 60);
    var seconds = total % 60;
    if (total < 3600) return minutes + ' min' + (seconds ? ' ' + seconds + ' sec' : '');

    var hours = Math.floor(total / 3600);
    minutes = Math.floor((total % 3600) / 60);
    if (total < 86400) return hours + (hours === 1 ? ' hr' : ' hrs') + (minutes ? ' ' + minutes + ' min' : '');

    var days = Math.floor(total / 86400);
    hours = Math.floor((total % 86400) / 3600);
    if (total < 604800) return days + (days === 1 ? ' day' : ' days') + (hours ? ' ' + hours + (hours === 1 ? ' hr' : ' hrs') : '');

    var weeks = Math.floor(total / 604800);
    days = Math.floor((total % 604800) / 86400);
    return weeks + (weeks === 1 ? ' week' : ' weeks') + (days ? ' ' + days + (days === 1 ? ' day' : ' days') : '');
  }

  function patchScannerRows() {
    if (window.location.pathname !== '/settings') return;
    var tab = new URLSearchParams(window.location.search).get('tab') || 'mealie';
    if (tab !== 'scanning') return;

    document.querySelectorAll('#scanner-health-body-v4 tr, #scanner-health-body tr').forEach(function (row) {
      var cells = row.querySelectorAll(':scope > td');
      if (cells.length < 5) return;

      var stats = cells[3];
      var detail = stats.querySelector('.text-secondary.small');
      if (detail && !detail.querySelector('[data-b2m-error-scans]')) {
        var text = detail.textContent.trim();
        var match = text.match(/^(\d+)\s+errors?\s*(?:·\s*(.*))?$/i);
        if (match) {
          var count = Number(match[1]);
          var suffix = (match[2] || '').trim();
          detail.innerHTML = '<a data-b2m-error-scans href="/activities?result=error" class="' + (count ? 'text-danger' : 'text-secondary') + ' text-decoration-none" title="Open error scans">' + count + ' error' + (count === 1 ? '' : 's') + '</a>' + (suffix ? ' · ' + esc(suffix) : '');
        }
      }

      var uptime = cells[4];
      var raw = uptime.dataset.b2mUptimeSeconds || uptime.textContent.trim();
      if (/^\d+$/.test(raw)) {
        var formatted = formatUptime(Number(raw));
        var title = Number(raw).toLocaleString() + ' seconds';
        if (uptime.dataset.b2mUptimeSeconds !== raw) uptime.dataset.b2mUptimeSeconds = raw;
        if (uptime.textContent.trim() !== formatted) uptime.textContent = formatted;
        if (uptime.title !== title) uptime.title = title;
      }
    });
  }

  function installScannerPolish() {
    patchScannerRows();
    if (window.location.pathname !== '/settings') return;
    var observer = new MutationObserver(function () { patchScannerRows(); });
    observer.observe(document.body, {childList: true, subtree: true});
  }

  function styleScanLinkMode() {
    if (window.location.pathname !== '/settings') return;
    Array.from(document.querySelectorAll('h3.card-title')).forEach(function (title) {
      if (title.textContent.trim() !== 'Scan & Link Mode') return;
      var card = title.closest('.card');
      if (card) card.classList.add('b2m-scan-link-card');
    });
  }

  function syncBulkCountVisibility() {
    var count = document.getElementById('b2m-bulk-count');
    if (!count) return false;
    var update = function () {
      var value = Number.parseInt(count.textContent.trim(), 10) || 0;
      count.classList.toggle('d-none', value < 1);
    };
    if (count.dataset.b2mHideZero !== '1') {
      count.dataset.b2mHideZero = '1';
      new MutationObserver(update).observe(count, {childList: true, characterData: true, subtree: true});
    }
    update();
    return true;
  }

  function installBulkCountPolish() {
    if (syncBulkCountVisibility()) return;
    var observer = new MutationObserver(function () {
      if (syncBulkCountVisibility()) observer.disconnect();
    });
    observer.observe(document.body, {childList: true, subtree: true});
  }

  function correctProductDbLabel() {
    if (!window.location.pathname.startsWith('/barcodes/') || window.location.pathname === '/barcodes/') return;
    var codeNode = document.querySelector('.page-pretitle code');
    var barcode = codeNode ? codeNode.textContent.trim() : '';
    var source = '';
    var dbMatchItem = null;

    document.querySelectorAll('.datagrid-item').forEach(function (item) {
      var title = item.querySelector('.datagrid-title');
      var content = item.querySelector('.datagrid-content');
      if (!title || !content) return;
      var label = title.textContent.trim();
      if (label === 'Lookup source') source = content.textContent.trim();
      if (label === 'Found in product DB') dbMatchItem = item;
    });

    if (!dbMatchItem) return;
    var providerMatch = /^\d+$/.test(barcode) && /(openfoodfacts|upcdatabase)/i.test(source);
    var title = dbMatchItem.querySelector('.datagrid-title');
    var content = dbMatchItem.querySelector('.datagrid-content');
    title.textContent = 'Product database match';
    content.innerHTML = providerMatch
      ? '<span class="badge bg-green text-green-fg">Yes</span>'
      : '<span class="badge bg-secondary-lt text-secondary">No</span>';
  }

  function installDashboardMealieSync() {
    if (window.location.pathname !== '/') return;
    fetch('/api/access/me', {headers: {Accept: 'application/json'}})
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (access) {
        if (!access || (!access.is_admin && !(access.permissions && access.permissions.items))) return;
        if (document.getElementById('b2m-dashboard-mealie-sync')) return;
        var heading = Array.from(document.querySelectorAll('h2.page-title')).find(function (node) { return node.textContent.trim() === 'Mealie'; });
        var row = heading && heading.closest('.row');
        if (!row) return;

        var slot = document.createElement('div');
        slot.className = 'col-auto ms-auto align-self-start';
        var button = document.createElement('button');
        button.type = 'button';
        button.id = 'b2m-dashboard-mealie-sync';
        button.className = 'btn btn-sm btn-icon btn-outline-primary';
        button.title = 'Sync Mealie items now';
        button.setAttribute('aria-label', 'Sync Mealie items now');
        button.innerHTML = '<i class="ti ti-refresh"></i>';
        slot.appendChild(button);
        row.appendChild(slot);

        button.addEventListener('click', async function () {
          var original = button.innerHTML;
          button.disabled = true;
          button.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>';
          try {
            var response = await fetch('/items/sync', {method: 'POST', credentials: 'same-origin', redirect: 'follow'});
            if (!response.ok) throw new Error('Mealie sync failed');
            button.innerHTML = '<i class="ti ti-check"></i>';
            window.setTimeout(function () { window.location.reload(); }, 250);
          } catch (error) {
            button.classList.remove('btn-outline-primary');
            button.classList.add('btn-outline-danger');
            button.title = error.message;
            button.innerHTML = '<i class="ti ti-alert-triangle"></i>';
            window.setTimeout(function () {
              button.disabled = false;
              button.classList.remove('btn-outline-danger');
              button.classList.add('btn-outline-primary');
              button.title = 'Sync Mealie items now';
              button.innerHTML = original;
            }, 2500);
          }
        });
      })
      .catch(function () {});
  }

  function init() {
    installScannerPolish();
    styleScanLinkMode();
    installBulkCountPolish();
    correctProductDbLabel();
    installDashboardMealieSync();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
