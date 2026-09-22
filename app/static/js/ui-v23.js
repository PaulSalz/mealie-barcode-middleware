/* v2026.09.22.2 — personal appearance, permission-aware controls and storage UI. */
(function(){
  'use strict';
  if(window.__b2mUiV23Loaded)return;window.__b2mUiV23Loaded=true;

  function esc(value){return String(value==null?'':value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');}
  function humanBytes(bytes){
    bytes=Number(bytes||0);if(bytes<1024)return bytes+' B';
    const units=['KB','MB','GB','TB'];let value=bytes/1024,index=0;
    while(value>=1024&&index<units.length-1){value/=1024;index++;}
    return (value>=100?value.toFixed(0):value>=10?value.toFixed(1):value.toFixed(2))+' '+units[index];
  }

  function installBrand(){
    const brand=document.querySelector('.navbar-brand a');if(!brand)return;
    const icon=brand.querySelector('i');
    const nodes=Array.from(brand.childNodes).filter(function(node){return node!==icon;});
    if(!nodes.length||brand.querySelector('.b2m-brand-text'))return;
    const span=document.createElement('span');span.className='b2m-brand-text';
    nodes.forEach(function(node){span.appendChild(node);});brand.appendChild(span);
  }

  function addPersonalAppearanceLink(access){
    const menu=document.querySelector('.navbar .dropdown-menu');if(!menu||menu.querySelector('[href="/profile/appearance"]'))return;
    const logout=menu.querySelector('form[action="/logout"]');
    const link=document.createElement('a');link.className='dropdown-item'+(window.location.pathname==='/profile/appearance'?' active':'');link.href='/profile/appearance';link.innerHTML='<i class="ti ti-palette icon dropdown-item-icon"></i> Personal appearance';
    if(logout)logout.insertAdjacentElement('beforebegin',link);else menu.appendChild(link);
    if(access?.permissions?.database&&!menu.querySelector('[href="/database"]')){
      const db=document.createElement('a');db.className='dropdown-item'+(window.location.pathname==='/database'?' active':'');db.href='/database';db.innerHTML='<i class="ti ti-database icon dropdown-item-icon"></i> Database';link.insertAdjacentElement('afterend',db);
    }
  }

  function enforceUiPermissions(access){
    if(!access||access.is_admin)return;
    const p=access.permissions||{};
    if(!p.items){
      document.querySelector('a[data-bs-target="#modal-add-item"]')?.classList.add('d-none');
      document.querySelector('form[action="/items/sync"]')?.classList.add('d-none');
    }
    if(!p.actions){
      document.querySelector('a[href="/actions/new"]')?.classList.add('d-none');
      document.querySelector('form[action^="/actions/"] button[type="submit"]')?.setAttribute('disabled','disabled');
      document.getElementById('action-test')?.setAttribute('disabled','disabled');
    }
    if(!p.printer&&window.location.pathname==='/labels'){
      ['label-niim-print','b21-connect-button','b21-new-profile','b21-edit-profile','b21-delete-profile','b21-save-profile','b21-read-rfid','b21-v2-test-cal'].forEach(function(id){const el=document.getElementById(id);if(el)el.disabled=true;});
    }
  }

  function permissionModal(){
    let modal=document.getElementById('b2m-permissions-modal');if(modal)return modal;
    modal=document.createElement('div');modal.className='modal modal-blur fade';modal.id='b2m-permissions-modal';modal.tabIndex=-1;
    modal.innerHTML='<div class="modal-dialog modal-lg modal-dialog-centered"><div class="modal-content"><div class="modal-header"><div><h3 class="modal-title">User permissions</h3><div class="text-secondary small" id="b2m-permission-user"></div></div><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div><div class="modal-body"><div class="alert alert-danger d-none" id="b2m-permission-error"></div><div class="b2m-permission-list" id="b2m-permission-list"></div><div class="form-hint mt-3">Appearance is always personal and does not need a permission. Admin users always have all permissions.</div></div><div class="modal-footer"><button class="btn" data-bs-dismiss="modal" type="button">Cancel</button><button class="btn btn-primary" type="button" id="b2m-permission-save"><i class="ti ti-device-floppy icon"></i> Save permissions</button></div></div></div>';
    document.body.appendChild(modal);
    const trigger=document.createElement('button');trigger.id='b2m-permissions-trigger';trigger.type='button';trigger.className='d-none';trigger.setAttribute('data-bs-toggle','modal');trigger.setAttribute('data-bs-target','#b2m-permissions-modal');document.body.appendChild(trigger);
    return modal;
  }

  async function installPermissionEditor(access){
    if(window.location.pathname!=='/settings'||(new URLSearchParams(location.search).get('tab')||'mealie')!=='users'||!access?.is_admin)return;
    const response=await fetch('/api/access/users',{headers:{Accept:'application/json'}});if(!response.ok)return;const data=await response.json();
    const table=Array.from(document.querySelectorAll('table')).find(function(t){return Array.from(t.querySelectorAll('th')).some(function(th){return th.textContent.trim()==='Username';});});if(!table)return;
    const head=table.querySelector('thead tr');if(head&&!head.querySelector('.b2m-permission-head')){const th=document.createElement('th');th.className='b2m-permission-head';th.textContent='Permissions';head.insertBefore(th,head.children[2]||null);}
    const byName=new Map((data.users||[]).map(function(user){return [user.username,user];}));
    table.querySelectorAll('tbody tr').forEach(function(row){
      const first=row.querySelector('td');if(!first)return;const user=byName.get(first.textContent.trim());if(!user||row.querySelector('.b2m-permission-cell'))return;
      const cell=document.createElement('td');cell.className='b2m-permission-cell';
      cell.innerHTML=user.is_admin?'<span class="badge bg-purple-lt">All permissions</span>':'<button class="btn btn-sm btn-outline-secondary" type="button"><i class="ti ti-shield-lock icon"></i> Configure</button>';
      row.insertBefore(cell,row.children[2]||null);
      const button=cell.querySelector('button');if(button)button.addEventListener('click',function(){openPermissionEditor(user,data.catalog||[]);});
    });
  }

  function openPermissionEditor(user,catalog){
    const modal=permissionModal(),list=modal.querySelector('#b2m-permission-list'),error=modal.querySelector('#b2m-permission-error'),save=modal.querySelector('#b2m-permission-save');
    modal.querySelector('#b2m-permission-user').textContent=user.username;error.classList.add('d-none');
    list.innerHTML=catalog.map(function(item){return '<label class="b2m-permission-option"><input class="form-check-input" type="checkbox" data-permission="'+esc(item.id)+'" '+(user.permissions?.[item.id]?'checked':'')+'><span><strong>'+esc(item.label)+'</strong><small>'+esc(item.description)+'</small></span></label>';}).join('');
    save.onclick=async function(){
      const permissions={};list.querySelectorAll('[data-permission]').forEach(function(input){permissions[input.dataset.permission]=input.checked;});save.disabled=true;
      try{const r=await fetch('/api/access/users/'+encodeURIComponent(user.id),{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({permissions:permissions})});const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not save permissions');user.permissions=d.permissions||permissions;document.querySelector('#b2m-permissions-modal .btn-close')?.click();}
      catch(e){error.textContent=e.message;error.classList.remove('d-none');}finally{save.disabled=false;}
    };
    document.getElementById('b2m-permissions-trigger').click();
  }

  async function installStorageOverview(access){
    if(window.location.pathname!=='/settings'||(new URLSearchParams(location.search).get('tab')||'mealie')!=='admin'||!access?.permissions?.database)return;
    const response=await fetch('/api/system/storage',{headers:{Accept:'application/json'}});if(!response.ok)return;const data=await response.json();
    const backupHeading=Array.from(document.querySelectorAll('h3.card-title')).find(function(h){return h.textContent.trim()==='Backup';});const card=backupHeading?.closest('.card');const body=card?.querySelector('.card-body');if(!body||body.querySelector('.b2m-storage-breakdown'))return;
    const block=document.createElement('div');block.className='b2m-storage-breakdown mt-3';block.innerHTML='<div><small>System data</small><strong>'+humanBytes(data.system_data_bytes)+'</strong><span class="text-secondary small">'+data.file_count+' files</span></div><div><small>SQLite database</small><strong>'+humanBytes(data.database_bytes)+'</strong><span class="text-secondary small">'+Math.round((data.system_data_bytes?data.database_bytes/data.system_data_bytes:0)*100)+'% of system data</span></div><div><small>Other persisted data</small><strong>'+humanBytes(data.other_bytes)+'</strong><span class="text-secondary small text-break">'+esc(data.data_root)+'</span></div>';body.appendChild(block);
  }

  function boot(){
    installBrand();
    fetch('/api/access/me',{headers:{Accept:'application/json'}}).then(function(r){return r.ok?r.json():null;}).then(function(access){if(!access)return;addPersonalAppearanceLink(access);enforceUiPermissions(access);installPermissionEditor(access).catch(function(){});installStorageOverview(access).catch(function(){});}).catch(function(){});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
