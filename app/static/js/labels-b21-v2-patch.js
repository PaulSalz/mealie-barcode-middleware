(function(){
  'use strict';
  if(window.location.pathname!=='/labels')return;

  function wait(){
    const stage=document.getElementById('b21-label-stage');
    const w=document.getElementById('b21-v2-w');
    const h=document.getElementById('b21-v2-h');
    if(!stage||!w||!h){setTimeout(wait,160);return;}

    function installCodeHandle(){
      const old=document.getElementById('b21-v2-code-resize-handle');if(old)old.remove();
      const selected=stage.querySelector('img.b21-v2-element-selected, img.b21-code.b21-v2-element-selected');
      if(!selected)return;
      const sr=stage.getBoundingClientRect(),r=selected.getBoundingClientRect();
      const handle=document.createElement('span');handle.id='b21-v2-code-resize-handle';handle.className='b21-v2-resize-handle';
      handle.style.left=(r.right-sr.left)+'px';handle.style.top=(r.bottom-sr.top)+'px';handle.style.right='auto';handle.style.bottom='auto';handle.style.transform='translate(-50%,-50%)';
      stage.appendChild(handle);
      handle.addEventListener('pointerdown',function(event){
        event.preventDefault();event.stopPropagation();const sx=event.clientX,sy=event.clientY,ow=Number(w.value),oh=Number(h.value);handle.setPointerCapture(event.pointerId);
        function move(e){const nw=Math.max(2,Math.min(100,ow+(e.clientX-sx)/sr.width*100)),nh=Math.max(1,Math.min(100,oh+(e.clientY-sy)/sr.height*100));w.value=nw;h.value=nh;selected.style.width=nw+'%';selected.style.height=nh+'%';handle.style.left=(selected.getBoundingClientRect().right-sr.left)+'px';handle.style.top=(selected.getBoundingClientRect().bottom-sr.top)+'px';}
        function end(e){try{handle.releasePointerCapture(e.pointerId);}catch(ignore){}handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',end);handle.removeEventListener('pointercancel',end);w.dispatchEvent(new Event('input',{bubbles:true}));h.dispatchEvent(new Event('input',{bubbles:true}));}
        handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',end);
      });
    }

    let pending=false;
    new MutationObserver(function(){if(pending)return;pending=true;requestAnimationFrame(function(){pending=false;installCodeHandle();});}).observe(stage,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
    stage.addEventListener('click',function(){setTimeout(installCodeHandle,0);});
    document.querySelectorAll('input[name="label-output"]').forEach(function(input){input.addEventListener('change',function(){if(input.checked&&input.value==='b21'){setTimeout(function(){const select=document.getElementById('b21-entry-select');if(select)select.dispatchEvent(new Event('change',{bubbles:true}));installCodeHandle();},20);}});});
    installCodeHandle();
  }
  wait();
})();
