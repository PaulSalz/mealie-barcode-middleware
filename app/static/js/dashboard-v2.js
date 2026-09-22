(function () {
  'use strict';
  if (window.location.pathname !== '/') return;

  var refreshTimer = null;
  var refreshing = false;
  var pollTimer = null;

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  function targetHtml(item) {
    var name = item.target_name || '';
    var id = item.target_id || '';
    var type = item.target_type || '';
    var html = '<span class="text-secondary">—</span>';
    if (name && id && type === 'food') {
      html = '<a href="/items/' + encodeURIComponent(id) + '">' + esc(name) + '</a>';
    } else if (name && id && type === 'recipe') {
      html = '<span class="badge bg-purple-lt me-1">Recipe</span><a href="/recipes/' + encodeURIComponent(id) + '">' + esc(name) + '</a>';
    } else if (name && id && type === 'action') {
      html = '<span class="badge bg-yellow-lt me-1">Action</span><a href="/actions/' + encodeURIComponent(id) + '">' + esc(name) + '</a>';
    } else if (name) {
      html = esc(name);
    }
    if (Number(item.target_count || 0) > 1) {
      html = '<span class="badge bg-azure-lt me-1">' + Number(item.target_count) + ' targets</span>' + html;
    }
    return html;
  }

  function renderRecent(rows) {
    var tbody = document.getElementById('recent-scans-body');
    if (!tbody || !Array.isArray(rows)) return;
    tbody.innerHTML = rows.map(function (item) {
      return '<tr>' +
        '<td><a href="/barcodes/' + encodeURIComponent(item.barcode || '') + '"><code>' + esc(item.barcode || '') + '</code></a></td>' +
        '<td>' + esc(item.product_name || '—') + '</td>' +
        '<td>' + targetHtml(item) + '</td>' +
        '<td>' + esc(item.source || '—') + '</td>' +
        '<td><span class="badge bg-muted-lt">' + esc(item.result || '—') + '</span></td>' +
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

  function refresh() {
    if (refreshing || document.hidden) return;
    refreshing = true;
    fetch('/api/dashboard?_=' + Date.now(), {
      headers: {Accept: 'application/json', 'Cache-Control': 'no-cache'},
      cache: 'no-store'
    })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        if (!data) return;
        renderRecent(data.recent_items || []);
        updateShoppingCounts(data.shopping_lists || []);
      })
      .catch(function () {})
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
    }, 3000);
  }

  function installRecentTableGuard() {
    var tbody = document.getElementById('recent-scans-body');
    if (!tbody) return;
    new MutationObserver(function () {
      var first = tbody.querySelector('tr');
      if (first && first.children.length !== 6) scheduleRefresh(80);
    }).observe(tbody, {childList: true});
  }

  function boot() {
    installRecentTableGuard();
    startPolling();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once: true});
  else boot();
})();
