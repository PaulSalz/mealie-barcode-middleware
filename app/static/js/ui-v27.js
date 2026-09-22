(function () {
  'use strict';

  /* app.js persists the mode server-side but historically removed the early-paint
     cache. Re-store it after the click handler so the next navigation starts in
     the correct mode before /api/theme finishes. */
  document.addEventListener('click', function (event) {
    var target = event.target.closest && event.target.closest('#theme-toggle-dark,#theme-toggle-light,#theme-toggle-dark-mobile,#theme-toggle-light-mobile');
    if (!target) return;
    var mode = target.id.indexOf('dark') !== -1 ? 'dark' : 'light';
    window.setTimeout(function () { localStorage.setItem('theme-mode-override', mode); }, 0);
  }, true);
})();
