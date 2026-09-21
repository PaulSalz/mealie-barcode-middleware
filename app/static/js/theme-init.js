/* Apply persisted theme before render, then load the current UI layers. */
(function() {
    'use strict';

    var override = localStorage.getItem('theme-mode-override');
    if (override) document.documentElement.setAttribute('data-bs-theme', override);

    var legacyCss = document.createElement('link');
    legacyCss.rel = 'stylesheet';
    legacyCss.href = '/static/css/ui-v2.css?v=2026.09.21.11';
    document.head.appendChild(legacyCss);

    var uiCss = document.createElement('link');
    uiCss.rel = 'stylesheet';
    uiCss.href = '/static/css/ui-v4.css?v=2026.09.21.11';
    document.head.appendChild(uiCss);

    var v6Css = document.createElement('link');
    v6Css.rel = 'stylesheet';
    v6Css.href = '/static/css/ui-v6.css?v=2026.09.21.11';
    document.head.appendChild(v6Css);

    var v9Css = document.createElement('link');
    v9Css.rel = 'stylesheet';
    v9Css.href = '/static/css/ui-v9.css?v=2026.09.21.11';
    document.head.appendChild(v9Css);

    var v11Css = document.createElement('link');
    v11Css.rel = 'stylesheet';
    v11Css.href = '/static/css/ui-v11.css?v=2026.09.21.11';
    document.head.appendChild(v11Css);

    var ui = document.createElement('script');
    ui.src = '/static/js/ui-v4.js?v=2026.09.21.11';
    ui.async = false;
    document.head.appendChild(ui);

    var v6 = document.createElement('script');
    v6.src = '/static/js/ui-v6.js?v=2026.09.21.11';
    v6.async = false;
    document.head.appendChild(v6);

    var v9 = document.createElement('script');
    v9.src = '/static/js/ui-v9.js?v=2026.09.21.11';
    v9.async = false;
    document.head.appendChild(v9);

    // Single bell controller: uses the existing /events EventSource and listens
    // to scan-start + scan-received before app.js handles the final scan result.
    var v11Bell = document.createElement('script');
    v11Bell.src = '/static/js/ui-v11-bell.js?v=2026.09.21.11';
    v11Bell.async = false;
    document.head.appendChild(v11Bell);

    if (window.location.pathname === '/settings') {
        var themePreview = document.createElement('script');
        themePreview.src = '/static/js/theme-live-v2.js?v=2026.09.21.11';
        themePreview.async = false;
        document.head.appendChild(themePreview);
    }

    if (window.location.pathname === '/labels') {
        var designer = document.createElement('script');
        designer.src = '/static/js/labels-b21-v2.js?v=2026.09.21.11';
        designer.async = false;
        document.head.appendChild(designer);

        var resizePatch = document.createElement('script');
        resizePatch.src = '/static/js/labels-b21-v2-patch.js?v=2026.09.21.11';
        resizePatch.async = false;
        document.head.appendChild(resizePatch);

        var v4Patch = document.createElement('script');
        v4Patch.src = '/static/js/labels-b21-v4.js?v=2026.09.21.11';
        v4Patch.async = false;
        document.head.appendChild(v4Patch);
    }

    if (window.location.pathname.startsWith('/barcodes/')) {
        var targets = document.createElement('script');
        targets.src = '/static/js/barcode-targets-v6.js?v=2026.09.21.11';
        targets.async = false;
        document.head.appendChild(targets);
    }
})();
