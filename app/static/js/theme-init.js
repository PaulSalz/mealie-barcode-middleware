/* Apply persisted theme before render, then load the current UI layers. */
(function() {
    'use strict';

    var override = localStorage.getItem('theme-mode-override');
    if (override) document.documentElement.setAttribute('data-bs-theme', override);

    var legacyCss = document.createElement('link');
    legacyCss.rel = 'stylesheet';
    legacyCss.href = '/static/css/ui-v2.css?v=2026.09.21.17';
    document.head.appendChild(legacyCss);

    var uiCss = document.createElement('link');
    uiCss.rel = 'stylesheet';
    uiCss.href = '/static/css/ui-v4.css?v=2026.09.21.17';
    document.head.appendChild(uiCss);

    var v6Css = document.createElement('link');
    v6Css.rel = 'stylesheet';
    v6Css.href = '/static/css/ui-v6.css?v=2026.09.21.17';
    document.head.appendChild(v6Css);

    var v9Css = document.createElement('link');
    v9Css.rel = 'stylesheet';
    v9Css.href = '/static/css/ui-v9.css?v=2026.09.21.17';
    document.head.appendChild(v9Css);

    // One final bell layer. Older v12/v14/v16 bell-only styles are no longer
    // loaded, so the notification control uses the native Tabler nav-link look.
    var v17Css = document.createElement('link');
    v17Css.rel = 'stylesheet';
    v17Css.href = '/static/css/ui-v17.css?v=2026.09.21.17';
    document.head.appendChild(v17Css);

    var ui = document.createElement('script');
    ui.src = '/static/js/ui-v4.js?v=2026.09.21.17';
    ui.async = false;
    document.head.appendChild(ui);

    var v6 = document.createElement('script');
    v6.src = '/static/js/ui-v6.js?v=2026.09.21.17';
    v6.async = false;
    document.head.appendChild(v6);

    var v9 = document.createElement('script');
    v9.src = '/static/js/ui-v9.js?v=2026.09.21.17';
    v9.async = false;
    document.head.appendChild(v9);

    // Listen to the physical scanner receipt event. This is the same early event
    // that drives the fast dashboard scan feedback; no routing/Mealie wait.
    var bell = document.createElement('script');
    bell.src = '/static/js/ui-v12-bell.js?v=2026.09.21.17';
    bell.async = false;
    document.head.appendChild(bell);

    if (window.location.pathname === '/settings') {
        var themePreview = document.createElement('script');
        themePreview.src = '/static/js/theme-live-v2.js?v=2026.09.21.17';
        themePreview.async = false;
        document.head.appendChild(themePreview);
    }

    if (window.location.pathname === '/labels') {
        // v13 CSS is retained only where its label preset styles are needed;
        // its old bell overrides are therefore not active application-wide.
        var v13Css = document.createElement('link');
        v13Css.rel = 'stylesheet';
        v13Css.href = '/static/css/ui-v13.css?v=2026.09.21.17';
        document.head.appendChild(v13Css);

        var designer = document.createElement('script');
        designer.src = '/static/js/labels-b21-v2.js?v=2026.09.21.17';
        designer.async = false;
        document.head.appendChild(designer);

        var resizePatch = document.createElement('script');
        resizePatch.src = '/static/js/labels-b21-v2-patch.js?v=2026.09.21.17';
        resizePatch.async = false;
        document.head.appendChild(resizePatch);

        var v4Patch = document.createElement('script');
        v4Patch.src = '/static/js/labels-b21-v4.js?v=2026.09.21.17';
        v4Patch.async = false;
        document.head.appendChild(v4Patch);

        var v13Fixes = document.createElement('script');
        v13Fixes.src = '/static/js/ui-v13-fixes.js?v=2026.09.21.17';
        v13Fixes.async = false;
        document.head.appendChild(v13Fixes);
    }

    if (window.location.pathname.startsWith('/barcodes/')) {
        var targets = document.createElement('script');
        targets.src = '/static/js/barcode-targets-v6.js?v=2026.09.21.17';
        targets.async = false;
        document.head.appendChild(targets);
    }
})();
