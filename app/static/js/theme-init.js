/* Apply persisted theme before render, then load the current UI layers. */
(function() {
    'use strict';

    var version = '2026.09.23.3';

    /* Reserve scrollbar width before body layout so the navbar does not jump
       horizontally when Items/Barcodes content makes the page scrollable. */
    var earlyStyle = document.createElement('style');
    earlyStyle.textContent = 'html{overflow-y:scroll;scrollbar-gutter:stable}';
    document.head.appendChild(earlyStyle);

    function preloadFont(path) {
        var link = document.createElement('link');
        link.rel = 'preload';
        link.as = 'font';
        link.type = 'font/woff2';
        link.crossOrigin = 'anonymous';
        link.href = path;
        document.head.appendChild(link);
    }
    preloadFont('/static/vendor/inter/InterVariable.woff2');
    preloadFont('/static/vendor/tabler-icons/fonts/tabler-icons.woff2?v3.44.0');

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

    function stylesheet(path) {
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = path + '?v=' + version;
        document.head.appendChild(link);
    }
    function script(path) {
        var node = document.createElement('script');
        node.src = path + '?v=' + version;
        node.async = false;
        document.head.appendChild(node);
    }

    stylesheet('/static/css/ui-v2.css');
    stylesheet('/static/css/ui-v4.css');
    stylesheet('/static/css/ui-v6.css');
    stylesheet('/static/css/ui-v9.css');
    stylesheet('/static/css/ui-v17.css');
    stylesheet('/static/css/ui-v22.css');
    stylesheet('/static/css/ui-v23.css');
    stylesheet('/static/css/ui-v24.css');
    stylesheet('/static/css/ui-v25.css');
    stylesheet('/static/css/ui-v27.css');

    // /user-theme.css is linked directly from base.html so it participates in
    // render blocking and the first painted frame already uses the user's accent.
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

    /* Shopping-print-v5 used to monkey-patch the legacy shopping-print client.
       The current page owns these behaviors directly and must not load that patch
       a second time. */

    if (window.location.pathname === '/settings') {
        script('/static/js/theme-live-v2.js');
    }

    if (window.location.pathname === '/actions/new' || /^\/actions\/[^/]+$/.test(window.location.pathname)) {
        script('/static/js/action-v22.js');
        script('/static/js/action-v23.js');
        script('/static/js/action-v24.js');
    }

    if (window.location.pathname === '/labels') {
        stylesheet('/static/css/ui-v13.css');
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