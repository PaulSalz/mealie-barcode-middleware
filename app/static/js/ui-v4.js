(function () {
  'use strict';

  const APP_VERSION = '2026.09.21.3';
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value == null ? '' : value)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');

  async function fetchJson(url, options) {
    const response = await fetch(url, Object.assign({headers:{Accept:'application/json'}}, options || {}));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    return data;
  }

  function settingsTab() {
    return new URLSearchParams(window.location.search).get('tab') || 'mealie';
  }

  function normalizeVersion() {
    document.querySelectorAll('span').forEach((span) => {
      if (/^v20\d\d\./.test(span.textContent.trim())) span.textContent = 'v' + APP_VERSION;
    });
  }

  function initVersion() {
    normalizeVersion();
    new MutationObserver(normalizeVersion).observe(document.documentElement, {childList:true,subtree:true,characterData:true});
    fetch('/api/version', {cache:'no-store'}).then((r) => r.json()).then((data) => {
      if (data && data.version) {
        document.querySelectorAll('span').forEach((span) => {
          if (/^v20\d\d\./.test(span.textContent.trim())) span.textContent = 'v' + data.version;
        });
      }
    }).catch(() => {});
  }

  function initBell() {
    const link = document.querySelector('#notif-dropdown > a');
    const badge = $('notif-badge');
    if (!link || !badge) return;
    if (!link.querySelector('.b2m-v4-bell-filled')) {
      const icon = document.createElement('span');
      icon.className = 'b2m-v4-bell-filled';
      icon.setAttribute('aria-hidden','true');
      icon.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 2a6 6 0 0 0-6 6v3.6c0 .7-.24 1.38-.68 1.92L3.4 15.9A1.3 1.3 0 0 0 4.4 18h15.2a1.3 1.3 0 0 0 1-2.1l-1.92-2.38A3.05 3.05 0 0 1 18 11.6V8a6 6 0 0 0-6-6Zm-2.35 18a2.5 2.5 0 0 0 4.7 0h-4.7Z"/></svg>';
      const outline = link.querySelector('.ti-bell');
      if (outline) outline.insertAdjacentElement('afterend', icon); else link.prepend(icon);
    }
    let serverUnread = false;
    function render() {
      link.classList.toggle('b2m-v4-unread', serverUnread);
      badge.classList.toggle('d-none', !serverUnread);
    }
    async function sync() {
      try {
        const items = await fetchJson('/api/notifications', {cache:'no-store'});
        serverUnread = Array.isArray(items) && items.some((item) => !item.is_read);
        render();
      } catch (e) {}
    }
    window.addEventListener('b2m:scan', () => {
      serverUnread = true; render();
      setTimeout(sync, 700);
    });
    ['notif-mark-all','notif-clear-read'].forEach((id) => {
      const el = $(id); if (el) el.addEventListener('click', () => setTimeout(sync, 400));
    });
    const list = $('notif-list'); if (list) new MutationObserver(() => setTimeout(sync, 50)).observe(list,{childList:true,subtree:true});
    sync();
    setInterval(sync, 5000);
  }

  function initBaseShade() {
    function apply(theme) {
      const base = theme && theme.base ? theme.base : 'gray';
      document.documentElement.dataset.b2mBase = base;
    }
    fetchJson('/api/theme').then(apply).catch(() => {});
    document.addEventListener('change', (event) => {
      if (event.target && event.target.name === 'theme_base' && event.target.checked) {
        document.documentElement.dataset.b2mBase = event.target.value;
      }
    });
  }

  function initBarcodeRouteUx() {
    const root = document.querySelector('[data-route-card]');
    if (!root) return;
    document.querySelectorAll('input[name="route_mode"]').forEach((radio) => {
      radio.addEventListener('change', () => {
        document.querySelectorAll('[data-route-card]').forEach((card) => card.classList.toggle('active', !!card.querySelector('input:checked')));
      });
    });
  }

  function initRecipePrefetch() {
    document.querySelectorAll('a[href^="/recipes/"]').forEach((link) => {
      if (link.dataset.b2mPrefetch === '1') return;
      link.dataset.b2mPrefetch = '1';
      const warm = () => fetch(link.href, {headers:{'X-B2M-Prefetch':'1'}}).catch(() => {});
      link.addEventListener('pointerenter', warm, {once:true});
      link.addEventListener('touchstart', warm, {once:true,passive:true});
    });
  }

  function removeLegacySettingsArtifacts() {
    if (window.location.pathname !== '/settings') return;
    const tab = settingsTab();
    document.body.dataset.b2mSettingsTab = tab;
    document.querySelectorAll('a[href="/settings?tab=printer"]').forEach((a) => a.closest('.list-group-item')?.remove());
    if (tab === 'tokens') {
      const health = $('scanner-health-card'); if (health) health.remove();
      document.querySelectorAll('h3.card-title').forEach((h) => {
        if (h.textContent.trim() === 'Last 5 scans') h.closest('.card')?.remove();
      });
    }
    if (tab === 'appearance') {
      const oldDate = $('b2m-date-style'); if (oldDate) oldDate.remove();
      const oldTop = $('b2m-appearance-v3-top'); if (oldTop) oldTop.remove();
    }
    if (tab === 'system') {
      const oldPrinter = $('b2m-printer-settings-card'); if (oldPrinter) oldPrinter.remove();
    }
  }

  function initAppearance() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'appearance') return;
    let tries = 0;
    function install() {
      const form = document.querySelector('form[action="/settings/theme"]');
      const body = form && form.querySelector('.card-body');
      const accessibility = $('theme-accessibility');
      if (!form || !body || !accessibility) {
        if (tries++ < 60) setTimeout(install, 80);
        return;
      }
      removeLegacySettingsArtifacts();
      if ($('b2m-appearance-v4')) return;
      const section = document.createElement('div');
      section.id = 'b2m-appearance-v4';
      section.innerHTML = '<hr class="my-4">' +
        '<h3 class="card-title">Font size</h3><p class="card-subtitle">Global interface scale. Useful for OpenDyslexic.</p>' +
        '<div class="row g-3 align-items-center mt-1"><div class="col"><input class="form-range" type="range" min="80" max="120" step="1" id="b2m-v4-font-size" value="100"></div><div class="col-auto"><strong id="b2m-v4-font-size-value">100%</strong></div></div>' +
        '<h3 class="card-title mt-4">Date format</h3><p class="card-subtitle">Format used for absolute dates and timestamps.</p>' +
        '<div class="form-selectgroup" id="b2m-v4-date-style">' +
          [['short','Short · 21.09.26'],['medium','Medium · 21.09.2026'],['long','Long · 21. September 2026']].map((row) => '<label class="form-selectgroup-item"><input class="form-selectgroup-input" type="radio" name="theme_date_style" value="'+row[0]+'"><span class="form-selectgroup-label">'+row[1]+'</span></label>').join('') +
        '</div><div class="form-hint mt-2" id="b2m-v4-pref-status"></div>';
      accessibility.insertAdjacentElement('afterend', section);
      const slider = $('b2m-v4-font-size'), out = $('b2m-v4-font-size-value'), status = $('b2m-v4-pref-status');
      let saveTimer;
      function save(payload) {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(async () => {
          try {
            await fetchJson('/api/ui-preferences-v3', {method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify(payload)});
            status.className='form-hint mt-2 text-success'; status.textContent='Saved'; setTimeout(() => {status.textContent='';},1000);
          } catch (e) { status.className='form-hint mt-2 text-danger'; status.textContent=e.message; }
        },180);
      }
      fetchJson('/api/ui-preferences-v3').then((prefs) => {
        slider.value = prefs.font_size || 100; out.textContent = slider.value + '%'; document.documentElement.style.fontSize = slider.value + '%';
        section.querySelectorAll('input[name="theme_date_style"]').forEach((r) => r.checked = r.value === (prefs.date_style || 'medium'));
      }).catch(() => {});
      slider.addEventListener('input', () => {out.textContent=slider.value+'%';document.documentElement.style.fontSize=slider.value+'%';save({font_size:Number(slider.value)});});
      section.querySelectorAll('input[name="theme_date_style"]').forEach((r) => r.addEventListener('change', () => {if(r.checked)save({date_style:r.value});}));
    }
    install();
  }

  function scannerRows(items) {
    if (!items.length) return '<tr><td colspan="5" class="text-center text-secondary py-4">No scanner bridge telemetry yet.</td></tr>';
    return items.map((s) => '<tr><td><div class="fw-bold">'+esc(s.token_name)+'</div><code class="text-secondary small">'+esc(s.token_prefix||'—')+'…</code></td><td><div>'+esc(s.hostname||'Unknown host')+'</div><div class="text-secondary small">v'+esc(s.version||'—')+' · '+esc((s.layout||'?').toUpperCase())+'</div></td><td><span class="badge '+(s.online?'bg-green text-green-fg':'bg-secondary-lt')+'">'+(s.online?'Online':'Offline')+'</span><div class="text-secondary small">'+esc(s.last_seen||'—')+'</div></td><td>'+Number(s.scans||0)+' scans<div class="text-secondary small">'+Number(s.errors||0)+' errors · '+(s.latency_ms==null?'—':Number(s.latency_ms)+' ms')+'</div></td><td class="text-secondary">'+esc(s.uptime||s.uptime_seconds||'—')+'</td></tr>').join('');
  }

  async function refreshScannerCards() {
    const health = $('scanner-health-body-v4'), recent = $('scanner-recent-body-v4');
    if (health) {
      try { const data=await fetchJson('/api/scanners'); health.innerHTML=scannerRows(data.items||[]); } catch(e) {}
    }
    if (recent) {
      try { const data=await fetchJson('/api/scanners/recent-scans?limit=5'); recent.innerHTML=(data.items||[]).map((r) => '<tr><td>'+esc(r.created_at||'—')+'</td><td><a href="/barcodes/'+encodeURIComponent(r.barcode)+'"><code>'+esc(r.barcode)+'</code></a></td><td><span class="badge bg-muted-lt">'+esc(r.result)+'</span></td><td>'+esc(r.target_type||'—')+'</td><td>'+esc(r.target_name||'—')+'</td></tr>').join('') || '<tr><td colspan="5" class="text-center text-secondary">No scan events yet.</td></tr>'; } catch(e) {}
    }
  }

  function initScanning() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'scanning') return;
    const pane = document.querySelector('.col-12.col-md-9.d-flex.flex-column');
    const body = pane && pane.querySelector('form > .card-body');
    if (!body) return;
    const subtitle = body.querySelector(':scope > .card-subtitle');
    let anchor = subtitle || body.querySelector('h2');
    const runtime = document.createElement('div');
    runtime.id='b2m-scanner-runtime-v4'; runtime.className='card mt-3 mb-3';
    runtime.innerHTML='<div class="card-header"><div><h3 class="card-title">USB scanner bridge</h3><p class="card-subtitle">Runtime keyboard-scanner parsing. Changes are picked up without rebuilding the bridge.</p></div></div><div class="card-body"><div class="row g-3"><div class="col-md-4"><label class="form-label">Minimum barcode length</label><input id="v4-min-barcode" class="form-control" type="number" min="1" max="64"></div><div class="col-md-4"><label class="form-label">Scan queue size</label><input id="v4-queue-size" class="form-control" type="number" min="8" max="2048"></div><div class="col-md-4"><label class="form-label">Maximum key gap</label><div class="input-group"><input id="v4-key-gap" class="form-control" type="number" min="0.05" max="5" step="0.05"><span class="input-group-text">s</span></div></div></div><div class="d-flex align-items-center gap-2 mt-3"><button id="v4-scanner-save" class="btn btn-primary" type="button"><i class="ti ti-device-floppy icon"></i> Save scanner settings</button><span id="v4-scanner-result" class="form-hint"></span></div></div>';
    anchor.insertAdjacentElement('afterend',runtime); anchor=runtime;
    const health=document.createElement('div'); health.id='scanner-health-card-v4';health.className='card mt-3';health.innerHTML='<div class="card-header"><div><h3 class="card-title">Scanner health</h3><p class="card-subtitle">Live telemetry reported by the USB bridge.</p></div></div><div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Token</th><th>Scanner</th><th>Status</th><th>Statistics</th><th>Uptime</th></tr></thead><tbody id="scanner-health-body-v4"></tbody></table></div>'; anchor.insertAdjacentElement('afterend',health); anchor=health;
    const recent=document.createElement('div');recent.id='scanner-recent-card-v4';recent.className='card mt-3';recent.innerHTML='<div class="card-header"><div><h3 class="card-title">Last 5 scans</h3><p class="card-subtitle">Raw scan result/target debug view.</p></div></div><div class="table-responsive"><table class="table table-vcenter card-table"><thead><tr><th>Time</th><th>Code</th><th>Result</th><th>Target</th><th>Name</th></tr></thead><tbody id="scanner-recent-body-v4"></tbody></table></div>';anchor.insertAdjacentElement('afterend',recent);
    fetchJson('/api/settings/scanner-bridge').then((d) => {const c=d.config||{};$('v4-min-barcode').value=c.min_barcode_length??4;$('v4-queue-size').value=c.scan_queue_size??64;$('v4-key-gap').value=c.scan_key_gap_seconds??0.4;}).catch(()=>{});
    $('v4-scanner-save').addEventListener('click',async()=>{const result=$('v4-scanner-result');try{await fetchJson('/api/settings/scanner-bridge',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({min_barcode_length:Number($('v4-min-barcode').value),scan_queue_size:Number($('v4-queue-size').value),scan_key_gap_seconds:Number($('v4-key-gap').value)})});result.className='form-hint text-success';result.textContent='Saved';}catch(e){result.className='form-hint text-danger';result.textContent=e.message;}});
    refreshScannerCards(); setInterval(refreshScannerCards,5000); window.addEventListener('b2m:scan',()=>setTimeout(refreshScannerCards,250));
  }

  function normalizeSettingsNav() {
    if (window.location.pathname !== '/settings') return;
    if (settingsTab() === 'printer') { window.location.replace('/settings?tab=printing'); return; }
    const printing = document.querySelector('a[href="/settings?tab=printing"]');
    if (printing) printing.childNodes[printing.childNodes.length-1].textContent=' Printer';
    document.querySelectorAll('a[href="/settings?tab=printer"]').forEach((a)=>a.remove());
  }

  function printerInfoHtml(data) {
    const status=data.status||{},info=status.info||{},pi=info.printerInfo||{},meta=info.modelMetadata||{};
    return [['Model',meta.model||'B21 Pro'],['State',status.connected?'Connected':'Disconnected'],['Serial',pi.serial||'—'],['Address',status.address||pi.mac||'—'],['DPI',meta.dpi||status.dpi||'—'],['Print task',info.detectedPrintTask||status.detected_print_task||status.print_task||'—'],['Firmware',pi.softwareVersion||'—'],['Hardware',pi.hardwareVersion||'—'],['Charge',pi.charge==null?'—':pi.charge],['Printed labels',data.labels||0],['Jobs',data.jobs||0],['Failed',data.failed||0],['Active jobs',data.active_jobs||0]].map((row)=>'<div class="datagrid-item"><div class="datagrid-title">'+esc(row[0])+'</div><div class="datagrid-content">'+esc(row[1])+'</div></div>').join('');
  }

  function initPrinting() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'printing') return;
    let tries=0;
    async function install() {
      normalizeSettingsNav();
      const body=$('niim-settings-body');
      if(!body){if(tries++<80)setTimeout(install,80);return;}
      const heading=document.querySelector('.col-12.col-md-9 h2');if(heading)heading.textContent='Printer';
      const subtitle=heading&&heading.nextElementSibling;if(subtitle&&subtitle.classList.contains('card-subtitle'))subtitle.textContent='Connection, statistics and runtime configuration for niimblue-node and the NIIMBOT printer.';
      if($('b2m-printer-runtime-v4'))return;
      const card=document.createElement('div');card.id='b2m-printer-runtime-v4';card.className='card mb-3';card.innerHTML='<div class="card-header"><div><h3 class="card-title">Printer</h3><p class="card-subtitle">Manual BLE connection and current printer state.</p></div><div class="card-actions d-flex align-items-center gap-2"><span id="v4-printer-state" class="badge bg-secondary-lt">Loading…</span><button id="v4-printer-connect" class="btn btn-outline-primary" type="button">Connect</button></div></div><div class="card-body"><div class="datagrid" id="v4-printer-datagrid"></div><div id="v4-printer-error" class="form-hint mt-2"></div></div>';
      body.prepend(card);
      async function refresh(){try{const d=await fetchJson('/labels/b21/stats',{cache:'no-store'});const connected=!!(d.status&&d.status.connected);$('v4-printer-state').className='badge '+(connected?'bg-green text-green-fg':'bg-red-lt text-red');$('v4-printer-state').textContent=connected?'Connected':'Not connected';$('v4-printer-connect').textContent=connected?'Disconnect':'Connect';$('v4-printer-connect').className='btn '+(connected?'btn-outline-danger':'btn-outline-primary');$('v4-printer-connect').dataset.connected=connected?'1':'0';$('v4-printer-datagrid').innerHTML=printerInfoHtml(d);if(d.last_error){$('v4-printer-error').className='form-hint mt-2 text-danger';$('v4-printer-error').textContent=d.last_error;}else{$('v4-printer-error').textContent='';}}catch(e){$('v4-printer-error').className='form-hint mt-2 text-danger';$('v4-printer-error').textContent=e.message;}}
      $('v4-printer-connect').addEventListener('click',async function(){this.disabled=true;$('v4-printer-error').textContent='';try{await fetchJson(this.dataset.connected==='1'?'/labels/b21/disconnect':'/labels/b21/connect',{method:'POST'});}catch(e){$('v4-printer-error').className='form-hint mt-2 text-danger';$('v4-printer-error').textContent=e.message;}finally{this.disabled=false;await refresh();}});
      refresh();setInterval(refresh,5000);
    }
    install();
  }

  function cleanupTokenTelemetry() {
    if (window.location.pathname !== '/settings' || settingsTab() !== 'tokens') return;
    const clean=()=>{const h=$('scanner-health-card');if(h)h.remove();document.querySelectorAll('h3.card-title').forEach((x)=>{if(x.textContent.trim()==='Last 5 scans')x.closest('.card')?.remove();});};
    clean();new MutationObserver(clean).observe(document.body,{childList:true,subtree:true});
  }

  initVersion();

  function init() {
    initBell(); initBaseShade(); initBarcodeRouteUx(); initRecipePrefetch();
    if (window.location.pathname === '/settings') {
      removeLegacySettingsArtifacts(); normalizeSettingsNav(); initAppearance(); initScanning(); initPrinting(); cleanupTokenTelemetry();
      new MutationObserver(() => {removeLegacySettingsArtifacts();normalizeSettingsNav();}).observe(document.body,{childList:true,subtree:true});
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init, 0));
  else setTimeout(init,0);
})();
