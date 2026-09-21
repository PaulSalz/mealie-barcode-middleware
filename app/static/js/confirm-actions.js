/** Global confirmation, clipboard and list-management helpers. */
(function() {
    var modalEl = document.getElementById('modal-confirm');
    if (!modalEl) return;

    // Keep the post-B21 visual fixes isolated from the B21 designer release.
    if (!document.querySelector('link[href^="/static/css/post-b21.css"]')) {
        var polishCss = document.createElement('link');
        polishCss.rel = 'stylesheet';
        polishCss.href = '/static/css/post-b21.css?v=20260921.2';
        document.head.appendChild(polishCss);
    }

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

    // Immediate scanner acknowledgement is deliberately not a notification.
    // On the dashboard it appears as a tiny transient status in the Mealie card;
    // elsewhere the bell briefly fills and turns blue.
    if(window.EventSource){
        var receivedEvents=new EventSource('/events');
        receivedEvents.addEventListener('received',function(event){
            var data;try{data=JSON.parse(event.data);}catch(e){return;}
            var barcode=String(data.barcode||'');
            var bell=document.querySelector('#notif-dropdown .ti-bell, #notif-dropdown .ti-bell-filled');
            if(bell){
                clearTimeout(window._b2mReceivedBellTimer);
                bell.classList.remove('ti-bell');
                bell.classList.add('ti-bell-filled','b2m-scan-received-bell');
                window._b2mReceivedBellTimer=setTimeout(function(){
                    bell.classList.remove('ti-bell-filled','b2m-scan-received-bell');
                    bell.classList.add('ti-bell');
                },1100);
            }
            if(window.location.pathname==='/'){
                var status=document.getElementById('scan-received-status');
                if(!status){
                    var health=document.getElementById('health-status');
                    var host=health&&health.closest('.col');
                    if(host){status=document.createElement('div');status.id='scan-received-status';status.className='small text-primary mt-1';host.appendChild(status);}
                }
                if(status){
                    clearTimeout(window._b2mReceivedStatusTimer);
                    status.textContent='Scan received'+(barcode?': '+barcode:'')+' · processing…';
                    status.style.opacity='1';
                    window._b2mReceivedStatusTimer=setTimeout(function(){status.style.opacity='0';setTimeout(function(){status.textContent='';},180);},1800);
                }
            }
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
            var td=document.createElement('td');td.className='b2m-bulk-col';var cb=document.createElement('input');cb.type='checkbox';cb.className='form-check-input b2m-bulk-row';cb.dataset.id=row.dataset.bulkId||'';cb.disabled=!enabled;cb.title=enabled?'Select':'Not selectable';td.appendChild(cb);row.insertBefore(td,row.firstChild);if(!enabled)td.classList.add('b2m-bulk-disabled');
            cb.addEventListener('click',function(e){e.stopPropagation();});cb.addEventListener('change',function(){row.classList.toggle('b2m-selected',cb.checked);update();});
        });
        var all=document.getElementById('b2m-bulk-all');all.addEventListener('change',function(){table.querySelectorAll('.b2m-bulk-row:not(:disabled)').forEach(function(cb){cb.checked=all.checked;cb.closest('tr').classList.toggle('b2m-selected',cb.checked);});update();});all.addEventListener('click',function(e){e.stopPropagation();});

        var pageRow=document.querySelector('.page-header .row');if(!pageRow)return;var slot=pageRow.querySelector('.col-auto:last-child');if(!slot){slot=document.createElement('div');slot.className='col-auto ms-auto';pageRow.appendChild(slot);}
        var toolbar=document.createElement('div');toolbar.className='b2m-bulk-toolbar ms-2';toolbar.innerHTML='<span class="badge bg-primary-lt" id="b2m-bulk-count">0</span><button type="button" class="btn btn-outline-danger" id="b2m-bulk-delete" disabled><i class="ti ti-trash icon"></i> Delete selected</button>';slot.appendChild(toolbar);
        var count=document.getElementById('b2m-bulk-count'),del=document.getElementById('b2m-bulk-delete');
        function selected(){return Array.from(table.querySelectorAll('.b2m-bulk-row:checked')).map(function(cb){return cb.dataset.id;});}
        function update(){var ids=selected();count.textContent=ids.length;del.disabled=!ids.length;var enabled=table.querySelectorAll('.b2m-bulk-row:not(:disabled)');all.checked=!!enabled.length&&Array.from(enabled).every(function(cb){return cb.checked;});}
        del.addEventListener('click',function(){var ids=selected();if(!ids.length)return;showConfirm('Delete '+ids.length+' selected '+kind+'?',kind==='items'?'Synced Mealie Foods are deleted in Mealie first; their local B2M targets and mappings are removed only after the upstream delete succeeds.':'Related local B2M records for the selection will be removed.',async function(){del.disabled=true;try{var r=await fetch('/api/bulk-delete',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({kind:kind,ids:ids})});var data=await r.json();if(!r.ok)throw new Error(data.error||'Delete failed');if(data.errors&&data.errors.length)window.alert(data.errors.join('\n'));window.location.reload();}catch(error){window.alert(error.message);del.disabled=false;}},'Delete selected');});
        update();
    }
    installBulkSelection();

    function installBarcodeTargetUxFixes(){
        if(!window.location.pathname.startsWith('/barcodes/')||window.location.pathname==='/barcodes/')return;
        var targetForms=Array.from(document.querySelectorAll('form[action*="/targets/"]:not([action$="/delete"])'));
        if(!targetForms.length)return;

        function relaxInheritedChoices(){
            targetForms.forEach(function(form){
                var grid=form.querySelector('.b2m-route-choice-grid');
                if(!grid)return;
                grid.querySelectorAll('input[type="checkbox"]:not([value="inherit"])').forEach(function(input){if(input.disabled)input.disabled=false;});
            });
        }
        relaxInheritedChoices();
        targetForms.forEach(function(form){
            var grid=form.querySelector('.b2m-route-choice-grid');
            if(!grid)return;
            new MutationObserver(relaxInheritedChoices).observe(grid,{subtree:true,attributes:true,attributeFilter:['disabled']});
        });

        function formSnapshot(form){
            var rows=[];
            new FormData(form).forEach(function(value,key){rows.push(key+'='+String(value));});
            return rows.sort().join('&');
        }
        var initial=targetForms.map(formSnapshot);
        function anyTargetDirty(){return targetForms.some(function(form,index){return formSnapshot(form)!==initial[index];});}
        function repairSaveAllState(){
            if(anyTargetDirty())return;
            var button=document.getElementById('save-all-targets');
            var status=document.querySelector('.b2m-target-save-status');
            if(button){button.classList.remove('btn-primary');button.classList.add('btn-outline-primary');}
            if(status){status.textContent='';status.className='b2m-target-save-status text-secondary me-2';}
        }
        var recipeForm=document.getElementById('recipe-map-form');
        if(recipeForm){
            ['input','change'].forEach(function(name){recipeForm.addEventListener(name,function(){setTimeout(repairSaveAllState,0);});});
        }
    }

    function installAppearancePreview(){
        if(window.location.pathname!=='/settings')return;
        var params=new URLSearchParams(window.location.search);
        if((params.get('tab')||'mealie')!=='appearance')return;
        var form=document.querySelector('form[action="/settings/theme"]');
        var epaper=document.getElementById('theme-epaper');
        var contrast=document.getElementById('theme-contrast');
        if(!form||!epaper||!contrast)return;

        var access=document.getElementById('theme-accessibility');
        if(access&&!document.getElementById('theme-date-style')){
            var dateBox=document.createElement('div');
            dateBox.className='mt-4';
            dateBox.innerHTML='<label class="form-label" for="theme-date-style">Date & time format</label><select class="form-select" id="theme-date-style" name="theme_date_style"><option value="short">Short · 21.09.26 14:32</option><option value="medium">Medium · 21.09.2026 14:32</option><option value="long">Long · 21. September 2026, 14:32</option></select><div class="form-hint">Used wherever B2M shows the complete local date/time. Relative timestamps stay unchanged.</div>';
            access.appendChild(dateBox);
        }
        var dateStyle=document.getElementById('theme-date-style');
        fetch('/api/theme',{headers:{'Accept':'application/json'}}).then(function(r){return r.ok?r.json():null;}).then(function(theme){if(theme&&dateStyle)dateStyle.value=theme.date_style||'medium';}).catch(function(){});

        var themeLink=document.querySelector('link[href="/theme.css"], link[href^="/theme.css?"]');
        var previewStyle=document.getElementById('b2m-theme-preview-style');
        if(!previewStyle){previewStyle=document.createElement('style');previewStyle.id='b2m-theme-preview-style';document.head.appendChild(previewStyle);}
        var previewTimer=null,previewSeq=0;
        function preview(){
            clearTimeout(previewTimer);
            previewTimer=setTimeout(async function(){
                var seq=++previewSeq;
                try{
                    var response=await fetch('/api/theme/preview',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({epaper:epaper.checked,contrast:Number(contrast.value)})});
                    var data=await response.json();
                    if(!response.ok||seq!==previewSeq)return;
                    if(themeLink)themeLink.disabled=true;
                    previewStyle.textContent=data.css||'';
                }catch(e){}
            },45);
        }
        epaper.addEventListener('change',preview);
        contrast.addEventListener('input',preview);
    }

    window.addEventListener('load',function(){
        installBarcodeTargetUxFixes();
        installAppearancePreview();
    });
})();
