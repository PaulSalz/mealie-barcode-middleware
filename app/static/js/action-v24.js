/* v2026.09.22.4 — example payloads mirror the user's action name. */
(function(){
  'use strict';
  if(!(location.pathname==='/actions/new'||/^\/actions\/[^/]+$/.test(location.pathname))||window.__b2mActionV24Loaded)return;
  window.__b2mActionV24Loaded=true;
  const $=id=>document.getElementById(id);
  const field=name=>document.querySelector('[name="'+name+'"]');
  let exampleActive=false,installed=false;

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
    const name=field('name'),buttons=Array.from(document.querySelectorAll('.b2m-action-preset[data-preset]'));
    if(!name||!buttons.length){setTimeout(install,80);return;}
    if(installed)return;installed=true;
    name.addEventListener('input',updatePayloadName);
    buttons.forEach(button=>button.addEventListener('click',function(){
      exampleActive=true;
      // v22 first loads the example into the object editor. Add/update the
      // human-readable Action name after that synchronous preset write.
      setTimeout(updatePayloadName,0);
    }));
    if(payloadRow('action_name'))exampleActive=true;
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(install,40),{once:true});else setTimeout(install,40);
})();
