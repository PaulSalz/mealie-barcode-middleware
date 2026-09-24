/* Keep the server-rendered personal theme stable and refresh the local cache. */
(function() {
    'use strict';

    var root = document.documentElement;
    var startedAtMutation = Number(window.__b2mThemeMutationVersion || 0);
    var radiusMap = {'0':0,'0.5':.25,'1':.5,'1.5':.8,'2':1.1};

    function applyRadius(scale) {
        var key = Object.prototype.hasOwnProperty.call(radiusMap, String(scale)) ? String(scale) : '1';
        var r = radiusMap[key];
        root.style.setProperty('--tblr-border-radius-scale', key);
        root.style.setProperty('--tblr-border-radius', r + 'rem');
        root.style.setProperty('--tblr-border-radius-sm', Math.max(0, r * .72) + 'rem');
        root.style.setProperty('--tblr-border-radius-lg', Math.max(0, r * 1.45) + 'rem');
        root.style.setProperty('--tblr-border-radius-xl', Math.max(0, r * 1.9) + 'rem');
        try { localStorage.setItem('theme-radius-override', key); } catch (e) {}
    }

    /* /user-theme.css is render-blocking and already contains the saved personal
       palette/e-paper variables. Complete the radius variables synchronously before
       first paint, using the saved cache or the stylesheet scale as source. */
    try {
        var mode = localStorage.getItem('theme-mode-override');
        if ((mode === 'light' || mode === 'dark') && !root.getAttribute('data-bs-theme')) root.setAttribute('data-bs-theme', mode);
        var base = localStorage.getItem('theme-base-override');
        if (base && !root.dataset.b2mBase) root.dataset.b2mBase = base;
        var epaper = localStorage.getItem('theme-epaper-override');
        if (epaper === 'true' || epaper === 'false') {
            var enabled = epaper === 'true';
            root.classList.toggle('b2m-epaper-v9', enabled);
            root.classList.toggle('b2m-epaper', enabled);
        }
        var cachedRadius = localStorage.getItem('theme-radius-override');
        var cssRadius = getComputedStyle(root).getPropertyValue('--tblr-border-radius-scale').trim();
        applyRadius(cachedRadius || cssRadius || '1');
    } catch (e) { applyRadius('1'); }

    fetch('/api/appearance-v24', {headers:{Accept:'application/json'}, cache:'no-store'})
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(data){
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
            applyRadius(theme.radius || '1');
        })
        .catch(function(){});
})();
