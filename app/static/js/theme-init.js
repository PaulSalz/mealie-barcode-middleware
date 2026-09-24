/* Keep the server-rendered personal theme stable and refresh the local cache. */
(function() {
    'use strict';

    var root = document.documentElement;
    var startedAtMutation = Number(window.__b2mThemeMutationVersion || 0);

    /* base.html now renders the effective personal mode before first paint.
       The local cache is only a navigation fallback. Never clear cached
       base/e-paper here: doing so causes a flash back to the default theme. */
    try {
        var mode = localStorage.getItem('theme-mode-override');
        if ((mode === 'light' || mode === 'dark') && !root.getAttribute('data-bs-theme')) {
            root.setAttribute('data-bs-theme', mode);
        }
        var base = localStorage.getItem('theme-base-override');
        if (base && !root.dataset.b2mBase) root.dataset.b2mBase = base;
        var epaper = localStorage.getItem('theme-epaper-override');
        if (epaper === 'true' || epaper === 'false') {
            var enabled = epaper === 'true';
            root.classList.toggle('b2m-epaper-v9', enabled);
            root.classList.toggle('b2m-epaper', enabled);
        }
    } catch (e) {}

    fetch('/api/appearance-v24', {headers:{Accept:'application/json'}, cache:'no-store'})
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(data){
            /* A navbar click or live Appearance edit may have happened while this
               request was in flight. Never let an older bootstrap response undo it. */
            if (Number(window.__b2mThemeMutationVersion || 0) !== startedAtMutation) return;
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
