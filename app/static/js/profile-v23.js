(function(){
  'use strict';
  if(window.location.pathname!=='/profile/appearance') return;
  const form=document.querySelector('form[action="/profile/appearance"]');
  const contrast=document.getElementById('profile-contrast');
  if(contrast){
    const out=document.getElementById('profile-contrast-value');
    contrast.addEventListener('input',function(){if(out)out.textContent=this.value;});
  }
  if(!form||window.__b2mThemeV32Loaded)return;
  form.querySelectorAll('input[name="theme_mode"]').forEach(function(input){
    input.addEventListener('change',function(){if(this.checked)document.documentElement.setAttribute('data-bs-theme',this.value);});
  });
})();
