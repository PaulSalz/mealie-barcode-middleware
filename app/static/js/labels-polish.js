(function() {
    'use strict';

    function showQueueFeedback(message) {
        var box = document.getElementById('label-queue-feedback');
        if (!box) return;
        box.textContent = message;
        box.classList.remove('d-none');
        clearTimeout(window._b2mLabelFeedbackTimer);
        window._b2mLabelFeedbackTimer = window.setTimeout(function() { box.classList.add('d-none'); }, 1800);
    }

    function moveQueueFeedback() {
        var box = document.getElementById('label-queue-feedback');
        if (!box) return;
        var queue = document.getElementById('label-queue');
        var card = queue ? queue.closest('.card') : null;
        var title = card ? card.querySelector('.card-title') : null;
        if (!title || box.parentElement === title.parentElement) return;
        box.className = 'd-none ms-2';
        box.style.verticalAlign = 'middle';
        title.appendChild(box);
    }

    function fixQueuePreviewImages() {
        document.querySelectorAll('#label-queue img.label-code-preview').forEach(function(img) {
            if (img.parentElement && img.parentElement.classList.contains('label-code-preview-frame')) return;
            var frame = document.createElement('div');
            frame.className = 'label-code-preview-frame rounded border bg-white p-1';
            img.parentNode.insertBefore(frame, img);
            frame.appendChild(img);
        });
    }

    function hideFoodIds() {
        var root = document.getElementById('generator-food-results');
        if (!root) return;
        root.querySelectorAll('code').forEach(function(code) { code.remove(); });
        root.querySelectorAll('.list-group-item').forEach(function(row) {
            row.classList.remove('justify-content-between');
            row.classList.add('text-start');
            var name = row.querySelector('span');
            if (name) { name.classList.add('fw-medium', 'flex-fill', 'text-truncate'); name.style.minWidth = '0'; }
        });
    }

    function preloadActions() {
        var input = document.getElementById('generator-action-search');
        if (input) input.dispatchEvent(new Event('focus'));
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
        tab.click(); input.value = recipeName;
        var observer = new MutationObserver(function() {
            var exact = Array.from(results.querySelectorAll('button.list-group-item')).find(function(button) {
                var code = button.querySelector('code');
                return code && code.textContent.trim() === recipeId;
            });
            if (!exact) return;
            observer.disconnect(); exact.click();
            showQueueFeedback('Added · ' + recipeName);
            params.delete('recipe'); params.delete('recipe_name');
            var query = params.toString();
            history.replaceState(null, '', window.location.pathname + (query ? '?' + query : ''));
        });
        observer.observe(results, {childList:true, subtree:true});
        input.dispatchEvent(new Event('input', {bubbles:true}));
        window.setTimeout(function() { observer.disconnect(); }, 5000);
    }

    function watchQueue() {
        var count = document.getElementById('label-count');
        var root = document.getElementById('label-queue');
        if (!count || !root) return;
        var previous = count.textContent;
        var ready = false;
        requestAnimationFrame(function() { ready = true; previous = count.textContent; fixQueuePreviewImages(); });
        new MutationObserver(function() {
            fixQueuePreviewImages();
            if (!ready) return;
            var current = count.textContent;
            if (current !== previous) {
                previous = current;
                showQueueFeedback('Updated · ' + current.replace(/[()]/g, ''));
            }
        }).observe(root, {childList:true, subtree:true});
        new MutationObserver(function() {
            if (!ready) return;
            var current = count.textContent;
            if (current === previous) return;
            previous = current;
            showQueueFeedback('Updated · ' + current.replace(/[()]/g, ''));
        }).observe(count, {childList:true, characterData:true, subtree:true});
    }

    function loadB21Designer() {
        if (!document.getElementById('b21-designer-stylesheet')) {
            var link = document.createElement('link');
            link.id = 'b21-designer-stylesheet';
            link.rel = 'stylesheet';
            link.href = '/static/css/labels-b21.css?v=20260921-1';
            document.head.appendChild(link);
        }
        if (document.getElementById('b21-designer-script')) return;
        var script = document.createElement('script');
        script.id = 'b21-designer-script';
        script.src = '/static/js/labels-b21.js?v=20260921-1';
        script.defer = true;
        document.body.appendChild(script);
    }

    moveQueueFeedback();
    preloadActions();
    prefillRecipeFromUrl();
    watchQueue();
    loadB21Designer();

    var foodResults = document.getElementById('generator-food-results');
    if (foodResults) {
        new MutationObserver(hideFoodIds).observe(foodResults, {childList:true, subtree:true});
        hideFoodIds();
    }
})();
