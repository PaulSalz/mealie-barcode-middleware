(function(){
  'use strict';
  if(window.location.pathname!=='/settings')return;
  const params=new URLSearchParams(window.location.search);
  if((params.get('tab')||'mealie')!=='appearance')return;

  function wait(){
    const form=document.querySelector('form[action="/settings/theme"]');
    const epaper=document.getElementById('theme-epaper');
    const contrast=document.getElementById('theme-contrast');
    if(!form||!epaper||!contrast){setTimeout(wait,120);return;}

    let link=document.getElementById('b2m-theme-live-link');
    if(!link){link=document.createElement('link');link.id='b2m-theme-live-link';link.rel='stylesheet';document.head.appendChild(link);}
    const inline=document.getElementById('b2m-theme-live-preview');if(inline)inline.textContent='';

    function checked(name,fallback){return form.querySelector('input[name="'+name+'"]:checked')?.value||fallback;}
    function update(){
      const query=new URLSearchParams({
        mode:checked('theme_mode','light'),
        color:checked('theme_color','blue'),
        font:checked('theme_font','sans-serif'),
        base:checked('theme_base','gray'),
        radius:checked('theme_radius','1'),
        epaper:epaper.checked?'true':'false',
        contrast:String(contrast.value||65),
        date_style:checked('theme_date_style','medium'),
        _:String(Date.now())
      });
      link.href='/api/theme/live.css?'+query.toString();
    }
    let timer=null;
    function schedule(){clearTimeout(timer);timer=setTimeout(update,20);}
    form.addEventListener('input',schedule,true);form.addEventListener('change',schedule,true);
    epaper.addEventListener('change',schedule);contrast.addEventListener('input',schedule);
    contrast.addEventListener('dblclick',function(){contrast.value='65';const out=document.getElementById('theme-contrast-value');if(out)out.textContent='65';schedule();});
    update();
  }
  wait();
})();
