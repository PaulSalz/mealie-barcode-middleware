(function () {
  'use strict';

  if (window.location.pathname !== '/labels') return;
  if (window.__b2mLabelsV22Loaded) return;
  window.__b2mLabelsV22Loaded = true;

  const QUEUE_KEY = 'b2m-label-generator-v2';
  const ENTRY_KEY = 'b2m-b21-entry-settings-v3';
  const STYLE_KEY = 'b2m-b21-text-style-v22';
  const THRESHOLD_KEY = 'b2m-b21-profile-threshold-v22';
  const PROFILE_KEY = 'b2m-b21-profile-v1';
  const $ = (id) => document.getElementById(id);

  let profiles = [];
  let calibrations = {};
  let activePointerNode = null;
  let jobPoll = null;
  let applyingStage = false;

  function readJson(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || '') || fallback; }
    catch (e) { return fallback; }
  }
  function writeJson(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }
  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, Object.assign({headers: {'Accept': 'application/json'}}, options || {}));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    return data;
  }

  function queueRows() {
    const data = readJson(QUEUE_KEY, {});
    return Array.isArray(data.queue) ? data.queue : [];
  }
  function currentIndex() { return Number(($('b21-entry-select') || {}).value || 0); }
  function entryKey(entry, index) {
    return String(entry && entry._id != null ? entry._id : ((entry && entry.code) || ('entry-' + index)));
  }
  function context(indexOverride) {
    const queue = queueRows();
    const index = indexOverride == null ? currentIndex() : Number(indexOverride);
    const entry = queue[index] || queue[0];
    if (!entry) return null;
    const states = readJson(ENTRY_KEY, {});
    const key = entryKey(entry, index);
    const state = states[key];
    return state ? {queue, index, entry, states, key, state} : null;
  }
  function selectedElementId() { return String(($('b21-v2-element-select') || {}).value || ''); }
  function selectedElement() {
    const c = context();
    if (!c || !Array.isArray(c.state.elements)) return null;
    return c.state.elements.find((row) => String(row.id) === selectedElementId()) || null;
  }
  function selectedProfileId() {
    const c = context();
    return String((c && c.state && c.state.profileId) || ($('b21-profile-select') || {}).value || localStorage.getItem(PROFILE_KEY) || '50x30');
  }
  function profileById(id) {
    return profiles.find((row) => String(row.id) === String(id)) || profiles[0] || {id:'50x30', width_mm:50, height_mm:30, dpi:300, density:3, label_type:1};
  }
  function calibrationFor(id) {
    const row = calibrations[String(id)] || {};
    return {xMm:Number(row.xMm || row.x_mm || 0), yMm:Number(row.yMm || row.y_mm || 0)};
  }

  function styleStore() { return readJson(STYLE_KEY, {}); }
  function defaultTextStyle(element) {
    return {
      fontFamily: element && element.mono ? 'mono' : 'sans',
      bold: !(element && element.mono),
      italic: false,
      underline: false,
      invert: false,
      textAlign: element && element.textAlign || 'center',
      verticalAlign: 'middle',
      letterSpacingPt: 0
    };
  }
  function styleFor(key, element) {
    const store = styleStore();
    const saved = store[key] && store[key][String(element.id)];
    return Object.assign(defaultTextStyle(element), saved || {});
  }
  function saveStyle(key, elementId, patch) {
    const store = styleStore();
    if (!store[key]) store[key] = {};
    store[key][String(elementId)] = Object.assign({}, store[key][String(elementId)] || {}, patch);
    writeJson(STYLE_KEY, store);
  }

  function thresholdStore() { return readJson(THRESHOLD_KEY, {}); }
  function thresholdFor(profileId, fallback) {
    const value = Number(thresholdStore()[String(profileId)]);
    return Number.isFinite(value) ? Math.max(1, Math.min(255, value)) : Math.max(1, Math.min(255, Number(fallback || 128)));
  }
  function saveThreshold(profileId, value) {
    const store = thresholdStore();
    store[String(profileId)] = Math.max(1, Math.min(255, Number(value || 128)));
    writeJson(THRESHOLD_KEY, store);
  }

  function currentStageNode() {
    const id = selectedElementId();
    return id ? document.querySelector('#b21-label-stage [data-element-id="' + CSS.escape(id) + '"]') : null;
  }

  function applyStyleToNode(node, style, element) {
    if (!node || !style || !element || element.type !== 'text') return;
    const families = {
      sans: 'Inter, "DejaVu Sans", Arial, sans-serif',
      serif: 'Georgia, "DejaVu Serif", serif',
      mono: 'ui-monospace, "DejaVu Sans Mono", monospace'
    };
    node.style.fontFamily = families[style.fontFamily] || families.sans;
    node.style.fontWeight = style.bold ? '700' : '400';
    node.style.fontStyle = style.italic ? 'italic' : 'normal';
    node.style.textDecoration = style.underline ? 'underline' : 'none';
    node.style.letterSpacing = Number(style.letterSpacingPt || 0) + 'pt';
    node.style.textAlign = style.textAlign || 'center';
    node.style.justifyContent = style.textAlign === 'left' ? 'flex-start' : style.textAlign === 'right' ? 'flex-end' : 'center';
    node.style.alignItems = style.verticalAlign === 'top' ? 'flex-start' : style.verticalAlign === 'bottom' ? 'flex-end' : 'center';
    node.style.padding = '2px';
    node.style.boxSizing = 'border-box';
    node.style.backgroundColor = style.invert ? '#000' : 'transparent';
    node.style.color = style.invert ? '#fff' : '#111';
  }

  function applyStageUx() {
    if (applyingStage) return;
    applyingStage = true;
    try {
      const c = context();
      const stage = $('b21-label-stage');
      if (!c || !stage || !Array.isArray(c.state.elements)) return;
      const selected = selectedElementId();
      c.state.elements.forEach((element) => {
        const node = stage.querySelector('[data-element-id="' + CSS.escape(String(element.id)) + '"]');
        if (!node) return;
        node.classList.toggle('b21-v22-selected', String(element.id) === selected);
        if (element.type === 'text') applyStyleToNode(node, styleFor(c.key, element), element);
      });
      syncTypographyControls();
    } finally {
      applyingStage = false;
    }
  }

  function buttonGroup(id, values) {
    return '<div class="btn-group w-100" id="' + id + '" role="group">' + values.map((row) =>
      '<button class="btn btn-outline-secondary" type="button" data-value="' + row[0] + '" title="' + esc(row[2] || row[1]) + '"><i class="ti ti-' + row[1] + '"></i></button>'
    ).join('') + '</div>';
  }

  function installTypography() {
    const inspector = $('b21-v2-inspector');
    const align = $('b21-v2-align');
    if (!inspector || !align || $('b21-v22-typography')) return false;

    $('b21-v18-text-center')?.remove();

    const alignWrap = align.parentElement;
    if (alignWrap && !alignWrap.closest('#b21-v22-element-align')) {
      const section = document.createElement('div');
      section.id = 'b21-v22-element-align';
      section.className = 'b21-section';
      section.innerHTML = '<div class="fw-semibold mb-1">Element alignment</div><div class="form-hint mb-2">Align the selected object on the physical label. Text alignment inside a text box is configured separately below.</div>';
      alignWrap.parentNode.insertBefore(section, alignWrap);
      section.appendChild(alignWrap);
      const centerBoth = document.createElement('button');
      centerBoth.type = 'button';
      centerBoth.className = 'btn btn-outline-secondary';
      centerBoth.title = 'Center element horizontally and vertically';
      centerBoth.innerHTML = '<i class="ti ti-focus-centered"></i>';
      centerBoth.addEventListener('click', function () {
        const x = $('b21-v2-x'), y = $('b21-v2-y');
        if (!x || !y) return;
        x.value = '50'; y.value = '50';
        x.dispatchEvent(new Event('input', {bubbles:true}));
        y.dispatchEvent(new Event('input', {bubbles:true}));
      });
      align.appendChild(centerBoth);
    }

    const section = document.createElement('div');
    section.id = 'b21-v22-typography';
    section.className = 'b21-section';
    section.innerHTML =
      '<div class="fw-semibold mb-1">Typography</div><div class="form-hint mb-3">Formatting applies to the selected text field and is included in B21 printing.</div>' +
      '<div class="row g-2">' +
        '<div class="col-12"><label class="form-label">Font</label><select class="form-select" id="b21-v22-font"><option value="sans">Sans serif</option><option value="serif">Serif</option><option value="mono">Monospace</option></select></div>' +
        '<div class="col-12"><label class="form-label">Style</label><div class="btn-group w-100" id="b21-v22-style-buttons"><button class="btn btn-outline-secondary" type="button" data-style="bold" title="Bold"><strong>B</strong></button><button class="btn btn-outline-secondary" type="button" data-style="italic" title="Italic"><em>I</em></button><button class="btn btn-outline-secondary" type="button" data-style="underline" title="Underline"><u>U</u></button></div></div><div class="col-12"><label class="form-label" for="b21-v22-text-color">Text color</label><select class="form-select" id="b21-v22-text-color"><option value="black">Black</option><option value="white">White</option></select><div class="form-hint">White text prints on a black background.</div></div>' +
        '<div class="col-12"><label class="form-label">Text alignment</label>' + buttonGroup('b21-v22-text-align', [['left','align-left','Left'],['center','align-center','Center'],['right','align-right','Right']]) + '</div>' +
        '<div class="col-12"><label class="form-label">Vertical alignment</label>' + buttonGroup('b21-v22-vertical-align', [['top','layout-align-top','Top'],['middle','layout-align-middle','Middle'],['bottom','layout-align-bottom','Bottom']]) + '</div>' +
        '<div class="col-12"><label class="form-label">Letter spacing: <strong id="b21-v22-letter-spacing-value">0</strong> pt</label><input class="form-range" id="b21-v22-letter-spacing" type="range" min="-1" max="5" step="0.1" value="0"><div class="form-hint">0 pt uses normal spacing. Increase for short headings or compact labels.</div></div>' +
      '</div>';

    const addRow = $('b21-v2-add-text')?.parentElement;
    (addRow || inspector).insertAdjacentElement('beforebegin', section);

    $('b21-v22-font').addEventListener('change', () => updateTextStyle({fontFamily:$('b21-v22-font').value}));
    $('b21-v22-text-color').addEventListener('change', () => updateTextStyle({invert:$('b21-v22-text-color').value === 'white'}));
    section.querySelectorAll('[data-style]').forEach((button) => button.addEventListener('click', function () {
      const current = currentTextStyle();
      if (!current) return;
      updateTextStyle({[this.dataset.style]: !current[this.dataset.style]});
    }));
    section.querySelectorAll('#b21-v22-text-align [data-value]').forEach((button) => button.addEventListener('click', () => updateTextStyle({textAlign:button.dataset.value})));
    section.querySelectorAll('#b21-v22-vertical-align [data-value]').forEach((button) => button.addEventListener('click', () => updateTextStyle({verticalAlign:button.dataset.value})));
    $('b21-v22-letter-spacing').addEventListener('input', function () {
      $('b21-v22-letter-spacing-value').textContent = Number(this.value).toFixed(1);
      updateTextStyle({letterSpacingPt:Number(this.value)}, false);
    });
    $('b21-v22-letter-spacing').addEventListener('change', () => applyStageUx());
    return true;
  }

  function currentTextStyle() {
    const c = context(), element = selectedElement();
    if (!c || !element || element.type !== 'text') return null;
    return styleFor(c.key, element);
  }
  function updateTextStyle(patch, rerender) {
    const c = context(), element = selectedElement();
    if (!c || !element || element.type !== 'text') return;
    saveStyle(c.key, element.id, patch);
    if (rerender !== false) applyStageUx();
    else {
      const node = currentStageNode();
      if (node) applyStyleToNode(node, styleFor(c.key, element), element);
      syncTypographyControls();
    }
  }
  function syncTypographyControls() {
    const section = $('b21-v22-typography');
    if (!section) return;
    const style = currentTextStyle();
    section.classList.toggle('d-none', !style);
    if (!style) return;
    $('b21-v22-font').value = style.fontFamily || 'sans';
    $('b21-v22-text-color').value = style.invert ? 'white' : 'black';
    section.querySelectorAll('[data-style]').forEach((button) => button.classList.toggle('active', !!style[button.dataset.style]));
    section.querySelectorAll('#b21-v22-text-align [data-value]').forEach((button) => button.classList.toggle('active', button.dataset.value === style.textAlign));
    section.querySelectorAll('#b21-v22-vertical-align [data-value]').forEach((button) => button.classList.toggle('active', button.dataset.value === style.verticalAlign));
    const spacing = Number(style.letterSpacingPt || 0);
    $('b21-v22-letter-spacing').value = String(spacing);
    $('b21-v22-letter-spacing-value').textContent = spacing.toFixed(1);
  }

  function installFrameAndThreshold() {
    const frame = $('b21-v2-frame');
    const inspector = $('b21-v2-inspector');
    const profileEditor = $('b21-profile-editor');
    if (!frame || !inspector) return false;

    if (!$('b21-v22-frame-section')) {
      const frameLabel = frame.closest('label');
      const section = document.createElement('div');
      section.id = 'b21-v22-frame-section';
      section.className = 'b21-section b21-v22-frame-section';
      section.innerHTML = '<div class="fw-semibold">Label frame</div>';
      if (frameLabel) section.appendChild(frameLabel);
      const typography = $('b21-v22-typography');
      (typography || inspector).insertAdjacentElement('afterend', section);
    }

    const oldThreshold = $('b21-v2-threshold');
    if (oldThreshold) {
      const oldCol = oldThreshold.closest('.col-6') || oldThreshold.parentElement;
      if (oldCol) oldCol.classList.add('d-none');
      oldThreshold.parentElement?.querySelector('.b21-v4-threshold-preview')?.remove();
    }

    if (profileEditor && !$('b21-v22-profile-threshold')) {
      const row = profileEditor.querySelector('.row');
      if (row) {
        const wrap = document.createElement('div');
        wrap.className = 'col-12 b21-v22-profile-threshold';
        wrap.innerHTML = '<label class="form-label">Print threshold: <strong id="b21-v22-profile-threshold-value">128</strong></label><input class="form-range" id="b21-v22-profile-threshold" type="range" min="1" max="255" step="1" value="128"><div class="form-hint">Raster black/white threshold used by niimblue-node. This is a roll/profile printing setting, not an element-layout setting.</div>';
        row.appendChild(wrap);
        $('b21-v22-profile-threshold').addEventListener('input', function () {
          const profileId = String(($('b21-profile-select') || {}).value || selectedProfileId());
          const value = Number(this.value || 128);
          $('b21-v22-profile-threshold-value').textContent = String(value);
          saveThreshold(profileId, value);
          syncLegacyThreshold(value);
        });
      }
    }
    syncProfileThreshold();
    return true;
  }

  function syncLegacyThreshold(value) {
    const old = $('b21-v2-threshold');
    if (old) old.value = String(value);
    const out = $('b21-v2-threshold-value');
    if (out) out.textContent = String(value);
    const c = context();
    if (c) {
      c.state.threshold = Number(value);
      c.states[c.key] = c.state;
      writeJson(ENTRY_KEY, c.states);
    }
  }
  function syncProfileThreshold() {
    const input = $('b21-v22-profile-threshold');
    if (!input) return;
    const c = context();
    const profileId = selectedProfileId();
    const value = thresholdFor(profileId, c && c.state.threshold);
    input.value = String(value);
    $('b21-v22-profile-threshold-value').textContent = String(value);
    syncLegacyThreshold(value);
  }

  function liveInspectorValue(key, value) {
    const input = $('b21-v2-' + key);
    const output = $('b21-v2-' + key + '-value');
    const rounded = Math.round(Number(value) * 10) / 10;
    if (input) input.value = String(rounded);
    if (output) output.textContent = String(rounded);
  }

  function updateLiveGeometry(node) {
    if (!node || !node.isConnected) return;
    const profile = profileById(selectedProfileId());
    const cal = calibrationFor(profile.id);
    const left = parseFloat(node.style.left || '0');
    const top = parseFloat(node.style.top || '0');
    const width = parseFloat(node.style.width || '0');
    const height = parseFloat(node.style.height || '0');
    if (Number.isFinite(left)) liveInspectorValue('x', left - (cal.xMm / Number(profile.width_mm || 50) * 100));
    if (Number.isFinite(top)) liveInspectorValue('y', top - (cal.yMm / Number(profile.height_mm || 30) * 100));
    if (Number.isFinite(width)) liveInspectorValue('w', width);
    if (Number.isFinite(height)) liveInspectorValue('h', height);
  }

  function installStageTracking() {
    const stage = $('b21-label-stage');
    const select = $('b21-v2-element-select');
    if (!stage || !select || stage.dataset.b2mV22Tracking === '1') return false;
    stage.dataset.b2mV22Tracking = '1';

    stage.addEventListener('pointerdown', function (event) {
      const node = event.target.closest && event.target.closest('[data-element-id]');
      if (!node) return;
      activePointerNode = node;
      stage.querySelectorAll('[data-element-id]').forEach((item) => item.classList.toggle('b21-v22-selected', item === node));
    }, true);
    stage.addEventListener('pointermove', function () { if (activePointerNode) updateLiveGeometry(activePointerNode); }, true);
    ['pointerup','pointercancel'].forEach((name) => stage.addEventListener(name, function () {
      if (activePointerNode) updateLiveGeometry(activePointerNode);
      activePointerNode = null;
      setTimeout(applyStageUx, 0);
    }, true));

    select.addEventListener('change', function () { setTimeout(applyStageUx, 0); });
    new MutationObserver(function () { requestAnimationFrame(applyStageUx); }).observe(stage, {childList:true, subtree:true});
    applyStageUx();
    return true;
  }

  function displayText(element, entry, state) {
    if (element.source === 'label') return entry.label || entry.code || '';
    if (element.source === 'value') return state.codeValue || entry.code || '';
    return element.text || '';
  }
  function loadImage(url) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error('Could not render code'));
      image.src = url;
    });
  }
  function drawContain(ctx, image, x, y, width, height) {
    const scale = Math.min(width / image.naturalWidth, height / image.naturalHeight);
    const dw = image.naturalWidth * scale, dh = image.naturalHeight * scale;
    ctx.drawImage(image, x + (width - dw) / 2, y + (height - dh) / 2, dw, dh);
  }
  function canvasFont(style, px) {
    const family = style.fontFamily === 'serif' ? 'serif' : style.fontFamily === 'mono' ? 'monospace' : 'sans-serif';
    return (style.italic ? 'italic ' : '') + (style.bold ? '700 ' : '400 ') + Math.max(8, px) + 'px ' + family;
  }
  function measureSpaced(ctx, text, spacing) {
    return ctx.measureText(text).width + Math.max(0, String(text).length - 1) * spacing;
  }
  function wrapText(ctx, text, width, spacing) {
    const words = String(text || '').split(/\s+/).filter(Boolean), lines = [];
    let line = '';
    words.forEach((word) => {
      const candidate = line ? line + ' ' + word : word;
      if (!line || measureSpaced(ctx, candidate, spacing) <= width) line = candidate;
      else { lines.push(line); line = word; }
    });
    if (line) lines.push(line);
    return lines.slice(0, 6);
  }
  function drawSpacedLine(ctx, text, x, y, spacing, align) {
    text = String(text || '');
    const width = measureSpaced(ctx, text, spacing);
    let cursor = align === 'center' ? x - width / 2 : align === 'right' ? x - width : x;
    for (const ch of text) {
      ctx.fillText(ch, cursor, y);
      cursor += ctx.measureText(ch).width + spacing;
    }
    return width;
  }
  function drawStyledText(ctx, text, cx, cy, width, height, fontPx, rotation, style) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(rotation * Math.PI / 180);
    ctx.beginPath(); ctx.rect(-width/2, -height/2, width, height); ctx.clip();
    if (style.invert) { ctx.fillStyle = '#000'; ctx.fillRect(-width/2, -height/2, width, height); }
    ctx.fillStyle = style.invert ? '#fff' : '#000';
    ctx.font = canvasFont(style, fontPx);
    ctx.textBaseline = 'middle';
    const spacing = Number(style.letterSpacingPt || 0) * fontPx / Math.max(1, Number(fontPx / (fontPx || 1))) / 72;
    const pad = Math.max(2, fontPx * .15);
    const maxWidth = Math.max(1, width - 2 * pad);
    const lines = wrapText(ctx, text, maxWidth, spacing);
    const lineHeight = fontPx * 1.12;
    const totalHeight = Math.max(fontPx, lines.length * lineHeight);
    let startY;
    if (style.verticalAlign === 'top') startY = -height/2 + pad + fontPx/2;
    else if (style.verticalAlign === 'bottom') startY = height/2 - pad - totalHeight + fontPx/2;
    else startY = -(lines.length - 1) * lineHeight / 2;
    const align = style.textAlign || 'center';
    const anchorX = align === 'left' ? -width/2 + pad : align === 'right' ? width/2 - pad : 0;
    lines.forEach((line, index) => {
      const y = startY + index * lineHeight;
      const lineWidth = drawSpacedLine(ctx, line, anchorX, y, spacing, align);
      if (style.underline) {
        const startX = align === 'center' ? anchorX - lineWidth/2 : align === 'right' ? anchorX - lineWidth : anchorX;
        ctx.save(); ctx.strokeStyle = ctx.fillStyle; ctx.lineWidth = Math.max(1, fontPx / 14); ctx.beginPath();
        ctx.moveTo(startX, y + fontPx * .42); ctx.lineTo(startX + lineWidth, y + fontPx * .42); ctx.stroke(); ctx.restore();
      }
    });
    ctx.restore();
  }

  async function renderSnapshot(def) {
    const {entry, state, profile, calibration, key} = def;
    const ppm = Number(profile.dpi || 300) / 25.4;
    const width = Math.max(8, Math.round(Number(profile.width_mm) * ppm));
    const height = Math.max(8, Math.round(Number(profile.height_mm) * ppm));
    const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0,0,width,height); ctx.fillStyle = '#000'; ctx.strokeStyle = '#000';
    ctx.save(); ctx.translate(Number(calibration.xMm || 0) * ppm, Number(calibration.yMm || 0) * ppm);
    if (state.frame !== false) {
      const inset = Number(state.frameInsetMm || 1) * ppm, line = Math.max(1, Number(state.frameWidthMm || .35) * ppm);
      ctx.lineWidth = line; ctx.strokeRect(inset + line/2, inset + line/2, width - 2*inset - line, height - 2*inset - line);
    }
    for (const element of (state.elements || []).filter((row) => row.visible !== false)) {
      const cx = width * Number(element.x || 0) / 100, cy = height * Number(element.y || 0) / 100;
      const w = width * Number(element.w || 10) / 100, h = height * Number(element.h || 10) / 100, rot = Number(element.rotation || 0);
      if (element.type === 'code') {
        const url = '/labels/code.svg?kind=' + encodeURIComponent(entry.kind || 'auto') + '&value=' + encodeURIComponent(state.codeValue || entry.code || '');
        const image = await loadImage(url);
        ctx.save(); ctx.translate(cx,cy); ctx.rotate(rot*Math.PI/180); drawContain(ctx,image,-w/2,-h/2,w,h); ctx.restore();
      } else if (element.type === 'line') {
        ctx.save(); ctx.translate(cx,cy); ctx.rotate(rot*Math.PI/180); ctx.lineWidth = Math.max(1,Number(element.lineWidthMm || .35)*ppm); ctx.beginPath(); ctx.moveTo(-w/2,0); ctx.lineTo(w/2,0); ctx.stroke(); ctx.restore();
      } else {
        drawStyledText(ctx, displayText(element,entry,state), cx,cy,w,h,Number(element.fontSizePt || 14)*Number(profile.dpi || 300)/72,rot,styleFor(key,element));
      }
    }
    ctx.restore();
    return canvas.toDataURL('image/png').split(',',2)[1];
  }

  async function refreshPrinterData() {
    try {
      const data = await fetchJson('/labels/b21/profiles', {cache:'no-store'});
      profiles = data.profiles || profiles;
      calibrations = data.calibrations || calibrations;
    } catch (e) {}
  }

  async function renderQueuePages() {
    await refreshPrinterData();
    if (window.__b2mB21LabelEditor) window.__b2mB21LabelEditor.prepareQueue();
    const queue = queueRows();
    const scope = ($('b21-v2-print-scope') || {}).value || 'queue';
    const indices = scope === 'current' ? [currentIndex()] : queue.map((_, index) => index);
    const pages = [];
    for (const index of indices) {
      const c = context(index);
      if (!c) continue;
      const profile = clone(profileById(c.state.profileId));
      const def = {entry:clone(c.entry), state:clone(c.state), profile, calibration:clone(calibrationFor(profile.id)), key:c.key};
      pages.push({
        image_base64: await renderSnapshot(def),
        width_mm:profile.width_mm, height_mm:profile.height_mm,
        quantity:Number(c.state.copies || 1), density:Number(profile.density || 3),
        label_type:Number(profile.label_type || 1), dpi:Number(profile.dpi || 300),
        threshold:thresholdFor(profile.id, c.state.threshold)
      });
    }
    return pages;
  }

  window.__b2mB21StyledPrint = {renderQueuePages:renderQueuePages};

  function pollJob(id, button, status) {
    clearInterval(jobPoll);
    jobPoll = setInterval(async function () {
      try {
        const job = await fetchJson('/labels/b21/jobs/' + encodeURIComponent(id), {cache:'no-store'});
        if (status) { status.className='small text-secondary b21-v2-job-state'; status.textContent=job.status+' · '+job.completed_pages+'/'+job.page_count+' · '+job.printed_labels+' labels'; }
        if (job.status === 'completed' || job.status === 'failed' || job.status === 'unknown') {
          clearInterval(jobPoll);
          if (status) {
            status.className='small '+(job.status==='completed'?'text-success':job.status==='unknown'?'text-warning':'text-danger')+' b21-v2-job-state';
            status.textContent=job.status==='unknown'?'Check printer output before retrying · '+(job.error || 'print result unknown'):job.error?'Failed · '+job.error:'Completed · '+job.printed_labels+' labels';
          }
          if (button) button.disabled=false;
        }
      } catch (e) {
        clearInterval(jobPoll);
        if (button) button.disabled=false;
        if (status) { status.className='small text-warning b21-v2-job-state'; status.textContent='Print status unavailable. Check printer output before retrying.'; }
      }
    }, 600);
  }

  async function printWithStyles(event) {
    const button = event.currentTarget;
    event.preventDefault(); event.stopImmediatePropagation(); event.stopPropagation();
    const queue = queueRows(); if (!queue.length) return;
    const status = $('b21-v2-job-state');
    button.disabled = true; if (status) { status.className='small text-secondary b21-v2-job-state'; status.textContent='Preparing styled labels…'; }
    let submitting = false;
    try {
      await refreshPrinterData();
      if (window.__b2mB21LabelEditor) window.__b2mB21LabelEditor.prepareQueue();
      const scope = ($('b21-v2-print-scope') || {}).value || 'queue';
      const indices = scope === 'current' ? [currentIndex()] : queue.map((_, index) => index);
      const defs = indices.map((index) => {
        const c = context(index);
        if (!c) return null;
        const profile = clone(profileById(c.state.profileId));
        return {entry:clone(c.entry), state:clone(c.state), profile, calibration:clone(calibrationFor(profile.id)), key:c.key};
      }).filter(Boolean);
      const pages = [];
      for (const def of defs) {
        pages.push({
          image_base64: await renderSnapshot(def), width_mm:def.profile.width_mm, height_mm:def.profile.height_mm,
          quantity:Number(def.state.copies || 1), density:Number(def.profile.density || 3), label_type:Number(def.profile.label_type || 1),
          dpi:Number(def.profile.dpi || 300), threshold:thresholdFor(def.profile.id, def.state.threshold)
        });
      }
      if (!pages.length) throw new Error('No labels to print');
      submitting = true;
      const job = await fetchJson('/labels/b21/jobs', {method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({pages})});
      submitting = false;
      if (status) status.textContent='Queued · '+job.id;
      pollJob(job.id,button,status);
    } catch (e) {
      button.disabled=false;
      if (status) {
        status.className='small '+(submitting?'text-warning':'text-danger')+' b21-v2-job-state';
        status.textContent=submitting?'Could not confirm print job submission. Check printer output before retrying.':e.message;
      }
    }
  }

  function installPrintOverride() {
    const button = $('label-niim-print');
    if (!button || button.dataset.b2mV22Print === '1') return false;
    button.dataset.b2mV22Print = '1';
    button.addEventListener('click', printWithStyles, true);
    return true;
  }

  function bindProfileChanges() {
    const select = $('b21-profile-select');
    if (!select || select.dataset.b2mV22Profile === '1') return false;
    select.dataset.b2mV22Profile = '1';
    select.addEventListener('change', function () { setTimeout(function () { syncProfileThreshold(); applyStageUx(); },0); });
    return true;
  }

  async function install() {
    if (!$('b21-v2-inspector') || !$('b21-label-stage') || !$('b21-profile-select') || !$('label-niim-print')) {
      setTimeout(install, 120); return;
    }
    await refreshPrinterData();
    installTypography();
    installFrameAndThreshold();
    installStageTracking();
    installPrintOverride();
    bindProfileChanges();
    syncProfileThreshold();
    applyStageUx();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(install,100), {once:true});
  else setTimeout(install,100);
})();
