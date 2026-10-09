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
  function resolvedCodeKind(entry, value) {
    const kind = String(entry && entry.kind || 'auto').toLowerCase();
    if (kind !== 'auto') return kind;
    const encoded = String(value == null ? (entry && entry.code || '') : value);
    return /^[\x00-\x7f]*$/.test(encoded) && encoded.length <= 32 ? 'code128' : 'qr';
  }

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
    entryStates = loadJson(ENTRY_KEY, entryStates);
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

  function syncHeaderVisibility() {
    const header = $('b21-v2-header');
    if (!header) return;
    const b21Output = document.querySelector('input[name="label-output"][value="b21"]');
    header.classList.toggle('d-none', !b21Output || !b21Output.checked);
  }

  function installHeader() {
    const bar = $('b21-connection-bar');
    const connect = $('b21-connect-button');
    if (!bar || !connect || $('b21-v2-header')) return false;

    const header = document.createElement('div');
    header.id = 'b21-v2-header';
    const browserOutput = $('b21-output-grid') && $('b21-output-grid').querySelector('input[value="browser"]');
    header.className = 'b21-v2-header' + (browserOutput && browserOutput.checked ? ' d-none' : '');
    header.innerHTML =
      '<div class="b21-v2-toolbar">' +
        '<select class="form-select w-auto" id="b21-v2-print-scope" title="Print scope"><option value="queue">Print queue</option><option value="current">Current label only</option></select>' +
        '<div class="input-group input-group-sm w-auto"><span class="input-group-text">Copies</span><input class="form-control" id="b21-v2-copies" type="number" min="1" max="99" value="1" style="width:5rem"></div>' +
        '<span class="small text-secondary b21-v2-job-state" id="b21-v2-job-state"></span>' +
      '</div>';
    bar.appendChild(header);
    window.addEventListener('b2m:advanced-change', syncHeaderVisibility);
    document.querySelectorAll('input[name="label-output"]').forEach((input) => {
      input.addEventListener('change', syncHeaderVisibility);
    });
    syncHeaderVisibility();

    const oldPrint = $('label-niim-print');
    if (oldPrint) {
      const print = oldPrint.cloneNode(true);
      oldPrint.replaceWith(print);
      print.innerHTML = '<i class="ti ti-printer icon"></i> Print';
      const browserOutput = $('b21-output-grid') && $('b21-output-grid').querySelector('input[value="browser"]');
      print.classList.toggle('d-none', !!(browserOutput && browserOutput.checked));
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

  function installInspector() {
    const body = $('b21-layout-body');
    if (!body || $('b21-v2-inspector')) return false;
    const sections = Array.from(body.querySelectorAll(':scope > .b21-section'));
    sections.forEach((section, index) => { if (index > 0) section.classList.add('d-none'); });

    const inspector = document.createElement('div');
    inspector.id = 'b21-v2-inspector';
    inspector.className = 'b21-section b21-v2-inspector';
    inspector.innerHTML =
      '<div id="b21-v2-layers-header" class="d-flex align-items-center justify-content-between gap-2 mb-2 b21-v2-layers-header"><div><div class="fw-semibold">Element inspector</div><div class="text-secondary small">Click an element on the label to edit it.</div></div><button class="btn btn-sm btn-outline-secondary" id="b21-v2-reset-all" type="button"><i class="ti ti-restore"></i> Reset all</button></div>' +
      '<select class="form-select mb-2" id="b21-v2-element-select"></select>' +
      '<div class="b21-v2-content-panel mb-2 d-none" id="b21-v2-content-row"><label class="form-label">Content / encoded value</label><input class="form-control" id="b21-v2-content"></div>' +
      '<div class="d-flex justify-content-between align-items-center gap-2 mb-2" id="b21-v2-content-actions"><button class="btn btn-sm btn-outline-secondary" type="button" id="b21-v2-reset-element"><i class="ti ti-restore"></i> Reset selected</button><button class="btn btn-sm btn-outline-danger" type="button" id="b21-v2-delete-element"><i class="ti ti-trash"></i> Delete</button></div>' +
      '<div class="row g-2" id="b21-v2-ranges">' +
        rangeHtml('X','x',0,100,1) + rangeHtml('Y','y',0,100,1) + rangeHtml('Width','w',2,100,1) + rangeHtml('Height','h',1,100,1) + rangeHtml('Rotation','rotation',0,359,1) + rangeHtml('Font size','fontSizePt',5,48,.5) + rangeHtml('Line width','lineWidthMm',.1,3,.05) +
      '</div>' +
      '<div class="mt-3"><div class="btn-group w-100" id="b21-v2-align">' +
        '<button type="button" class="btn btn-outline-secondary" data-align="left" title="Left"><i class="ti ti-align-left"></i></button>' +
        '<button type="button" class="btn btn-outline-secondary" data-align="hcenter" title="Horizontal center"><i class="ti ti-layout-align-center"></i></button>' +
        '<button type="button" class="btn btn-outline-secondary" data-align="right" title="Right"><i class="ti ti-align-right"></i></button>' +
        '<button type="button" class="btn btn-outline-secondary" data-align="top" title="Top"><i class="ti ti-layout-align-top"></i></button>' +
        '<button type="button" class="btn btn-outline-secondary" data-align="vcenter" title="Vertical center"><i class="ti ti-layout-align-middle"></i></button>' +
        '<button type="button" class="btn btn-outline-secondary" data-align="bottom" title="Bottom"><i class="ti ti-layout-align-bottom"></i></button>' +
      '</div></div>' +
      '<div class="d-flex gap-2 mt-3"><button class="btn btn-outline-primary flex-fill" type="button" id="b21-v2-add-text"><i class="ti ti-letter-t"></i> Free text</button><button class="btn btn-outline-primary flex-fill" type="button" id="b21-v2-add-line"><i class="ti ti-minus"></i> Line</button></div>' +
      '<div class="mt-3"><div class="form-hint">Double-click any slider to reset that value.</div></div>' +
      '<div class="b21-section"><div class="fw-semibold mb-2">Label / calibration</div>' +
        '<div class="row g-2"><div class="col-6"><label class="form-check form-switch"><input class="form-check-input" type="checkbox" id="b21-v2-frame"><span class="form-check-label">Frame</span></label></div><div class="col-6"><label class="form-label">Threshold</label><input class="form-range" id="b21-v2-threshold" type="range" min="1" max="255" step="1"><div class="text-secondary small"><span id="b21-v2-threshold-value"></span></div></div></div>' +
        '<div class="row g-2 mt-1"><div class="col-6"><label class="form-label">Print offset X: <strong id="b21-v2-cal-x-value">0</strong> mm</label><input class="form-range" id="b21-v2-cal-x" type="range" min="-5" max="5" step="0.1" value="0"></div><div class="col-6"><label class="form-label">Print offset Y: <strong id="b21-v2-cal-y-value">0</strong> mm</label><input class="form-range" id="b21-v2-cal-y" type="range" min="-5" max="5" step="0.1" value="0"></div></div>' +
        '<div class="d-flex gap-2 mt-2"><button class="btn btn-sm btn-outline-secondary" id="b21-v2-reset-cal" type="button"><i class="ti ti-crosshair"></i> Reset calibration</button><button class="btn btn-sm btn-outline-primary" id="b21-v2-test-cal" type="button"><i class="ti ti-printer"></i> Calibration test</button></div>' +
      '</div>';
    body.appendChild(inspector);
    installRangeSteppers(inspector);

    $('b21-v2-element-select').addEventListener('change', function(){ selectedElementId=this.value; renderStage(); syncInspector(); });
    $('b21-v2-content').addEventListener('input', updateSelectedFromInspector);
    body.querySelectorAll('.b21-v2-range').forEach((range) => {
      range.addEventListener('input', updateSelectedFromInspector);
      range.addEventListener('dblclick', function(){ this.value=this.dataset.default; this.dispatchEvent(new Event('input',{bubbles:true})); });
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

  function installRangeSteppers(root) {
    root.querySelectorAll('input[type="range"]').forEach((input) => {
      if (input.dataset.stepper === '1') return;
      input.dataset.stepper = '1';
      const row = document.createElement('div');
      row.className = 'b21-range-stepper-row';
      input.parentNode.insertBefore(row, input);
      row.appendChild(input);
      const controls = document.createElement('div');
      controls.className = 'b21-range-stepper';
      const label = input.closest('.b21-v2-range-wrap')?.querySelector('.form-label')?.textContent?.split(':')[0] || input.id;
      [['1','▲','Increase '],['-1','▼','Decrease ']].forEach(([direction, icon, prefix]) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.id = input.id + (Number(direction) < 0 ? '-step-down' : '-step-up');
        button.className = 'btn btn-outline-secondary b21-range-stepper-button';
        button.textContent = icon;
        button.title = prefix + label;
        button.setAttribute('aria-label', prefix + label);
        button.addEventListener('click', () => {
          const step = Number(input.step) || 1;
          const precision = Math.min(5, (String(input.step).split('.')[1] || '').length);
          const factor = Math.pow(10, precision);
          const current = Number(input.value) || 0;
          const minimum = input.min === '' ? -Infinity : Number(input.min);
          const maximum = input.max === '' ? Infinity : Number(input.max);
          const next = Math.max(minimum, Math.min(maximum, current + Number(direction) * step));
          input.value = String(Math.round(next * factor) / factor);
          input.dispatchEvent(new Event('input', {bubbles:true}));
          input.focus();
        });
        controls.appendChild(button);
      });
      row.appendChild(controls);
    });
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
    if(!s.elements.some((row)=>row.id===selectedElementId)) selectedElementId=s.elements[0] ? s.elements[0].id : '';
    const select=$('b21-v2-element-select');
    select.innerHTML=s.elements.map((row)=>'<option value="'+esc(row.id)+'"'+(row.id===selectedElementId?' selected':'')+'>'+esc(row.name||row.type)+'</option>').join('');
    const el=s.elements.find((row)=>row.id===selectedElementId); if(!el) return;
    const contentRow=$('b21-v2-content-row');
    const content=$('b21-v2-content');
    const hasContent=el.type==='text'||el.type==='code';
    contentRow.classList.toggle('d-none',!hasContent);
    if(el.type==='code') content.value=s.codeValue||currentEntry().code||'';
    else if(el.source==='label') content.value=currentEntry().label||'';
    else if(el.source==='value') content.value=s.codeValue||currentEntry().code||'';
    else content.value=el.text||'';
    content.readOnly=el.source==='label'||el.source==='value';

    const p=profileById(s.profileId);
    const codeKind=resolvedCodeKind(currentEntry(),s.codeValue);
    let normalizedQr=false;
    if(codeKind==='qr'){
      const code=s.elements.find((row)=>row.type==='code');
      if(code){
        const sideMm=Math.min(Number(code.w||0)*p.width_mm/100,Number(code.h||0)*p.height_mm/100);
        const nextW=sideMm/p.width_mm*100,nextH=sideMm/p.height_mm*100;
        normalizedQr=Math.abs(Number(code.w||0)-nextW)>0.0001||Math.abs(Number(code.h||0)-nextH)>0.0001;
        code.w=nextW;code.h=nextH;
      }
    }
    if(el.type==='code'){
      const width=$('b21-v2-w'),height=$('b21-v2-h');
      const isQr=codeKind==='qr';
      if(width){width.step=isQr?'any':'1';width.max=String(isQr?Math.min(100,100*p.height_mm/p.width_mm):100);}
      if(height){height.step=isQr?'any':'1';height.max=String(isQr?Math.min(100,100*p.width_mm/p.height_mm):100);}
    }
    const defs=defaultForElement(el.type,el.id);
    ['x','y','w','h','rotation','fontSizePt','lineWidthMm'].forEach((key)=>{
      const input=$('b21-v2-'+key); const wrap=input&&input.closest('.b21-v2-range-wrap'); if(!input)return;
      const relevant=key==='fontSizePt'?el.type==='text':key==='lineWidthMm'?el.type==='line':true;
      if(wrap)wrap.classList.toggle('d-none',!relevant);
      if(relevant){input.value=Number(el[key]??defs[key]??0);input.dataset.default=Number(defs[key]??0);const out=$('b21-v2-'+key+'-value');if(out)out.textContent=input.value;}
    });
    $('b21-v2-delete-element').disabled=['code','label','value'].includes(el.id);
    $('b21-v2-frame').checked=s.frame!==false;
    $('b21-v2-threshold').value=Number(s.threshold||128);$('b21-v2-threshold-value').textContent=$('b21-v2-threshold').value;
    if(normalizedQr){saveEntryStates();renderStage();}
  }

  function updateSelectedFromInspector(event){
    const s=currentState();if(!s)return;
    const el=s.elements.find((row)=>row.id===selectedElementId);if(!el)return;
    const target=event&&event.target;
    const changedKey=target&&target.dataset?target.dataset.key:'';
    if(target&&target.id==='b21-v2-content'){
      if(el.type==='code'&&!target.readOnly)s.codeValue=target.value;
      if(el.type==='text'&&!el.source&&!target.readOnly)el.text=target.value;
    } else if(target&&target.matches&&target.matches('.b21-v2-range')) {
      if(changedKey in el||['fontSizePt','lineWidthMm'].includes(changedKey))el[changedKey]=Number(target.value);
    }
    const codeKind=resolvedCodeKind(currentEntry(),s.codeValue);
    if(el.type==='code'&&codeKind==='qr'&&(changedKey==='w'||changedKey==='h')){
      const p=profileById(s.profileId);
      const sideMm=changedKey==='w'?Number(el.w||0)*p.width_mm/100:Number(el.h||0)*p.height_mm/100;
      el.w=sideMm/p.width_mm*100;el.h=sideMm/p.height_mm*100;
    }
    if(changedKey==='w'||changedKey==='h'){
      ['w','h'].forEach((key)=>{const input=$('b21-v2-'+key),out=$('b21-v2-'+key+'-value');if(input){input.value=el[key];if(out)out.textContent=input.value;}});
    } else if(changedKey){const out=$('b21-v2-'+changedKey+'-value');if(out)out.textContent=target.value;}
    saveEntryStates();
    if(target&&target.id==='b21-v2-content')syncInspector();
    renderStage();
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
    const select=$('b21-v2-element-select');if(select&&select.value)selectedElementId=select.value;
    const el=selectedElement(),state=currentState();if(!el||!state)return;
    const profile=profileById(state.profileId),angle=Number(el.rotation||0)*Math.PI/180;
    const widthMm=Number(el.w||0)*profile.width_mm/100,heightMm=Number(el.h||0)*profile.height_mm/100;
    const halfX=(Math.abs(widthMm*Math.cos(angle))+Math.abs(heightMm*Math.sin(angle)))/2/profile.width_mm*100;
    const halfY=(Math.abs(widthMm*Math.sin(angle))+Math.abs(heightMm*Math.cos(angle)))/2/profile.height_mm*100;
    if(mode==='left')el.x=halfX;else if(mode==='hcenter')el.x=50;else if(mode==='right')el.x=100-halfX;
    else if(mode==='top')el.y=halfY;else if(mode==='vcenter')el.y=50;else if(mode==='bottom')el.y=100-halfY;
    el.x=Math.max(0,Math.min(100,el.x));el.y=Math.max(0,Math.min(100,el.y));
    saveEntryStates();syncInspector();renderStage();
  }
  function renderStage(){
    const stage=$('b21-label-stage'), entry=currentEntry(), s=currentState(); if(!stage||!entry||!s)return;
    const p=profileById(s.profileId), cal=getCalibration(p.id);
    stage.style.aspectRatio=p.width_mm+' / '+p.height_mm; stage.innerHTML='';

    if(s.frame!==false){const frame=document.createElement('div');frame.className='b21-label-frame';stage.appendChild(frame);requestAnimationFrame(()=>{const scale=stage.clientWidth/p.width_mm;frame.style.inset=(Number(s.frameInsetMm||1)*scale)+'px';frame.style.borderWidth=Math.max(1,Number(s.frameWidthMm||.35)*scale)+'px';});}
    s.elements.filter((el)=>el.visible!==false).forEach((el)=>{
      const node=buildStageElement(el,entry,s,p,cal);stage.appendChild(node);
      if(el.type==='text'&&el.id===selectedElementId){
        const handle=stage.querySelector(':scope > .b21-v2-resize-handle');
        if(handle){positionTextResizeHandle(node,handle);requestAnimationFrame(()=>{if(handle.isConnected)positionTextResizeHandle(node,handle);});}
      }
    });
  }

  function displayText(el,entry,s){ if(el.type==='code')return ''; if(el.source==='label')return entry.label||entry.code||''; if(el.source==='value')return s.codeValue||entry.code||''; return el.text||''; }
  function buildStageElement(el,entry,s,p,cal){
    const stage=$('b21-label-stage');
    let node, selectionNode, codeVisual=null, codeImage=null;
    if(el.type==='code'){
      node=document.createElement('div');node.className='b21-element b21-code-box';
      codeVisual=document.createElement('div');codeVisual.className='b21-code-content';node.appendChild(codeVisual);
      codeImage=document.createElement('img');codeImage.className='b21-code';codeImage.alt=entry.code||'';
      codeVisual.appendChild(codeImage);
      selectionNode=codeImage;
      codeImage.addEventListener('load',()=>fitCodeContent(codeVisual,codeImage,el,p));
      codeImage.src='/labels/code.svg?kind='+encodeURIComponent(entry.kind||'auto')+'&value='+encodeURIComponent(s.codeValue||entry.code||'');
    } else {
      node=document.createElement('div');node.className=el.type==='line'?'b21-v2-line':'b21-v2-free-text';
      if(el.type==='line')node.style.borderTopWidth=Math.max(1,(Number(el.lineWidthMm||.35)*(stageScale(p))))+'px';
      else {
        selectionNode=document.createElement('span');selectionNode.className='b21-v2-text-content';
        selectionNode.textContent=displayText(el,entry,s);node.appendChild(selectionNode);
        requestAnimationFrame(()=>{selectionNode.style.fontSize=physicalFontPx(p,Number(el.fontSizePt||14))+'px';});
      }
    }
    if(!selectionNode)selectionNode=node;
    node.dataset.elementId=el.id;
    if(el.id===selectedElementId)selectionNode.classList.add('b21-v2-element-selected');
    const ox=(Number(cal.xMm||0)/p.width_mm)*100, oy=(Number(cal.yMm||0)/p.height_mm)*100;
    applyBox(node,Number(el.x||0)+ox,Number(el.y||0)+oy,Number(el.w||10),Number(el.h||10),Number(el.rotation||0));
    if(codeImage)fitCodeContent(codeVisual,codeImage,el,p);
    node.addEventListener('pointerdown',(event)=>startRelativeDrag(event,node,el,p));
    node.addEventListener('click',(event)=>{event.stopPropagation();selectedElementId=el.id;syncInspector();renderStage();});
    if(el.id===selectedElementId&&!codeImage){
      const handle=document.createElement('span');handle.className='b21-v2-resize-handle';
      handle.addEventListener('pointerdown',(event)=>startResize(event,node,el));stage.appendChild(handle);

    }
    return node;
  }
  function positionTextResizeHandle(node,handle){
    const stage=$('b21-label-stage');if(!node||!handle||!stage)return;
    const nodeRect=node.getBoundingClientRect(),stageRect=stage.getBoundingClientRect(),transform=getComputedStyle(node).transform;
    let angle=0;
    if(transform&&transform!=='none'){
      const values=transform.match(/^matrix\(([^)]+)\)$/);
      if(values){const parts=values[1].split(',').map(Number);angle=Math.atan2(parts[1]||0,parts[0]||1);}
    }
    const localX=node.offsetWidth/2,localY=node.offsetHeight/2;
    const centerX=(nodeRect.left+nodeRect.right)/2,centerY=(nodeRect.top+nodeRect.bottom)/2;
    const screenX=centerX+Math.cos(angle)*localX-Math.sin(angle)*localY;
    const screenY=centerY+Math.sin(angle)*localX+Math.cos(angle)*localY;
    handle.style.left=(screenX-stageRect.left-stage.clientLeft)+'px';
    handle.style.top=(screenY-stageRect.top-stage.clientTop)+'px';
  }
  function fitCodeContent(visual,image,el,p){
    const maxWidthMm=Math.max(.01,Number(el.w||10)*p.width_mm/100);
    const maxHeightMm=Math.max(.01,Number(el.h||10)*p.height_mm/100);
    if(resolvedCodeKind(currentEntry(),currentState()?.codeValue)==='code128'){
      visual.style.width='100%';
      visual.style.height='100%';
      image.style.objectFit='fill';
      return;
    }
    const sideMm=Math.min(maxWidthMm,maxHeightMm);
    visual.style.width=(sideMm/maxWidthMm*100)+'%';
    visual.style.height=(sideMm/maxHeightMm*100)+'%';
    image.style.objectFit='contain';
  }
  function stageScale(p){const stage=$('b21-label-stage');return stage?stage.clientWidth/p.width_mm:1;}
  function physicalFontPx(p,pt){return Math.max(7,(pt*25.4/72)*stageScale(p));}
  function applyBox(node,x,y,w,h,rotation){node.style.left=x+'%';node.style.top=y+'%';node.style.width=w+'%';node.style.height=h+'%';node.style.transform='translate(-50%,-50%) rotate('+rotation+'deg)';}

  function startRelativeDrag(event,node,el,p){
    if(event.target.closest&&event.target.closest('.b21-v2-resize-handle'))return;
    const hit=el.type==='code'?event.target.closest&&event.target.closest('.b21-code-content'):el.type==='line'?event.target===node:event.target.closest&&event.target.closest('.b21-v2-text-content');
    if(!hit)return;
    event.preventDefault();event.stopPropagation();selectedElementId=el.id;
    const startX=event.clientX,startY=event.clientY,origX=Number(el.x||0),origY=Number(el.y||0),rect=$('b21-label-stage').getBoundingClientRect(),elementId=String(el.id);node.setPointerCapture(event.pointerId);
    const move=(e)=>{
      /* Other editor controls can reload entryStates while a pointer is held.
         Always update the current persisted element instead of the render-time object. */
      const state=currentState(),target=state&&state.elements.find((row)=>String(row.id)===elementId);
      if(!target)return;
      target.x=Math.max(0,Math.min(100,origX+(e.clientX-startX)/rect.width*100));target.y=Math.max(0,Math.min(100,origY+(e.clientY-startY)/rect.height*100));
      const cal=getCalibration(p.id);applyBox(node,target.x+(cal.xMm/p.width_mm*100),target.y+(cal.yMm/p.height_mm*100),target.w,target.h,target.rotation);saveEntryStates();
    };
    const end=(e)=>{try{node.releasePointerCapture(e.pointerId);}catch(ignore){}node.removeEventListener('pointermove',move);node.removeEventListener('pointerup',end);node.removeEventListener('pointercancel',end);saveEntryStates();syncInspector();renderStage();};
    node.addEventListener('pointermove',move);node.addEventListener('pointerup',end);node.addEventListener('pointercancel',end);
  }
  function startResize(event,node,el){
    event.preventDefault();event.stopPropagation();
    const elementId=String(el.id),startX=event.clientX,startY=event.clientY;
    const stage=$('b21-label-stage'),rect=stage.getBoundingClientRect(),p=currentProfile(),angle=Number(el.rotation||0)*Math.PI/180,handle=event.target;
    const initial=currentState()?.elements.find((row)=>String(row.id)===elementId);
    if(!initial||!rect.width||!rect.height)return;
    const origW=Number(initial.w||10),origH=Number(initial.h||10);
    handle.setPointerCapture(event.pointerId);
    const move=(e)=>{
      const state=currentState(),target=state&&state.elements.find((row)=>String(row.id)===elementId);
      if(!target)return;
      const dx=(e.clientX-startX)/rect.width*p.width_mm,dy=(e.clientY-startY)/rect.height*p.height_mm;
      const localX=dx*Math.cos(angle)+dy*Math.sin(angle),localY=-dx*Math.sin(angle)+dy*Math.cos(angle);
      target.w=Math.max(2,Math.min(100,origW+2*localX/p.width_mm*100));
      target.h=Math.max(1,Math.min(100,origH+2*localY/p.height_mm*100));
      node.style.width=target.w+'%';node.style.height=target.h+'%';
      positionTextResizeHandle(node,handle);
      ['w','h'].forEach((key)=>{const input=$('b21-v2-'+key),out=$('b21-v2-'+key+'-value');if(input){input.value=target[key];if(out)out.textContent=input.value;}});
      saveEntryStates();
    };
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
      if(el.type==='code'){const value=s.codeValue||entry.code||'',url='/labels/code.svg?kind='+encodeURIComponent(entry.kind||'auto')+'&value='+encodeURIComponent(value),img=await loadImage(url);ctx.save();ctx.translate(cx,cy);ctx.rotate(rot*Math.PI/180);if(resolvedCodeKind(entry,value)==='code128')ctx.drawImage(img,-w/2,-h/2,w,h);else{const side=Math.min(w,h);drawContain(ctx,img,-side/2,-side/2,side,side);}ctx.restore();}
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
  function pollJob(id){
    clearInterval(jobPoll);
    const status=$('b21-v2-job-state'),button=$('label-niim-print');
    jobPoll=setInterval(async()=>{
      try{
        const job=await fetchJson('/labels/b21/jobs/'+encodeURIComponent(id));
        if(status){status.className='small text-secondary b21-v2-job-state';status.textContent=job.status+' · '+job.completed_pages+'/'+job.page_count+' · '+job.printed_labels+' labels';}
        if(job.status==='completed'||job.status==='failed'||job.status==='unknown'){
          clearInterval(jobPoll);
          const tone=job.status==='completed'?'text-success':job.status==='unknown'?'text-warning':'text-danger';
          if(status)status.className='small '+tone+' b21-v2-job-state';
          if(job.status==='unknown'&&status)status.textContent='Print result unknown · check printer output before retrying'+(job.error?' · '+job.error:'');
          else if(job.error&&status)status.textContent='Failed · '+job.error;
          if(button)button.disabled=false;

        }
      }catch(e){clearInterval(jobPoll);if(button)button.disabled=false;}
    },600);
  }
  async function printCalibrationTest(){const entry=currentEntry(),s=currentState(),p=currentProfile(),cal=getCalibration(p.id);if(!entry)return;const status=$('b21-v2-job-state');try{if(status)status.textContent='Preparing calibration…';const image=await renderSnapshot(entry,clone(s),clone(p),clone(cal),true);const job=await fetchJson('/labels/b21/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pages:[{image_base64:image,width_mm:p.width_mm,height_mm:p.height_mm,quantity:1,density:p.density,label_type:p.label_type,dpi:p.dpi,threshold:128}]})});pollJob(job.id);}catch(e){if(status){status.className='small text-danger';status.textContent=e.message;}}}

  function bindExistingControls(){
    const entrySelect=$('b21-entry-select');if(entrySelect)entrySelect.addEventListener('change',()=>{selectedElementId='code';syncEntryControls();});
    const profileSelect=$('b21-profile-select');if(profileSelect)profileSelect.addEventListener('change',function(){const s=currentState();if(!s)return;s.profileId=this.value;saveEntryStates();localStorage.setItem(PROFILE_KEY,this.value);syncCalibration();renderStage();});
    const queue=$('label-queue');
    if(queue){
      new MutationObserver(()=>setTimeout(()=>{syncEntryControls();},0)).observe(queue,{childList:true,subtree:true});
      queue.addEventListener('change',function(event){
        if(event.target&&event.target.matches('.entry-kind'))syncEntryControls();
      });
    }
  }

  window.__b2mB21LabelEditor = {
    selectQueueEntry: function (entryId) {
      const queue=readQueue(),index=queue.findIndex((entry)=>String(entry&&entry._id)===String(entryId));
      const select=$('b21-entry-select');
      if(index<0||!select)return false;
      select.value=String(index);
      select.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    },
    moveLayer: function (id, direction) {
      const state = currentState();
      if (!state || !Array.isArray(state.elements)) return false;
      const step = Number(direction);
      const index = state.elements.findIndex((row) => String(row.id) === String(id));
      const next = index + step;
      if (!Number.isInteger(step) || Math.abs(step) !== 1 || index < 0 || next < 0 || next >= state.elements.length) return false;
      [state.elements[index], state.elements[next]] = [state.elements[next], state.elements[index]];
      selectedElementId = String(id);
      persistAndRender();
      return true;
    },
    setVisibility: function (id, visible) {
      const state = currentState();
      const element = state && Array.isArray(state.elements) && state.elements.find((row) => String(row.id) === String(id));
      if (!element) return false;
      element.visible = !!visible;
      selectedElementId = String(id);
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
    syncEntryControls();
  }

  init();
})();
