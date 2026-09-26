(function () {
  'use strict';

  if (window.location.pathname !== '/labels') return;

  const QUEUE_KEY = 'b2m-label-generator-v2';
  const ENTRY_KEY = 'b2m-b21-entry-settings-v3';
  const CAL_KEY = 'b2m-b21-calibration-v1';
  const OLD_DESIGN_KEY = 'b2m-b21-design-v1';
  const PROFILE_KEY = 'b2m-b21-profile-v1';
  const $ = (id) => document.getElementById(id);

  let profiles = [];
  let entryStates = loadJson(ENTRY_KEY, {});
  let calibrations = loadJson(CAL_KEY, {});
  let selectedElementId = 'code';
  let activeJobId = null;
  let jobPoll = null;

  function loadJson(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || '') || fallback; }
    catch (e) { return fallback; }
  }
  function saveJson(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {} }
  function clone(value) { return JSON.parse(JSON.stringify(value)); }
  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
  }
  function readQueue() {
    try {
      const data = JSON.parse(localStorage.getItem(QUEUE_KEY) || '{}');
      return Array.isArray(data.queue) ? data.queue : [];
    } catch (e) { return []; }
  }
  function entryKey(entry, index) { return String(entry && entry._id != null ? entry._id : ((entry && entry.code) || 'entry-' + index)); }
  function currentIndex() { return Number(($('b21-entry-select') && $('b21-entry-select').value) || 0); }
  function currentEntry() { const queue = readQueue(); return queue[currentIndex()] || queue[0] || null; }
  function profileById(id) { return profiles.find((row) => String(row.id) === String(id)) || profiles[0] || {id:'50x30',name:'50 × 30 mm',width_mm:50,height_mm:30,dpi:300,density:3,label_type:1}; }

  function oldDesign(profileId) {
    const all = loadJson(OLD_DESIGN_KEY, {});
    return all[profileId] || {};
  }

  function defaultElements(entry, profileId) {
    const old = oldDesign(profileId);
    return [
      {id:'code', type:'code', name:'Code', visible:old.showCode !== false, x:Number(old.codeX ?? 50), y:Number(old.codeY ?? 42), w:Number(old.codeW ?? 86), h:Number(old.codeH ?? 58), rotation:Number(old.codeRotation ?? 0)},
      {id:'label', type:'text', name:'Label text', source:'label', text:'', visible:old.showLabel !== false, x:Number(old.textX ?? 50), y:Number(old.textY ?? 82), w:Number(old.textW ?? 88), h:24, rotation:Number(old.textRotation ?? 0), fontSizePt:Number(old.textSizePt ?? 14)},
      {id:'value', type:'text', name:'Code value', source:'value', text:'', visible:!!old.showValue, x:Number(old.valueX ?? 50), y:Number(old.valueY ?? 94), w:Number(old.valueW ?? 90), h:16, rotation:Number(old.valueRotation ?? 0), fontSizePt:Number(old.valueSizePt ?? 7), mono:true}
    ];
  }

  function getEntryState(entry, index) {
    if (!entry) return null;
    const key = entryKey(entry, index);
    if (!entryStates[key]) {
      const profileId = localStorage.getItem(PROFILE_KEY) || (profiles[0] && profiles[0].id) || '50x30';
      const old = oldDesign(profileId);
      entryStates[key] = {
        profileId,
        copies: Math.max(1, Math.min(99, Number(entry.qty || 1))),
        codeValue: String(entry.code || ''),
        threshold: Number(old.threshold || 128),
        frame: old.frame !== false,
        frameInsetMm: Number(old.frameInsetMm ?? 1),
        frameWidthMm: Number(old.frameWidthMm ?? .35),
        elements: defaultElements(entry, profileId)
      };
      saveEntryStates();
    }
    const state = entryStates[key];
    if (!Array.isArray(state.elements)) state.elements = defaultElements(entry, state.profileId);
    if (!state.codeValue) state.codeValue = String(entry.code || '');
    return state;
  }
  function saveEntryStates() { saveJson(ENTRY_KEY, entryStates); }
  function getCalibration(profileId) {
    if (!calibrations[profileId]) calibrations[profileId] = {xMm:0, yMm:0};
    return calibrations[profileId];
  }
  function saveCalibrations() { saveJson(CAL_KEY, calibrations); }

  function defaultForElement(type, id) {
    if (type === 'code') return {x:50,y:42,w:86,h:58,rotation:0,visible:true};
    if (type === 'line') return {x:50,y:50,w:70,h:1,rotation:0,visible:true,lineWidthMm:.35};
    if (id === 'value') return {x:50,y:94,w:90,h:16,rotation:0,visible:false,fontSizePt:7};
    return {x:50,y:50,w:88,h:24,rotation:0,visible:true,fontSizePt:14};
  }

  async function fetchJson(url, options) {
    const response = await fetch(url, Object.assign({headers:{'Accept':'application/json'}}, options || {}));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    return data;
  }

  function replaceLabelTypeInput() {
    const old = $('b21-profile-label-type');
    if (!old || old.tagName === 'SELECT') return;
    const select = document.createElement('select');
    select.id = old.id;
    select.className = 'form-select';
    select.innerHTML = [
      [1,'Die-cut / gaps'],[2,'Black mark'],[3,'Continuous'],[4,'Perforated'],
      [5,'Transparent'],[6,'PVC tag'],[10,'Black mark + gap'],[11,'Heat-shrink tube']
    ].map(([value,label]) => '<option value="'+value+'">'+label+'</option>').join('');
    select.value = old.value || '1';
    old.replaceWith(select);
  }

  function installHeader() {
    const bar = $('b21-connection-bar');
    const connect = $('b21-connect-button');
    if (!bar || !connect || $('b21-v2-header')) return false;

    const header = document.createElement('div');
    header.id = 'b21-v2-header';
    header.className = 'mt-3';
    header.innerHTML =
      '<div class="b21-v2-toolbar">' +
        '<select class="form-select w-auto" id="b21-v2-print-scope" title="Print scope"><option value="queue">Print queue</option><option value="current">Current label only</option></select>' +
        '<div class="input-group input-group-sm w-auto"><span class="input-group-text">Copies</span><input class="form-control" id="b21-v2-copies" type="number" min="1" max="99" value="1" style="width:5rem"></div>' +
        '<span class="small text-secondary b21-v2-job-state" id="b21-v2-job-state"></span>' +
      '</div>' +
      '<div class="b21-v2-printer-data" id="b21-v2-printer-data"></div>';
    bar.appendChild(header);

    const oldPrint = $('label-niim-print');
    if (oldPrint) {
      const print = oldPrint.cloneNode(true);
      oldPrint.replaceWith(print);
      print.innerHTML = '<i class="ti ti-printer icon"></i> Print';
      print.classList.remove('d-none');
      connect.insertAdjacentElement('afterend', print);
      print.addEventListener('click', submitPrintJob);
    }
    $('b21-v2-copies').addEventListener('change', function () {
      const entry = currentEntry(); if (!entry) return;
      const s = getEntryState(entry, currentIndex());
      s.copies = Math.max(1, Math.min(99, Number(this.value || 1)));
      this.value = s.copies; saveEntryStates();
    });
    return true;
  }

  async function refreshPrinterHeader() {
    const root = $('b21-v2-printer-data');
    if (!root) return;
    try {
      const data = await fetchJson('/labels/b21/status');
      const info = data.info || {};
      const meta = info.modelMetadata || {};
      const firmware = info.firmwareVersion || info.firmware || info.softwareVersion || '—';
      const hardware = info.hardwareVersion || info.hardware || '—';
      root.innerHTML = [
        ['Printer', meta.model || info.model || 'B21 Pro'],
        ['Address', data.address || '—'],
        ['Transport', data.transport || '—'],
        ['DPI', meta.dpi || data.dpi || '—'],
        ['Print task', info.detectedPrintTask || data.detected_print_task || data.print_task || '—'],
        ['Firmware', firmware],
        ['Hardware', hardware],
        ['State', data.connected ? 'Connected' : 'Disconnected']
      ].map(([k,v]) => '<div><small>'+esc(k)+'</small><strong title="'+esc(v)+'">'+esc(v)+'</strong></div>').join('');
    } catch (e) {
      root.innerHTML = '<div><small>Printer</small><strong class="text-danger">'+esc(e.message)+'</strong></div>';
    }
  }

  function installInspector() {
    const body = $('b21-layout-body');
    if (!body || $('b21-v2-inspector')) return false;
    const sections = Array.from(body.querySelectorAll(':scope > .b21-section'));
    sections.forEach((section, index) => { if (index > 0) section.classList.add('d-none'); });

    const inspector = document.createElement('div');
    inspector.id = 'b21-v2-inspector';
    inspector.className = 'b21-section b21-v2-inspector';
    inspector.innerHTML =
      '<div class="d-flex align-items-center justify-content-between gap-2 mb-2"><div><div class="fw-semibold">Element inspector</div><div class="text-secondary small">Click an element on the label to edit it.</div></div><button class="btn btn-sm btn-outline-secondary" id="b21-v2-reset-all" type="button"><i class="ti ti-restore"></i> Reset all</button></div>' +
      '<select class="form-select mb-2" id="b21-v2-element-select"></select>' +
      '<div class="mb-2 d-none" id="b21-v2-content-row"><label class="form-label">Content / encoded value</label><input class="form-control" id="b21-v2-content"></div>' +
      '<div class="row g-2 mb-2"><div class="col-6"><label class="form-check form-switch"><input class="form-check-input" type="checkbox" id="b21-v2-visible"><span class="form-check-label">Visible</span></label></div><div class="col-6 text-end"><button class="btn btn-sm btn-outline-danger" type="button" id="b21-v2-delete-element"><i class="ti ti-trash"></i> Delete</button></div></div>' +
      '<div class="row g-2" id="b21-v2-ranges">' +
        rangeHtml('X','x',0,100,1) + rangeHtml('Y','y',0,100,1) + rangeHtml('Width','w',2,100,1) + rangeHtml('Height','h',1,100,1) + rangeHtml('Rotation','rotation',0,359,1) + rangeHtml('Font size','fontSizePt',5,48,1) + rangeHtml('Line width','lineWidthMm',.1,3,.05) +
      '</div>' +
      '<div class="mt-3"><label class="form-label">Align selected element</label><div class="btn-group w-100" id="b21-v2-align">' +
        '<button class="btn btn-outline-secondary" data-align="left" title="Left"><i class="ti ti-align-left"></i></button>' +
        '<button class="btn btn-outline-secondary" data-align="hcenter" title="Horizontal center"><i class="ti ti-layout-align-center"></i></button>' +
        '<button class="btn btn-outline-secondary" data-align="right" title="Right"><i class="ti ti-align-right"></i></button>' +
        '<button class="btn btn-outline-secondary" data-align="top" title="Top"><i class="ti ti-layout-align-top"></i></button>' +
        '<button class="btn btn-outline-secondary" data-align="vcenter" title="Vertical center"><i class="ti ti-layout-align-middle"></i></button>' +
        '<button class="btn btn-outline-secondary" data-align="bottom" title="Bottom"><i class="ti ti-layout-align-bottom"></i></button>' +
      '</div></div>' +
      '<div class="d-flex gap-2 mt-3"><button class="btn btn-outline-primary flex-fill" type="button" id="b21-v2-add-text"><i class="ti ti-letter-t"></i> Free text</button><button class="btn btn-outline-primary flex-fill" type="button" id="b21-v2-add-line"><i class="ti ti-minus"></i> Line</button></div>' +
      '<div class="mt-3"><button class="btn btn-sm btn-outline-secondary" type="button" id="b21-v2-reset-element"><i class="ti ti-restore"></i> Reset selected</button><div class="form-hint">Double-click any slider to reset that value.</div></div>' +
      '<div class="b21-section"><div class="fw-semibold mb-2">Label / calibration</div>' +
        '<div class="row g-2"><div class="col-6"><label class="form-check form-switch"><input class="form-check-input" type="checkbox" id="b21-v2-frame"><span class="form-check-label">Frame</span></label></div><div class="col-6"><label class="form-label">Threshold</label><input class="form-range" id="b21-v2-threshold" type="range" min="1" max="255" step="1"><div class="text-secondary small"><span id="b21-v2-threshold-value"></span></div></div></div>' +
        '<div class="row g-2 mt-1"><div class="col-6"><label class="form-label">Print offset X: <strong id="b21-v2-cal-x-value">0</strong> mm</label><input class="form-range" id="b21-v2-cal-x" type="range" min="-5" max="5" step="0.1" value="0"></div><div class="col-6"><label class="form-label">Print offset Y: <strong id="b21-v2-cal-y-value">0</strong> mm</label><input class="form-range" id="b21-v2-cal-y" type="range" min="-5" max="5" step="0.1" value="0"></div></div>' +
        '<div class="d-flex gap-2 mt-2"><button class="btn btn-sm btn-outline-secondary" id="b21-v2-reset-cal" type="button"><i class="ti ti-crosshair"></i> Reset calibration</button><button class="btn btn-sm btn-outline-primary" id="b21-v2-test-cal" type="button"><i class="ti ti-printer"></i> Calibration test</button></div>' +
      '</div>';
    body.appendChild(inspector);

    $('b21-v2-element-select').addEventListener('change', function(){ selectedElementId=this.value; renderStage(); syncInspector(); });
    $('b21-v2-visible').addEventListener('change', updateSelectedFromInspector);
    $('b21-v2-content').addEventListener('input', updateSelectedFromInspector);
    body.querySelectorAll('.b21-v2-range').forEach((range) => {
      range.addEventListener('input', updateSelectedFromInspector);
      range.addEventListener('dblclick', function(){ this.value=this.dataset.default; updateSelectedFromInspector(); });
    });
    $('b21-v2-reset-element').addEventListener('click', resetSelected);
    $('b21-v2-reset-all').addEventListener('click', resetAll);
    $('b21-v2-add-text').addEventListener('click', addFreeText);
    $('b21-v2-add-line').addEventListener('click', addLine);
    $('b21-v2-delete-element').addEventListener('click', deleteSelected);
    $('b21-v2-align').querySelectorAll('[data-align]').forEach((button) => button.addEventListener('click', function(e){e.preventDefault();alignSelected(this.dataset.align);}));
    $('b21-v2-frame').addEventListener('change', function(){const s=currentState();if(s){s.frame=this.checked;persistAndRender();}});
    $('b21-v2-threshold').addEventListener('input', function(){const s=currentState();if(s){s.threshold=Number(this.value);$('b21-v2-threshold-value').textContent=this.value;saveEntryStates();}});
    $('b21-v2-threshold').addEventListener('dblclick', function(){this.value=128;this.dispatchEvent(new Event('input'));});
    ['x','y'].forEach((axis) => {
      const input=$('b21-v2-cal-'+axis);
      input.addEventListener('input', function(){const p=currentProfile();const c=getCalibration(p.id);c[axis+'Mm']=Number(this.value);saveCalibrations();syncCalibration();renderStage();});
      input.addEventListener('dblclick', function(){this.value=0;this.dispatchEvent(new Event('input'));});
    });
    $('b21-v2-reset-cal').addEventListener('click', function(){const p=currentProfile();calibrations[p.id]={xMm:0,yMm:0};saveCalibrations();syncCalibration();renderStage();});
    $('b21-v2-test-cal').addEventListener('click', printCalibrationTest);
    return true;
  }

  function rangeHtml(label, key, min, max, step) {
    return '<div class="col-6 b21-v2-range-wrap" data-range-key="'+key+'"><label class="form-label">'+label+': <strong id="b21-v2-'+key+'-value"></strong></label><input class="form-range b21-v2-range" id="b21-v2-'+key+'" data-key="'+key+'" data-default="0" type="range" min="'+min+'" max="'+max+'" step="'+step+'"></div>';
  }

  function currentState() { const e=currentEntry(); return e ? getEntryState(e,currentIndex()) : null; }
  function currentProfile() { const s=currentState(); return profileById(s ? s.profileId : null); }
  function selectedElement() { const s=currentState(); return s && s.elements.find((el)=>el.id===selectedElementId); }
  function persistAndRender(){ saveEntryStates(); renderStage(); syncInspector(); }

  function syncEntryControls() {
    const s=currentState(); if(!s) return;
    const profileSelect=$('b21-profile-select');
    if(profileSelect && profiles.some((p)=>String(p.id)===String(s.profileId))) profileSelect.value=s.profileId;
    if($('b21-v2-copies')) $('b21-v2-copies').value=s.copies || 1;
    syncCalibration(); syncInspector(); renderStage();
  }

  function syncCalibration(){
    const p=currentProfile(), c=getCalibration(p.id);
    if($('b21-v2-cal-x')) $('b21-v2-cal-x').value=c.xMm||0;
    if($('b21-v2-cal-y')) $('b21-v2-cal-y').value=c.yMm||0;
    if($('b21-v2-cal-x-value')) $('b21-v2-cal-x-value').textContent=Number(c.xMm||0).toFixed(1);
    if($('b21-v2-cal-y-value')) $('b21-v2-cal-y-value').textContent=Number(c.yMm||0).toFixed(1);
  }

  function syncInspector(){
    const s=currentState(); if(!s || !$('b21-v2-element-select')) return;
    if(!s.elements.some((el)=>el.id===selectedElementId)) selectedElementId=s.elements[0] ? s.elements[0].id : '';
    const select=$('b21-v2-element-select');
    select.innerHTML=s.elements.map((el)=>'<option value="'+esc(el.id)+'"'+(el.id===selectedElementId?' selected':'')+'>'+esc(el.name||el.type)+'</option>').join('');
    const el=selectedElement(); if(!el) return;
    const contentRow=$('b21-v2-content-row');
    const content=$('b21-v2-content');
    const hasContent=el.type==='text'||el.type==='code';
    contentRow.classList.toggle('d-none',!hasContent);
    if(el.type==='code') content.value=s.codeValue||currentEntry().code||'';
    else if(el.source==='label') content.value=currentEntry().label||'';
    else if(el.source==='value') content.value=s.codeValue||currentEntry().code||'';
    else content.value=el.text||'';
    content.readOnly=el.source==='label'||el.source==='value';
    $('b21-v2-visible').checked=el.visible!==false;
    const defs=defaultForElement(el.type,el.id);
    ['x','y','w','h','rotation','fontSizePt','lineWidthMm'].forEach((key)=>{
      const input=$('b21-v2-'+key); const wrap=input && input.closest('.b21-v2-range-wrap'); if(!input)return;
      const relevant = key==='fontSizePt' ? el.type==='text' : key==='lineWidthMm' ? el.type==='line' : true;
      if(wrap) wrap.classList.toggle('d-none',!relevant);
      if(relevant){input.value=Number(el[key] ?? defs[key] ?? 0);input.dataset.default=Number(defs[key] ?? 0);const out=$('b21-v2-'+key+'-value');if(out)out.textContent=input.value;}
    });
    $('b21-v2-delete-element').disabled=['code','label','value'].includes(el.id);
    $('b21-v2-frame').checked=s.frame!==false;
    $('b21-v2-threshold').value=Number(s.threshold||128); $('b21-v2-threshold-value').textContent=$('b21-v2-threshold').value;
  }

  function updateSelectedFromInspector(){
    const s=currentState(), el=selectedElement(); if(!s||!el)return;
    el.visible=$('b21-v2-visible').checked;
    if(el.type==='code' && !$('b21-v2-content').readOnly) s.codeValue=$('b21-v2-content').value;
    if(el.type==='text' && !el.source && !$('b21-v2-content').readOnly) el.text=$('b21-v2-content').value;
    document.querySelectorAll('.b21-v2-range:not(.d-none)').forEach((input)=>{const key=input.dataset.key;if(key in el || ['fontSizePt','lineWidthMm'].includes(key)) el[key]=Number(input.value);const out=$('b21-v2-'+key+'-value');if(out)out.textContent=input.value;});
    saveEntryStates(); renderStage();
  }

  function resetSelected(){
    const el=selectedElement(); if(!el)return; Object.assign(el,defaultForElement(el.type,el.id)); saveEntryStates(); syncInspector(); renderStage();
  }
  function resetAll(){
    const entry=currentEntry(); if(!entry)return; const key=entryKey(entry,currentIndex()); delete entryStates[key]; saveEntryStates(); selectedElementId='code'; syncEntryControls();
  }
  function addFreeText(){
    const s=currentState(); if(!s)return; const id='text-'+Date.now(); s.elements.push({id,type:'text',name:'Free text',text:'Text',visible:true,x:50,y:50,w:70,h:24,rotation:0,fontSizePt:14}); selectedElementId=id; persistAndRender();
  }
  function addLine(){
    const s=currentState(); if(!s)return; const id='line-'+Date.now(); s.elements.push({id,type:'line',name:'Line',visible:true,x:50,y:50,w:70,h:1,rotation:0,lineWidthMm:.35}); selectedElementId=id; persistAndRender();
  }
  function deleteSelected(){
    if(['code','label','value'].includes(selectedElementId))return; const s=currentState(); if(!s)return; s.elements=s.elements.filter((el)=>el.id!==selectedElementId); selectedElementId='code'; persistAndRender();
  }
  function alignSelected(mode){
    const el=selectedElement();if(!el)return;
    if(mode==='left') el.x=Math.max(0,el.w/2); else if(mode==='hcenter')el.x=50; else if(mode==='right')el.x=Math.min(100,100-el.w/2);
    else if(mode==='top')el.y=Math.max(0,el.h/2); else if(mode==='vcenter')el.y=50; else if(mode==='bottom')el.y=Math.min(100,100-el.h/2);
    saveEntryStates();syncInspector();renderStage();
  }

  function renderStage(){
    const stage=$('b21-label-stage'), entry=currentEntry(), s=currentState(); if(!stage||!entry||!s)return;
    const p=profileById(s.profileId), cal=getCalibration(p.id);
    stage.style.aspectRatio=p.width_mm+' / '+p.height_mm; stage.innerHTML='';
    if($('b21-preview-meta')) $('b21-preview-meta').innerHTML='<span class="badge bg-blue-lt">'+esc(p.name)+'</span><span class="badge bg-secondary-lt">'+p.width_mm+'×'+p.height_mm+' mm</span><span class="badge bg-secondary-lt">'+p.dpi+' dpi</span><span class="badge bg-secondary-lt b21-v2-calibration-note">offset '+Number(cal.xMm||0).toFixed(1)+' / '+Number(cal.yMm||0).toFixed(1)+' mm</span>';
    if(s.frame!==false){const frame=document.createElement('div');frame.className='b21-label-frame';stage.appendChild(frame);requestAnimationFrame(()=>{const scale=stage.clientWidth/p.width_mm;frame.style.inset=(Number(s.frameInsetMm||1)*scale)+'px';frame.style.borderWidth=Math.max(1,Number(s.frameWidthMm||.35)*scale)+'px';});}
    s.elements.filter((el)=>el.visible!==false).forEach((el)=>stage.appendChild(buildStageElement(el,entry,s,p,cal)));
  }

  function displayText(el,entry,s){ if(el.type==='code')return ''; if(el.source==='label')return entry.label||entry.code||''; if(el.source==='value')return s.codeValue||entry.code||''; return el.text||''; }
  function buildStageElement(el,entry,s,p,cal){
    let node;
    if(el.type==='code'){node=document.createElement('img');node.src='/labels/code.svg?kind='+encodeURIComponent(entry.kind||'auto')+'&value='+encodeURIComponent(s.codeValue||entry.code||'');node.className='b21-element b21-code';}
    else {node=document.createElement('div');node.textContent=displayText(el,entry,s);node.className=el.type==='line'?'b21-v2-line':'b21-v2-free-text';if(el.type==='line')node.style.borderTopWidth=Math.max(1,(Number(el.lineWidthMm||.35)*(stageScale(p))))+'px';else requestAnimationFrame(()=>{node.style.fontSize=physicalFontPx(p,Number(el.fontSizePt||14))+'px';});}
    node.dataset.elementId=el.id; if(el.id===selectedElementId)node.classList.add('b21-v2-element-selected');
    const ox=(Number(cal.xMm||0)/p.width_mm)*100, oy=(Number(cal.yMm||0)/p.height_mm)*100;
    applyBox(node,Number(el.x||0)+ox,Number(el.y||0)+oy,Number(el.w||10),Number(el.h||10),Number(el.rotation||0));
    node.addEventListener('pointerdown',(event)=>startRelativeDrag(event,node,el,p));
    node.addEventListener('click',(event)=>{event.stopPropagation();selectedElementId=el.id;syncInspector();renderStage();});
    if(el.id===selectedElementId){const handle=document.createElement('span');handle.className='b21-v2-resize-handle';handle.addEventListener('pointerdown',(event)=>startResize(event,node,el));node.appendChild(handle);}
    return node;
  }
  function stageScale(p){const stage=$('b21-label-stage');return stage?stage.clientWidth/p.width_mm:1;}
  function physicalFontPx(p,pt){return Math.max(7,(pt*25.4/72)*stageScale(p));}
  function applyBox(node,x,y,w,h,rotation){node.style.left=x+'%';node.style.top=y+'%';node.style.width=w+'%';node.style.height=h+'%';node.style.transform='translate(-50%,-50%) rotate('+rotation+'deg)';}

  function startRelativeDrag(event,node,el,p){
    if(event.target.classList.contains('b21-v2-resize-handle'))return; event.preventDefault();event.stopPropagation();selectedElementId=el.id;
    const startX=event.clientX,startY=event.clientY,origX=Number(el.x||0),origY=Number(el.y||0),rect=$('b21-label-stage').getBoundingClientRect();node.setPointerCapture(event.pointerId);
    const move=(e)=>{el.x=Math.max(0,Math.min(100,origX+(e.clientX-startX)/rect.width*100));el.y=Math.max(0,Math.min(100,origY+(e.clientY-startY)/rect.height*100));const cal=getCalibration(p.id);applyBox(node,el.x+(cal.xMm/p.width_mm*100),el.y+(cal.yMm/p.height_mm*100),el.w,el.h,el.rotation);};
    const end=(e)=>{try{node.releasePointerCapture(e.pointerId);}catch(ignore){}node.removeEventListener('pointermove',move);node.removeEventListener('pointerup',end);node.removeEventListener('pointercancel',end);saveEntryStates();syncInspector();renderStage();};
    node.addEventListener('pointermove',move);node.addEventListener('pointerup',end);node.addEventListener('pointercancel',end);
  }
  function startResize(event,node,el){
    event.preventDefault();event.stopPropagation();const startX=event.clientX,startY=event.clientY,origW=Number(el.w||10),origH=Number(el.h||10),rect=$('b21-label-stage').getBoundingClientRect();event.target.setPointerCapture(event.pointerId);
    const handle=event.target;
    const move=(e)=>{el.w=Math.max(2,Math.min(100,origW+(e.clientX-startX)/rect.width*100));el.h=Math.max(1,Math.min(100,origH+(e.clientY-startY)/rect.height*100));node.style.width=el.w+'%';node.style.height=el.h+'%';};
    const end=(e)=>{try{handle.releasePointerCapture(e.pointerId);}catch(ignore){}handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',end);handle.removeEventListener('pointercancel',end);saveEntryStates();syncInspector();renderStage();};
    handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',end);
  }

  function loadImage(url){return new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('Could not render code'));img.src=url;});}
  function drawContain(ctx,img,x,y,w,h){const scale=Math.min(w/img.naturalWidth,h/img.naturalHeight),dw=img.naturalWidth*scale,dh=img.naturalHeight*scale;ctx.drawImage(img,x+(w-dw)/2,y+(h-dh)/2,dw,dh);}
  function drawText(ctx,text,cx,cy,maxWidth,fontPx,rotation,mono){ctx.save();ctx.translate(cx,cy);ctx.rotate(rotation*Math.PI/180);ctx.fillStyle='#000';ctx.textAlign='center';ctx.textBaseline='middle';ctx.font=(mono?'500 ':'600 ')+Math.max(8,fontPx)+'px '+(mono?'monospace':'sans-serif');const words=String(text||'').split(/\s+/),lines=[];let line='';words.forEach((word)=>{const c=line?line+' '+word:word;if(ctx.measureText(c).width<=maxWidth||!line)line=c;else{lines.push(line);line=word;}});if(line)lines.push(line);const rows=lines.slice(0,4),lh=fontPx*1.08,start=-(rows.length-1)*lh/2;rows.forEach((row,i)=>ctx.fillText(row,0,start+i*lh,maxWidth));ctx.restore();}

  async function renderSnapshot(entry,s,p,cal,calibrationOnly){
    const ppm=p.dpi/25.4,width=Math.max(8,Math.round(p.width_mm*ppm)),height=Math.max(8,Math.round(p.height_mm*ppm));const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,width,height);ctx.fillStyle='#000';ctx.strokeStyle='#000';ctx.save();ctx.translate(Number(cal.xMm||0)*ppm,Number(cal.yMm||0)*ppm);
    if(calibrationOnly){ctx.lineWidth=Math.max(1,.35*ppm);ctx.strokeRect(.8*ppm,.8*ppm,width-1.6*ppm,height-1.6*ppm);ctx.beginPath();ctx.moveTo(width/2-4*ppm,height/2);ctx.lineTo(width/2+4*ppm,height/2);ctx.moveTo(width/2,height/2-4*ppm);ctx.lineTo(width/2,height/2+4*ppm);ctx.stroke();ctx.font=Math.max(10,9*p.dpi/72)+'px sans-serif';ctx.textAlign='center';ctx.fillText('CENTER',width/2,height/2+7*ppm);ctx.restore();return canvas.toDataURL('image/png').split(',',2)[1];}
    if(s.frame!==false){const inset=Number(s.frameInsetMm||1)*ppm,line=Math.max(1,Number(s.frameWidthMm||.35)*ppm);ctx.lineWidth=line;ctx.strokeRect(inset+line/2,inset+line/2,width-2*inset-line,height-2*inset-line);}
    for(const el of s.elements.filter((row)=>row.visible!==false)){
      const cx=width*el.x/100,cy=height*el.y/100,w=width*el.w/100,h=height*el.h/100,rot=Number(el.rotation||0);
      if(el.type==='code'){const url='/labels/code.svg?kind='+encodeURIComponent(entry.kind||'auto')+'&value='+encodeURIComponent(s.codeValue||entry.code||'');const img=await loadImage(url);ctx.save();ctx.translate(cx,cy);ctx.rotate(rot*Math.PI/180);drawContain(ctx,img,-w/2,-h/2,w,h);ctx.restore();}
      else if(el.type==='line'){ctx.save();ctx.translate(cx,cy);ctx.rotate(rot*Math.PI/180);ctx.lineWidth=Math.max(1,Number(el.lineWidthMm||.35)*ppm);ctx.beginPath();ctx.moveTo(-w/2,0);ctx.lineTo(w/2,0);ctx.stroke();ctx.restore();}
      else drawText(ctx,displayText(el,entry,s),cx,cy,w,Number(el.fontSizePt||14)*p.dpi/72,rot,!!el.mono);
    }
    ctx.restore();return canvas.toDataURL('image/png').split(',',2)[1];
  }

  async function submitPrintJob(){
    const queue=readQueue();if(!queue.length)return;const scope=($('b21-v2-print-scope')||{}).value||'queue';const indices=scope==='current'?[currentIndex()]:queue.map((_,i)=>i);const button=$('label-niim-print'),status=$('b21-v2-job-state');if(button)button.disabled=true;if(status)status.textContent='Preparing…';
    try{
      // Snapshot first: subsequent UI changes cannot alter this job.
      const defs=indices.map((index)=>{const entry=clone(queue[index]),s=clone(getEntryState(queue[index],index)),p=clone(profileById(s.profileId)),cal=clone(getCalibration(p.id));return{entry,s,p,cal};});
      const pages=[];for(const def of defs){pages.push({image_base64:await renderSnapshot(def.entry,def.s,def.p,def.cal,false),width_mm:def.p.width_mm,height_mm:def.p.height_mm,quantity:def.s.copies||1,density:def.p.density,label_type:def.p.label_type,dpi:def.p.dpi,threshold:def.s.threshold||128});}
      const job=await fetchJson('/labels/b21/jobs',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({pages})});activeJobId=job.id;if(status)status.textContent='Queued · '+job.id;pollJob(job.id);
    }catch(error){if(status){status.className='small text-danger b21-v2-job-state';status.textContent=error.message;}if(button)button.disabled=false;}
  }
  function pollJob(id){clearInterval(jobPoll);const status=$('b21-v2-job-state'),button=$('label-niim-print');jobPoll=setInterval(async()=>{try{const job=await fetchJson('/labels/b21/jobs/'+encodeURIComponent(id));if(status){status.className='small text-secondary b21-v2-job-state';status.textContent=job.status+' · '+job.completed_pages+'/'+job.page_count+' · '+job.printed_labels+' labels';}if(job.status==='completed'||job.status==='failed'){clearInterval(jobPoll);if(status)status.className='small '+(job.status==='completed'?'text-success':'text-danger')+' b21-v2-job-state';if(job.error&&status)status.textContent='Failed · '+job.error;if(button)button.disabled=false;refreshPrinterHeader();}}catch(e){clearInterval(jobPoll);if(button)button.disabled=false;}},600);}
  async function printCalibrationTest(){const entry=currentEntry(),s=currentState(),p=currentProfile(),cal=getCalibration(p.id);if(!entry)return;const status=$('b21-v2-job-state');try{if(status)status.textContent='Preparing calibration…';const image=await renderSnapshot(entry,clone(s),clone(p),clone(cal),true);const job=await fetchJson('/labels/b21/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pages:[{image_base64:image,width_mm:p.width_mm,height_mm:p.height_mm,quantity:1,density:p.density,label_type:p.label_type,dpi:p.dpi,threshold:128}]})});pollJob(job.id);}catch(e){if(status){status.className='small text-danger';status.textContent=e.message;}}}

  function bindExistingControls(){
    const entrySelect=$('b21-entry-select');if(entrySelect)entrySelect.addEventListener('change',()=>{selectedElementId='code';syncEntryControls();});
    const profileSelect=$('b21-profile-select');if(profileSelect)profileSelect.addEventListener('change',function(){const s=currentState();if(!s)return;s.profileId=this.value;saveEntryStates();localStorage.setItem(PROFILE_KEY,this.value);syncCalibration();renderStage();});
    const connect=$('b21-connect-button');if(connect)connect.addEventListener('click',()=>setTimeout(()=>{refreshPrinterHeader();},500));
    const queue=$('label-queue');if(queue)new MutationObserver(()=>setTimeout(()=>{syncEntryControls();},0)).observe(queue,{childList:true,subtree:true});
  }

  window.__b2mB21LabelEditor = {
    moveLayer: function (id, direction) {
      const state = currentState();
      if (!state || !Array.isArray(state.elements)) return false;
      const index = state.elements.findIndex((row) => String(row.id) === String(id));
      const next = index + Number(direction);
      if (index < 0 || next < 0 || next >= state.elements.length) return false;
      [state.elements[index], state.elements[next]] = [state.elements[next], state.elements[index]];
      persistAndRender();
      return true;
    },
    prepareQueue: function () {
      readQueue().forEach((entry, index) => getEntryState(entry, index));
      saveEntryStates();
      return true;
    }
  };

  async function init(){
    if(!$('b21-layout-body')||!$('b21-label-stage')){setTimeout(init,120);return;}
    try{const data=await fetchJson('/labels/b21/profiles');profiles=data.profiles||[];}catch(e){profiles=[];}
    replaceLabelTypeInput();installHeader();installInspector();bindExistingControls();
    const entry=currentEntry();if(entry){const s=getEntryState(entry,currentIndex());const psel=$('b21-profile-select');if(psel&&profiles.some((p)=>String(p.id)===String(s.profileId)))psel.value=s.profileId;}
    syncEntryControls();refreshPrinterHeader();setInterval(refreshPrinterHeader,5000);
  }

  init();
})();
