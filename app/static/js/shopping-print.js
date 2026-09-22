(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var scanRefreshTimer = null;
  var pollTimer = null;
  var pollBusy = false;
  var lastFingerprint = '';

  var state = {
    settings: null,
    data: null,
    order: [],
    aliases: {},
    localComment: '',
    localEntries: [],
    itemOverrides: [],
    printer: {},
    canPrint: false,
  };

  var els = {
    list: $('shopping-print-list'),
    refresh: $('shopping-print-refresh'),
    print: $('shopping-print-button'),
    connect: $('shopping-print-connect'),
    printerStatus: $('shopping-print-printer-status'),
    status: $('shopping-print-status'),
    summary: $('shopping-print-item-summary'),
    order: $('shopping-print-category-order'),
    saveOrder: $('shopping-print-save-order'),
    orderStatus: $('shopping-print-order-status'),
    saveSettings: $('shopping-print-save-settings'),
    settingsStatus: $('shopping-print-settings-status'),
    localComment: $('shopping-print-local-comment'),
    localName: $('shopping-print-local-name'),
    localQty: $('shopping-print-local-qty'),
    localCategory: $('shopping-print-local-category'),
    localCategoryOptions: $('shopping-print-category-options'),
    localAdd: $('shopping-print-local-add'),
    localEntries: $('shopping-print-local-entries'),
    saveLocal: $('shopping-print-save-local'),
    localStatus: $('shopping-print-local-status'),
    overrideItem: $('shopping-print-override-item'),
    overrideName: $('shopping-print-override-name'),
    overrideQty: $('shopping-print-override-qty'),
    overrideSave: $('shopping-print-override-save'),
    overrideStatus: $('shopping-print-override-status'),
    overrideList: $('shopping-print-overrides-list'),
    canvas: $('shopping-print-canvas'),
    shell: document.querySelector('.shopping-print-paper-shell'),
    empty: $('shopping-print-empty'),
    paperSize: $('shopping-print-paper-size'),
  };

  if (!els.list || !els.canvas) return;

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  async function fetchJson(url, options) {
    var opts = Object.assign({}, options || {});
    opts.headers = Object.assign({Accept: 'application/json', 'Cache-Control': 'no-cache'}, opts.headers || {});
    opts.cache = 'no-store';
    var response = await fetch(url, opts);
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.error || data.detail || ('HTTP ' + response.status));
    return data;
  }

  function setStatus(el, text, tone) {
    if (!el) return;
    el.textContent = text || '';
    el.className = 'form-hint' + (tone ? ' text-' + tone : '');
  }

  function markerStyle() {
    var checked = document.querySelector('input[name="sp-item-marker-style"]:checked');
    return checked ? checked.value : 'checkbox';
  }

  function inputSettings() {
    var marker = markerStyle();
    return {
      paper_width_mm: Number($('sp-width').value),
      margin_mm: Number($('sp-margin').value),
      body_font_mm: Number($('sp-font').value),
      line_gap_mm: Number($('sp-line-gap').value),
      category_gap_mm: Number($('sp-category-gap').value),
      bottom_margin_mm: Number($('sp-bottom-margin').value),
      density: Number($('sp-density').value),
      threshold: Number($('sp-threshold').value),
      dpi: Number($('sp-dpi').value),
      label_type: Number($('sp-label-type').value),
      show_checkboxes: marker === 'checkbox',
      item_marker_style: marker,
      show_items: $('sp-show-items').checked,
      show_quantities: $('sp-show-quantities').checked,
      show_item_dividers: $('sp-show-item-dividers').checked,
      show_category_dividers: $('sp-show-category-dividers').checked,
      category_divider_style: $('sp-category-divider-style').value || 'solid',
    };
  }

  function syncConditionalSettings() {
    var showItems = $('sp-show-items').checked;
    $('sp-category-divider-style').disabled = !$('sp-show-category-dividers').checked;
    document.querySelectorAll('input[name="sp-item-marker-style"]').forEach(function (input) { input.disabled = !showItems; });
    $('sp-show-quantities').disabled = !showItems;
    $('sp-show-item-dividers').disabled = !showItems;
  }

  function populateSettings(settings) {
    state.settings = Object.assign({}, settings || {});
    $('sp-width').value = state.settings.paper_width_mm == null ? 50 : state.settings.paper_width_mm;
    $('sp-margin').value = state.settings.margin_mm == null ? 2.2 : state.settings.margin_mm;
    $('sp-font').value = state.settings.body_font_mm == null ? 3 : state.settings.body_font_mm;
    $('sp-line-gap').value = state.settings.line_gap_mm == null ? .8 : state.settings.line_gap_mm;
    $('sp-category-gap').value = state.settings.category_gap_mm == null ? 1.6 : state.settings.category_gap_mm;
    $('sp-bottom-margin').value = state.settings.bottom_margin_mm == null ? 3 : state.settings.bottom_margin_mm;
    $('sp-density').value = state.settings.density == null ? 3 : state.settings.density;
    $('sp-threshold').value = state.settings.threshold == null ? 145 : state.settings.threshold;
    $('sp-dpi').value = state.settings.dpi == null ? 300 : state.settings.dpi;
    $('sp-label-type').value = state.settings.label_type == null ? 3 : state.settings.label_type;
    $('sp-show-items').checked = state.settings.show_items !== false;
    $('sp-show-quantities').checked = state.settings.show_quantities !== false;
    $('sp-show-item-dividers').checked = state.settings.show_item_dividers === true;
    $('sp-show-category-dividers').checked = state.settings.show_category_dividers !== false;
    $('sp-category-divider-style').value = state.settings.category_divider_style === 'dashed' ? 'dashed' : 'solid';
    var wantedMarker = state.settings.item_marker_style || (state.settings.show_checkboxes === false ? 'none' : 'checkbox');
    var markerInput = document.querySelector('input[name="sp-item-marker-style"][value="' + wantedMarker + '"]');
    if (!markerInput) markerInput = document.querySelector('input[name="sp-item-marker-style"][value="checkbox"]');
    if (markerInput) markerInput.checked = true;
    syncConditionalSettings();
  }

  function updatePrinterStatus(printer) {
    state.printer = printer || {};
    var configured = !!state.printer.configured;
    var connected = !!state.printer.connected;
    els.printerStatus.className = 'badge ' + (connected ? 'bg-green text-green-fg' : configured ? 'bg-yellow-lt text-yellow' : 'bg-red-lt text-red');
    els.printerStatus.textContent = connected ? 'Printer connected' : configured ? 'Printer disconnected' : 'Printer not configured';
    els.connect.disabled = !configured || !state.canPrint;
    els.connect.innerHTML = connected
      ? '<i class="ti ti-plug-off icon"></i> Disconnect printer'
      : '<i class="ti ti-plug-connected icon"></i> Connect printer';
    updateButtons();
  }

  function hasPrintableContent() {
    return !!(state.data && (((state.data.items || []).length) || state.localEntries.length || String(state.localComment || '').trim()));
  }

  function updateButtons() {
    els.print.disabled = !(state.canPrint && hasPrintableContent() && state.printer && state.printer.connected);
    els.saveOrder.disabled = !(state.canPrint && state.data && state.order.length);
    els.saveSettings.disabled = !state.canPrint;
    if (els.saveLocal) els.saveLocal.disabled = !(state.canPrint && state.data);
    if (els.localAdd) els.localAdd.disabled = !(state.canPrint && state.data);
    if (els.overrideSave) els.overrideSave.disabled = !(state.canPrint && state.data && els.overrideItem && els.overrideItem.value);
  }

  function populateLists(rows, defaultId) {
    rows = Array.isArray(rows) ? rows : [];
    if (!rows.length) {
      els.list.innerHTML = '<option value="">No shopping lists available</option>';
      els.list.disabled = true;
      return;
    }
    els.list.innerHTML = rows.map(function (row) {
      return '<option value="' + esc(row.id) + '">' + esc(row.name || 'Shopping list') + '</option>';
    }).join('');
    els.list.disabled = false;
    var remembered = localStorage.getItem('b2m-shopping-print-list') || '';
    var wanted = rows.some(function (row) { return String(row.id) === remembered; }) ? remembered : String(defaultId || rows[0].id);
    els.list.value = wanted;
  }

  function displayCategory(name) {
    var alias = String(state.aliases[name] || '').trim();
    return alias || name;
  }

  function activeCategoryMap() {
    var map = {};
    ((state.data && state.data.items) || []).forEach(function (item) {
      var name = String(item.category || 'Other').trim() || 'Other';
      map[name.toLowerCase()] = name;
    });
    state.localEntries.forEach(function (entry) {
      var name = String(entry.category || 'Extra').trim() || 'Extra';
      map[name.toLowerCase()] = name;
    });
    return map;
  }

  function normalizeOrder(prune) {
    var available = activeCategoryMap();
    var merged = [];
    var seen = {};
    state.order.forEach(function (name) {
      var key = String(name || '').toLowerCase();
      var actual = available[key];
      if ((!prune || actual) && key && !seen[key]) {
        merged.push(actual || name);
        seen[key] = true;
      }
    });
    Object.keys(available).sort(function (a, b) { return available[a].localeCompare(available[b]); }).forEach(function (key) {
      if (!seen[key]) {
        merged.push(available[key]);
        seen[key] = true;
      }
    });
    state.order = merged;
    if (prune) {
      Object.keys(state.aliases).forEach(function (source) {
        if (!available[String(source).toLowerCase()]) delete state.aliases[source];
      });
    }
  }

  function renderCategoryOptions() {
    if (!els.localCategoryOptions) return;
    els.localCategoryOptions.innerHTML = state.order.map(function (name) {
      return '<option value="' + esc(name) + '"></option>';
    }).join('');
  }

  function updateSummary() {
    if (!state.data) {
      els.summary.textContent = '—';
      return;
    }
    var mealieCount = Number(state.data.mealie_count == null ? (state.data.items || []).length : state.data.mealie_count) || 0;
    var localCount = state.localEntries.length;
    els.summary.textContent = mealieCount + ' Mealie item' + (mealieCount === 1 ? '' : 's') +
      (localCount ? ' · ' + localCount + ' print-only' : '') +
      ' · ' + state.order.length + ' categor' + (state.order.length === 1 ? 'y' : 'ies');
  }

  function renderOrder() {
    if (!state.data) {
      els.order.innerHTML = '<div class="list-group-item text-secondary">Choose a shopping list first.</div>';
      updateButtons();
      return;
    }
    normalizeOrder(true);
    if (!state.order.length) {
      els.order.innerHTML = '<div class="list-group-item text-secondary">This list has no categorized items.</div>';
      renderCategoryOptions();
      updateSummary();
      updateButtons();
      return;
    }
    els.order.innerHTML = state.order.map(function (name, index) {
      var alias = state.aliases[name] || '';
      return '<div class="list-group-item d-flex align-items-center shopping-print-category-row" data-index="' + index + '">' +
        '<span class="shopping-print-category-position text-secondary">' + (index + 1) + '</span>' +
        '<div class="shopping-print-category-main">' +
          '<div class="fw-medium shopping-print-category-original" title="' + esc(name) + '">' + esc(name) + '</div>' +
          '<input type="text" maxlength="120" class="form-control form-control-sm shopping-print-category-alias" data-alias-index="' + index + '" value="' + esc(alias) + '" placeholder="Print alias (optional)">' +
        '</div>' +
        '<div class="btn-list shopping-print-category-actions">' +
          '<button type="button" class="btn btn-sm btn-icon btn-outline-secondary" data-move="up" title="Move up"' + (index === 0 ? ' disabled' : '') + '><i class="ti ti-chevron-up"></i></button>' +
          '<button type="button" class="btn btn-sm btn-icon btn-outline-secondary" data-move="down" title="Move down"' + (index === state.order.length - 1 ? ' disabled' : '') + '><i class="ti ti-chevron-down"></i></button>' +
        '</div></div>';
    }).join('');
    renderCategoryOptions();
    updateSummary();
    updateButtons();
  }

  function renderLocalEntries() {
    if (!els.localEntries) return;
    if (!state.localEntries.length) {
      els.localEntries.innerHTML = '<div class="list-group-item text-secondary">No print-only entries.</div>';
    } else {
      els.localEntries.innerHTML = state.localEntries.map(function (entry, index) {
        var meta = [entry.quantity_text, entry.category || 'Extra'].filter(Boolean).join(' · ');
        return '<div class="list-group-item shopping-print-local-entry" data-local-index="' + index + '">' +
          '<div class="shopping-print-local-entry-main"><div class="fw-medium shopping-print-local-entry-title">' + esc(entry.name) + '</div>' +
          '<div class="text-secondary shopping-print-local-entry-meta">' + esc(meta) + '</div></div>' +
          '<button type="button" class="btn btn-sm btn-icon btn-outline-danger shopping-print-square-action" data-local-remove title="Remove"><i class="ti ti-trash"></i></button></div>';
      }).join('');
    }
    if (els.localComment && els.localComment.value !== state.localComment) els.localComment.value = state.localComment;
    renderCategoryOptions();
    updateSummary();
    updateButtons();
  }

  function currentItemForOverride() {
    if (!els.overrideItem || !state.data) return null;
    var key = els.overrideItem.value;
    return (state.data.items || []).find(function (item) { return String(item.override_key || '') === key; }) || null;
  }

  function overrideForKey(key) {
    return state.itemOverrides.find(function (row) { return String(row.key) === String(key); }) || null;
  }

  function syncOverrideEditor() {
    if (!els.overrideItem) return;
    var item = currentItemForOverride();
    var saved = item ? overrideForKey(item.override_key) : null;
    els.overrideName.value = saved ? (saved.name_alias || '') : '';
    els.overrideQty.value = saved ? (saved.quantity_alias || '') : '';
    updateButtons();
  }

  function renderOverrideEditor() {
    if (!els.overrideItem || !els.overrideList) return;
    var previous = els.overrideItem.value;
    var items = (state.data && state.data.items) || [];
    els.overrideItem.innerHTML = '<option value="">Choose an item…</option>' + items.map(function (item) {
      var originalName = item.original_name || item.name || 'Item';
      var originalQty = item.original_quantity_text || item.quantity_text || '';
      var label = originalName + (originalQty ? ' · ' + originalQty : '');
      return '<option value="' + esc(item.override_key || '') + '">' + esc(label) + '</option>';
    }).join('');
    els.overrideItem.disabled = !state.canPrint || !items.length;
    if (items.some(function (item) { return String(item.override_key || '') === previous; })) els.overrideItem.value = previous;

    if (!state.itemOverrides.length) {
      els.overrideList.innerHTML = '<div class="list-group-item text-secondary">No item overrides.</div>';
    } else {
      els.overrideList.innerHTML = state.itemOverrides.map(function (row) {
        var parts = [];
        if (row.name_alias) parts.push('name → ' + row.name_alias);
        if (row.quantity_alias) parts.push('quantity → ' + row.quantity_alias);
        return '<div class="list-group-item d-flex align-items-center gap-2" data-override-key="' + esc(row.key) + '">' +
          '<div class="min-w-0 flex-fill"><div class="fw-medium text-truncate">' + esc(row.source_name || row.key) + '</div>' +
          '<div class="text-secondary small text-truncate">' + esc(parts.join(' · ')) + (row.active ? '' : ' · currently not open') + '</div></div>' +
          '<button type="button" class="btn btn-sm btn-icon btn-outline-danger shopping-print-square-action" data-override-remove title="Remove override"><i class="ti ti-trash"></i></button>' +
          '</div>';
      }).join('');
    }
    syncOverrideEditor();
  }

  function combinedItems() {
    var items = ((state.data && state.data.items) || []).map(function (item) { return Object.assign({}, item); });
    state.localEntries.forEach(function (entry) {
      items.push({
        id: 'local:' + entry.id,
        name: entry.name,
        quantity_text: entry.quantity_text || '',
        category: entry.category || 'Extra',
        local_only: true,
      });
    });
    return items;
  }

  function orderedItems() {
    if (!state.data) return [];
    var pos = {};
    state.order.forEach(function (name, index) { pos[String(name).toLowerCase()] = index; });
    return combinedItems().sort(function (a, b) {
      var ai = pos[String(a.category || 'Other').toLowerCase()];
      var bi = pos[String(b.category || 'Other').toLowerCase()];
      if (ai == null) ai = 9999;
      if (bi == null) bi = 9999;
      if (ai !== bi) return ai - bi;
      return String(a.name || '').localeCompare(String(b.name || ''), undefined, {sensitivity: 'base'});
    });
  }

  function mmToPx(mm, dpi) {
    return Math.max(1, Math.round(Number(mm || 0) * Number(dpi || 300) / 25.4));
  }

  function wrapText(ctx, text, maxWidth) {
    text = String(text || '').trim();
    if (!text) return [];
    var words = text.split(/\s+/);
    var lines = [];
    var current = '';
    words.forEach(function (word) {
      var candidate = current ? current + ' ' + word : word;
      if (current && ctx.measureText(candidate).width > maxWidth) {
        lines.push(current);
        current = word;
      } else {
        current = candidate;
      }
    });
    if (current) lines.push(current);
    return lines;
  }

  function receiptDate() {
    try {
      return new Intl.DateTimeFormat(undefined, {year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());
    } catch (e) {
      return new Date().toLocaleDateString();
    }
  }

  function drawHorizontalRule(ctx, left, right, y, dpi, style) {
    if (style === 'dashed') ctx.setLineDash([Math.max(3, Math.round(dpi / 42)), Math.max(2, Math.round(dpi / 70))]);
    else ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.lineWidth = Math.max(1, Math.round(dpi / 180));
    ctx.strokeStyle = '#000';
    ctx.stroke();
    ctx.setLineDash([]);
  }

  function renderReceipt() {
    if (!state.data) {
      els.shell.classList.remove('is-visible');
      els.empty.classList.remove('d-none');
      els.paperSize.textContent = (state.settings && state.settings.paper_width_mm || 50) + ' mm × —';
      return;
    }

    var cfg = inputSettings();
    state.settings = Object.assign({}, state.settings || {}, cfg);
    var dpi = Math.max(100, cfg.dpi || 300);
    var widthPx = mmToPx(cfg.paper_width_mm, dpi);
    var margin = mmToPx(cfg.margin_mm, dpi);
    var body = mmToPx(cfg.body_font_mm, dpi);
    var titleSize = Math.round(body * 1.58);
    var dateSize = Math.max(8, Math.round(body * .82));
    var noteSize = Math.max(8, Math.round(body * .9));
    var categorySize = Math.round(body * 1.08);
    var lineGap = mmToPx(cfg.line_gap_mm, dpi);
    var categoryGap = mmToPx(cfg.category_gap_mm, dpi);
    var bottom = mmToPx(cfg.bottom_margin_mm, dpi);
    var contentWidth = Math.max(20, widthPx - margin * 2);
    var canvas = els.canvas;

    canvas.width = widthPx;
    canvas.height = 100;
    var ctx = canvas.getContext('2d');
    ctx.textBaseline = 'top';
    ctx.fillStyle = '#000';

    function font(size, weight) {
      ctx.font = (weight || 400) + ' ' + size + 'px Arial, Helvetica, sans-serif';
    }

    function layout(draw) {
      var y = margin;
      font(titleSize, 700);
      wrapText(ctx, state.data.name || 'Shopping list', contentWidth).forEach(function (line) {
        if (draw) ctx.fillText(line, margin + (contentWidth - ctx.measureText(line).width) / 2, y);
        y += Math.round(titleSize * 1.12);
      });

      font(dateSize, 400);
      var date = receiptDate();
      if (draw) ctx.fillText(date, margin + (contentWidth - ctx.measureText(date).width) / 2, y);
      y += Math.round(dateSize * 1.55);

      var comment = String(state.localComment || '').trim();
      if (comment) {
        font(noteSize, 400);
        comment.split(/\n+/).forEach(function (paragraph) {
          wrapText(ctx, paragraph, contentWidth).forEach(function (line) {
            if (draw) ctx.fillText(line, margin, y);
            y += Math.round(noteSize * 1.22);
          });
        });
        y += Math.round(lineGap * .55);
      }

      if (draw) drawHorizontalRule(ctx, margin, widthPx - margin, y, dpi, 'solid');
      y += Math.round(body * .65);

      var items = orderedItems();
      if (!items.length) {
        font(body, 400);
        var emptyText = 'No open items';
        if (draw) ctx.fillText(emptyText, margin + (contentWidth - ctx.measureText(emptyText).width) / 2, y);
        y += Math.round(body * 1.4);
        return y + bottom;
      }

      var grouped = {};
      items.forEach(function (item) {
        var category = item.category || 'Other';
        if (!grouped[category]) grouped[category] = [];
        grouped[category].push(item);
      });
      var categories = state.order.slice();
      Object.keys(grouped).sort(function (a, b) { return a.localeCompare(b); }).forEach(function (category) {
        if (!categories.some(function (name) { return name.toLowerCase() === category.toLowerCase(); })) categories.push(category);
      });

      var renderedCategoryCount = 0;
      categories.forEach(function (category) {
        var rows = grouped[category] || [];
        if (!rows.length) return;
        if (renderedCategoryCount > 0) y += categoryGap;
        renderedCategoryCount += 1;

        font(categorySize, 700);
        wrapText(ctx, String(displayCategory(category)).toUpperCase(), contentWidth).forEach(function (line) {
          if (draw) ctx.fillText(line, margin, y);
          y += Math.round(categorySize * 1.15);
        });
        if (cfg.show_category_dividers) {
          y += Math.max(1, Math.round(lineGap * .2));
          if (draw) drawHorizontalRule(ctx, margin, widthPx - margin, y, dpi, cfg.category_divider_style);
          y += Math.max(2, Math.round(lineGap * .65));
        } else {
          y += Math.round(lineGap * .4);
        }

        if (!cfg.show_items) return;
        rows.forEach(function (item, rowIndex) {
          font(body, 400);
          var marker = cfg.item_marker_style || 'checkbox';
          var markerWidth = marker === 'none' ? 0 : Math.max(8, Math.round(body * .72));
          var markerGap = marker === 'none' ? 0 : Math.round(body * .38);
          var qty = cfg.show_quantities ? String(item.quantity_text || '').trim() : '';
          var qtyWidth = qty ? Math.min(Math.round(contentWidth * .30), Math.ceil(ctx.measureText(qty).width)) : 0;
          var qtyGap = qty ? Math.round(body * .35) : 0;
          var textX = margin + markerWidth + markerGap;
          var nameWidth = Math.max(body * 3, contentWidth - markerWidth - markerGap - qtyWidth - qtyGap);
          var lines = wrapText(ctx, item.name || 'Item', nameWidth);
          var lineHeight = Math.round(body * 1.18);
          var rowHeight = Math.max(markerWidth || 0, lines.length * lineHeight || body);

          if (draw) {
            ctx.lineWidth = Math.max(1, Math.round(dpi / 200));
            ctx.strokeStyle = '#000';
            if (marker === 'checkbox') {
              ctx.strokeRect(margin, y + Math.round((body - markerWidth) / 3), markerWidth, markerWidth);
            } else if (marker === 'dash') {
              font(body, 700);
              ctx.fillText('-', margin + Math.round(markerWidth * .18), y);
              font(body, 400);
            }
            lines.forEach(function (line, lineIndex) { ctx.fillText(line, textX, y + lineIndex * lineHeight); });
            if (qty) ctx.fillText(qty, widthPx - margin - ctx.measureText(qty).width, y);
          }
          y += rowHeight + lineGap;
          if (cfg.show_item_dividers && rowIndex < rows.length - 1) {
            if (draw) drawHorizontalRule(ctx, margin + Math.round(body * .35), widthPx - margin, y - Math.max(1, Math.round(lineGap * .35)), dpi, 'solid');
            y += Math.max(1, Math.round(lineGap * .25));
          }
        });
      });

      return y + bottom;
    }

    var height = Math.max(mmToPx(20, dpi), layout(false));
    canvas.height = Math.ceil(height);
    ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#000';
    ctx.textBaseline = 'top';
    layout(true);

    var heightMm = canvas.height / dpi * 25.4;
    canvas.dataset.heightMm = heightMm.toFixed(2);
    els.paperSize.textContent = Number(cfg.paper_width_mm).toFixed(1).replace('.0', '') + ' mm × ' + heightMm.toFixed(1) + ' mm';
    els.shell.classList.add('is-visible');
    els.empty.classList.add('d-none');
  }

  function dataFingerprint(data) {
    return JSON.stringify(((data && data.items) || []).map(function (item) {
      return [item.id, item.original_name || item.name, item.original_quantity_text || item.quantity_text, item.category, item.override_key];
    }).sort(function (a, b) { return String(a[0]).localeCompare(String(b[0])); }));
  }

  function mergeLocalRoute(data, oldOrder, oldAliases, oldEntries) {
    state.order = oldOrder.slice();
    state.aliases = Object.assign({}, data.category_aliases || {}, oldAliases || {});
    state.localEntries = oldEntries;
    normalizeOrder(true);
  }

  async function loadList(listId, options) {
    options = options || {};
    listId = String(listId || '').trim();
    if (!listId) return;
    localStorage.setItem('b2m-shopping-print-list', listId);
    var sameList = !!(state.data && String(state.data.id) === listId);
    var oldOrder = sameList ? state.order.slice() : [];
    var oldAliases = sameList ? Object.assign({}, state.aliases) : {};
    var oldComment = sameList ? state.localComment : '';
    var oldEntries = sameList ? state.localEntries.map(function (entry) { return Object.assign({}, entry); }) : [];
    if (!options.silent) setStatus(els.status, 'Loading open items…', 'secondary');
    if (!options.background) els.list.disabled = true;

    try {
      var data = await fetchJson('/api/shopping-print/lists/' + encodeURIComponent(listId) + '?_=' + Date.now());
      var freshFingerprint = dataFingerprint(data);
      var changed = !sameList || freshFingerprint !== lastFingerprint;
      state.data = data;
      state.itemOverrides = Array.isArray(data.item_overrides) ? data.item_overrides.slice() : [];

      if (options.preserveLocal && sameList) {
        state.localComment = oldComment;
        mergeLocalRoute(data, oldOrder, oldAliases, oldEntries);
      } else {
        state.order = (data.category_order || []).slice();
        state.aliases = Object.assign({}, data.category_aliases || {});
        state.localComment = data.local_comment || '';
        state.localEntries = (data.local_entries || []).map(function (entry) { return Object.assign({}, entry); });
        normalizeOrder(true);
      }

      lastFingerprint = freshFingerprint;
      renderOrder();
      renderLocalEntries();
      renderOverrideEditor();
      renderReceipt();

      if (!options.silent) {
        setStatus(els.status, data.mealie_count ? 'Preview uses the current open items from Mealie.' : 'This shopping list currently has no open Mealie items.', data.mealie_count ? 'secondary' : 'yellow');
        setStatus(els.orderStatus, '', '');
        setStatus(els.localStatus, '', '');
      } else if (changed) {
        setStatus(els.status, options.reason === 'scan' ? 'Shopping list updated after scan.' : 'Shopping list synced from Mealie.', 'success');
      }
      return changed;
    } catch (error) {
      if (!options.silent) {
        state.data = null;
        state.order = [];
        state.aliases = {};
        state.localComment = '';
        state.localEntries = [];
        state.itemOverrides = [];
        els.summary.textContent = 'Could not load list';
        renderOrder();
        renderLocalEntries();
        renderOverrideEditor();
        renderReceipt();
        setStatus(els.status, error.message, 'danger');
      } else if (!options.background) {
        setStatus(els.status, 'Mealie sync failed: ' + error.message, 'danger');
      }
      return false;
    } finally {
      if (!options.background) els.list.disabled = false;
      updateButtons();
    }
  }

  async function refreshPrinter() {
    try {
      var printer = await fetchJson('/labels/b21/status');
      updatePrinterStatus(printer);
    } catch (error) {
      updatePrinterStatus({configured: true, connected: false, error: error.message});
    }
  }

  async function bootstrap() {
    setStatus(els.status, 'Loading shopping lists…', 'secondary');
    try {
      var results = await Promise.all([
        fetchJson('/api/shopping-print/bootstrap'),
        fetchJson('/api/access/me').catch(function () { return null; }),
      ]);
      var data = results[0];
      var access = results[1];
      state.canPrint = !!(access && (access.is_admin || (access.permissions && access.permissions.printer)));
      populateSettings(data.settings || {});
      populateLists(data.lists || [], data.default_list_id);
      updatePrinterStatus(data.printer || {});
      if (!state.canPrint) {
        setStatus(els.settingsStatus, 'Preview only: your account does not have printer permission.', 'secondary');
        setStatus(els.localStatus, 'Preview only: printer permission is required to save local content.', 'secondary');
        setStatus(els.overrideStatus, 'Preview only: printer permission is required to save overrides.', 'secondary');
      }
      if (els.list.value) await loadList(els.list.value);
      else setStatus(els.status, 'No shopping lists are available.', 'yellow');
      startPolling();
    } catch (error) {
      setStatus(els.status, error.message, 'danger');
      els.list.innerHTML = '<option value="">Could not load shopping lists</option>';
      els.list.disabled = true;
    }
  }

  function startPolling() {
    clearInterval(pollTimer);
    pollTimer = window.setInterval(async function () {
      if (pollBusy || document.hidden || !els.list.value) return;
      pollBusy = true;
      try {
        await loadList(els.list.value, {preserveLocal: true, silent: true, background: true, reason: 'poll'});
      } finally {
        pollBusy = false;
      }
    }, 2500);
  }

  function foregroundSync() {
    if (document.hidden || !els.list.value || pollBusy) return;
    pollBusy = true;
    loadList(els.list.value, {preserveLocal: true, silent: true, background: true, reason: 'focus'})
      .finally(function () { pollBusy = false; });
  }

  els.list.addEventListener('change', function () {
    lastFingerprint = '';
    loadList(els.list.value);
  });

  els.refresh.addEventListener('click', function () {
    if (els.list.value) loadList(els.list.value, {preserveLocal: true});
    refreshPrinter();
  });

  els.order.addEventListener('click', function (event) {
    var button = event.target.closest('button[data-move]');
    var row = event.target.closest('[data-index]');
    if (!button || !row) return;
    var index = Number(row.dataset.index);
    var next = button.dataset.move === 'up' ? index - 1 : index + 1;
    if (next < 0 || next >= state.order.length) return;
    var moved = state.order.splice(index, 1)[0];
    state.order.splice(next, 0, moved);
    renderOrder();
    renderReceipt();
    setStatus(els.orderStatus, 'Route changed — save to make it global.', 'yellow');
  });

  els.order.addEventListener('input', function (event) {
    var input = event.target.closest('input[data-alias-index]');
    if (!input) return;
    var name = state.order[Number(input.dataset.aliasIndex)];
    if (!name) return;
    if (input.value.trim()) state.aliases[name] = input.value;
    else delete state.aliases[name];
    renderReceipt();
    setStatus(els.orderStatus, 'Alias changed — save to make it global.', 'yellow');
  });

  els.saveOrder.addEventListener('click', async function () {
    if (!state.data) return;
    els.saveOrder.disabled = true;
    setStatus(els.orderStatus, 'Saving route and aliases…', 'secondary');
    try {
      var data = await fetchJson('/api/shopping-print/category-order', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({list_id: state.data.id, category_order: state.order, category_aliases: state.aliases}),
      });
      state.order = (data.category_order || state.order).slice();
      state.aliases = Object.assign({}, data.category_aliases || {});
      renderOrder();
      renderReceipt();
      setStatus(els.orderStatus, 'Route and aliases saved globally for this list.', 'success');
    } catch (error) {
      setStatus(els.orderStatus, error.message, 'danger');
    } finally {
      updateButtons();
    }
  });

  if (els.localComment) {
    els.localComment.addEventListener('input', function () {
      state.localComment = els.localComment.value;
      renderReceipt();
      setStatus(els.localStatus, 'Comment changed — save to keep it for this list.', 'yellow');
      updateButtons();
    });
  }

  if (els.localAdd) {
    els.localAdd.addEventListener('click', function () {
      if (!state.data || !state.canPrint) return;
      var name = String(els.localName.value || '').trim();
      if (!name) {
        setStatus(els.localStatus, 'Enter a name for the print-only entry.', 'danger');
        els.localName.focus();
        return;
      }
      state.localEntries.push({
        id: 'local-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8),
        name: name,
        quantity_text: String(els.localQty.value || '').trim(),
        category: String(els.localCategory.value || '').trim() || 'Extra',
      });
      els.localName.value = '';
      els.localQty.value = '';
      els.localCategory.value = '';
      normalizeOrder(true);
      renderOrder();
      renderLocalEntries();
      renderReceipt();
      setStatus(els.localStatus, 'Entry added — save to keep it for this list.', 'yellow');
      els.localName.focus();
    });
  }

  if (els.localName) {
    els.localName.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        els.localAdd.click();
      }
    });
  }

  if (els.localEntries) {
    els.localEntries.addEventListener('click', function (event) {
      var button = event.target.closest('[data-local-remove]');
      var row = event.target.closest('[data-local-index]');
      if (!button || !row) return;
      var index = Number(row.dataset.localIndex);
      if (index < 0 || index >= state.localEntries.length) return;
      state.localEntries.splice(index, 1);
      normalizeOrder(true);
      renderOrder();
      renderLocalEntries();
      renderReceipt();
      setStatus(els.localStatus, 'Entry removed; unused category removed from the route. Save to keep the change.', 'yellow');
    });
  }

  if (els.saveLocal) {
    els.saveLocal.addEventListener('click', async function () {
      if (!state.data) return;
      els.saveLocal.disabled = true;
      setStatus(els.localStatus, 'Saving print-only content…', 'secondary');
      try {
        var data = await fetchJson('/api/shopping-print/local-content', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({list_id: state.data.id, comment: state.localComment, entries: state.localEntries}),
        });
        state.localComment = data.comment || '';
        state.localEntries = (data.entries || []).map(function (entry) { return Object.assign({}, entry); });
        state.order = (data.category_order || state.order).slice();
        state.aliases = Object.assign({}, data.category_aliases || state.aliases);
        normalizeOrder(true);
        renderOrder();
        renderLocalEntries();
        renderReceipt();
        setStatus(els.localStatus, 'Print-only content saved for this list.', 'success');
      } catch (error) {
        setStatus(els.localStatus, error.message, 'danger');
      } finally {
        updateButtons();
      }
    });
  }

  if (els.overrideItem) els.overrideItem.addEventListener('change', syncOverrideEditor);

  if (els.overrideSave) {
    els.overrideSave.addEventListener('click', async function () {
      var item = currentItemForOverride();
      if (!item || !state.data) return;
      els.overrideSave.disabled = true;
      setStatus(els.overrideStatus, 'Saving override…', 'secondary');
      try {
        await fetchJson('/api/shopping-print/item-overrides', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            list_id: state.data.id,
            key: item.override_key,
            name_alias: els.overrideName.value,
            quantity_alias: els.overrideQty.value,
            source_name: item.original_name || item.name || '',
            source_quantity_text: item.original_quantity_text || item.quantity_text || '',
          }),
        });
        await loadList(state.data.id, {preserveLocal: true, silent: true, reason: 'override'});
        els.overrideItem.value = item.override_key;
        syncOverrideEditor();
        setStatus(els.overrideStatus, (els.overrideName.value.trim() || els.overrideQty.value.trim()) ? 'Override saved for this shopping list.' : 'Override removed.', 'success');
      } catch (error) {
        setStatus(els.overrideStatus, error.message, 'danger');
      } finally {
        updateButtons();
      }
    });
  }

  if (els.overrideList) {
    els.overrideList.addEventListener('click', async function (event) {
      var button = event.target.closest('[data-override-remove]');
      var row = event.target.closest('[data-override-key]');
      if (!button || !row || !state.data) return;
      button.disabled = true;
      try {
        await fetchJson('/api/shopping-print/item-overrides/delete', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({list_id: state.data.id, key: row.dataset.overrideKey}),
        });
        await loadList(state.data.id, {preserveLocal: true, silent: true, reason: 'override'});
        setStatus(els.overrideStatus, 'Override removed.', 'success');
      } catch (error) {
        setStatus(els.overrideStatus, error.message, 'danger');
        button.disabled = false;
      }
    });
  }

  document.querySelectorAll('#sp-width,#sp-margin,#sp-font,#sp-line-gap,#sp-category-gap,#sp-bottom-margin,#sp-density,#sp-threshold,#sp-dpi,#sp-label-type,#sp-show-items,#sp-show-quantities,#sp-show-item-dividers,#sp-show-category-dividers,#sp-category-divider-style,input[name="sp-item-marker-style"]').forEach(function (input) {
    input.addEventListener('input', function () { syncConditionalSettings(); if (state.data) renderReceipt(); });
    input.addEventListener('change', function () { syncConditionalSettings(); if (state.data) renderReceipt(); });
  });

  els.saveSettings.addEventListener('click', async function () {
    els.saveSettings.disabled = true;
    setStatus(els.settingsStatus, 'Saving global settings…', 'secondary');
    try {
      var data = await fetchJson('/api/shopping-print/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(inputSettings()),
      });
      populateSettings(data.settings || inputSettings());
      if (state.data) renderReceipt();
      setStatus(els.settingsStatus, 'Global receipt settings saved.', 'success');
    } catch (error) {
      setStatus(els.settingsStatus, error.message, 'danger');
    } finally {
      updateButtons();
    }
  });

  els.connect.addEventListener('click', async function () {
    if (!state.canPrint) return;
    var connected = !!state.printer.connected;
    els.connect.disabled = true;
    setStatus(els.status, connected ? 'Disconnecting printer…' : 'Connecting printer…', 'secondary');
    try {
      await fetchJson(connected ? '/labels/b21/disconnect' : '/labels/b21/connect', {method: 'POST'});
      await refreshPrinter();
      setStatus(els.status, connected ? 'Printer disconnected.' : 'Printer connected.', 'success');
    } catch (error) {
      setStatus(els.status, error.message, 'danger');
      await refreshPrinter();
    }
  });

  els.print.addEventListener('click', async function () {
    if (!state.data || !hasPrintableContent()) return;
    renderReceipt();
    els.print.disabled = true;
    var original = els.print.innerHTML;
    els.print.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span> Printing…';
    setStatus(els.status, 'Sending shopping list to printer…', 'secondary');
    try {
      var data = await fetchJson('/api/shopping-print/print', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({image_base64: els.canvas.toDataURL('image/png'), height_mm: Number(els.canvas.dataset.heightMm || 0)}),
      });
      setStatus(els.status, 'Printed · ' + Number(data.height_mm || els.canvas.dataset.heightMm).toFixed(1) + ' mm paper used.', 'success');
    } catch (error) {
      setStatus(els.status, error.message, 'danger');
      await refreshPrinter();
    } finally {
      els.print.innerHTML = original;
      updateButtons();
    }
  });

  window.addEventListener('b2m:scan', function () {
    if (!els.list.value) return;
    clearTimeout(scanRefreshTimer);
    scanRefreshTimer = window.setTimeout(function () {
      loadList(els.list.value, {preserveLocal: true, silent: true, reason: 'scan'});
    }, 350);
  });

  window.addEventListener('focus', foregroundSync);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) foregroundSync(); });

  bootstrap();
})();
