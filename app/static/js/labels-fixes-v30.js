/* v2026.09.23.30 — small-label fitting and native multi-page B21 queue printing. */
(function () {
  'use strict';
  if (window.location.pathname !== '/labels' || window.__b2mLabelsV30Loaded) return;
  window.__b2mLabelsV30Loaded = true;

  var QUEUE_KEY = 'b2m-label-generator-v2';
  var DESIGN_KEY = 'b2m-b21-design-v1';
  var PROFILE_KEY = 'b2m-b21-profile-v1';
  var previewBusy = false;

  function $(id) { return document.getElementById(id); }
  function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }

  function queue() {
    try {
      var value = JSON.parse(localStorage.getItem(QUEUE_KEY) || '{}');
      return Array.isArray(value.queue) ? value.queue : [];
    } catch (e) { return []; }
  }

  function profile() {
    var select = $('b21-profile-select');
    var text = select && select.options[select.selectedIndex] ? select.options[select.selectedIndex].textContent : '';
    var match = String(text || '').match(/([0-9]+(?:\.[0-9]+)?)\s*[×x]\s*([0-9]+(?:\.[0-9]+)?)\s*mm/i);
    return {
      id: String((select || {}).value || localStorage.getItem(PROFILE_KEY) || '50x30'),
      width_mm: Number(($('b21-profile-width') || {}).value || (match && match[1]) || 50),
      height_mm: Number(($('b21-profile-height') || {}).value || (match && match[2]) || 30),
      dpi: Number(($('b21-profile-dpi') || {}).value || 300),
      density: Number(($('b21-profile-density') || {}).value || 3),
      label_type: Number(($('b21-profile-label-type') || {}).value || 1)
    };
  }

  function designs() {
    try { return JSON.parse(localStorage.getItem(DESIGN_KEY) || '{}') || {}; }
    catch (e) { return {}; }
  }

  function fallbackDesign() {
    return {
      frame:true, frameInsetMm:1, frameWidthMm:.35,
      showCode:true, showLabel:true, showValue:false,
      codeX:50, codeY:42, codeW:86, codeH:58, codeRotation:0,
      textX:50, textY:82, textW:88, textSizePt:14, textRotation:0,
      valueX:50, valueY:94, valueW:90, valueSizePt:7, valueRotation:0,
      threshold:128
    };
  }

  function currentDesign() {
    var all = designs();
    var p = profile();
    return Object.assign(fallbackDesign(), all[p.id] || {});
  }

  function saveDesign(d) {
    var all = designs();
    all[profile().id] = d;
    try { localStorage.setItem(DESIGN_KEY, JSON.stringify(all)); } catch (e) {}
  }

  function physicalBounds(p, wPct, hPct, rotation) {
    var rad = Number(rotation || 0) * Math.PI / 180;
    var w = p.width_mm * Number(wPct || 0) / 100;
    var h = p.height_mm * Number(hPct || 0) / 100;
    return {
      w: Math.abs(w * Math.cos(rad)) + Math.abs(h * Math.sin(rad)),
      h: Math.abs(w * Math.sin(rad)) + Math.abs(h * Math.cos(rad))
    };
  }

  function clampCenter(p, x, y, wPct, hPct, rotation) {
    var bounds = physicalBounds(p, wPct, hPct, rotation);
    var marginX = Math.min(49, bounds.w / p.width_mm * 50 + .6);
    var marginY = Math.min(49, bounds.h / p.height_mm * 50 + .6);
    return {
      x: clamp(Number(x || 50), marginX, 100 - marginX),
      y: clamp(Number(y || 50), marginY, 100 - marginY)
    };
  }

  function fittedDesign() {
    var p = profile();
    var d = currentDesign();
    var changed = false;

    // Code elements may be too large after rotating a preset on a narrow custom
    // roll. Scale the physical box until its rotated bounds fit the actual label.
    var bounds = physicalBounds(p, d.codeW, d.codeH, d.codeRotation);
    if (bounds.w > p.width_mm || bounds.h > p.height_mm) {
      var scale = Math.min(p.width_mm / Math.max(bounds.w, .01), p.height_mm / Math.max(bounds.h, .01)) * .96;
      d.codeW = Math.max(8, Number(d.codeW) * scale);
      d.codeH = Math.max(8, Number(d.codeH) * scale);
      changed = true;
    }
    var code = clampCenter(p, d.codeX, d.codeY, d.codeW, d.codeH, d.codeRotation);
    if (code.x !== Number(d.codeX) || code.y !== Number(d.codeY)) changed = true;
    d.codeX = code.x; d.codeY = code.y;

    var text = clampCenter(p, d.textX, d.textY, d.textW, 28, d.textRotation);
    if (text.x !== Number(d.textX) || text.y !== Number(d.textY)) changed = true;
    d.textX = text.x; d.textY = text.y;
    var value = clampCenter(p, d.valueX, d.valueY, d.valueW, 18, d.valueRotation);
    if (value.x !== Number(d.valueX) || value.y !== Number(d.valueY)) changed = true;
    d.valueX = value.x; d.valueY = value.y;

    if (changed) saveDesign(d);
    return d;
  }

  function applyPreviewFit() {
    if (previewBusy) return;
    var stage = $('b21-label-stage');
    if (!stage || !stage.clientWidth || !stage.clientHeight) return;
    previewBusy = true;
    try {
      var p = profile();
      var d = fittedDesign();
      var map = [
        ['.b21-code', d.codeX, d.codeY, d.codeW, d.codeH, d.codeRotation],
        ['.b21-text', d.textX, d.textY, d.textW, 28, d.textRotation],
        ['.b21-value', d.valueX, d.valueY, d.valueW, 18, d.valueRotation]
      ];
      map.forEach(function (row) {
        var el = stage.querySelector(row[0]);
        if (!el) return;
        el.style.left = row[1] + '%';
        el.style.top = row[2] + '%';
        el.style.width = row[3] + '%';
        el.style.height = row[4] + '%';
        el.style.transform = 'translate(-50%,-50%) rotate(' + Number(row[5] || 0) + 'deg)';
      });

      [['.b21-text', d.textSizePt], ['.b21-value', d.valueSizePt]].forEach(function (row) {
        var el = stage.querySelector(row[0]);
        if (!el) return;
        var desired = Math.max(5, Number(row[1] || 7) * 25.4 / 72 * (stage.clientWidth / p.width_mm));
        var size = desired;
        el.style.fontSize = size + 'px';
        // Preview and print use the same physical box. Shrink instead of merely
        // clipping text that does not fit a short custom label.
        for (var i = 0; i < 40 && size > 5 && (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1); i++) {
          size *= .94;
          el.style.fontSize = size + 'px';
        }
      });
    } finally {
      previewBusy = false;
    }
  }

  function loadImage(url) {
    return new Promise(function (resolve, reject) {
      var img = new Image();
      img.onload = function () { resolve(img); };
      img.onerror = reject;
      img.src = url;
    });
  }

  function codeUrl(entry) {
    return '/labels/code.svg?kind=' + encodeURIComponent(entry.kind || 'auto') + '&value=' + encodeURIComponent(entry.code || '');
  }

  function wrapLines(ctx, text, maxWidth) {
    var words = String(text || '').trim().split(/\s+/).filter(Boolean);
    var lines = [], line = '';
    words.forEach(function (word) {
      var candidate = line ? line + ' ' + word : word;
      if (line && ctx.measureText(candidate).width > maxWidth) { lines.push(line); line = word; }
      else line = candidate;
    });
    if (line) lines.push(line);
    return lines.slice(0, 3);
  }

  function drawTextFit(ctx, text, cx, cy, maxWidth, maxHeight, desiredPx, rotation, mono) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(Number(rotation || 0) * Math.PI / 180);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#000';
    var size = Math.max(5, desiredPx);
    var lines = [];
    for (var i = 0; i < 60; i++) {
      ctx.font = (mono ? '400 ' : '600 ') + size + 'px ' + (mono ? 'monospace' : 'Arial, Helvetica, sans-serif');
      lines = wrapLines(ctx, text, maxWidth);
      var widest = lines.reduce(function (m, line) { return Math.max(m, ctx.measureText(line).width); }, 0);
      if (widest <= maxWidth + .5 && lines.length * size * 1.08 <= maxHeight) break;
      size *= .94;
      if (size <= 5) break;
    }
    ctx.beginPath();
    ctx.rect(-maxWidth / 2, -maxHeight / 2, maxWidth, maxHeight);
    ctx.clip();
    var lineH = size * 1.08;
    var start = -(lines.length - 1) * lineH / 2;
    lines.forEach(function (line, index) { ctx.fillText(line, 0, start + index * lineH, maxWidth); });
    ctx.restore();
  }

  function drawImageFit(ctx, img, cx, cy, w, h, rotation) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(Number(rotation || 0) * Math.PI / 180);
    var scale = Math.min(w / img.naturalWidth, h / img.naturalHeight);
    var dw = img.naturalWidth * scale, dh = img.naturalHeight * scale;
    ctx.drawImage(img, -dw / 2, -dh / 2, dw, dh);
    ctx.restore();
  }

  async function renderPng(entry) {
    var p = profile();
    var d = fittedDesign();
    var pxPerMm = p.dpi / 25.4;
    var width = Math.max(8, Math.round(p.width_mm * pxPerMm));
    var height = Math.max(8, Math.round(p.height_mm * pxPerMm));
    var canvas = document.createElement('canvas');
    canvas.width = width; canvas.height = height;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = '#000'; ctx.strokeStyle = '#000';

    if (d.frame) {
      var inset = Number(d.frameInsetMm || 0) * pxPerMm;
      ctx.lineWidth = Math.max(1, Number(d.frameWidthMm || .35) * pxPerMm);
      ctx.strokeRect(inset, inset, Math.max(1, width - inset * 2), Math.max(1, height - inset * 2));
    }
    if (d.showCode) {
      var img = await loadImage(codeUrl(entry));
      drawImageFit(ctx, img, width * d.codeX / 100, height * d.codeY / 100, width * d.codeW / 100, height * d.codeH / 100, d.codeRotation);
    }
    if (d.showLabel) {
      drawTextFit(ctx, entry.label || entry.code || '', width * d.textX / 100, height * d.textY / 100,
        width * d.textW / 100, height * .28, Number(d.textSizePt || 14) * p.dpi / 72, d.textRotation, false);
    }
    if (d.showValue) {
      drawTextFit(ctx, entry.code || '', width * d.valueX / 100, height * d.valueY / 100,
        width * d.valueW / 100, height * .18, Number(d.valueSizePt || 7) * p.dpi / 72, d.valueRotation, true);
    }
    return canvas.toDataURL('image/png').split(',', 2)[1];
  }

  async function registerQueue(rows) {
    var response = await fetch('/labels/register', {
      method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'},
      body:JSON.stringify({labels:rows.map(function(entry){return {
        code:entry.code,label:entry.label,symbology:entry.kind,target_type:entry.target_type,
        target_id:entry.target_id,target_name:entry.target_name
      };})})
    });
    if (!response.ok) throw new Error('Could not register label queue (HTTP ' + response.status + ')');
  }

  async function printWholeQueue(button) {
    var rows = queue();
    if (!rows.length) return;
    var p = profile(), d = fittedDesign();
    var old = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Printing ' + rows.length + '…';
    try {
      await registerQueue(rows);
      var pages = [];
      for (var i = 0; i < rows.length; i++) {
        pages.push({image_base64: await renderPng(rows[i]), quantity: Math.max(1, Number(rows[i].qty || 1))});
      }
      var response = await fetch('/labels/b21/print-batch-v30', {
        method:'POST', headers:{'Content-Type':'application/json','Accept':'application/json'},
        body:JSON.stringify({pages:pages,width_mm:p.width_mm,height_mm:p.height_mm,density:p.density,label_type:p.label_type,dpi:p.dpi,threshold:d.threshold})
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
      button.className = 'btn btn-success';
      button.innerHTML = '<i class="ti ti-check icon"></i> Printed ' + (data.quantity || rows.length);
    } catch (error) {
      button.className = 'btn btn-outline-danger';
      button.innerHTML = '<i class="ti ti-alert-triangle icon"></i> Failed';
      window.alert('B21 Pro queue print failed: ' + error.message);
    } finally {
      window.setTimeout(function () {
        button.className = 'btn btn-outline-primary';
        button.innerHTML = old;
        button.disabled = false;
      }, 1800);
    }
  }

  function bindPreview() {
    var stage = $('b21-label-stage');
    if (!stage || stage.dataset.b2mV30Observed === '1') return;
    stage.dataset.b2mV30Observed = '1';
    new MutationObserver(function () { window.requestAnimationFrame(applyPreviewFit); })
      .observe(stage, {childList:true, subtree:true, attributes:true});
    window.addEventListener('resize', applyPreviewFit);
    window.setTimeout(applyPreviewFit, 0);
  }

  document.addEventListener('click', function (event) {
    var button = event.target && event.target.closest && event.target.closest('#label-niim-print');
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    printWholeQueue(button);
  }, true);

  function boot() {
    bindPreview();
    var select = $('b21-profile-select');
    if (select) select.addEventListener('change', function () { window.setTimeout(applyPreviewFit, 0); });
    document.querySelectorAll('input[name="b21-preset"]').forEach(function (input) {
      input.addEventListener('change', function () { window.setTimeout(applyPreviewFit, 0); });
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { window.setTimeout(boot, 50); }, {once:true});
  else window.setTimeout(boot, 50);
})();
