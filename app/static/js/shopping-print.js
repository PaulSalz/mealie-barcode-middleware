(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  var state = {
    settings: null,
    data: null,
    order: [],
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
    var response = await fetch(url, Object.assign({headers: {Accept: 'application/json'}}, options || {}));
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    return data;
  }

  function setStatus(el, text, tone) {
    if (!el) return;
    el.textContent = text || '';
    el.className = 'form-hint' + (tone ? ' text-' + tone : '');
  }

  function inputSettings() {
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
    };
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
    $('sp-label-type').value = state.settings.label_type == null ? 1 : state.settings.label_type;
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

  function updateButtons() {
    var hasItems = !!(state.data && state.data.items && state.data.items.length);
    els.print.disabled = !(state.canPrint && hasItems && state.printer && state.printer.connected);
    els.saveOrder.disabled = !(state.canPrint && state.data && state.order.length);
    els.saveSettings.disabled = !state.canPrint;
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

  function renderOrder() {
    if (!state.data) {
      els.order.innerHTML = '<div class="list-group-item text-secondary">Choose a shopping list first.</div>';
      updateButtons();
      return;
    }
    if (!state.order.length) {
      els.order.innerHTML = '<div class="list-group-item text-secondary">This list has no categorized open items.</div>';
      updateButtons();
      return;
    }
    els.order.innerHTML = state.order.map(function (name, index) {
      return '<div class="list-group-item d-flex align-items-center shopping-print-category-row" data-index="' + index + '">' +
        '<span class="shopping-print-category-position text-secondary">' + (index + 1) + '</span>' +
        '<span class="me-auto fw-medium">' + esc(name) + '</span>' +
        '<div class="btn-list shopping-print-category-actions">' +
          '<button type="button" class="btn btn-sm btn-icon btn-outline-secondary" data-move="up" title="Move up"' + (index === 0 ? ' disabled' : '') + '><i class="ti ti-chevron-up"></i></button>' +
          '<button type="button" class="btn btn-sm btn-icon btn-outline-secondary" data-move="down" title="Move down"' + (index === state.order.length - 1 ? ' disabled' : '') + '><i class="ti ti-chevron-down"></i></button>' +
        '</div></div>';
    }).join('');
    updateButtons();
  }

  function orderedItems() {
    if (!state.data) return [];
    var pos = {};
    state.order.forEach(function (name, index) { pos[String(name).toLowerCase()] = index; });
    return (state.data.items || []).slice().sort(function (a, b) {
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
    if (!text) return [''];
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
    return lines.length ? lines : [text];
  }

  function receiptDate() {
    try {
      return new Intl.DateTimeFormat(undefined, {year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date());
    } catch (e) {
      return new Date().toLocaleDateString();
    }
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
      var titleLines = wrapText(ctx, state.data.name || 'Shopping list', contentWidth);
      titleLines.forEach(function (line) {
        if (draw) ctx.fillText(line, margin + (contentWidth - ctx.measureText(line).width) / 2, y);
        y += Math.round(titleSize * 1.12);
      });

      font(dateSize, 400);
      var date = receiptDate();
      if (draw) ctx.fillText(date, margin + (contentWidth - ctx.measureText(date).width) / 2, y);
      y += Math.round(dateSize * 1.7);
      if (draw) {
        ctx.beginPath();
        ctx.moveTo(margin, y);
        ctx.lineTo(widthPx - margin, y);
        ctx.lineWidth = Math.max(1, Math.round(dpi / 150));
        ctx.strokeStyle = '#000';
        ctx.stroke();
      }
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

      categories.forEach(function (category, categoryIndex) {
        var rows = grouped[category] || [];
        if (!rows.length) return;
        if (categoryIndex > 0) y += categoryGap;
        font(categorySize, 700);
        var heading = String(category).toUpperCase();
        var headingLines = wrapText(ctx, heading, contentWidth);
        headingLines.forEach(function (line) {
          if (draw) ctx.fillText(line, margin, y);
          y += Math.round(categorySize * 1.15);
        });
        y += Math.round(lineGap * .4);

        rows.forEach(function (item) {
          font(body, 400);
          var box = Math.max(8, Math.round(body * .72));
          var boxGap = Math.round(body * .38);
          var qty = String(item.quantity_text || '').trim();
          var qtyWidth = qty ? Math.min(Math.round(contentWidth * .30), Math.ceil(ctx.measureText(qty).width)) : 0;
          var qtyGap = qty ? Math.round(body * .35) : 0;
          var textX = margin + box + boxGap;
          var nameWidth = Math.max(body * 3, contentWidth - box - boxGap - qtyWidth - qtyGap);
          var lines = wrapText(ctx, item.name || 'Item', nameWidth);
          var lineHeight = Math.round(body * 1.18);
          var rowHeight = Math.max(box, lines.length * lineHeight);

          if (draw) {
            ctx.lineWidth = Math.max(1, Math.round(dpi / 200));
            ctx.strokeStyle = '#000';
            ctx.strokeRect(margin, y + Math.round((body - box) / 3), box, box);
            lines.forEach(function (line, lineIndex) {
              ctx.fillText(line, textX, y + lineIndex * lineHeight);
            });
            if (qty) {
              var measured = ctx.measureText(qty).width;
              ctx.fillText(qty, widthPx - margin - measured, y);
            }
          }
          y += rowHeight + lineGap;
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

  async function loadList(listId) {
    listId = String(listId || '').trim();
    if (!listId) return;
    localStorage.setItem('b2m-shopping-print-list', listId);
    setStatus(els.status, 'Loading open items…', 'secondary');
    els.list.disabled = true;
    try {
      var data = await fetchJson('/api/shopping-print/lists/' + encodeURIComponent(listId), {cache: 'no-store'});
      state.data = data;
      state.order = (data.category_order || []).slice();
      els.summary.textContent = data.count + ' open item' + (data.count === 1 ? '' : 's') + ' · ' + state.order.length + ' categor' + (state.order.length === 1 ? 'y' : 'ies');
      setStatus(els.status, data.count ? 'Preview uses the current unchecked items from Mealie.' : 'This shopping list currently has no unchecked items.', data.count ? 'secondary' : 'yellow');
      setStatus(els.orderStatus, '', '');
      renderOrder();
      renderReceipt();
    } catch (error) {
      state.data = null;
      state.order = [];
      els.summary.textContent = 'Could not load list';
      setStatus(els.status, error.message, 'danger');
      renderOrder();
      renderReceipt();
    } finally {
      els.list.disabled = false;
      updateButtons();
    }
  }

  async function refreshPrinter() {
    try {
      var printer = await fetchJson('/labels/b21/status', {cache: 'no-store'});
      updatePrinterStatus(printer);
    } catch (error) {
      updatePrinterStatus({configured: true, connected: false, error: error.message});
    }
  }

  async function bootstrap() {
    setStatus(els.status, 'Loading shopping lists…', 'secondary');
    try {
      var results = await Promise.all([
        fetchJson('/api/shopping-print/bootstrap', {cache: 'no-store'}),
        fetchJson('/api/access/me', {cache: 'no-store'}).catch(function () { return null; }),
      ]);
      var data = results[0];
      var access = results[1];
      state.canPrint = !!(access && (access.is_admin || (access.permissions && access.permissions.printer)));
      populateSettings(data.settings || {});
      populateLists(data.lists || [], data.default_list_id);
      updatePrinterStatus(data.printer || {});
      if (!state.canPrint) {
        setStatus(els.settingsStatus, 'Preview only: your account does not have printer permission.', 'secondary');
      }
      if (els.list.value) await loadList(els.list.value);
      else setStatus(els.status, 'No shopping lists are available.', 'yellow');
    } catch (error) {
      setStatus(els.status, error.message, 'danger');
      els.list.innerHTML = '<option value="">Could not load shopping lists</option>';
      els.list.disabled = true;
    }
  }

  els.list.addEventListener('change', function () { loadList(els.list.value); });
  els.refresh.addEventListener('click', function () {
    if (els.list.value) loadList(els.list.value);
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

  els.saveOrder.addEventListener('click', async function () {
    if (!state.data) return;
    els.saveOrder.disabled = true;
    setStatus(els.orderStatus, 'Saving route…', 'secondary');
    try {
      var data = await fetchJson('/api/shopping-print/category-order', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', Accept: 'application/json'},
        body: JSON.stringify({list_id: state.data.id, category_order: state.order}),
      });
      state.order = (data.category_order || state.order).slice();
      renderOrder();
      renderReceipt();
      setStatus(els.orderStatus, 'Route saved globally for this list.', 'success');
    } catch (error) {
      setStatus(els.orderStatus, error.message, 'danger');
    } finally {
      updateButtons();
    }
  });

  document.querySelectorAll('#sp-width,#sp-margin,#sp-font,#sp-line-gap,#sp-category-gap,#sp-bottom-margin,#sp-density,#sp-threshold,#sp-dpi,#sp-label-type').forEach(function (input) {
    input.addEventListener('input', function () { if (state.data) renderReceipt(); });
  });

  els.saveSettings.addEventListener('click', async function () {
    els.saveSettings.disabled = true;
    setStatus(els.settingsStatus, 'Saving global settings…', 'secondary');
    try {
      var data = await fetchJson('/api/shopping-print/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', Accept: 'application/json'},
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
      await fetchJson(connected ? '/labels/b21/disconnect' : '/labels/b21/connect', {
        method: 'POST',
        headers: {Accept: 'application/json'},
      });
      await refreshPrinter();
      setStatus(els.status, connected ? 'Printer disconnected.' : 'Printer connected.', 'success');
    } catch (error) {
      setStatus(els.status, error.message, 'danger');
      await refreshPrinter();
    }
  });

  els.print.addEventListener('click', async function () {
    if (!state.data || !(state.data.items || []).length) return;
    renderReceipt();
    els.print.disabled = true;
    var original = els.print.innerHTML;
    els.print.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span> Printing…';
    setStatus(els.status, 'Sending shopping list to printer…', 'secondary');
    try {
      var data = await fetchJson('/api/shopping-print/print', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', Accept: 'application/json'},
        body: JSON.stringify({
          image_base64: els.canvas.toDataURL('image/png'),
          height_mm: Number(els.canvas.dataset.heightMm || 0),
        }),
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

  bootstrap();
})();
