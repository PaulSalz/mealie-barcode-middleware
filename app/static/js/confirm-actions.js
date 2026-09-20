/** Global confirmation, clipboard and list-management helpers. */
(function() {
    var modalEl = document.getElementById('modal-confirm');
    if (!modalEl) return;
    var titleEl = document.getElementById('modal-confirm-title');
    var msgEl = document.getElementById('modal-confirm-msg');
    var okBtn = document.getElementById('modal-confirm-ok');
    var dismissBtn = modalEl.querySelector('[data-bs-dismiss="modal"]');
    var pendingAction = null;
    var trigger = document.createElement('button');
    trigger.setAttribute('data-bs-toggle','modal'); trigger.setAttribute('data-bs-target','#modal-confirm'); trigger.style.display='none'; document.body.appendChild(trigger);

    okBtn.addEventListener('click',function(){if(pendingAction){var action=pendingAction;pendingAction=null;dismissBtn.click();setTimeout(action,50);}});
    modalEl.addEventListener('hidden.bs.modal',function(){pendingAction=null;okBtn.textContent='Delete';});
    function showConfirm(title,detail,onConfirm,btnLabel){titleEl.textContent=title;msgEl.textContent=detail||'';okBtn.textContent=btnLabel||'Delete';pendingAction=onConfirm;trigger.click();}
    window.showConfirm=showConfirm;

    document.querySelectorAll('form[data-confirm]').forEach(function(form){form.addEventListener('submit',function(e){e.preventDefault();showConfirm(form.dataset.confirm,form.dataset.confirmDetail||'',function(){form.submit();});});});
    document.querySelectorAll('[data-confirm-post]').forEach(function(btn){btn.addEventListener('click',function(e){e.preventDefault();showConfirm(btn.dataset.confirmMsg||'Are you sure?',btn.dataset.confirmDetail||'',function(){var f=document.createElement('form');f.method='post';f.action=btn.dataset.confirmPost;f.style.display='none';document.body.appendChild(f);f.submit();});});});
    document.querySelectorAll('[data-copy-target]').forEach(function(btn){btn.addEventListener('click',function(){var target=document.getElementById(btn.dataset.copyTarget);if(target)navigator.clipboard.writeText(target.value.trim()).then(function(){var icon=btn.querySelector('.ti');if(icon){icon.className='ti ti-check icon';setTimeout(function(){icon.className='ti ti-copy icon';},1500);}});});});

    // Labels already has a prominent page entry from relevant screens; keep the
    // tools dropdown focused on status/activity/settings.
    document.querySelectorAll('header .dropdown-menu a[href="/labels"]').forEach(function(link){link.remove();});

    function installScannerMenuStatus(){
        var menu=Array.from(document.querySelectorAll('header .dropdown-menu')).find(function(m){return m.querySelector('a[href^="/activities"]');});
        if(!menu||document.getElementById('scanner-menu-status'))return;
        var item=document.createElement('a');item.id='scanner-menu-status';item.className='dropdown-item';item.href='/settings?tab=tokens';item.innerHTML='<i class="ti ti-scan icon dropdown-item-icon"></i><span>Scanner <span class="text-secondary">checking…</span></span>';
        var activity=menu.querySelector('a[href^="/activities"]');activity.insertAdjacentElement('afterend',item);
        function refresh(){fetch('/api/scanners',{headers:{'Accept':'application/json'}}).then(function(r){return r.ok?r.json():null;}).then(function(data){if(!data)return;var rows=data.items||[];var bridge=rows.filter(function(r){return r.bridge_online;}).length;var connected=rows.filter(function(r){return r.device_connected;}).length;var color=connected===rows.length&&rows.length?'green':bridge?'yellow':'red';item.innerHTML='<i class="ti ti-scan icon dropdown-item-icon text-'+color+'"></i><span>Scanner <strong class="text-'+color+'">'+connected+'/'+rows.length+'</strong><span class="text-secondary"> connected</span></span>';}).catch(function(){});}
        refresh();setInterval(refresh,20000);
    }
    installScannerMenuStatus();

    // Immediate acknowledgement from scanner bridge, before Mealie routing completes.
    if(window.EventSource&&document.getElementById('scan-toasts')){
        var receivedEvents=new EventSource('/events');
        receivedEvents.addEventListener('received',function(event){
            var data;try{data=JSON.parse(event.data);}catch(e){return;}
            var container=document.getElementById('scan-toasts');var toast=document.createElement('div');toast.className='toast show';
            toast.innerHTML='<div class="toast-header"><span class="avatar avatar-xs me-2 bg-azure"><i class="ti ti-scan icon-sm text-white"></i></span><strong class="me-auto">Scan received</strong></div><div class="toast-body py-2"><code>'+String(data.barcode||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</code> <span class="text-secondary">· processing…</span></div>';
            container.prepend(toast);setTimeout(function(){if(toast.isConnected)toast.remove();},1800);
        });
        window.addEventListener('beforeunload',function(){receivedEvents.close();});
    }

    function installBulkSelection(){
        if(!document.querySelector('a[href="/settings"]'))return; // admin-only UI
        var path=window.location.pathname,kind='',table=null,rows=[];
        if(path==='/barcodes'){kind='barcodes';table=document.getElementById('barcodes-table');}
        else if(path==='/activities'){kind='activities';table=document.getElementById('activity-table');}
        else if(path==='/actions'){kind='actions';table=document.querySelector('.card table');}
        else if(path==='/items'){kind='items';table=document.getElementById('items-table');}
        else return;
        if(!table)return;
        rows=Array.from(table.querySelectorAll('tbody tr')).filter(function(row){return !row.className.includes('empty-row')&&!row.querySelector('.empty');});
        if(!rows.length)return;

        if(kind==='actions')rows.forEach(function(row){var a=row.querySelector('a[href^="/actions/"]');if(a)row.dataset.bulkId=decodeURIComponent(a.getAttribute('href').substring('/actions/'.length));});
        if(kind==='items')rows.forEach(function(row){row.dataset.bulkId=row.dataset.itemId||'';});

        var headRow=table.querySelector('thead tr');var th=document.createElement('th');th.className='b2m-bulk-col';th.innerHTML='<input type="checkbox" class="form-check-input" id="b2m-bulk-all" aria-label="Select all">';headRow.insertBefore(th,headRow.firstChild);
        rows.forEach(function(row){
            var enabled=!!row.dataset.bulkId;
            if(kind==='items')enabled=enabled&&/custom/i.test((row.querySelector('.sort-source')||{}).textContent||'');
            var td=document.createElement('td');td.className='b2m-bulk-col';var cb=document.createElement('input');cb.type='checkbox';cb.className='form-check-input b2m-bulk-row';cb.dataset.id=row.dataset.bulkId||'';cb.disabled=!enabled;cb.title=enabled?'Select':'Synced Mealie items are not batch-deleted';td.appendChild(cb);row.insertBefore(td,row.firstChild);if(!enabled)td.classList.add('b2m-bulk-disabled');
            cb.addEventListener('click',function(e){e.stopPropagation();});cb.addEventListener('change',function(){row.classList.toggle('b2m-selected',cb.checked);update();});
        });
        var all=document.getElementById('b2m-bulk-all');all.addEventListener('change',function(){table.querySelectorAll('.b2m-bulk-row:not(:disabled)').forEach(function(cb){cb.checked=all.checked;cb.closest('tr').classList.toggle('b2m-selected',cb.checked);});update();});all.addEventListener('click',function(e){e.stopPropagation();});

        var pageRow=document.querySelector('.page-header .row');if(!pageRow)return;var slot=pageRow.querySelector('.col-auto:last-child');if(!slot){slot=document.createElement('div');slot.className='col-auto ms-auto';pageRow.appendChild(slot);}
        var toolbar=document.createElement('div');toolbar.className='b2m-bulk-toolbar ms-2';toolbar.innerHTML='<span class="badge bg-primary-lt" id="b2m-bulk-count">0</span><button type="button" class="btn btn-outline-danger" id="b2m-bulk-delete" disabled><i class="ti ti-trash icon"></i> Delete selected</button>';slot.appendChild(toolbar);
        var count=document.getElementById('b2m-bulk-count'),del=document.getElementById('b2m-bulk-delete');
        function selected(){return Array.from(table.querySelectorAll('.b2m-bulk-row:checked')).map(function(cb){return cb.dataset.id;});}
        function update(){var ids=selected();count.textContent=ids.length;del.disabled=!ids.length;var enabled=table.querySelectorAll('.b2m-bulk-row:not(:disabled)');all.checked=!!enabled.length&&Array.from(enabled).every(function(cb){return cb.checked;});}
        del.addEventListener('click',function(){var ids=selected();if(!ids.length)return;showConfirm('Delete '+ids.length+' selected '+kind+'?',kind==='items'?'Only custom/local items are deleted; synced Mealie Foods are protected.':'Related local B2M records for the selection will be removed.',async function(){del.disabled=true;try{var r=await fetch('/api/bulk-delete',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({kind:kind,ids:ids})});var data=await r.json();if(!r.ok)throw new Error(data.error||'Delete failed');window.location.reload();}catch(error){window.alert(error.message);del.disabled=false;}},'Delete selected');});
        update();
    }
    installBulkSelection();
})();
