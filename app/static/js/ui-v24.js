/* v2026.09.22.4 — async item controls and appearance polish. */
(function(){
  'use strict';
  if(window.__b2mUiV24Loaded)return;window.__b2mUiV24Loaded=true;
  const $=id=>document.getElementById(id);
  const COLORS=['blue','azure','indigo','purple','pink','red','orange','yellow','lime','green','teal','cyan'];
  const ITEMS_STATE_KEY='b2m-items-list-v2';

  async function json(url,options){const response=await fetch(url,Object.assign({headers:{Accept:'application/json'}},options||{}));const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data.error||data.detail||('HTTP '+response.status));return data;}

  function rainbowClass(value){return value==='smooth'?'b2m-rainbow-buttons-smooth':'b2m-rainbow-buttons-'+value;}
  function applyRainbow(theme,preference){
    const root=document.documentElement;
    ['b2m-rainbow-buttons-smooth',...COLORS.map(color=>'b2m-rainbow-buttons-'+color)].forEach(cls=>root.classList.remove(cls));
    const active=theme&&theme.color==='rainbow'&&theme.epaper!=='true';
    root.classList.toggle('b2m-rainbow-active',active);
    root.classList.toggle('b2m-rainbow-disabled',!active);
    if(active)root.classList.add(rainbowClass(preference||'smooth'));
  }

  async function bootRainbow(){
    try{
      const result=await Promise.all([json('/api/theme',{cache:'no-store'}),json('/api/appearance-v24',{cache:'no-store'})]);
      applyRainbow(result[0],result[1].rainbow_buttons||'smooth');
      installRainbowControl(result[0],result[1].rainbow_buttons||'smooth');
    }catch(e){}
  }

  function currentProfileTheme(fallback){
    if(location.pathname!=='/profile/appearance')return fallback;
    const color=document.querySelector('input[name="theme_color"]:checked')?.value||fallback.color;
    const epaper=document.querySelector('input[name="theme_epaper"]')?.checked?'true':'false';
    return Object.assign({},fallback,{color,epaper});
  }

  function installRainbowControl(theme,value){
    if(location.pathname!=='/profile/appearance'||$('b2m-v24-rainbow-buttons'))return;
    const accent=document.querySelector('input[name="theme_color"]')?.closest('.mb-4');if(!accent)return;
    const wrap=document.createElement('div');wrap.id='b2m-v24-rainbow-buttons';wrap.className='mt-3';
    wrap.innerHTML='<label class="form-label">Buttons when Accent is Rainbow</label><select class="form-select" id="b2m-v24-rainbow-buttons-select"><option value="smooth">Smooth rainbow</option>'+COLORS.map(color=>'<option value="'+color+'">Fixed '+color[0].toUpperCase()+color.slice(1)+'</option>').join('')+'</select><div class="form-hint">The logo stays rainbow. E-paper mode disables rainbow animation completely.</div>';
    accent.appendChild(wrap);
    const select=$('b2m-v24-rainbow-buttons-select');select.value=value;
    function syncControl(){
      const current=currentProfileTheme(theme),disabled=current.epaper==='true';
      select.disabled=disabled;wrap.classList.toggle('opacity-50',disabled);applyRainbow(current,select.value);
    }
    select.addEventListener('change',async function(){
      syncControl();
      try{await json('/api/appearance-v24',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({rainbow_buttons:this.value})});}catch(e){}
    });
    document.querySelectorAll('input[name="theme_color"],input[name="theme_epaper"]').forEach(input=>input.addEventListener('change',syncControl));
    syncControl();
  }

  function radiusClass(value){return 'b2m-radius-'+String(value).replace('.','_');}
  function makeRadiusChoices(select){
    const group=document.createElement('div');group.className='form-selectgroup b2m-radius-preview-group';
    Array.from(select.options).forEach(option=>{
      const label=document.createElement('label');label.className='form-selectgroup-item';
      label.innerHTML='<input type="radio" name="'+select.name+'" value="'+option.value+'" class="form-selectgroup-input" '+(option.selected?'checked':'')+'><span class="form-selectgroup-label b2m-radius-preview '+radiusClass(option.value)+'">'+option.textContent+'</span>';
      group.appendChild(label);
    });
    select.replaceWith(group);
  }
  function installRadiusPreviews(){
    if(location.pathname==='/profile/appearance'){
      const select=document.querySelector('select[name="theme_radius"]');if(select)makeRadiusChoices(select);
    }
    if(location.pathname==='/settings'&&new URLSearchParams(location.search).get('tab')==='appearance'){
      document.querySelectorAll('input[name="theme_radius"]').forEach(input=>{const span=input.nextElementSibling;if(span)span.classList.add('b2m-radius-preview',radiusClass(input.value));});
    }
  }

  function installDefaultsHint(){
    if(location.pathname!=='/settings'||new URLSearchParams(location.search).get('tab')!=='appearance'||$('b2m-v24-default-hint'))return;
    const form=document.querySelector('form[action="/settings/theme"]'),body=form?.querySelector('.card-body');if(!body)return;
    const hint=document.createElement('div');hint.id='b2m-v24-default-hint';hint.className='alert alert-info';
    hint.innerHTML='<strong>Default appearance.</strong> These values are the defaults for accounts without personal overrides. <a class="alert-link" href="/profile/appearance">Open Personal appearance</a> to configure your own account.';
    const subtitle=body.querySelector('.card-subtitle');(subtitle||body.querySelector('h2'))?.insertAdjacentElement('afterend',hint);
  }

  function syncClientSort(form){
    const table=$('items-table');if(!table)return;
    const map={name:'sort-name',updated:'sort-updated',last_scan:'sort-last-scan',scans:'sort-scans',barcodes:'sort-mappings',category:'sort-category'};
    const sort=form.querySelector('[name="sort"]')?.value||'name',order=form.querySelector('[name="order"]')?.value||'asc';
    const button=table.querySelector('.table-sort[data-sort="'+map[sort]+'"]');if(!button)return;
    let guard=0;
    while(guard++<3&&(!button.classList.contains('active')||!button.classList.contains(order==='desc'?'desc':'asc')))button.click();
  }

  function persistItemFilters(form){
    try{
      const state=JSON.parse(localStorage.getItem(ITEMS_STATE_KEY)||'{}')||{},data=new FormData(form);
      state.server={
        filter:String(data.get('filter')||'all'),label:String(data.get('label')||''),
        sort:String(data.get('sort')||'name'),order:String(data.get('order')||'asc')
      };
      localStorage.setItem(ITEMS_STATE_KEY,JSON.stringify(state));
    }catch(e){}
  }

  function installAsyncItems(){
    if(location.pathname!=='/items')return;
    const form=$('items-filter-form');if(!form||form.dataset.b2mV24==='1')return;form.dataset.b2mV24='1';
    let requestId=0;
    async function load(){
      persistItemFilters(form);
      const id=++requestId,params=new URLSearchParams(new FormData(form));
      const url='/items?'+params.toString();
      form.querySelectorAll('select').forEach(select=>select.disabled=true);
      try{
        const response=await fetch(url,{headers:{Accept:'text/html','X-B2M-Live':'1'}});if(!response.ok)throw new Error('HTTP '+response.status);
        const fresh=new DOMParser().parseFromString(await response.text(),'text/html');if(id!==requestId)return;
        ['items-table-body','items-count','items-last-sync'].forEach(target=>{const from=fresh.getElementById(target),to=$(target);if(from&&to)to.innerHTML=from.innerHTML;});
        const freshCfg=fresh.getElementById('items-page-config'),cfg=$('items-page-config');if(freshCfg&&cfg)Array.from(freshCfg.attributes).filter(a=>a.name.startsWith('data-')).forEach(a=>cfg.setAttribute(a.name,a.value));
        history.replaceState(null,'',url);
        if(window._itemsTable)window._itemsTable.reload();
        syncClientSort(form);
        const search=$('items-table-search');if(search&&search.value)search.dispatchEvent(new Event('input',{bubbles:true}));
      }catch(error){console.debug('Item filter refresh failed',error);}
      finally{if(id===requestId)form.querySelectorAll('select').forEach(select=>select.disabled=false);}
    }
    form.addEventListener('change',function(event){if(!event.target.matches('select[name="filter"],select[name="label"],select[name="sort"],select[name="order"]'))return;event.preventDefault();event.stopImmediatePropagation();load();},true);
    form.addEventListener('submit',function(event){event.preventDefault();event.stopImmediatePropagation();load();},true);
  }

  async function installDatabaseRoot(){
    if(location.pathname!=='/settings'||new URLSearchParams(location.search).get('tab')!=='admin'||$('b2m-v24-data-root'))return;
    try{
      const data=await json('/api/system/storage',{cache:'no-store'});
      const backup=Array.from(document.querySelectorAll('h3.card-title')).find(h=>h.textContent.trim()==='Backup')?.closest('.card');
      const grid=backup?.querySelector('.datagrid');if(!grid)return;
      const oldPath=Array.from(grid.querySelectorAll('.datagrid-title')).find(node=>node.textContent.trim()==='Path');if(oldPath)oldPath.textContent='Database path';
      const item=document.createElement('div');item.className='datagrid-item';item.id='b2m-v24-data-root';item.innerHTML='<div class="datagrid-title">Data root</div><div class="datagrid-content"><code class="text-break"></code></div>';item.querySelector('code').textContent=data.data_root||'—';grid.appendChild(item);
      function normalizeBreakdown(){
        const other=backup.querySelector('.b2m-storage-breakdown > div:nth-child(3) span');if(!other)return false;
        if(other.textContent.trim()===String(data.data_root||'').trim()){
          other.textContent='Persisted files outside SQLite';other.classList.remove('text-break');
        }
        return true;
      }
      if(!normalizeBreakdown()){
        const observer=new MutationObserver(()=>{if(normalizeBreakdown())observer.disconnect();});observer.observe(backup,{childList:true,subtree:true});
        setTimeout(()=>observer.disconnect(),3000);
      }
    }catch(e){}
  }

  function boot(){installRadiusPreviews();installDefaultsHint();installAsyncItems();installDatabaseRoot();bootRainbow();}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
