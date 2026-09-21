/* Apply theme before render to prevent FOUC.
 * Server renders the correct data-bs-theme* attributes on <html>,
 * so this script only needs to handle the navbar quick-toggle override
 * stored in localStorage (if the user toggled dark/light without saving).
 */
(function() {
    var override = localStorage.getItem('theme-mode-override');
    if (override) {
        document.documentElement.setAttribute('data-bs-theme', override);
    }

    /* Global UI v2 layer. Loaded from self so the strict CSP stays intact. */
    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/css/ui-v2.css?v=2';
    document.head.appendChild(link);

    var script = document.createElement('script');
    script.src = '/static/js/ui-v2.js?v=2';
    script.async = false;
    document.head.appendChild(script);

    /* Corrective UI v3 layer. Keep this after v2 so it can normalize legacy
       dynamically-created controls without weakening the CSP. */
    var linkV3 = document.createElement('link');
    linkV3.rel = 'stylesheet';
    linkV3.href = '/static/css/ui-v3.css?v=2026.09.21.2';
    document.head.appendChild(linkV3);

    var guardV3 = document.createElement('script');
    guardV3.src = '/static/js/ui-v3-guard.js?v=2026.09.21.2';
    guardV3.async = false;
    document.head.appendChild(guardV3);

    var scriptV3 = document.createElement('script');
    scriptV3.src = '/static/js/ui-v3.js?v=2026.09.21.2';
    scriptV3.async = false;
    document.head.appendChild(scriptV3);

    if (window.location.pathname === '/settings') {
        var themePreview = document.createElement('script');
        themePreview.src = '/static/js/theme-live-v2.js?v=2';
        themePreview.async = false;
        document.head.appendChild(themePreview);
    }

    if (window.location.pathname === '/labels') {
        var resizePatch = document.createElement('script');
        resizePatch.src = '/static/js/labels-b21-v2-patch.js?v=2';
        resizePatch.async = false;
        document.head.appendChild(resizePatch);
    }
})();
