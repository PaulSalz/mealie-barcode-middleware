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
  var frequentAddModal = null;
  var frequentAddTarget = null;
  var frequentAddBackdrop = null;

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

    var section = document.createElement('details');
    section.className = 'b2m-dashboard-frequent b2m-mobile-collapsible mb-3';
    section.open = true;
    section.innerHTML =
      '<summary class="card-header b2m-mobile-collapse-summary d-md-none"><span class="card-title">Frequently used</span><span class="b2m-mobile-collapse-icon" aria-hidden="true"><i class="ti ti-chevron-down"></i></span></summary>' +
      '<div class="row row-deck row-cards b2m-dashboard-frequent-cards" id="b2m-frequent-dashboard">' +
      '<div class="col-lg-4"><div class="card h-100"><div class="card-header"><div><h3 class="card-title">Frequently used Foods</h3><p class="card-subtitle">Based on scan target snapshots.</p></div></div><div class="list-group list-group-flush" id="b2m-frequent-foods"></div></div></div>' +
      '<div class="col-lg-4"><div class="card h-100"><div class="card-header"><div><h3 class="card-title">Frequently used Recipes</h3><p class="card-subtitle">Historical recipe targets.</p></div></div><div class="list-group list-group-flush" id="b2m-frequent-recipes"></div></div></div>' +
      '<div class="col-lg-4"><div class="card h-100"><div class="card-header"><div><h3 class="card-title">Frequently used Actions</h3><p class="card-subtitle">Webhook / automation codes.</p></div></div><div class="list-group list-group-flush" id="b2m-frequent-actions"></div></div></div></div>';
    recentRow.parentNode.insertBefore(section, recentRow);
    return section.querySelector('#b2m-frequent-dashboard');
  }

  function frequentHref(type, id) {
    if (type === 'food') return '/items/' + encodeURIComponent(id);
    if (type === 'recipe') return '/recipes/' + encodeURIComponent(id);
    return '/actions/' + encodeURIComponent(id);
  }

  function frequentLimit() {
    var config = document.getElementById('dashboard-poll-config');
    var value = Number(config && config.dataset.frequentLimit || 6);
    return Number.isFinite(value) ? Math.max(1, Math.min(20, Math.floor(value))) : 6;
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
    root.innerHTML = rows.slice(0, frequentLimit()).map(function (entry) {
      var link = '<a href="' + frequentHref(type, entry.id) + '" class="me-auto min-w-0 text-reset text-decoration-none">' + icon + esc(entry.name) + '</a>';
      var add = '';
      if (type === 'food' || type === 'recipe') {
        add = '<button type="button" class="btn btn-outline-primary b2m-frequent-add" data-target-type="' + type +
          '" data-target-id="' + esc(entry.id) + '" data-target-name="' + esc(entry.name) +
          '" title="Add to shopping list" aria-label="Add ' + esc(entry.name) + ' to a shopping list"><i class="ti ti-shopping-cart-plus"></i></button>';
      } else if (type === 'action') {
        add = '<button type="button" class="btn btn-outline-warning b2m-frequent-trigger" data-action-id="' + esc(entry.id) +
          '" data-action-name="' + esc(entry.name) + '" title="Trigger action" aria-label="Trigger ' + esc(entry.name) +
          '"><i class="ti ti-player-play"></i></button>';
      }
      return '<div class="list-group-item d-flex align-items-center gap-2">' + link +
        '<span class="badge bg-' + badge + '-lt">' + Number(entry.uses || 0) + ' scans</span>' + add + '</div>';
    }).join('');
  }

  function showFrequentAddModal(modal) {
    if (window.bootstrap && window.bootstrap.Modal) {
      frequentAddModal = window.bootstrap.Modal.getOrCreateInstance(modal);
      frequentAddModal.show();
      return;
    }
    modal.style.display = 'block';
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    if (!frequentAddBackdrop) {
      frequentAddBackdrop = document.createElement('div');
      frequentAddBackdrop.className = 'modal-backdrop fade show';
      frequentAddBackdrop.addEventListener('click', function () { hideFrequentAddModal(modal); });
      document.body.appendChild(frequentAddBackdrop);
    }
  }

  function hideFrequentAddModal(modal) {
    if (window.bootstrap && window.bootstrap.Modal && frequentAddModal) {
      frequentAddModal.hide();
      return;
    }
    modal.classList.remove('show');
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
    if (frequentAddBackdrop) {
      frequentAddBackdrop.remove();
      frequentAddBackdrop = null;
    }
  }

  function ensureFrequentAddModal() {
    var modal = document.getElementById('b2m-frequent-add-modal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.className = 'modal modal-blur fade';
    modal.id = 'b2m-frequent-add-modal';
    modal.tabIndex = -1;
    modal.setAttribute('aria-hidden', 'true');
    modal.setAttribute('data-bs-backdrop', 'true');
    modal.setAttribute('data-bs-keyboard', 'true');
    modal.innerHTML =
      '<div class="modal-dialog modal-dialog-centered" role="document"><div class="modal-content">' +
      '<div class="modal-header"><h3 class="modal-title">Add to shopping list</h3><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>' +
      '<form id="b2m-frequent-add-form"><div class="modal-body">' +
      '<div class="fs-3 fw-bold mb-3 text-break" id="b2m-frequent-add-name"></div>' +
      '<div class="mb-3"><label class="form-label" for="b2m-frequent-add-list">Shopping list</label><select class="form-select" id="b2m-frequent-add-list" required></select></div>' +
      '<div><label class="form-label" for="b2m-frequent-add-quantity">Quantity</label><input class="form-control" id="b2m-frequent-add-quantity" type="number" min="0.01" max="1000" step="0.01" value="1" required></div>' +
      '<div class="form-hint mt-2">For recipes, quantity sets the recipe scale.</div>' +
      '<div class="text-secondary small mt-2" id="b2m-frequent-add-status" role="status" aria-live="polite"></div>' +
      '</div><div class="modal-footer"><button type="button" class="btn me-auto" data-bs-dismiss="modal">Cancel</button>' +
      '<button type="submit" class="btn btn-primary" id="b2m-frequent-add-submit">Add to list</button></div></form></div></div>';
    document.body.appendChild(modal);
    modal.querySelectorAll('[data-bs-dismiss="modal"]').forEach(function (button) {
      button.addEventListener('click', function () {
        hideFrequentAddModal(modal);
      });
    });
    modal.addEventListener('click', function (event) {
      if (event.target === modal) hideFrequentAddModal(modal);
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && modal.classList.contains('show')) {
        if (!(window.bootstrap && window.bootstrap.Modal)) hideFrequentAddModal(modal);
      }
    });
    modal.querySelector('#b2m-frequent-add-form').addEventListener('submit', submitFrequentAdd);
    if (window.bootstrap && window.bootstrap.Modal) frequentAddModal = window.bootstrap.Modal.getOrCreateInstance(modal);
    return modal;
  }

  function openFrequentAdd(event) {
    var button = event.target && event.target.closest && event.target.closest('.b2m-frequent-add');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    frequentAddTarget = {
      type: button.dataset.targetType,
      id: button.dataset.targetId,
      name: button.dataset.targetName || ''
    };
    var modal = ensureFrequentAddModal();
    modal.querySelector('#b2m-frequent-add-name').textContent = frequentAddTarget.name;
    var list = modal.querySelector('#b2m-frequent-add-list');
    var status = modal.querySelector('#b2m-frequent-add-status');
    var submit = modal.querySelector('#b2m-frequent-add-submit');
    var quantity = modal.querySelector('#b2m-frequent-add-quantity');
    quantity.value = '1';
    submit.disabled = true;
    status.textContent = 'Loading shopping lists…';
    list.innerHTML = '<option value="">Loading…</option>';
    showFrequentAddModal(modal);
    fetch('/api/dashboard', {headers: {Accept: 'application/json'}, cache: 'no-store'})
      .then(function (response) {
        if (!response.ok) throw new Error('Could not load shopping lists');
        return response.json();
      })
      .then(function (data) {
        var lists = Array.isArray(data.shopping_lists) ? data.shopping_lists : [];
        list.innerHTML = lists.map(function (entry) {
          return '<option value="' + esc(entry.id) + '"' + (entry.default ? ' selected' : '') + '>' + esc(entry.name) + '</option>';
        }).join('');
        submit.disabled = lists.length === 0;
        status.textContent = lists.length ? '' : 'No shopping lists are available.';
      })
      .catch(function () {
        list.innerHTML = '';
        submit.disabled = true;
        status.textContent = 'Shopping lists could not be loaded.';
      });
  }

  function submitFrequentAdd(event) {
    event.preventDefault();
    if (!frequentAddTarget) return;
    var modal = ensureFrequentAddModal();
    var submit = modal.querySelector('#b2m-frequent-add-submit');
    var status = modal.querySelector('#b2m-frequent-add-status');
    var quantity = Number(modal.querySelector('#b2m-frequent-add-quantity').value);
    var listId = modal.querySelector('#b2m-frequent-add-list').value;
    if (!Number.isFinite(quantity) || quantity < 0.01 || quantity > 1000 || !listId) {
      status.textContent = 'Choose a list and enter a quantity between 0.01 and 1000.';
      return;
    }
    submit.disabled = true;
    status.textContent = 'Adding…';
    fetch('/api/dashboard/frequent/add', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', Accept: 'application/json'},
      body: JSON.stringify({
        target_type: frequentAddTarget.type,
        target_id: frequentAddTarget.id,
        list_id: listId,
        quantity: quantity
      })
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.error || 'Could not add to list');
        status.textContent = 'Added to ' + (data.list_name || 'shopping list') + '.';
        window.dispatchEvent(new CustomEvent('b2m:shopping-list-updated'));
        window.setTimeout(function () {
          hideFrequentAddModal(modal);
        }, 700);
      });
    }).catch(function (error) {
      status.textContent = error.message || 'Could not add to list.';
      submit.disabled = false;
    });
  }

  function triggerFrequentAction(event) {
    var button = event.target && event.target.closest && event.target.closest('.b2m-frequent-trigger');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    if (button.disabled) return;
    var actionName = button.dataset.actionName || 'Action';
    button.disabled = true;
    button.innerHTML = '<span class="spinner-border spinner-border-sm" aria-hidden="true"></span>';
    button.setAttribute('aria-label', 'Triggering ' + actionName);
    fetch('/api/dashboard/frequent/actions/' + encodeURIComponent(button.dataset.actionId) + '/trigger', {
      method: 'POST',
      headers: {Accept: 'application/json'}
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.error || data.detail || 'Could not trigger action');
        button.innerHTML = '<i class="ti ti-check" aria-hidden="true"></i>';
        button.title = data.status === 'queued' ? 'Action queued' : 'Action triggered';
        button.setAttribute('aria-label', button.title + ': ' + actionName);
        window.setTimeout(refreshFrequent, 1200);
      });
    }).catch(function (error) {
      button.innerHTML = '<i class="ti ti-alert-circle" aria-hidden="true"></i>';
      button.title = error.message || 'Could not trigger action';
      button.setAttribute('aria-label', button.title);
    }).finally(function () {
      window.setTimeout(function () {
        button.disabled = false;
        button.innerHTML = '<i class="ti ti-player-play" aria-hidden="true"></i>';
        button.title = 'Trigger action';
        button.setAttribute('aria-label', 'Trigger ' + actionName);
      }, 1400);
    });
  }

  function installFrequentAddButtons() {
    document.addEventListener('click', openFrequentAdd);
    document.addEventListener('click', triggerFrequentAction);
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
    installFrequentAddButtons();
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
