/* v2026.09.22.2 — action identity + Home Assistant UX. */
(function(){
  'use strict';
  if(!(window.location.pathname==='/actions/new'||/^\/actions\/[^/]+$/.test(window.location.pathname)))return;
  if(window.__b2mActionV23Loaded)return;window.__b2mActionV23Loaded=true;
  const $=(id)=>document.getElementById(id);
  let programmatic=false,idOverridden=false,urlOverridden=false,flashTimer=null;

  function slug(value){
    return String(value||'').trim().toLowerCase()
      .replace(/ä/g,'ae').replace(/ö/g,'oe').replace(/ü/g,'ue').replace(/ß/g,'ss')
      .normalize('NFKD').replace(/[\u0300-\u036f]/g,'')
      .replace(/[^a-z0-9._-]+/g,'_').replace(/^[-_.]+|[-_.]+$/g,'').replace(/_+/g,'_');
  }
  function generatedId(name){const clean=slug(name);return clean?'action_'+clean:'action_';}
  function webhookPrefix(value){
    value=String(value||'').trim();
    const match=value.match(/^(.*\/api\/webhook\/)([^/?#]*)/i);
    if(match)return match[1];
    if(/\/api\/webhook\/?$/i.test(value))return value.replace(/\/?$/,'/');
    return '';
  }
  function field(name){return document.querySelector('[name="'+name+'"]');}
  function dispatch(el){if(el){el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}}

  function updatePayloadActionId(id){
    const root=$('action-v22-payload');if(!root)return;
    const row=Array.from(root.querySelectorAll('.b2m-kv-row')).find(function(item){return item.querySelector('.b2m-kv-key')?.value.trim()==='action_id';});
    const value=row&&row.querySelector('.b2m-kv-value');
    if(value){value.value=id;value.dispatchEvent(new Event('input',{bubbles:true}));}
  }

  function syncGeneratedIdentity(force){
    const name=field('name'),id=field('action_id'),url=field('webhook_url');if(!name)return;
    const nextId=generatedId(name.value);
    programmatic=true;
    if(id&&(force||!idOverridden)){id.value=nextId;dispatch(id);}
    const activeId=id?String(id.value||nextId):nextId;
    if(url&&(force||!urlOverridden)){
      const prefix=webhookPrefix(url.dataset.b2mWebhookSeed||url.value);
      if(prefix){url.value=prefix+encodeURIComponent(activeId);dispatch(url);}
    }
    updatePayloadActionId(activeId);
    programmatic=false;
  }

  function moveProtocolFieldsToAdvanced(){
    const execHeading=Array.from(document.querySelectorAll('h3.card-title')).find(function(el){return el.textContent.trim()==='Execution controls';});
    const row=execHeading?.closest('.card')?.querySelector('.card-body .row');if(!row)return;
    ['action_type','method','execution_mode'].forEach(function(name){
      const el=field(name),col=el?.closest('[class*="col-"]');if(!col||col.closest('.card')===execHeading.closest('.card'))return;
      col.className='col-12';row.insertBefore(col,row.firstChild);
    });
  }

  function improveBuilderCopy(){
    const copy={
      params:'Parameters are reusable server-side values stored with the Action. They are not sent automatically; reference one in the Payload as {{ params.key }}. Use them for values you may want to change later — timer duration, quantity, brightness, a room name — without printing a new barcode.',
      payload:'Payload is the actual data B2M sends to the webhook. For POST/PUT/PATCH it becomes the JSON request body; for GET it becomes query parameters. Template values are resolved at scan time, so the remote automation receives the current Action ID, barcode and Parameters.',
      headers:'Headers are HTTP metadata, not normal action data. Most Home Assistant webhooks need none. Use them only when another endpoint requires something such as Content-Type or Authorization. Secrets here stay in B2M and are never encoded in the barcode.'
    };
    Object.entries(copy).forEach(function(entry){
      const collapse=$('action-v22-'+entry[0]+'-collapse');const hint=collapse?.querySelector('.accordion-body > .form-hint');if(hint)hint.textContent=entry[1];
    });
  }

  function flashPresetNote(){
    const note=$('action-v22-preset-note');if(!note)return;
    note.classList.remove('d-none');clearTimeout(flashTimer);flashTimer=setTimeout(function(){note.classList.add('d-none');},1800);
  }

  const presetNames={light:'Light',tts:'TTS',timer:'Timer',automation:'Automation',data:'Data'};
  function applyPresetIdentity(key){
    const name=field('name'),type=field('action_type'),method=field('method'),execution=field('execution_mode');
    if(name){programmatic=true;name.value=presetNames[key]||'Action';dispatch(name);programmatic=false;}
    idOverridden=false;urlOverridden=false;syncGeneratedIdentity(true);
    if(type){type.value='homeassistant';dispatch(type);}
    if(method){method.value='POST';dispatch(method);}
    if(execution){execution.value='async';dispatch(execution);}
    const id=field('action_id');if(id)updatePayloadActionId(id.value);
    flashPresetNote();
  }

  function install(){
    const name=field('name'),id=field('action_id'),url=field('webhook_url');if(!name||!url){setTimeout(install,100);return;}
    if(url.dataset.b2mV23==='1')return;url.dataset.b2mV23='1';url.dataset.b2mWebhookSeed=url.value||'';

    // Home Assistant is the normal path. Generic webhook protocol details stay
    // available under Advanced rather than taking space in the main request UI.
    if(window.location.pathname==='/actions/new'){
      const type=field('action_type'),method=field('method'),execution=field('execution_mode');
      if(type)type.value='homeassistant';if(method)method.value='POST';if(execution)execution.value='async';
      syncGeneratedIdentity(false);
    }

    name.addEventListener('input',function(){if(!programmatic&&window.location.pathname==='/actions/new')syncGeneratedIdentity(false);});
    if(id){id.addEventListener('input',function(){if(programmatic)return;idOverridden=true;updatePayloadActionId(id.value);if(!urlOverridden){programmatic=true;const prefix=webhookPrefix(url.dataset.b2mWebhookSeed||url.value);if(prefix){url.value=prefix+encodeURIComponent(id.value);dispatch(url);}programmatic=false;}});}
    url.addEventListener('input',function(){if(!programmatic)urlOverridden=true;});

    moveProtocolFieldsToAdvanced();
    improveBuilderCopy();

    document.querySelectorAll('.b2m-action-preset[data-preset]').forEach(function(button){
      button.addEventListener('click',function(){setTimeout(function(){applyPresetIdentity(button.dataset.preset);},0);});
    });

    // The permanent introductory message is useful before the first click; after
    // loading an example the confirmation becomes a short transient status only.
    const note=$('action-v22-preset-note');if(note)note.dataset.b2mV23='1';
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){setTimeout(install,30);},{once:true});else setTimeout(install,30);
})();
