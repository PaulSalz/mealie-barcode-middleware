/* Personal theme is rendered server-side before first paint.
   This file only keeps a just-clicked navbar mode responsive while its save
   request is crossing the network; it must never clear or asynchronously
   replace background/e-paper state during navigation. */
(function() {
    'use strict';

    var root = document.documentElement;
    try {
        var override = localStorage.getItem('theme-mode-override');
        if (override === 'light' || override === 'dark') {
            root.setAttribute('data-bs-theme', override);
        }
    } catch (e) {}
})();
