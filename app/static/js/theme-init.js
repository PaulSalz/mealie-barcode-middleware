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

    var releaseCss = document.createElement('link');
    releaseCss.rel = 'stylesheet';
    releaseCss.href = '/static/css/release-ui.css?v=20260920.2';
    document.head.appendChild(releaseCss);

    // Release-scoped UI additions are isolated from the stable app/enhancements
    // bundles. The file waits for DOMContentLoaded before touching the page.
    var releaseUi = document.createElement('script');
    releaseUi.src = '/static/js/release-ui.js?v=20260920.2';
    releaseUi.defer = true;
    document.head.appendChild(releaseUi);
})();
