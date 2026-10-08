(function () {
  'use strict';
  if (window.location.pathname !== '/labels') return;

  const QUEUE_KEY='b2m-label-generator-v2';
  const ENTRY_KEY='b2m-b21-entry-settings-v3';
  const $=(id)=>document.getElementById(id);

  function readJson(key,fallback){try{return JSON.parse(localStorage.getItem(key)||'')||fallback;}catch(e){return fallback;}}
  function writeJson(key,value){try{localStorage.setItem(key,JSON.stringify(value));}catch(e){}}
  function queue(){const data=readJson(QUEUE_KEY,{});return Array.isArray(data.queue)?data.queue:[];}
  function currentIndex(){return Number(($('b21-entry-select')||{}).value||0);}
  function entryKey(entry,index){return String(entry&&entry._id!=null?entry._id:((entry&&entry.code)||('entry-'+index)));}
  function context(){const q=queue(),i=currentIndex(),entry=q[i]||q[0];if(!entry)return null;const states=readJson(ENTRY_KEY,{}),key=entryKey(entry,i),state=states[key];return state?{q,i,entry,states,key,state}:null;}
  function refreshDesigner(){const select=$('b21-entry-select');if(select)select.dispatchEvent(new Event('change',{bubbles:true}));}


  const DESIGN_CLIPBOARD_KEY='b2m-b21-design-clipboard-v1';
  const TEXT_STYLE_KEY='b2m-b21-text-style-v22';

  function clone(value){return JSON.parse(JSON.stringify(value));}
  function dimensions(){
    const ratio=String(($('b21-label-stage')||{}).style?.aspectRatio||'').match(/([\d.]+)\s*\/\s*([\d.]+)/);
    const widthMm=ratio?Number(ratio[1]):50,heightMm=ratio?Number(ratio[2]):30;
    return {widthMm:widthMm>0?widthMm:50,heightMm:heightMm>0?heightMm:30};
  }
  function fontSizeFor(text,box,size,element){
    const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
    const maxPt=Math.max(5,Number(size)||14);
    const widthPx=Math.max(1,dimensions().widthMm*box.w/100*96/25.4);
    const heightPt=Math.max(1,dimensions().heightMm*box.h/100*72/25.4);
    const words=String(text||'').trim().split(/\s+/).filter(Boolean);
    if(!ctx)return Math.max(5,Math.min(maxPt,Math.floor(heightPt/1.2)));
    for(let pt=Math.floor(maxPt);pt>=5;pt--){
      ctx.font=(element&&element.mono?'500 ':'600 ')+(pt*96/72)+'px '+(element&&element.mono?'monospace':'sans-serif');
      const lines=[];let line='';
      words.forEach((word)=>{
        const candidate=line?line+' '+word:word;
        if(!line||ctx.measureText(candidate).width<=widthPx)line=candidate;
        else{lines.push(line);line=word;}
      });
      if(line)lines.push(line);
      if(lines.length<=4&&lines.length*pt*1.08<=heightPt*.9)return pt;
    }
    return 5;
  }
  function elementText(element,c){
    if(element.source==='label')return c.entry.label||c.entry.code||'';
    if(element.source==='value')return c.state.codeValue||c.entry.code||'';
    return element.text||'';
  }
  function presetElements(name,c){
    const size=dimensions(),narrow=size.widthMm<38,portrait=size.heightMm>size.widthMm*1.08;
    const stack=name==='stacked'||((name==='left'||name==='right')&&(narrow||portrait));
    const presets={
      stacked:{
        code:{visible:true,x:50,y:34,w:92,h:50,rotation:0},
        label:{visible:true,x:50,y:81,w:92,h:34,rotation:0}
      },
      left:{
        code:{visible:true,x:27,y:50,w:48,h:80,rotation:0},
        label:{visible:true,x:76,y:50,w:44,h:64,rotation:0}
      },
      right:{
        code:{visible:true,x:73,y:50,w:48,h:80,rotation:0},
        label:{visible:true,x:24,y:50,w:44,h:64,rotation:0}
      },
      code:{
        code:{visible:true,x:50,y:50,w:92,h:86,rotation:0},
        label:{visible:false}
      },
      text:{
        code:{visible:false},
        label:{visible:true,x:50,y:50,w:92,h:84,rotation:0}
      }
    };
    const selected=presets[name];if(!selected)return null;
    const layout=clone(selected);
    if(stack&&(name==='left'||name==='right')){
      layout.code={visible:true,x:50,y:34,w:92,h:50,rotation:0};
      layout.label={visible:true,x:50,y:81,w:92,h:34,rotation:0};
    }
    if(layout.label.visible){
      const label=c.state.elements.find((element)=>element.id==='label');
      if(label)layout.label.fontSizePt=fontSizeFor(elementText(label,c),layout.label,name==='text'?20:14,label);
    }
    if(name==='code'||name==='text')layout.value={visible:false};
    else layout.value={visible:false};
    return layout;
  }
  function setDesignStatus(message){
    const status=$('b21-v4-design-status');if(status)status.textContent=message||'';
  }
  function clipboard(){
    const value=readJson(DESIGN_CLIPBOARD_KEY,null);
    return value&&Array.isArray(value.elements)?value:null;
  }
  function syncDesignControls(){
    const paste=$('b21-v4-paste-design');if(paste)paste.disabled=!clipboard();
    const applyAll=$('b21-v4-apply-all-design');if(applyAll)applyAll.disabled=!queue().length;
  }
  function captureDesign(c){
    const styles=readJson(TEXT_STYLE_KEY,{});
    return {
      version:1,
      sourceKey:c.key,
      sourceLabel:String(c.entry.label||c.entry.code||''),
      elements:clone(c.state.elements),
      frame:c.state.frame!==false,
      frameInsetMm:Number(c.state.frameInsetMm??1),
      frameWidthMm:Number(c.state.frameWidthMm??.35),
      threshold:Number(c.state.threshold||128),
      textStyles:clone(styles[c.key]||{})
    };
  }
  function applyDesignToState(state,key,design,styles){
    state.elements=clone(design.elements);
    state.frame=design.frame!==false;
    state.frameInsetMm=Number(design.frameInsetMm??1);
    state.frameWidthMm=Number(design.frameWidthMm??.35);
    state.threshold=Number(design.threshold||128);
    if(Object.keys(design.textStyles||{}).length)styles[key]=clone(design.textStyles);
    else delete styles[key];
  }
  function copyDesign(){
    const c=context();if(!c||!Array.isArray(c.state.elements))return;
    writeJson(DESIGN_CLIPBOARD_KEY,captureDesign(c));
    syncDesignControls();
    setDesignStatus('Design copied. Select another code and paste it.');
  }
  function pasteDesign(){
    const c=context(),design=clipboard();if(!c||!design)return;
    applyDesignToState(c.state,c.key,design,readJson(TEXT_STYLE_KEY,{}));
    writeJson(ENTRY_KEY,c.states);
    const styles=readJson(TEXT_STYLE_KEY,{});
    if(Object.keys(design.textStyles||{}).length)styles[c.key]=clone(design.textStyles);
    else delete styles[c.key];
    writeJson(TEXT_STYLE_KEY,styles);
    refreshDesigner();
    setDesignStatus('Design applied to this code.');
  }
  function applyDesignToAll(){
    const c=context();if(!c||!Array.isArray(c.state.elements))return;
    const design=captureDesign(c),items=queue();
    const editor=window.__b2mB21LabelEditor;
    if(editor&&typeof editor.prepareQueue==='function')editor.prepareQueue();
    const states=readJson(ENTRY_KEY,{});
    const styles=readJson(TEXT_STYLE_KEY,{});
    let applied=0;
    items.forEach((entry,index)=>{
      const key=entryKey(entry,index),state=states[key];
      if(!state)return;
      applyDesignToState(state,key,design,styles);
      applied++;
    });
    writeJson(ENTRY_KEY,states);
    writeJson(TEXT_STYLE_KEY,styles);
    refreshDesigner();
    setDesignStatus('Current design applied to '+applied+' codes.');
  }


  if(window.__b2mB21LabelEditor){
    Object.assign(window.__b2mB21LabelEditor,{applyPreset,copyDesign,pasteDesign,applyDesignToAll,syncDesignControls});
  }

  function applyPreset(name){
    const c=context();if(!c)return;
    const code=c.state.elements.find((e)=>e.id==='code');
    const label=c.state.elements.find((e)=>e.id==='label');
    const value=c.state.elements.find((e)=>e.id==='value');
    const preset=presetElements(name,c);if(!preset)return;
    if(code&&preset.code)Object.assign(code,preset.code);
    if(label&&preset.label)Object.assign(label,preset.label);
    if(value&&preset.value)Object.assign(value,preset.value);
    writeJson(ENTRY_KEY,c.states);refreshDesigner();
    document.querySelectorAll('#b21-v4-presets .btn[data-preset]').forEach((b)=>b.classList.toggle('active',b.dataset.preset===name));
  }

  function installPresets(){
    const inspector=$('b21-v2-inspector');if(!inspector||$('b21-v4-presets'))return false;
    const section=document.createElement('div');section.id='b21-v4-presets';section.className='b21-section';
    section.innerHTML='<div class="fw-semibold mb-2">Layout presets</div><div class="btn-group w-100 flex-wrap" role="group">'+
      [['stacked','Stacked'],['left','Code left'],['right','Code right'],['code','Code only'],['text','Text only']].map((p)=>'<button class="btn btn-outline-secondary" type="button" data-preset="'+p[0]+'">'+p[1]+'</button>').join('')+'</div>';
    section.insertAdjacentHTML('beforeend','<div class="form-hint mt-2">Text size adapts to the selected roll and label. Narrow or portrait rolls stack side layouts to keep the code readable.</div><div class="btn-group w-100 mt-3" role="group"><button class="btn btn-outline-primary" type="button" id="b21-v4-copy-design">Copy design</button><button class="btn btn-outline-primary" type="button" id="b21-v4-paste-design" disabled>Paste design</button><button class="btn btn-outline-primary" type="button" id="b21-v4-apply-all-design">Apply to all</button></div><div class="small text-secondary mt-2" id="b21-v4-design-status" role="status" aria-live="polite"></div>');
    inspector.insertAdjacentElement('afterbegin',section);
    section.querySelectorAll('[data-preset]').forEach((button)=>button.addEventListener('click',()=>applyPreset(button.dataset.preset)));
    $('b21-v4-copy-design').addEventListener('click',copyDesign);
    $('b21-v4-paste-design').addEventListener('click',pasteDesign);
    $('b21-v4-apply-all-design').addEventListener('click',applyDesignToAll);
    const selector=$('b21-entry-select');if(selector)selector.addEventListener('change',syncDesignControls);
    syncDesignControls();
    return true;
  }

  function installAppearanceSection(){
    const inspector=$('b21-v2-inspector');if(!inspector||$('b21-v4-label-appearance'))return false;
    const calibration=Array.from(inspector.querySelectorAll('.b21-section')).find((s)=>s.textContent.includes('Print offset X'));
    if(!calibration)return false;
    const rows=calibration.querySelectorAll(':scope > .row');
    const appearanceRow=Array.from(rows).find((r)=>r.querySelector('#b21-v2-frame')||r.querySelector('#b21-v2-threshold'));
    if(!appearanceRow)return false;
    const section=document.createElement('div');section.id='b21-v4-label-appearance';
    section.innerHTML='<div class="fw-semibold mb-2">Label appearance</div>';
    section.appendChild(appearanceRow);
    calibration.insertAdjacentElement('beforebegin',section);
    const title=calibration.querySelector('.fw-semibold');if(title)title.textContent='Calibration';

    const input=$('b21-v2-threshold');
    if(input){
      const preview=document.createElement('div');preview.className='b21-v4-threshold-preview';preview.innerHTML='<div class="b21-v4-threshold-source"><span class="b21-v4-threshold-marker"></span></div><div class="b21-v4-threshold-result"></div><div class="b21-v4-threshold-caption"><span>source grayscale</span><span>binarized preview</span></div>';
      input.parentElement.appendChild(preview);
      const marker=preview.querySelector('.b21-v4-threshold-marker'),result=preview.querySelector('.b21-v4-threshold-result');
      function update(){
        const value=Math.max(1,Math.min(255,Number(input.value||128))),pct=value/255*100;
        marker.style.left=pct+'%';
        result.style.background='linear-gradient(90deg,#000 0 '+pct+'%,#fff '+pct+'% 100%)';
        const stage=$('b21-label-stage');
        if(stage){
          const brightness=Math.max(.5,Math.min(8,127.5/value));
          stage.querySelectorAll('.b21-element,.b21-v2-free-text,.b21-v2-line,.b21-label-frame').forEach((el)=>{el.style.filter='grayscale(1) brightness('+brightness.toFixed(3)+') contrast(1000%)';});
        }
      }
      input.addEventListener('input',()=>requestAnimationFrame(update));
      const stage=$('b21-label-stage');if(stage)new MutationObserver(()=>requestAnimationFrame(update)).observe(stage,{childList:true,subtree:true});
      update();
    }
    return true;
  }

  async function printerConnected(){
    try{const r=await fetch('/labels/b21/status',{headers:{Accept:'application/json'},cache:'no-store'});if(!r.ok)return false;return !!(await r.json()).connected;}catch(e){return false;}
  }

  function guardCalibrationTest(){
    const button=$('b21-v2-test-cal');if(!button||button.dataset.v4Guard==='1')return;
    button.dataset.v4Guard='1';let bypass=false;
    button.addEventListener('click',async function(event){
      if(bypass){bypass=false;return;}
      event.preventDefault();event.stopImmediatePropagation();
      if(!(await printerConnected())){const state=$('b21-v2-job-state');if(state){state.textContent='';state.className='small text-secondary b21-v2-job-state';}return;}
      bypass=true;button.click();
    },true);
  }

  function installOutputStatus(){
    const choice=document.querySelector('#b21-output-grid input[value="b21"]')?.closest('.b2m-choice-card');
    if(choice&&!$('b21-v4-output-status')){
      const span=choice.querySelector('span');const status=document.createElement('small');status.id='b21-v4-output-status';status.textContent='Not connected';span?.appendChild(status);
    }
    async function sync(){
      try{
        const response=await fetch('/labels/b21/status',{headers:{Accept:'application/json'},cache:'no-store'});const data=await response.json();const connected=!!data.connected;
        const title=$('b21-status-title'),detail=$('b21-status-detail'),out=$('b21-v4-output-status');
        if(title){title.classList.remove('text-success','text-danger');title.classList.add(connected?'text-success':'text-danger');}
        if(detail){detail.classList.toggle('text-success',connected);detail.classList.toggle('text-danger',!connected&&!data.error);}
        if(out){out.textContent=connected?'Connected':'Not connected';out.className=connected?'text-success':'text-danger';}
      }catch(e){}
    }
    sync();setInterval(sync,2500);
    const connect=$('b21-connect-button');if(connect)connect.addEventListener('click',()=>setTimeout(sync,500));
  }

  function wait(){
    if(!$('b21-v2-inspector')||!$('b21-label-stage')){setTimeout(wait,120);return;}
    installPresets();installAppearanceSection();guardCalibrationTest();installOutputStatus();
  }
  wait();
})();
