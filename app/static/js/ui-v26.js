(function () {
  'use strict';
  if (window.__b2mUiV26Loaded) return;
  window.__b2mUiV26Loaded = true;

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  var latestErrorScanCount = null;
  var errorRefreshTimer = null;
  var frequentRefreshTimer = null;

  function onScanningSettings() {
    if (window.location.pathname !== '/settings') return false;
    return (new URLSearchParams(window.location.search).get('tab') || 'mealie') === 'scanning';
  }

  function patchScannerErrorRows() {
    if (!onScanningSettings() || latestErrorScanCount == null) return;

    document.querySelectorAll('#scanner-health-body-v4 tr, #scanner-health-body tr').forEach(function (row) {
      var cells = row.querySelectorAll(':scope > td');
      if (cells.length < 4) return;
      var detail = cells[3].querySelector('.text-secondary.small');
      if (!detail) return;

      var bridgeErrors = detail.dataset.b2mBridgeErrors;
      var tail = detail.dataset.b2mStatsTail;
      if (bridgeErrors == null) {
        var match = detail.textContent.trim().match(/^(\d+)\s+errors?\s*(?:·\s*(.*))?$/i);
        if (!match) return;
        bridgeErrors = String(Number(match[1]) || 0);
        tail = (match[2] || '').trim();
        detail.dataset.b2mBridgeErrors = bridgeErrors;
        detail.dataset.b2mStatsTail = tail;
      }

      var errorCount = Number(latestErrorScanCount) || 0;
      var bridgeCount = Number(bridgeErrors) || 0;
      var signature = [errorCount, bridgeCount, tail || ''].join('|');
      if (detail.dataset.b2mErrorUi === signature) return;
      detail.dataset.b2mErrorUi = signature;

      var html = '<a data-b2m-error-scans href="/activities?result=errors" class="' +
        (errorCount ? 'text-danger' : 'text-secondary') +
        ' text-decoration-none" title="Open failed/degraded scan events">' +
        errorCount + ' error scan' + (errorCount === 1 ? '' : 's') + '</a>';
      html += ' · <span class="text-secondary" title="USB bridge / HTTP delivery errors">' +
        bridgeCount + ' bridge error' + (bridgeCount === 1 ? '' : 's') + '</span>';
      if (tail) html += ' · ' + esc(tail);
      detail.innerHTML = html;
    });
  }

  function refreshErrorScanCount() {
    if (!onScanningSettings()) return;
    fetch('/api/activities?result=errors', {headers: {Accept: 'application/json'}, cache: 'no-store'})
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        if (!data) return;
        latestErrorScanCount = Number(data.count == null ? ((data.items || []).length) : data.count) || 0;
        patchScannerErrorRows();
      })
      .catch(function () {});
  }

  function installScannerErrorUi() {
    if (!onScanningSettings()) return;
    refreshErrorScanCount();
    new MutationObserver(function () { patchScannerErrorRows(); })
      .observe(document.body, {childList: true, subtree: true});
  }

  function findHeading(text) {
    return Array.from(document.querySelectorAll('h3.card-title')).find(function (node) {
      return node.textContent.trim() === text;
    });
  }

  function ensureFrequentSection() {
    if (window.location.pathname !== '/') return null;
    var existing = document.getElementById('b2m-frequent-dashboard');
    if (existing) return existing;

    var foodHeading = findHeading('Frequently used Foods');
    if (foodHeading) {
      var row = foodHeading.closest('.row.row-deck') || foodHeading.closest('.row');
      if (row) {
        row.id = 'b2m-frequent-dashboard';
        var mappings = [
          ['Frequently used Foods', 'b2m-frequent-foods'],
          ['Frequently used Recipes', 'b2m-frequent-recipes'],
          ['Frequently used Actions', 'b2m-frequent-actions']
        ];
        mappings.forEach(function (pair) {
          var heading = findHeading(pair[0]);
          var list = heading && heading.closest('.card') && heading.closest('.card').querySelector('.list-group.list-group-flush');
          if (list) list.id = pair[1];
        });
        return row;
      }
    }

    var recent = document.getElementById('recent-scans-card');
    var recentRow = recent && recent.closest('.row.row-deck');
    if (!recentRow || !recentRow.parentNode) return null;

    var row = document.createElement('div');
    row.id = 'b2m-frequent-dashboard';
    row.className = 'row row-deck row-cards mb-3';
    row.innerHTML =
      '<div class="col-lg-4"><div class="card h-100"><div class="card-header"><div><h3 class="card-title">Frequently used Foods</h3><p class="card-subtitle">Based on scan target snapshots.</p></div></div><div class="list-group list-group-flush" id="b2m-frequent-foods"></div></div></div>' +
      '<div class="col-lg-4"><div class="card h-100"><div class="card-header"><div><h3 class="card-title">Frequently used Recipes</h3><p class="card-subtitle">Historical recipe targets.</p></div></div><div class="list-group list-group-flush" id="b2m-frequent-recipes"></div></div></div>' +
      '<div class="col-lg-4"><div class="card h-100"><div class="card-header"><div><h3 class="card-title">Frequently used Actions</h3><p class="card-subtitle">Webhook / automation codes.</p></div></div><div class="list-group list-group-flush" id="b2m-frequent-actions"></div></div></div>';
    recentRow.parentNode.insertBefore(row, recentRow);
    return row;
  }

  function frequentHref(type, id) {
    if (type === 'food') return '/items/' + encodeURIComponent(id);
    if (type === 'recipe') return '/recipes/' + encodeURIComponent(id);
    return '/actions/' + encodeURIComponent(id);
  }

  function renderFrequentList(rootId, rows, type) {
    var root = document.getElementById(rootId);
    if (!root) return;
    if (!Array.isArray(rows) || !rows.length) {
      root.innerHTML = '<div class="list-group-item text-secondary">No scans yet.</div>';
      return;
    }
    var badge = type === 'food' ? 'blue' : type === 'recipe' ? 'purple' : 'yellow';
    var icon = type === 'recipe' ? '<i class="ti ti-receipt me-1"></i>' : type === 'action' ? '<i class="ti ti-bolt me-1"></i>' : '';
    root.innerHTML = rows.map(function (entry) {
      return '<a href="' + frequentHref(type, entry.id) + '" class="list-group-item list-group-item-action d-flex align-items-center">' +
        '<span class="me-auto">' + icon + esc(entry.name) + '</span>' +
        '<span class="badge bg-' + badge + '-lt">' + Number(entry.uses || 0) + ' scans</span></a>';
    }).join('');
  }

  function renderFrequent(data) {
    ensureFrequentSection();
    renderFrequentList('b2m-frequent-foods', data.foods || [], 'food');
    renderFrequentList('b2m-frequent-recipes', data.recipes || [], 'recipe');
    renderFrequentList('b2m-frequent-actions', data.actions || [], 'action');
  }

  function refreshFrequent() {
    if (window.location.pathname !== '/') return;
    fetch('/api/dashboard/frequent', {headers: {Accept: 'application/json'}, cache: 'no-store'})
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) { if (data) renderFrequent(data); })
      .catch(function () {});
  }

  function init() {
    installScannerErrorUi();
    if (window.location.pathname === '/') refreshFrequent();

    window.addEventListener('b2m:scan', function () {
      if (onScanningSettings()) {
        clearTimeout(errorRefreshTimer);
        errorRefreshTimer = window.setTimeout(refreshErrorScanCount, 250);
      }
      if (window.location.pathname === '/') {
        clearTimeout(frequentRefreshTimer);
        frequentRefreshTimer = window.setTimeout(refreshFrequent, 250);
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true});
  else init();
})();
