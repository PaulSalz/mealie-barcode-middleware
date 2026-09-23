/* B21 editor layers, snap rotation and roll calibration. */
(function(){
  'use strict';
  if(window.location.pathname!=='/labels'||window.__b2mLabelsV24Loaded)return;
  window.__b2mLabelsV24Loaded=true;

  const QUEUE_KEY='b2m-label-generator-v2';
  const ENTRY_KEY='b2m-b21-entry-settings-v3';
  const $=id=>document.getElementById(id);
  let handleRaf=0;

  function readJson(key,fallback){try{return JSON.parse(localStorage.getItem(key)||'')||fallback;}catch(e){return fallback;}}
  function writeJson(key,value){try{localStorage.setItem(key,JSON.stringify(value));}catch(e){}}
  function esc(value){return String(value==null?'':value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');}
  function context(){
    const data=readJson(QUEUE_KEY,{}),queue=Array.isArray(data.queue)?data.queue:[];
    const index=Number(($('b21-entry-select')||{}).value||0),entry=queue[index]||queue[0];
    if(!entry)return null;
    const states=readJson(ENTRY_KEY,{}),key=String(entry._id!=null?entry._id:(entry.code||('entry-'+index)));
    return states[key]?{states,key,state:states[key]}:null;
  }
  function refreshEditor(){const select=$('b21-v2-element-select');if(select)select.dispatchEvent(new Event('change',{bubbles:true}));}
  function selectedId(){return String(($('b21-v2-element-select')||{}).value||'');}

  function removeLegacyAppearance(){const appearance=$('b21-v4-label-appearance');if(appearance)appearance.remove();}

  function installRotationSnap(){
    const input=$('b21-v2-rotation');if(!input)return;
    input.min='0';input.max='315';input.step='45';
    let list=$('b21-v24-rotation-ticks');
    if(!list){
      list=document.createElement('datalist');list.id='b21-v24-rotation-ticks';
      list.innerHTML=[0,45,90,135,180,225,270,315].map(value=>'<option value="'+value+'"></option>').join('');
      input.insertAdjacentElement('afterend',list);
    }
    input.setAttribute('list',list.id);
    const wrap=input.closest('.b21-v2-range-wrap');
    if(wrap&&!wrap.querySelector('.b21-v24-rotation-hint')){
      const hint=document.createElement('div');hint.className='form-hint b21-v24-rotation-hint';hint.textContent='Snaps every 45°.';wrap.appendChild(hint);
    }
  }

  function installRollCalibration(){
    const editor=$('b21-profile-editor'),x=$('b21-v2-cal-x'),y=$('b21-v2-cal-y');
    if(!editor||!x||!y||$('b21-v24-roll-calibration'))return;
    const oldSection=x.closest('.b21-section');
    const wrap=document.createElement('div');wrap.id='b21-v24-roll-calibration';wrap.className='col-12 b21-v24-roll-calibration';
    wrap.innerHTML='<div class="fw-semibold mb-1">Roll calibration</div><div class="form-hint mb-2">Physical printer offsets for this roll profile.</div><div class="row g-2" id="b21-v24-cal-row"></div>';
    const row=wrap.querySelector('#b21-v24-cal-row');
    [x,y].forEach(input=>{const col=input.closest('.col-6')||input.parentElement;if(col)row.appendChild(col);});
    const buttons=$('b21-v2-reset-cal')?.closest('.d-flex')||$('b21-v2-test-cal')?.closest('.d-flex');
    if(buttons){buttons.classList.add('col-12','mt-1');row.appendChild(buttons);}
    (editor.querySelector('.row')||editor).appendChild(wrap);
    if(oldSection){
      const useful=Array.from(oldSection.querySelectorAll('input,select,button')).some(el=>!el.classList.contains('d-none')&&!el.closest('.d-none'));
      if(!useful)oldSection.remove();
    }
    removeLegacyAppearance();
  }

  function persist(c){c.states[c.key]=c.state;writeJson(ENTRY_KEY,c.states);}
  function layerName(element){return element.name||(element.type==='code'?'Code':element.type==='line'?'Line':'Text');}
  function selectLayer(id){const select=$('b21-v2-element-select');if(!select)return;select.value=String(id);refreshEditor();renderLayers();}
  function setVisible(id,visible){
    const c=context();if(!c||!Array.isArray(c.state.elements))return;
    const element=c.state.elements.find(row=>String(row.id)===String(id));if(!element)return;
    element.visible=!!visible;persist(c);refreshEditor();renderLayers();
  }
  function moveLayer(id,direction){
    const c=context();if(!c||!Array.isArray(c.state.elements))return;
    const index=c.state.elements.findIndex(row=>String(row.id)===String(id)),next=index+direction;
    if(index<0||next<0||next>=c.state.elements.length)return;
    [c.state.elements[index],c.state.elements[next]]=[c.state.elements[next],c.state.elements[index]];
    persist(c);refreshEditor();renderLayers();
  }
  function renderLayers(){
    const root=$('b21-v24-layer-list'),c=context();if(!root||!c||!Array.isArray(c.state.elements))return;
    const selected=selectedId();
    root.innerHTML=c.state.elements.map((element,index)=>({element,index})).reverse().map(({element,index})=>{
      const id=String(element.id),active=id===selected;
      return '<div class="b21-v24-layer'+(active?' active':'')+'">'+
        '<button type="button" class="b21-v24-layer-select" data-layer-select="'+esc(id)+'"><i class="ti ti-'+(element.type==='code'?'qrcode':element.type==='line'?'minus':'letter-t')+'"></i><span><strong>'+esc(layerName(element))+'</strong><small>'+esc(element.type||'element')+'</small></span></button>'+
        '<label class="form-check form-switch b21-v24-layer-visible" title="Visibility"><input class="form-check-input" type="checkbox" data-layer-visible="'+esc(id)+'" '+(element.visible!==false?'checked':'')+'></label>'+
        '<div class="btn-group btn-group-sm"><button class="btn btn-outline-secondary" type="button" data-layer-forward="'+esc(id)+'" title="Bring forward" '+(index<c.state.elements.length-1?'':'disabled')+'><i class="ti ti-arrow-up"></i></button><button class="btn btn-outline-secondary" type="button" data-layer-back="'+esc(id)+'" title="Send backward" '+(index>0?'':'disabled')+'><i class="ti ti-arrow-down"></i></button></div></div>';
    }).join('');
    root.querySelectorAll('[data-layer-select]').forEach(button=>button.addEventListener('click',()=>selectLayer(button.dataset.layerSelect)));
    root.querySelectorAll('[data-layer-visible]').forEach(input=>input.addEventListener('change',()=>setVisible(input.dataset.layerVisible,input.checked)));
    root.querySelectorAll('[data-layer-forward]').forEach(button=>button.addEventListener('click',()=>moveLayer(button.dataset.layerForward,1)));
    root.querySelectorAll('[data-layer-back]').forEach(button=>button.addEventListener('click',()=>moveLayer(button.dataset.layerBack,-1)));
  }
  function installLayerInspector(){
    const inspector=$('b21-v2-inspector'),select=$('b21-v2-element-select');if(!inspector||!select)return;
    const header=$('b21-v2-reset-all')?.parentElement||Array.from(inspector.children).find(node=>node.querySelector?.('#b21-v2-reset-all'));
    if(header){const title=header.querySelector('.fw-semibold'),subtitle=header.querySelector('.text-secondary.small');if(title)title.textContent='Layers';if(subtitle)subtitle.textContent='Visibility and stacking order. Select a layer to edit it below.';}
    select.classList.add('d-none');
    if(!$('b21-v24-layer-list')){
      const list=document.createElement('div');list.id='b21-v24-layer-list';list.className='b21-v24-layer-list mb-3';select.insertAdjacentElement('beforebegin',list);
      select.addEventListener('change',()=>requestAnimationFrame(renderLayers));
      const stage=$('b21-label-stage');if(stage)new MutationObserver(()=>requestAnimationFrame(renderLayers)).observe(stage,{childList:true,subtree:true});
    }
    renderLayers();
  }

  function syncFloatingHandle(){
    cancelAnimationFrame(handleRaf);handleRaf=requestAnimationFrame(()=>{
      const stage=$('b21-label-stage'),handle=$('b21-v2-code-resize-handle');if(!stage||!handle)return;
      const node=stage.querySelector('img.b21-v2-element-selected,img.b21-code.b21-v2-element-selected,img.b21-v22-selected');if(!node)return;
      const sr=stage.getBoundingClientRect(),r=node.getBoundingClientRect();handle.style.left=(r.right-sr.left)+'px';handle.style.top=(r.bottom-sr.top)+'px';
    });
  }
  function installHandleTracking(){
    const stage=$('b21-label-stage');if(!stage||stage.dataset.b2mV24Handle==='1')return;
    stage.dataset.b2mV24Handle='1';
    ['pointerdown','pointermove','pointerup'].forEach(name=>stage.addEventListener(name,syncFloatingHandle,true));
    new MutationObserver(syncFloatingHandle).observe(stage,{subtree:true,attributes:true,attributeFilter:['style','class']});
  }

  function install(){
    if(!$('b21-v2-inspector')||!$('b21-label-stage'))return false;
    removeLegacyAppearance();installRotationSnap();installRollCalibration();installLayerInspector();installHandleTracking();
    return true;
  }
  function start(){
    if(install())return;
    const observer=new MutationObserver(function(){if(install())observer.disconnect();});
    observer.observe(document.body,{childList:true,subtree:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
