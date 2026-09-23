/* B21 editor cleanup after the canonical v22 controller. */
(function(){
  'use strict';
  if(window.location.pathname!=='/labels')return;
  if(window.__b2mLabelsV23Loaded)return;window.__b2mLabelsV23Loaded=true;

  function install(){
    const align=document.getElementById('b21-v2-align');
    if(!align)return false;
    if(align.dataset.b2mV23==='1')return true;align.dataset.b2mV23='1';

    // These align the object box on the physical label, not text inside it.
    const icons={left:'layout-align-left',hcenter:'layout-align-center',right:'layout-align-right'};
    Object.entries(icons).forEach(function(entry){
      const button=align.querySelector('[data-align="'+entry[0]+'"]');
      const icon=button&&button.querySelector('i');
      if(icon){icon.className='ti ti-'+entry[1];}
    });

    // v4 created a Label appearance wrapper for Frame + Threshold. v22 moved
    // both controls elsewhere, so remove the wrapper when it has no useful UI.
    const appearance=document.getElementById('b21-v4-label-appearance');
    if(appearance){
      const useful=Array.from(appearance.querySelectorAll('input,select,button')).some(function(el){
        return !el.closest('.d-none')&&!el.classList.contains('d-none')&&el.type!=='hidden';
      });
      if(!useful||!appearance.textContent.trim().replace(/Label appearance/i,''))appearance.remove();
      else {
        const visible=Array.from(appearance.children).some(function(el){return !el.classList.contains('d-none')&&el.offsetParent!==null;});
        if(!visible)appearance.remove();
      }
    }
    return true;
  }

  function start(){
    if(install())return;
    const observer=new MutationObserver(function(){if(install())observer.disconnect();});
    observer.observe(document.body,{childList:true,subtree:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
