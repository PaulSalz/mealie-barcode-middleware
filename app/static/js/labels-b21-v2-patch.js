(function(){
  'use strict';
  if(window.location.pathname!=='/labels')return;

  let installed=false;

  function install(){
    if(installed)return true;
    const stage=document.getElementById('b21-label-stage');
    const w=document.getElementById('b21-v2-w');
    const h=document.getElementById('b21-v2-h');
    if(!stage||!w||!h)return false;
    installed=true;

    function installCodeHandle(){
      const selected=stage.querySelector('img.b21-v2-element-selected, img.b21-code.b21-v2-element-selected');
      let handle=document.getElementById('b21-v2-code-resize-handle');
      if(!selected){if(handle)handle.remove();return;}

      function position(){
        if(!handle||!selected.isConnected)return;
        const sr=stage.getBoundingClientRect(),r=selected.getBoundingClientRect();
        handle.style.left=(r.right-sr.left)+'px';
        handle.style.top=(r.bottom-sr.top)+'px';
      }

      if(handle){position();return;}
      handle=document.createElement('span');handle.id='b21-v2-code-resize-handle';handle.className='b21-v2-resize-handle';
      handle.style.right='auto';handle.style.bottom='auto';handle.style.transform='translate(-50%,-50%)';
      stage.appendChild(handle);position();
      handle.addEventListener('pointerdown',function(event){
        const active=stage.querySelector('img.b21-v2-element-selected, img.b21-code.b21-v2-element-selected');
        if(!active)return;
        event.preventDefault();event.stopPropagation();
        const sr=stage.getBoundingClientRect(),sx=event.clientX,sy=event.clientY,ow=Number(w.value),oh=Number(h.value);
        handle.setPointerCapture(event.pointerId);
        function move(e){
          const nw=Math.max(2,Math.min(100,ow+(e.clientX-sx)/sr.width*100));
          const nh=Math.max(1,Math.min(100,oh+(e.clientY-sy)/sr.height*100));
          w.value=nw;h.value=nh;active.style.width=nw+'%';active.style.height=nh+'%';
          const r=active.getBoundingClientRect();handle.style.left=(r.right-sr.left)+'px';handle.style.top=(r.bottom-sr.top)+'px';
        }
        function end(e){
          try{handle.releasePointerCapture(e.pointerId);}catch(ignore){}
          handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',end);handle.removeEventListener('pointercancel',end);
          w.dispatchEvent(new Event('input',{bubbles:true}));h.dispatchEvent(new Event('input',{bubbles:true}));
        }
        handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',end);
      });
    }

    let pending=false;
    new MutationObserver(function(records){
      if(records.every(function(record){return record.target.id==='b21-v2-code-resize-handle';}))return;
      if(pending)return;pending=true;
      requestAnimationFrame(function(){pending=false;installCodeHandle();});
    }).observe(stage,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
    stage.addEventListener('click',function(){requestAnimationFrame(installCodeHandle);});
    document.querySelectorAll('input[name="label-output"]').forEach(function(input){
      input.addEventListener('change',function(){
        if(input.checked&&input.value==='b21'){
          requestAnimationFrame(function(){
            const select=document.getElementById('b21-entry-select');if(select)select.dispatchEvent(new Event('change',{bubbles:true}));
            installCodeHandle();
          });
        }
      });
    });
    installCodeHandle();
    return true;
  }

  if(!install()){
    const observer=new MutationObserver(function(){if(install())observer.disconnect();});
    observer.observe(document.body,{childList:true,subtree:true});
  }
})();
