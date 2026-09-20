(function() {
    'use strict';

    var form = document.getElementById('barcode-metadata-form');
    var status = document.getElementById('metadata-save-status');
    var barcode = '';
    try { barcode = decodeURIComponent(window.location.pathname.substring('/barcodes/'.length)); } catch (e) {}

    window.addEventListener('pageshow', function(event) {
        if (event.persisted) window.location.reload();
    });

    async function saveMetadata(event) {
        var submitter = event.submitter;
        if (submitter && submitter.getAttribute('formaction')) return;
        event.preventDefault();
        if (!form) return;
        if (status) { status.className = 'form-hint text-secondary'; status.textContent = 'Saving…'; }
        try {
            var response = await fetch(form.action, {method:'POST', headers:{'X-Requested-With':'fetch','Accept':'application/json'}, body:new FormData(form)});
            var data = await response.json();
            if (!response.ok) throw new Error(data.error || 'Save failed');
            var title = document.getElementById('displayed-title');
            var brand = document.getElementById('displayed-brand');
            if (title) title.textContent = data.title || '—';
            if (brand) brand.textContent = data.brand || '—';
            if (status) { status.className='form-hint text-success'; status.textContent='Saved.'; setTimeout(function(){status.textContent='';},2500); }
        } catch (error) { if (status) { status.className='form-hint text-danger'; status.textContent=error.message; } }
    }
    if (form) form.addEventListener('submit', saveMetadata);
    if (form) form.querySelectorAll('input[name="title"], input[name="brand"]').forEach(function(input) {
        input.addEventListener('keydown', function(event) {
            if (event.key === 'Enter') { event.preventDefault(); if (form.requestSubmit) form.requestSubmit(); else form.dispatchEvent(new Event('submit',{cancelable:true,bubbles:true})); }
        });
    });

    document.querySelectorAll('.target-unit-select').forEach(function(select) {
        select.addEventListener('change', function() {
            var defaultId=select.dataset.itemUnit||'';
            var existing=select.parentElement.querySelector('.b2m-unit-live-warning'); if(existing) existing.remove();
            var selected=select.value==='__item_default__'?defaultId:select.value;
            if(defaultId&&selected&&selected!==defaultId){var warning=document.createElement('div');warning.className='form-hint text-warning b2m-unit-live-warning';warning.innerHTML='<i class="ti ti-alert-triangle"></i> Selected unit differs from the item default.';select.insertAdjacentElement('afterend',warning);}
        });
    });

    function targetIdForForm(targetForm) {
        var m=(targetForm.action||'').match(/\/targets\/(\d+)(?:$|\?)/); return m?Number(m[1]):null;
    }

    function routeValues(route) {
        if(route==='both') return ['mealie','homeassistant'];
        if(route==='mealie'||route==='homeassistant') return [route];
        return [];
    }

    function applyInheritedState(select) {
        var box=select.nextElementSibling;
        if(!box||!box.classList.contains('b2m-route-choice-grid')) return;
        var inherit=box.querySelector('input[value="inherit"]');
        var inherited=routeValues(select.closest('form').dataset.effectiveRoute||'');
        box.querySelectorAll('input').forEach(function(input){
            var card=input.closest('.b2m-choice-card');
            if(input.value==='inherit') return;
            var locked=!!(inherit&&inherit.checked);
            input.disabled=locked;
            if(card) card.classList.toggle('b2m-inherited-active',locked&&inherited.includes(input.value));
        });
    }

    function installRouteChoices(select) {
        if(!select||select.dataset.checkboxUi==='1') return;
        select.dataset.checkboxUi='1';
        var original=select.value||'none'; select.classList.add('d-none');
        var allowInherit=Array.from(select.options).some(function(option){return option.value==='inherit';});
        var box=document.createElement('div'); box.className='b2m-choice-grid b2m-route-choice-grid';
        var entries=[]; if(allowInherit) entries.push(['inherit','Inherit','Use item/default route']);
        entries.push(['mealie','Mealie','Shopping list'],['homeassistant','Home Assistant','Webhook event']);
        box.innerHTML=entries.map(function(entry){return '<label class="b2m-choice-card"><input class="form-check-input me-2" type="checkbox" value="'+entry[0]+'"><span><strong>'+entry[1]+'</strong><small>'+entry[2]+'</small></span></label>';}).join('');
        select.insertAdjacentElement('afterend',box);
        var checks=Array.from(box.querySelectorAll('input[type="checkbox"]'));
        function check(value,state){var el=checks.find(function(row){return row.value===value;});if(el)el.checked=state;}
        if(original==='inherit'&&allowInherit)check('inherit',true); else if(original==='both'){check('mealie',true);check('homeassistant',true);} else if(original==='mealie')check('mealie',true); else if(original==='homeassistant')check('homeassistant',true);
        function sync(changed){
            if(changed&&changed.value==='inherit'&&changed.checked) checks.forEach(function(row){if(row!==changed)row.checked=false;});
            else if(changed&&changed.value!=='inherit'&&changed.checked) check('inherit',false);
            var values=checks.filter(function(row){return row.checked;}).map(function(row){return row.value;});
            if(values.includes('inherit'))select.value='inherit'; else if(values.includes('mealie')&&values.includes('homeassistant'))select.value='both'; else if(values.includes('mealie'))select.value='mealie'; else if(values.includes('homeassistant'))select.value='homeassistant'; else select.value='none';
            applyInheritedState(select); updateListChoiceState(select.closest('form')); markDirty();
        }
        checks.forEach(function(row){row.addEventListener('change',function(){sync(row);});});
        applyInheritedState(select); updateListChoiceState(select.closest('form'));
    }

    function installListChoices(select) {
        if(!select||select.dataset.checkboxUi==='1')return;
        select.dataset.checkboxUi='1'; select.classList.add('d-none');
        var box=document.createElement('div');box.className='b2m-choice-grid b2m-list-choice-grid';
        box.innerHTML=Array.from(select.options).map(function(option){
            var text=option.textContent.replace(/ · default$/,'');var isDefault=/ · default$/.test(option.textContent);
            return '<label class="b2m-choice-card" data-list-id="'+option.value.replace(/"/g,'&quot;')+'"><input class="form-check-input me-2" type="checkbox" value="'+option.value.replace(/"/g,'&quot;')+'"'+(option.selected?' checked':'')+'><span><strong>'+text.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</strong>'+(isDefault?'<small><span class="badge bg-blue-lt">default</span></small>':'<small>Mealie list</small>')+'</span></label>';
        }).join('');
        select.insertAdjacentElement('afterend',box);
        var hint=select.parentElement.querySelector('.form-hint');if(hint&&hint.textContent.includes('Ctrl/Cmd'))hint.textContent='Select any number of lists. No selection = current default list.';
        box.querySelectorAll('input[type="checkbox"]').forEach(function(check){check.addEventListener('change',function(){Array.from(select.options).forEach(function(option){if(option.value===check.value)option.selected=check.checked;});markDirty();});});
    }

    function updateListChoiceState(targetForm){
        if(!targetForm)return;var route=targetForm.querySelector('select[name="route"]');var listBox=targetForm.querySelector('.b2m-list-choice-grid');if(!route||!listBox)return;
        var enabled=route.value==='mealie'||route.value==='both'||route.value==='inherit';
        listBox.classList.toggle('b2m-choice-disabled',!enabled);listBox.querySelectorAll('input').forEach(function(input){input.disabled=!enabled;});
    }

    var targetForms=Array.from(document.querySelectorAll('form[action*="/targets/"]:not([action$="/delete"])'));
    document.querySelectorAll('select[name="route"]').forEach(installRouteChoices);
    document.querySelectorAll('select[multiple][name="shopping_list_ids"]').forEach(installListChoices);
    document.querySelectorAll('select[name="route"]').forEach(function(select){updateListChoiceState(select.closest('form'));});

    function styleTargetCards(){
        targetForms.forEach(function(targetForm){
            var wrapper=targetForm.parentElement;if(!wrapper||wrapper.classList.contains('b2m-target-card'))return;
            wrapper.classList.add('b2m-target-card',targetForm.querySelector('.target-unit-select')?'b2m-target-food':'b2m-target-recipe');
            var heading=wrapper.querySelector(':scope > .d-flex');if(heading)heading.classList.add('b2m-target-heading');targetForm.classList.add('b2m-target-body');
            var remove=wrapper.querySelector('form[action$="/delete"] button');if(remove){remove.className='btn btn-icon btn-outline-danger b2m-target-remove';remove.title='Remove target';}
            wrapper.querySelectorAll('.text-secondary.small').forEach(function(el){el.textContent=el.textContent.replace(/ · target #\d+/,'');});
            var ownSave=targetForm.querySelector('button[type="submit"]');if(ownSave)ownSave.closest('.text-end')?.classList.add('d-none');
            targetForm.addEventListener('input',markDirty);targetForm.addEventListener('change',markDirty);
        });
    }
    styleTargetCards();

    var saveAllButton=null, saveAllStatus=null;
    function markDirty(){if(saveAllButton){saveAllButton.disabled=false;saveAllButton.classList.add('btn-primary');saveAllButton.classList.remove('btn-outline-primary');}if(saveAllStatus){saveAllStatus.textContent='Unsaved changes';saveAllStatus.className='b2m-target-save-status text-warning me-2';}}

    function installHeaderActions(){
        var title=Array.from(document.querySelectorAll('h3.card-title')).find(function(el){return el.textContent.trim().startsWith('Current targets');});if(!title||!barcode)return;
        var header=title.closest('.card-header');if(!header)return;header.classList.add('d-flex','align-items-center');
        var actions=header.querySelector('.card-actions')||document.createElement('div');actions.className='card-actions ms-auto d-flex align-items-center gap-2';if(!actions.parentElement)header.appendChild(actions);
        if(targetForms.length&&!document.getElementById('save-all-targets')){
            saveAllStatus=document.createElement('span');saveAllStatus.className='b2m-target-save-status text-secondary me-2';
            saveAllButton=document.createElement('button');saveAllButton.id='save-all-targets';saveAllButton.type='button';saveAllButton.className='btn btn-sm btn-outline-primary';saveAllButton.innerHTML='<i class="ti ti-device-floppy icon"></i> Save all targets';
            actions.prepend(saveAllButton);actions.prepend(saveAllStatus);
            saveAllButton.addEventListener('click',async function(){
                saveAllButton.disabled=true;saveAllStatus.className='b2m-target-save-status text-secondary me-2';saveAllStatus.textContent='Saving…';
                try{
                    for(var i=0;i<targetForms.length;i++){
                        var response=await fetch(targetForms[i].action,{method:'POST',body:new FormData(targetForms[i]),headers:{'X-Requested-With':'fetch'}});
                        if(!response.ok)throw new Error('Target '+(i+1)+' could not be saved');
                    }
                    saveAllStatus.className='b2m-target-save-status text-success me-2';saveAllStatus.textContent='Saved';
                    window.location.replace(window.location.pathname+'?targets_saved=1');
                }catch(error){saveAllButton.disabled=false;saveAllStatus.className='b2m-target-save-status text-danger me-2';saveAllStatus.textContent=error.message;}
            });
        }
        if(!header.querySelector('.b2m-clear-targets')){
            var clear=document.createElement('form');clear.method='post';clear.action='/barcodes/'+encodeURIComponent(barcode)+'/unmap';clear.dataset.confirm='Clear all targets for this barcode?';clear.innerHTML='<button type="submit" class="btn btn-sm btn-outline-danger b2m-clear-targets"><i class="ti ti-trash icon"></i> Clear all</button>';actions.appendChild(clear);
        }
    }
    installHeaderActions();

    async function loadEffectiveDestinations(){
        if(!barcode||!targetForms.length)return;
        try{
            var r=await fetch('/api/barcode-destination?barcode='+encodeURIComponent(barcode),{headers:{'Accept':'application/json'}});if(!r.ok)return;var data=await r.json();
            (data.targets||[]).forEach(function(target){
                var targetForm=targetForms.find(function(f){return targetIdForForm(f)===Number(target.id);});if(!targetForm)return;
                targetForm.dataset.effectiveRoute=target.effective_route||'';
                var route=targetForm.querySelector('select[name="route"]');if(route)applyInheritedState(route);
                if(route&&route.value==='inherit'){
                    var listBox=targetForm.querySelector('.b2m-list-choice-grid');
                    (target.shopping_lists||[]).forEach(function(list){var card=listBox&&listBox.querySelector('[data-list-id="'+CSS.escape(String(list.id))+'"]');if(card&&!card.querySelector('input').checked)card.classList.add('b2m-inherited-active');});
                }
            });
        }catch(e){}
    }
    loadEffectiveDestinations();

    function installTestSend(){
        if(!barcode||!targetForms.length)return;var list=document.querySelector('.page-header .btn-list');if(!list||document.getElementById('barcode-test-send'))return;
        var result=document.createElement('span');result.id='barcode-test-result';result.className='small text-secondary align-self-center';
        var button=document.createElement('button');button.type='button';button.id='barcode-test-send';button.className='btn btn-outline-primary';button.innerHTML='<i class="ti ti-send icon"></i> Test send';
        list.insertBefore(result,list.firstChild);list.insertBefore(button,result);
        button.addEventListener('click',async function(){
            var old=button.innerHTML;button.disabled=true;result.className='small text-secondary align-self-center';result.textContent='Sending…';
            try{var response=await fetch('/api/barcodes/'+encodeURIComponent(barcode)+'/test-route',{method:'POST',headers:{'Accept':'application/json'}});var data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||data.result||'Test send failed');button.className='btn btn-success';button.innerHTML='<i class="ti ti-check icon"></i> Sent';result.className='small text-success align-self-center';result.textContent='OK · '+data.duration_ms+' ms · '+data.success_count+'/'+data.target_count;setTimeout(function(){button.className='btn btn-outline-primary';button.innerHTML=old;button.disabled=false;},2200);}
            catch(error){button.className='btn btn-outline-danger';button.innerHTML='<i class="ti ti-alert-triangle icon"></i> Failed';result.className='small text-danger align-self-center';result.textContent=error.message;setTimeout(function(){button.className='btn btn-outline-primary';button.innerHTML=old;button.disabled=false;},3500);}
        });
    }
    installTestSend();

    function polishRecipePicker(){var selected=document.getElementById('recipe-selected-name');if(selected)selected.classList.add('fw-bold','fs-3');var results=document.getElementById('recipe-search-results');if(!results)return;function clean(){results.querySelectorAll('code').forEach(function(code){code.remove();});results.querySelectorAll('.list-group-item').forEach(function(row){var name=row.querySelector('span');if(name)name.classList.add('fw-semibold');});}clean();new MutationObserver(clean).observe(results,{childList:true,subtree:true});}
    polishRecipePicker();
})();
