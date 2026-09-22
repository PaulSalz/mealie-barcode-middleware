/* v2026.09.22.4 — examples keep the user's action name and mirror it into payload. */
(function(){
  'use strict';
  if(!(location.pathname==='/actions/new'||/^\/actions\/[^/]+$/.test(location.pathname))||window.__b2mActionV24Loaded)return;
  window.__b2mActionV24Loaded=true;
  const $=id=>document.getElementById(id);
  const field=name=>document.querySelector('[name="'+name+'"]');
  let exampleActive=false;

  function payloadRow(key){
    const root=$('action-v22-payload');
    return root&&Array.from(root.querySelectorAll('.b2m-kv-row')).find(row=>row.querySelector('.b2m-kv-key')?.value.trim()===key);
  }
  function updatePayloadName(){
    const name=field('name');if(!name)return;
    const row=payloadRow('action_name'),value=row&&row.querySelector('.b2m-kv-value');
    if(value){value.value=name.value;value.dispatchEvent(new Event('input',{bubbles:true}));return;}
    if(!exampleActive)return;
    const textarea=$('action-payload-json');if(!textarea)return;
    try{
      const payload=JSON.parse(textarea.value||'{}');
      if(!payload||typeof payload!=='object'||Array.isArray(payload))return;
      payload.action_name=name.value;
      textarea.value=JSON.stringify(payload,null,2);
      textarea.dispatchEvent(new Event('change',{bubbles:true}));
    }catch(e){}
  }

  function install(){
    const name=field('name');if(!name){setTimeout(install,80);return;}
    name.addEventListener('input',updatePayloadName);
    document.querySelectorAll('.b2m-action-preset[data-preset]').forEach(button=>{
      button.addEventListener('click',function(){
        const keepName=name.value;
        exampleActive=true;
        setTimeout(function(){
          if(name.value!==keepName){name.value=keepName;name.dispatchEvent(new Event('input',{bubbles:true}));name.dispatchEvent(new Event('change',{bubbles:true}));}
          updatePayloadName();
        },0);
      });
    });
    if(payloadRow('action_name'))exampleActive=true;
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(install,40),{once:true});else setTimeout(install,40);
})();
