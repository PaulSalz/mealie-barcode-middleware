(function () {
  'use strict';
  if (window.location.pathname !== '/') return;

  var refreshTimer = null;
  var refreshing = false;
  var pollTimer = null;
  var lastSuccessfulRefresh = null;
  var config = document.getElementById('dashboard-poll-config');
  var pollSeconds = Math.max(1, Number(config && config.dataset.dashboardSeconds || 5));
  var refreshState = null;

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  function ensureRefreshState() {
    if (refreshState) return refreshState;
    var title = document.querySelector('.page-header .page-title');
    if (!title || !title.parentElement) return null;
    refreshState = document.createElement('div');
    refreshState.id = 'dashboard-refresh-state';
    refreshState.className = 'text-secondary small mt-1';
    refreshState.setAttribute('role', 'status');
    refreshState.textContent = 'Live data · updating…';
    title.insertAdjacentElement('afterend', refreshState);
    return refreshState;
  }

  function setRefreshState(ok) {
    var node = ensureRefreshState();
    if (!node) return;
    if (ok) {
      lastSuccessfulRefresh = new Date();
      node.className = 'text-secondary small mt-1';
      node.innerHTML = '<i class="ti ti-circle-check me-1 text-green"></i>Live data · updated just now';
      return;
    }
    var suffix = lastSuccessfulRefresh
      ? ' Last successful update: ' + lastSuccessfulRefresh.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) + '.'
      : '';
    node.className = 'text-warning small mt-1';
    node.innerHTML = '<i class="ti ti-wifi-off me-1"></i>Connection interrupted · showing last known data.' + esc(suffix) + ' <button type="button" class="btn btn-link btn-sm p-0 align-baseline" id="dashboard-retry-now">Retry now</button>';
    var retry = document.getElementById('dashboard-retry-now');
    if (retry) retry.addEventListener('click', function () { refresh(); });
  }

  function resultPresentation(result) {
    var map = {
      added: ['green', 'Added'],
      added_as_note: ['green', 'Added as note'],
      queued: ['yellow', 'Waiting · will retry'],
      needs_mapping: ['yellow', 'Needs linking'],
      unknown: ['red', 'Unknown barcode'],
      unknown_action: ['red', 'Unknown action'],
      retry_failed: ['red', 'Retry failed'],
      error: ['red', 'Could not add'],
      partial: ['orange', 'Partly completed'],
      auto_mapped: ['azure', 'Linked automatically'],
      resolved: ['green', 'Linked'],
      action_queued: ['purple', 'Action waiting'],
      action_triggered: ['green', 'Action completed'],
      action_ignored: ['secondary', 'Skipped · cooldown'],
      action_paused: ['azure', 'Skipped · scan & link mode'],
      action_disabled: ['red', 'Action disabled']
    };
    return map[result] || ['secondary', String(result || 'Scan').replace(/_/g, ' ')];
  }

  function targetHtml(item) {
    var targets = Array.isArray(item.targets) ? item.targets.filter(function (target) {
      return target && target.id && target.type;
    }) : [];
    if (!targets.length && item.target_type && item.target_id) {
      targets = [{type: item.target_type, id: item.target_id, name: item.target_name}];
    }
    var html = targets.map(function (target) {
      var id = String(target.id);
      var name = target.name || item.target_name || id;
      var type = target.type;
      var link = '';
      var button = '';
      if (type === 'food') {
        link = '<a href="/items/' + encodeURIComponent(id) + '">' + esc(name) + '</a>';
        button = '<button type="button" class="btn btn-outline-primary btn-icon b2m-frequent-add" data-target-type="food" data-target-id="' +
          esc(id) + '" data-target-name="' + esc(name) + '" title="Add to shopping list" aria-label="Add ' + esc(name) +
          ' to a shopping list"><i class="ti ti-shopping-cart-plus"></i></button>';
      } else if (type === 'recipe') {
        link = '<span class="badge bg-purple-lt me-1">Recipe</span><a href="/recipes/' + encodeURIComponent(id) + '">' + esc(name) + '</a>';
        button = '<button type="button" class="btn btn-outline-primary btn-icon b2m-frequent-add" data-target-type="recipe" data-target-id="' +
          esc(id) + '" data-target-name="' + esc(name) + '" title="Add to shopping list" aria-label="Add ' + esc(name) +
          ' to a shopping list"><i class="ti ti-shopping-cart-plus"></i></button>';
      } else if (type === 'action') {
        link = '<span class="badge bg-yellow-lt me-1">Action</span><a href="/actions/' + encodeURIComponent(id) + '">' + esc(name) + '</a>';
        button = '<button type="button" class="btn btn-outline-warning btn-icon b2m-frequent-trigger" data-action-id="' +
          esc(id) + '" data-action-name="' + esc(name) + '" title="Trigger action" aria-label="Trigger ' + esc(name) +
          '"><i class="ti ti-player-play"></i></button>';
      } else {
        link = esc(name);
      }
      return '<span class="d-inline-flex align-items-center gap-1 me-2 mb-1">' + link + button + '</span>';
    }).join('');
    if (!html && item.target_name) html = esc(item.target_name);
    if (!html) html = '<span class="text-secondary">—</span>';
    if (Number(item.target_count || targets.length) > 1) {
      html = '<span class="badge bg-azure-lt me-1">' + Number(item.target_count || targets.length) + ' targets</span>' + html;
    }
    return html;
  }

  function renderRecent(rows) {
    var tbody = document.getElementById('recent-scans-body');
    if (!tbody || !Array.isArray(rows)) return;
    tbody.innerHTML = rows.map(function (item) {
      var presentation = resultPresentation(item.result);
      return '<tr>' +
        '<td><a href="/barcodes/' + encodeURIComponent(item.barcode || '') + '"><code>' + esc(item.barcode || '') + '</code></a></td>' +
        '<td>' + esc(item.product_name || '—') + '</td>' +
        '<td>' + targetHtml(item) + '</td>' +
        '<td>' + esc(item.source || '—') + '</td>' +
        '<td><span class="badge bg-' + presentation[0] + '-lt">' + esc(presentation[1]) + '</span></td>' +
        '<td title="' + esc(item.created_at_absolute || '') + '">' + esc(item.created_at || '—') + '</td>' +
        '</tr>';
    }).join('');
  }

  function updateShoppingCounts(rows) {
    if (!Array.isArray(rows)) return;
    rows.forEach(function (row) {
      var card = document.querySelector('[data-shopping-list-id="' + CSS.escape(String(row.id || '')) + '"]');
      var count = card && card.querySelector('.shopping-list-count');
      if (count) count.textContent = Number(row.count || 0);
    });
  }

  function updateScannerStats(data) {
    var online = document.getElementById('stat-scanner-online');
    var total = document.getElementById('stat-scanner-total');
    if (online && data.scanner_online != null) online.textContent = Number(data.scanner_online || 0);
    if (total && data.scanner_total != null) total.textContent = Number(data.scanner_total || 0);
  }

  function refresh() {
    if (refreshing || document.hidden) return;
    refreshing = true;
    fetch('/api/dashboard?_=' + Date.now(), {
      headers: {Accept: 'application/json', 'Cache-Control': 'no-cache'},
      cache: 'no-store'
    })
      .then(function (response) {
        if (!response.ok) throw new Error('Dashboard refresh failed');
        return response.json();
      })
      .then(function (data) {
        renderRecent(data.recent_items || []);
        updateShoppingCounts(data.shopping_lists || []);
        updateScannerStats(data);
        setRefreshState(true);
      })
      .catch(function () { setRefreshState(false); })
      .finally(function () { refreshing = false; });
  }

  function scheduleRefresh(delay) {
    clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(refresh, delay == null ? 650 : delay);
  }

  window.addEventListener('b2m:scan', function () { scheduleRefresh(350); });
  window.addEventListener('focus', function () { scheduleRefresh(0); });
  document.addEventListener('visibilitychange', function () { if (!document.hidden) scheduleRefresh(0); });

  function startPolling() {
    clearInterval(pollTimer);
    pollTimer = window.setInterval(function () {
      if (!document.hidden) refresh();
    }, pollSeconds * 1000);
  }

  function installRecentTableGuard() {
    var tbody = document.getElementById('recent-scans-body');
    if (!tbody) return;
    new MutationObserver(function () {
      var first = tbody.querySelector('tr');
      if (first && first.children.length !== 6) scheduleRefresh(80);
    }).observe(tbody, {childList: true});
  }

  function installMobileCollapses() {
    var media = window.matchMedia('(max-width: 767.98px)');
    function keepDesktopSectionsOpen() {
      if (media.matches) return;
      document.querySelectorAll('details.b2m-mobile-collapsible').forEach(function (section) {
        section.open = true;
      });
    }
    document.querySelectorAll('details.b2m-mobile-collapsible').forEach(function (section) {
      section.addEventListener('toggle', function () {
        if (!media.matches && !section.open) section.open = true;
      });
    });
    keepDesktopSectionsOpen();
    if (media.addEventListener) media.addEventListener('change', keepDesktopSectionsOpen);
    else if (media.addListener) media.addListener(keepDesktopSectionsOpen);
  }

  function boot() {
    ensureRefreshState();
    installRecentTableGuard();
    installMobileCollapses();
    startPolling();
    scheduleRefresh(0);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();