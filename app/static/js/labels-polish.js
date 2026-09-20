(function() {
    'use strict';

    function showQueueFeedback(message) {
        var box = document.getElementById('label-queue-feedback');
        if (!box) return;
        box.textContent = message;
        box.classList.remove('d-none');
        clearTimeout(window._b2mLabelFeedbackTimer);
        window._b2mLabelFeedbackTimer = setTimeout(function() {
            box.classList.add('d-none');
        }, 2200);
    }

    function preloadActions() {
        var input = document.getElementById('generator-action-search');
        if (!input) return;
        // labels-page.js loads the complete enabled action list on focus. Trigger it
        // immediately so the list is ready before the user opens the Action tab.
        input.dispatchEvent(new Event('focus'));
    }

    function prefillRecipeFromUrl() {
        var params = new URLSearchParams(window.location.search);
        var recipeId = params.get('recipe');
        var recipeName = params.get('recipe_name');
        if (!recipeId || !recipeName) return;

        var tab = document.querySelector('[data-code-type="recipe"]');
        var input = document.getElementById('generator-recipe-search');
        var results = document.getElementById('generator-recipe-results');
        if (!tab || !input || !results) return;

        tab.click();
        input.value = recipeName;

        var observer = new MutationObserver(function() {
            var buttons = Array.from(results.querySelectorAll('button.list-group-item'));
            var exact = buttons.find(function(button) {
                var text = (button.querySelector('span') || button).textContent.trim();
                return text.toLocaleLowerCase() === recipeName.toLocaleLowerCase();
            });
            if (!exact) return;
            observer.disconnect();
            exact.click();
            showQueueFeedback('Added recipe “' + recipeName + '” to the queue.');
            params.delete('recipe');
            params.delete('recipe_name');
            var query = params.toString();
            history.replaceState(null, '', window.location.pathname + (query ? '?' + query : ''));
        });
        observer.observe(results, {childList: true, subtree: true});
        input.dispatchEvent(new Event('input', {bubbles: true}));
        setTimeout(function() { observer.disconnect(); }, 5000);
    }

    function watchQueue() {
        var count = document.getElementById('label-count');
        if (!count) return;
        var previous = count.textContent;
        var ready = false;
        requestAnimationFrame(function() { ready = true; previous = count.textContent; });
        new MutationObserver(function() {
            if (!ready) return;
            var current = count.textContent;
            if (current === previous) return;
            previous = current;
            showQueueFeedback('Queue updated · ' + current.replace(/[()]/g, '') + ' label' + (current === '(1)' ? '' : 's') + '.');
        }).observe(count, {childList: true, characterData: true, subtree: true});
    }

    preloadActions();
    prefillRecipeFromUrl();
    watchQueue();
})();
