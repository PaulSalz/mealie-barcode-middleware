(function() {
    'use strict';

    var MODE_KEY = 'b2m-label-editor-mode-v1';
    var advancedMode = false;
    try { advancedMode = localStorage.getItem(MODE_KEY) === 'advanced'; } catch (e) {}

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

    function ensureModeSwitch() {
        var header = document.querySelector('.page-header .btn-list');
        if (!header || document.getElementById('label-editor-mode')) return;
        var group = document.createElement('div');
        group.id = 'label-editor-mode';
        group.className = 'btn-group me-2';
        group.setAttribute('role', 'group');
        group.setAttribute('aria-label', 'Label editor mode');
        group.innerHTML = '<button type="button" class="btn btn-outline-secondary" data-label-mode="quick"><i class="ti ti-sparkles icon"></i> Quick print</button>' +
            '<button type="button" class="btn btn-outline-secondary" data-label-mode="advanced"><i class="ti ti-adjustments icon"></i> Advanced editor</button>';
        header.insertBefore(group, header.firstChild);
        group.querySelectorAll('[data-label-mode]').forEach(function(button) {
            button.addEventListener('click', function() {
                advancedMode = button.dataset.labelMode === 'advanced';
                try { localStorage.setItem(MODE_KEY, advancedMode ? 'advanced' : 'quick'); } catch (e) {}
                applyEditorMode();
            });
        });
    }

    function setHidden(node, hidden) {
        if (node) node.classList.toggle('d-none', hidden);
    }

    function applyEditorMode() {
        ensureModeSwitch();
        document.querySelectorAll('#label-editor-mode [data-label-mode]').forEach(function(button) {
            var active = (button.dataset.labelMode === 'advanced') === advancedMode;
            button.classList.toggle('btn-primary', active);
            button.classList.toggle('btn-outline-secondary', !active);
        });

        var pageTitle = document.querySelector('.page-header .page-title');
        var subtitle = pageTitle && pageTitle.parentElement ? pageTitle.parentElement.querySelector('.text-secondary') : null;
        if (pageTitle) pageTitle.firstChild.textContent = advancedMode ? 'Code Generator ' : 'Labels ';
        if (subtitle) subtitle.textContent = advancedMode
            ? 'Build, edit and keep a reusable label queue. Code style is chosen per label.'
            : 'Choose what to print, set the number of copies, pick a label size and print.';

        var queue = document.getElementById('label-queue');
        var queueCard = queue ? queue.closest('.card') : null;
        if (queueCard) setHidden(queueCard.querySelector('.card-actions'), !advancedMode);

        document.querySelectorAll('#label-queue .label-card').forEach(function(card) {
            var code = card.querySelector('.entry-code');
            var kind = card.querySelector('.entry-kind');
            var hint = card.querySelector('.entry-hint');
            setHidden(code ? code.closest('.col-md-6') : null, !advancedMode);
            setHidden(kind ? kind.closest('.col-md-5') : null, !advancedMode);
            setHidden(hint, !advancedMode);
            var badges = card.querySelector('.col-md-4');
            setHidden(badges, !advancedMode);
        });

        var printCard = document.getElementById('label-format');
        printCard = printCard ? printCard.closest('.card') : null;
        if (printCard) {
            var body = printCard.querySelector('.card-body');
            var title = printCard.querySelector('.card-title');
            var cardSubtitle = printCard.querySelector('.card-subtitle');
            if (title) title.textContent = advancedMode ? 'Print layout' : 'Label size';
            if (cardSubtitle) cardSubtitle.textContent = advancedMode
                ? 'Physical label/page settings. Code type is configured in the queue.'
                : 'Choose a common size. The recommended defaults handle spacing and text automatically.';
            if (body) {
                Array.from(body.children).forEach(function(child, index) {
                    setHidden(child, !advancedMode && index !== 1);
                });
            }
        }
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
        requestAnimationFrame(function() { ready = true; previous = count.textContent; fixQueuePreviewImages(); applyEditorMode(); });
        new MutationObserver(function() {
            fixQueuePreviewImages();
            applyEditorMode();
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
        }).observe(count, {childList:true, characterData:true,subtree:true});
    }

    function loadB21Styles() {
        if (document.getElementById('b21-designer-stylesheet')) return;
        var link = document.createElement('link');
        link.id = 'b21-designer-stylesheet';
        link.rel = 'stylesheet';
        link.href = '/static/css/labels-b21.css?v=20260921-1';
        document.head.appendChild(link);
    }

    ensureModeSwitch();
    moveQueueFeedback();
    preloadActions();
    prefillRecipeFromUrl();
    watchQueue();
    loadB21Styles();
    applyEditorMode();

    var foodResults = document.getElementById('generator-food-results');
    if (foodResults) {
        new MutationObserver(hideFoodIds).observe(foodResults, {childList:true, subtree:true});
        hideFoodIds();
    }
})();
