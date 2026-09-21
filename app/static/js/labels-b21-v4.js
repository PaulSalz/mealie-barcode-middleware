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

  function applyPreset(name){
    const c=context();if(!c)return;
    const code=c.state.elements.find((e)=>e.id==='code');
    const label=c.state.elements.find((e)=>e.id==='label');
    const value=c.state.elements.find((e)=>e.id==='value');
    const presets={
      stacked:{code:{visible:true,x:50,y:40,w:86,h:55,rotation:0},label:{visible:true,x:50,y:82,w:88,h:20,rotation:0,fontSizePt:14},value:{visible:false}},
      left:{code:{visible:true,x:28,y:50,w:50,h:80,rotation:0},label:{visible:true,x:75,y:50,w:42,h:42,rotation:0,fontSizePt:14},value:{visible:false}},
      right:{code:{visible:true,x:72,y:50,w:50,h:80,rotation:0},label:{visible:true,x:25,y:50,w:42,h:42,rotation:0,fontSizePt:14},value:{visible:false}},
      code:{code:{visible:true,x:50,y:50,w:92,h:86,rotation:0},label:{visible:false},value:{visible:false}},
      text:{code:{visible:false},label:{visible:true,x:50,y:50,w:90,h:70,rotation:0,fontSizePt:20},value:{visible:false}}
    };
    const p=presets[name];if(!p)return;
    if(code)Object.assign(code,p.code);if(label)Object.assign(label,p.label);if(value)Object.assign(value,p.value);
    writeJson(ENTRY_KEY,c.states);refreshDesigner();
    document.querySelectorAll('#b21-v4-presets .btn').forEach((b)=>b.classList.toggle('active',b.dataset.preset===name));
  }

  function installPresets(){
    const inspector=$('b21-v2-inspector');if(!inspector||$('b21-v4-presets'))return false;
    const section=document.createElement('div');section.id='b21-v4-presets';section.className='b21-section';
    section.innerHTML='<div class="fw-semibold mb-2">Layout presets</div><div class="btn-group w-100 flex-wrap" role="group">'+
      [['stacked','Stacked'],['left','Code left'],['right','Code right'],['code','Code only'],['text','Text only']].map((p)=>'<button class="btn btn-outline-secondary" type="button" data-preset="'+p[0]+'">'+p[1]+'</button>').join('')+'</div>';
    inspector.insertAdjacentElement('afterbegin',section);
    section.querySelectorAll('[data-preset]').forEach((button)=>button.addEventListener('click',()=>applyPreset(button.dataset.preset)));
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
