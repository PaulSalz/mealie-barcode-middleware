/* Apply persisted theme before render, then load the current UI layers. */
(function() {
    'use strict';

    var version = '2026.09.22.1';
    var override = localStorage.getItem('theme-mode-override');
    if (override) document.documentElement.setAttribute('data-bs-theme', override);

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

    script('/static/js/ui-v4.js');
    script('/static/js/ui-v6.js');
    script('/static/js/ui-v9.js');

    // Physical scanner receipt timing remains the early /scanner/received event.
    script('/static/js/ui-v12-bell.js');

    if (window.location.pathname === '/settings') {
        script('/static/js/theme-live-v2.js');
    }

    if (window.location.pathname === '/actions/new' || /^\/actions\/[^/]+$/.test(window.location.pathname)) {
        script('/static/js/action-v22.js');
    }

    if (window.location.pathname === '/labels') {
        stylesheet('/static/css/ui-v13.css');
        script('/static/js/labels-b21-v2.js');
        script('/static/js/labels-b21-v2-patch.js');
        script('/static/js/labels-b21-v4.js');
        script('/static/js/ui-v13-fixes.js');
        script('/static/js/labels-v18.js');
        script('/static/js/labels-v22.js');
    }

    if (window.location.pathname.startsWith('/barcodes/')) {
        script('/static/js/barcode-targets-v6.js');
    }
})();
