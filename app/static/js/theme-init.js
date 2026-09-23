/* Apply persisted theme before render, then load behavior-only UI layers. */
(function() {
    'use strict';

    var version = '2026.09.23.4';

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

    function script(path) {
        var node = document.createElement('script');
        node.src = path + '?v=' + version;
        node.async = false;
        document.head.appendChild(node);
    }

    // /user-theme.css and all global UI styles are linked directly from
    // base.html. They are therefore render-blocking and cannot change layout
    // after the first painted frame.
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

    script('/static/js/ui-v4.js');
    script('/static/js/ui-v6.js');
    script('/static/js/ui-v9.js');
    script('/static/js/ui-v23.js');
    script('/static/js/ui-v24.js');
    script('/static/js/ui-v25.js');
    script('/static/js/ui-v26.js');
    script('/static/js/ui-v27.js');

    // Physical scanner receipt timing remains the early /scanner/received event.
    script('/static/js/ui-v12-bell.js');

    if (window.location.pathname === '/profile/appearance') {
        script('/static/js/profile-live-v27.js');
    }

    if (window.location.pathname === '/settings') {
        script('/static/js/theme-live-v2.js');
    }

    if (window.location.pathname === '/actions/new' || /^\/actions\/[^/]+$/.test(window.location.pathname)) {
        script('/static/js/action-v22.js');
        script('/static/js/action-v23.js');
        script('/static/js/action-v24.js');
    }

    if (window.location.pathname === '/labels') {
        script('/static/js/labels-b21-v2.js');
        script('/static/js/labels-b21-v2-patch.js');
        script('/static/js/labels-b21-v4.js');
        script('/static/js/ui-v13-fixes.js');
        script('/static/js/labels-v18.js');
        script('/static/js/labels-v22.js');
        script('/static/js/labels-v23.js');
        script('/static/js/labels-v24.js');
    }

    if (window.location.pathname.startsWith('/barcodes/')) {
        script('/static/js/barcode-targets-v6.js');
    }
})();