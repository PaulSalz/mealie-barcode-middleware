(function(){
  'use strict';
  if(window.location.pathname!=='/labels')return;

  let installed=false;
  const $=id=>document.getElementById(id);

  function profileSize(stage){
    const match=String(stage.style.aspectRatio||'').match(/([\d.]+)\s*\/\s*([\d.]+)/);
    return {width:match?Number(match[1]):50,height:match?Number(match[2]):30};
  }
  function rotationOf(node){
    const value=getComputedStyle(node).transform;
    if(!value||value==='none')return 0;
    const match=value.match(/^matrix\(([^)]+)\)$/);
    if(!match)return 0;
    const values=match[1].split(',').map(Number);
    return Math.atan2(values[1]||0,values[0]||1);
  }
  function positionHandle(stage,handle,box,visual){
    if(!stage||!handle||!box||!visual||!box.isConnected)return;
    const sr=stage.getBoundingClientRect(),vr=visual.getBoundingClientRect();
    const cx=(vr.left+vr.right)/2,cy=(vr.top+vr.bottom)/2;
    const width=visual.offsetWidth||box.offsetWidth,height=visual.offsetHeight||box.offsetHeight;
    const angle=rotationOf(box),cos=Math.cos(angle),sin=Math.sin(angle);
    const left=cx+cos*width/2-sin*height/2-sr.left;
    const top=cy+sin*width/2+cos*height/2-sr.top;
    const leftValue=left+'px',topValue=top+'px';
    if(handle.style.left!==leftValue)handle.style.left=leftValue;
    if(handle.style.top!==topValue)handle.style.top=topValue;
  }
  window.__b2mPositionB21ResizeHandle=positionHandle;
  function currentCodeKind(image){
    try{
      const url=new URL(image&&image.src||'',window.location.href);
      let kind=String(url.searchParams.get('kind')||'auto').toLowerCase();
      const value=url.searchParams.get('value')||'';
      if(kind==='auto')kind=/^[\x00-\x7f]*$/.test(value)&&value.length<=32?'code128':'qr';
      return kind;
    }catch(e){return 'auto';}
  }

  function install(){
    if(installed)return true;
    const stage=$('b21-label-stage'),w=$('b21-v2-w'),h=$('b21-v2-h');
    if(!stage||!w||!h)return false;
    installed=true;

    function installCodeHandle(){
      const selected=stage.querySelector('img.b21-v2-element-selected, img.b21-code.b21-v2-element-selected');
      let handle=$('b21-v2-code-resize-handle');
      if(!selected){if(handle)handle.remove();return;}
      const box=selected.closest('.b21-code-box')||selected;
      const visual=selected.closest('.b21-code-content')||selected;
      const position=()=>positionHandle(stage,handle,box,visual);
      if(handle){position();return;}

      handle=document.createElement('span');
      handle.id='b21-v2-code-resize-handle';
      handle.className='b21-v2-resize-handle';
      handle.style.right='auto';
      handle.style.bottom='auto';
      handle.style.transform='translate(-50%,-50%)';
      stage.appendChild(handle);
      position();

      handle.addEventListener('pointerdown',function(event){
        const active=stage.querySelector('img.b21-v2-element-selected, img.b21-code.b21-v2-element-selected');
        if(!active)return;
        const activeBox=active.closest('.b21-code-box')||active;
        const activeVisual=active.closest('.b21-code-content')||active;
        const dimensions=profileSize(stage);
        const kind=currentCodeKind(active);
        const originalWidthMm=(activeBox.offsetWidth||active.offsetWidth)/Math.max(1,stage.clientWidth)*dimensions.width;
        const originalHeightMm=(activeBox.offsetHeight||active.offsetHeight)/Math.max(1,stage.clientHeight)*dimensions.height;
        if(!originalWidthMm||!originalHeightMm)return;
        event.preventDefault();event.stopPropagation();
        const sx=event.clientX,sy=event.clientY,angle=rotationOf(activeBox);
        handle.setPointerCapture(event.pointerId);

        function move(e){
          const dx=(e.clientX-sx)/Math.max(1,stage.clientWidth)*dimensions.width;
          const dy=(e.clientY-sy)/Math.max(1,stage.clientHeight)*dimensions.height;
          const localX=dx*Math.cos(angle)+dy*Math.sin(angle);
          const localY=-dx*Math.sin(angle)+dy*Math.cos(angle);
          let newWidthMm,newHeightMm;
          if(kind==='qr'){
            const maxSideMm=Math.max(.5,Math.min(dimensions.width,dimensions.height));
            const minSideMm=Math.min(maxSideMm,Math.max(dimensions.width*.02,dimensions.height*.02));
            const sideMm=Math.max(minSideMm,Math.min(maxSideMm,Math.min(originalWidthMm,originalHeightMm)+localX+localY));
            newWidthMm=sideMm;
            newHeightMm=sideMm;
          }else{
            newWidthMm=Math.max(Math.min(2,dimensions.width),Math.min(dimensions.width,originalWidthMm+2*localX));
            newHeightMm=Math.max(Math.min(1,dimensions.height),Math.min(dimensions.height,originalHeightMm+2*localY));
          }
          const widthPct=newWidthMm/dimensions.width*100;
          const heightPct=newHeightMm/dimensions.height*100;

          w.value=String(widthPct);
          h.value=String(heightPct);
          activeBox.style.width=widthPct+'%';
          activeBox.style.height=heightPct+'%';
          activeVisual.style.width='100%';
          activeVisual.style.height='100%';
          active.style.width='100%';
          active.style.height='100%';
          positionHandle(stage,handle,activeBox,activeVisual);
        }
        function end(e){
          try{handle.releasePointerCapture(e.pointerId);}catch(ignore){}
          handle.removeEventListener('pointermove',move);
          handle.removeEventListener('pointerup',end);
          handle.removeEventListener('pointercancel',end);
          const editor=window.__b2mB21LabelEditor;
          if(editor&&typeof editor.setCodeDimensions==='function')editor.setCodeDimensions(Number(w.value),Number(h.value));
        }
        handle.addEventListener('pointermove',move);
        handle.addEventListener('pointerup',end);
        handle.addEventListener('pointercancel',end);
      });
    }

    let pending=false;
    new MutationObserver(function(records){
      if(records.length&&records.every(function(record){return record.target.id==='b21-v2-code-resize-handle';}))return;
      if(pending)return;
      pending=true;
      requestAnimationFrame(function(){pending=false;installCodeHandle();});
    }).observe(stage,{childList:true,subtree:true,attributes:true,attributeFilter:['class','style']});
    stage.addEventListener('click',function(){requestAnimationFrame(installCodeHandle);});
    document.querySelectorAll('input[name="label-output"]').forEach(function(input){
      input.addEventListener('change',function(){
        if(input.checked&&input.value==='b21'){
          requestAnimationFrame(function(){
            const select=$('b21-entry-select');
            if(select)select.dispatchEvent(new Event('change',{bubbles:true}));
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
