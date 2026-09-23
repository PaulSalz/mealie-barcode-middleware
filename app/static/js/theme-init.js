/* Apply and refresh persisted personal theme state before the rest of the UI starts. */
(function() {
    'use strict';

    var root = document.documentElement;
    var override = localStorage.getItem('theme-mode-override');
    if (override === 'light' || override === 'dark') {
        root.setAttribute('data-bs-theme', override);
    }

    /* base.html historically applied cached base/e-paper values before CSS and
       this file then replaced them with /api/theme (the global theme). That made
       personal background/e-paper settings flash and then revert. The personal
       /user-theme.css is render blocking, so discard those stale marker classes
       here and restore only the authenticated user's effective values below. */
    delete root.dataset.b2mBase;
    root.classList.remove('b2m-epaper-v9');
    root.classList.remove('b2m-epaper');

    fetch('/api/appearance-v24', {headers:{Accept:'application/json'}, cache:'no-store'})
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(data){
            var theme = data && data.theme;
            if (!theme) return;
            if (theme.mode === 'light' || theme.mode === 'dark') {
                root.setAttribute('data-bs-theme', theme.mode);
                localStorage.setItem('theme-mode-override', theme.mode);
            }
            if (theme.base) {
                root.dataset.b2mBase = theme.base;
                localStorage.setItem('theme-base-override', theme.base);
            }
            var mono = theme.epaper === 'true';
            root.classList.toggle('b2m-epaper-v9', mono);
            root.classList.toggle('b2m-epaper', mono);
            localStorage.setItem('theme-epaper-override', mono ? 'true' : 'false');
        })
        .catch(function(){});
})();
