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
    script.defer = true;
    document.head.appendChild(script);

    if (window.location.pathname === '/settings') {
        var themePreview = document.createElement('script');
        themePreview.src = '/static/js/theme-live-v2.js?v=2';
        themePreview.defer = true;
        document.head.appendChild(themePreview);
    }

    if (window.location.pathname === '/labels') {
        var resizePatch = document.createElement('script');
        resizePatch.src = '/static/js/labels-b21-v2-patch.js?v=2';
        resizePatch.defer = true;
        document.head.appendChild(resizePatch);
    }
})();
