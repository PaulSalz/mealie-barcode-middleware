/* Apply persisted theme before render, then load the single current UI layer. */
(function() {
    'use strict';

    var override = localStorage.getItem('theme-mode-override');
    if (override) document.documentElement.setAttribute('data-bs-theme', override);

    var legacyCss = document.createElement('link');
    legacyCss.rel = 'stylesheet';
    legacyCss.href = '/static/css/ui-v2.css?v=2026.09.21.3';
    document.head.appendChild(legacyCss);

    var uiCss = document.createElement('link');
    uiCss.rel = 'stylesheet';
    uiCss.href = '/static/css/ui-v4.css?v=2026.09.21.3';
    document.head.appendChild(uiCss);

    var ui = document.createElement('script');
    ui.src = '/static/js/ui-v4.js?v=2026.09.21.3';
    ui.async = false;
    document.head.appendChild(ui);

    if (window.location.pathname === '/settings') {
        var themePreview = document.createElement('script');
        themePreview.src = '/static/js/theme-live-v2.js?v=2026.09.21.3';
        themePreview.async = false;
        document.head.appendChild(themePreview);
    }

    if (window.location.pathname === '/labels') {
        var designer = document.createElement('script');
        designer.src = '/static/js/labels-b21-v2.js?v=2026.09.21.3';
        designer.async = false;
        document.head.appendChild(designer);

        var resizePatch = document.createElement('script');
        resizePatch.src = '/static/js/labels-b21-v2-patch.js?v=2026.09.21.3';
        resizePatch.async = false;
        document.head.appendChild(resizePatch);

        var v4Patch = document.createElement('script');
        v4Patch.src = '/static/js/labels-b21-v4.js?v=2026.09.21.3';
        v4Patch.async = false;
        document.head.appendChild(v4Patch);
    }
})();
