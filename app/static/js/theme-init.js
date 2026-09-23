/* Apply and refresh persisted theme state before the rest of the UI starts. */
(function() {
    'use strict';

    var override = localStorage.getItem('theme-mode-override');
    if (override === 'light' || override === 'dark') {
        document.documentElement.setAttribute('data-bs-theme', override);
    }
    var baseOverride = localStorage.getItem('theme-base-override');
    if (baseOverride) document.documentElement.dataset.b2mBase = baseOverride;
    var epaperOverride = localStorage.getItem('theme-epaper-override');
    if (epaperOverride === 'true' || epaperOverride === 'false') {
        document.documentElement.classList.toggle('b2m-epaper-v9', epaperOverride === 'true');
        document.documentElement.classList.toggle('b2m-epaper', epaperOverride === 'true');
    }

    fetch('/api/theme', {headers:{Accept:'application/json'}, cache:'no-store'})
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(theme){
            if (!theme) return;
            if (theme.mode === 'light' || theme.mode === 'dark') {
                document.documentElement.setAttribute('data-bs-theme', theme.mode);
                localStorage.setItem('theme-mode-override', theme.mode);
            }
            if (theme.base) {
                document.documentElement.dataset.b2mBase = theme.base;
                localStorage.setItem('theme-base-override', theme.base);
            }
            var mono = theme.epaper === 'true';
            document.documentElement.classList.toggle('b2m-epaper-v9', mono);
            document.documentElement.classList.toggle('b2m-epaper', mono);
            localStorage.setItem('theme-epaper-override', mono ? 'true' : 'false');
        })
        .catch(function(){});
})();