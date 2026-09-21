(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }
  async function json(url, options) {
    const response = await fetch(url, Object.assign({headers:{'Accept':'application/json'}}, options || {}));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    return data;
  }

  function initBell() {
    const link = document.querySelector('#notif-dropdown > a');
    const badge = $('notif-badge');
    if (!link || !badge) return;
    function sync() {
      const active = !badge.classList.contains('d-none') || !!document.querySelector('#notif-dropdown .b2m-scan-received-bell');
      link.classList.toggle('b2m-bell-active', active);
      const icon = link.querySelector('.ti-bell,.ti-bell-filled');
      if (icon) {
        icon.classList.toggle('ti-bell-filled', active);
        icon.classList.toggle('ti-bell', !active);
      }
    }
    new MutationObserver(sync).observe(badge, {attributes:true,attributeFilter:['class']});
    new MutationObserver(sync).observe(link, {subtree:true,childList:true,attributes:true,attributeFilter:['class']});
    sync();
  }

  function initBarcodeRouteUx() {
    if (!window.location.pathname.startsWith('/barcodes/')) return;
    function unlock() {
      document.querySelectorAll('.b2m-route-choice-grid input[type="checkbox"]:not([value="inherit"])').forEach((input) => {
        if (input.disabled) input.disabled = false;
      });
      document.querySelectorAll('.b2m-list-choice-grid .b2m-choice-card.b2m-inherited-active').forEach((card) => card.classList.remove('b2m-inherited-active'));
    }
    document.addEventListener('pointerdown', function (event) {
      const card = event.target.closest('.b2m-route-choice-grid .b2m-choice-card');
      if (!card) return;
      const input = card.querySelector('input[type="checkbox"]');
      if (!input || input.value === 'inherit') return;
      input.disabled = false;
      const inherit = card.closest('.b2m-route-choice-grid').querySelector('input[value="inherit"]');
      if (inherit && inherit.checked) inherit.checked = false;
    }, true);
    const observer = new MutationObserver(unlock);
    observer.observe(document.body, {subtree:true,childList:true,attributes:true,attributeFilter:['disabled','class']});
    unlock();
  }

  function initRecipePrefetch() {
    if (window.location.pathname !== '/') return;
    const warmed = new Set();
    function warm(anchor) {
      const href = anchor && anchor.getAttribute('href');
      if (!href || !href.startsWith('/recipes/') || warmed.has(href)) return;
      warmed.add(href);
      fetch(href, {credentials:'same-origin',headers:{'X-B2M-Prefetch':'1'},priority:'low'}).catch(() => {});
    }
    document.querySelectorAll('a[href^="/recipes/"]').forEach((anchor) => {
      anchor.addEventListener('pointerenter', () => warm(anchor), {once:true,passive:true});
      anchor.addEventListener('focus', () => warm(anchor), {once:true});
      anchor.addEventListener('touchstart', () => warm(anchor), {once:true,passive:true});
    });
  }

  function settingsContentBody() {
    return document.querySelector('/settings' === window.location.pathname ? '.col-12.col-md-9 > form > .card-body' : 'body');
  }

  function initAppearance() {
    const form = document.querySelector('form[action="/settings/theme"]');
    if (!form) return;
    const body = form.querySelector('.card-body');
    if (!body) return;

    const liveStyle = document.createElement('style');
    liveStyle.id = 'b2m-theme-live-preview';
    document.head.appendChild(liveStyle);

    const date = document.createElement('section');
    date.id = 'b2m-date-style';
    date.innerHTML =
      '<h3 class="card-title mt-2">Date format</h3><p class="card-subtitle">Format used for full timestamps throughout the interface.</p>' +
      '<div class="form-selectgroup mb-4">' +
      [['short','21.09.26 04:26'],['medium','21.09.2026 04:26'],['long','21. September 2026, 04:26']].map(([value,label]) =>
        '<label class="form-selectgroup-item"><input class="form-selectgroup-input" type="radio" name="theme_date_style" value="'+value+'"><span class="form-selectgroup-label">'+label+'</span></label>'
      ).join('') + '</div>';
    const firstHeading = body.querySelector('h3.card-title');
    if (firstHeading) firstHeading.insertAdjacentElement('beforebegin', date); else body.prepend(date);

    let currentTheme = null;
    function values() {
      const chosen = (name, fallback) => form.querySelector('input[name="'+name+'"]:checked')?.value || fallback;
      return {
        mode: chosen('theme_mode','light'), color: chosen('theme_color','blue'), font: chosen('theme_font','sans-serif'),
        base: chosen('theme_base','gray'), radius: chosen('theme_radius','1'),
        epaper: $('theme-epaper') && $('theme-epaper').checked ? 'true' : 'false',
        contrast: $('theme-contrast') ? $('theme-contrast').value : '65',
        date_style: chosen('theme_date_style','medium')
      };
    }
    let previewTimer = null;
    function preview() {
      clearTimeout(previewTimer);
      previewTimer = setTimeout(async function () {
        try {
          const response = await fetch('/api/theme/preview', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(values())});
          if (!response.ok) return;
          // Remove inline preview variables installed by the older settings script;
          // the generated server CSS is now the single source of truth.
          ['--tblr-primary','--tblr-primary-rgb','--tblr-body-font-family','--tblr-border-radius-scale'].forEach((key)=>document.documentElement.style.removeProperty(key));
          liveStyle.textContent = await response.text();
        } catch (e) {}
      }, 40);
    }

    fetch('/api/theme').then((r)=>r.json()).then((theme) => {
      currentTheme = theme;
      const radio = form.querySelector('input[name="theme_date_style"][value="'+CSS.escape(theme.date_style || 'medium')+'"]');
      if (radio) radio.checked = true;
      setTimeout(preview, 0);
    }).catch(()=>{});

    form.addEventListener('input', preview, true);
    form.addEventListener('change', function (event) {
      preview();
      if (event.target && event.target.name === 'theme_date_style' && event.target.checked) {
        fetch('/api/theme/preferences', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date_style:event.target.value})}).catch(()=>{});
      }
    }, true);

    // The legacy accessibility controls are injected by settings-page.js.
    const waitAccessibility = new MutationObserver(function () {
      const epaper = $('theme-epaper'), contrast = $('theme-contrast');
      if (!epaper || !contrast) return;
      waitAccessibility.disconnect();
      epaper.addEventListener('change', preview);
      contrast.addEventListener('input', preview);
      contrast.addEventListener('dblclick', function(){ this.value=65; const out=$('theme-contrast-value');if(out)out.textContent='65';preview(); });
      preview();
    });
    waitAccessibility.observe(body, {subtree:true,childList:true});
  }

  function makeSettingsCard(title, subtitle) {
    const card = document.createElement('div');
    card.className = 'card mt-3';
    card.innerHTML = '<div class="card-header"><div><h3 class="card-title">'+esc(title)+'</h3><p class="card-subtitle">'+esc(subtitle)+'</p></div></div><div class="card-body"></div>';
    return card;
  }

  function initScannerSettings() {
    const params = new URLSearchParams(window.location.search);
    if (window.location.pathname !== '/settings' || (params.get('tab') || 'mealie') !== 'scanning') return;
    const body = document.querySelector('.col-12.col-md-9 form[action="/settings/configuration"] > .card-body');
    if (!body || $('b2m-scanner-runtime-card')) return;
    const card = makeSettingsCard('USB scanner bridge', 'Live scanner thresholds. The bridge pulls these values from B2M and applies them without an image rebuild.');
    card.id = 'b2m-scanner-runtime-card';
    card.querySelector('.card-body').innerHTML =
      '<div class="row g-3"><div class="col-md-4"><label class="form-label">Minimum barcode length</label><input id="b2m-min-barcode" class="form-control" type="number" min="1" max="64"><div class="form-hint">MIN_BARCODE_LENGTH · default 4</div></div>' +
      '<div class="col-md-4"><label class="form-label">Scan queue size</label><input id="b2m-scan-queue" class="form-control" type="number" min="8" max="2048"><div class="form-hint">SCAN_QUEUE_SIZE · default 64</div></div>' +
      '<div class="col-md-4"><label class="form-label">Maximum key gap</label><div class="input-group"><input id="b2m-key-gap" class="form-control" type="number" min="0.05" max="5" step="0.05"><span class="input-group-text">s</span></div><div class="form-hint">SCAN_KEY_GAP_SECONDS · default 0.4</div></div>' +
      '<div class="col-12 d-flex align-items-center gap-2"><button class="btn btn-primary" id="b2m-save-scanner-runtime" type="button"><i class="ti ti-device-floppy icon"></i> Save scanner settings</button><button class="btn btn-outline-secondary" id="b2m-reset-scanner-runtime" type="button"><i class="ti ti-restore icon"></i> Defaults</button><span class="small text-secondary" id="b2m-scanner-runtime-status"></span></div></div>';
    body.insertBefore(card, body.firstElementChild && body.firstElementChild.nextSibling);
    const fill=(c)=>{$('b2m-min-barcode').value=c.min_barcode_length;$('b2m-scan-queue').value=c.scan_queue_size;$('b2m-key-gap').value=c.scan_key_gap_seconds;};
    json('/api/settings/scanner-bridge').then((d)=>fill(d.config)).catch((e)=>{$('b2m-scanner-runtime-status').textContent=e.message;});
    $('b2m-reset-scanner-runtime').addEventListener('click',()=>fill({min_barcode_length:4,scan_queue_size:64,scan_key_gap_seconds:.4}));
    $('b2m-save-scanner-runtime').addEventListener('click',async()=>{const status=$('b2m-scanner-runtime-status');status.textContent='Saving…';try{const d=await json('/api/settings/scanner-bridge',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({min_barcode_length:Number($('b2m-min-barcode').value),scan_queue_size:Number($('b2m-scan-queue').value),scan_key_gap_seconds:Number($('b2m-key-gap').value)})});fill(d.config);status.className='small text-success';status.textContent='Saved · scanner applies this on its next config refresh.';}catch(e){status.className='small text-danger';status.textContent=e.message;}});
  }

  function initPrinterSettings() {
    const params = new URLSearchParams(window.location.search);
    if (window.location.pathname !== '/settings' || (params.get('tab') || 'mealie') !== 'system') return;
    const body = document.querySelector('.col-12.col-md-9 form[action="/settings/configuration"] > .card-body');
    if (!body || $('b2m-printer-settings-card')) return;
    const card = makeSettingsCard('B21 Pro printer', 'Connection, detected printer data and print statistics.');
    card.id = 'b2m-printer-settings-card';
    card.querySelector('.card-header').insertAdjacentHTML('beforeend','<div class="card-actions"><button class="btn btn-outline-primary" id="b2m-settings-printer-connect" type="button"><i class="ti ti-bluetooth icon"></i> Connect</button></div>');
    card.querySelector('.card-body').innerHTML = '<div class="row row-cards" id="b2m-printer-stats"><div class="col-12 text-secondary">Loading printer…</div></div><div class="datagrid mt-3" id="b2m-printer-data"></div><div class="form-hint text-danger mt-2" id="b2m-printer-error"></div>';
    body.prepend(card);
    async function refresh(){
      try{
        const d=await json('/labels/b21/stats'),s=d.status||{},info=s.info||{},meta=info.modelMetadata||{};
        const stats=[['printer','primary',s.connected?'Connected':'Disconnected','Printer'],['printer','green',d.labels||0,'Labels printed'],['briefcase','azure',d.jobs||0,'Print jobs'],['alert-triangle','red',d.failed||0,'Failed jobs']];
        $('b2m-printer-stats').innerHTML=stats.map(([icon,color,value,label])=>'<div class="col-sm-6 col-lg-3"><div class="card card-sm b2m-settings-stat"><div class="card-body"><div class="row align-items-center"><div class="col-auto"><span class="avatar bg-'+color+'-lt text-'+color+'"><i class="ti ti-'+icon+'"></i></span></div><div class="col"><div class="font-weight-medium">'+esc(value)+'</div><div class="text-secondary">'+esc(label)+'</div></div></div></div></div></div>').join('');
        const rows=[['Model',meta.model||info.model||'B21 Pro'],['Address',s.address||'—'],['Transport',s.transport||'—'],['DPI',meta.dpi||s.dpi||'—'],['Print task',info.detectedPrintTask||s.detected_print_task||s.print_task||'—'],['Firmware',info.firmwareVersion||info.firmware||'—'],['Hardware',info.hardwareVersion||info.hardware||'—'],['Active jobs',d.active_jobs||0],['Last print',d.last_print_at||'—']];
        $('b2m-printer-data').innerHTML=rows.map(([k,v])=>'<div class="datagrid-item"><div class="datagrid-title">'+esc(k)+'</div><div class="datagrid-content">'+esc(v)+'</div></div>').join('');
        $('b2m-printer-error').textContent=d.last_error||'';
        const button=$('b2m-settings-printer-connect');button.dataset.connected=s.connected?'1':'0';button.className='btn '+(s.connected?'btn-outline-danger':'btn-outline-primary');button.innerHTML='<i class="ti ti-'+(s.connected?'bluetooth-off':'bluetooth')+' icon"></i> '+(s.connected?'Disconnect':'Connect');
      }catch(e){$('b2m-printer-error').textContent=e.message;}
    }
    $('b2m-settings-printer-connect').addEventListener('click',async function(){this.disabled=true;try{await json(this.dataset.connected==='1'?'/labels/b21/disconnect':'/labels/b21/connect',{method:'POST'});}catch(e){$('b2m-printer-error').textContent=e.message;}finally{this.disabled=false;refresh();}});
    refresh(); setInterval(refresh,5000);
  }

  function initSettings() { initAppearance(); initScannerSettings(); initPrinterSettings(); }

  function init() {
    initBell(); initBarcodeRouteUx(); initRecipePrefetch(); initSettings();
    if (window.location.pathname === '/labels' && !document.getElementById('b21-v2-script')) {
      const script=document.createElement('script');script.id='b21-v2-script';script.src='/static/js/labels-b21-v2.js';script.defer=true;document.body.appendChild(script);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init,0));
  else setTimeout(init,0);
})();
