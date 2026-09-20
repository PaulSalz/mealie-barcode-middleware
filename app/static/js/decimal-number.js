(function() {
    'use strict';

    var EMPTY_SENTINEL = 0.001;

    function allowEmpty(input) { return input.dataset.allowEmpty === 'true'; }
    function rawValue(input) { return String(input.value || '').trim().replace(',', '.'); }
    function parseValue(input) {
        var value = rawValue(input);
        if (!value) return null;
        var number = Number.parseFloat(value);
        return Number.isFinite(number) ? number : null;
    }
    function formatValue(value) {
        var rounded = Math.round((value + Number.EPSILON) * 1000) / 1000;
        return String(rounded);
    }
    function dispatch(input) {
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
    }
    function setValue(input, value) {
        if (allowEmpty(input) && (value == null || value <= 0)) {
            input.value = '';
            dispatch(input);
            return;
        }
        var min = Number.parseFloat(input.dataset.min || '0.001');
        if (!Number.isFinite(min)) min = 0.001;
        var normalized = Number.isFinite(value) ? Math.max(value, min) : min;
        input.value = formatValue(normalized);
        dispatch(input);
    }
    function normalizeInput(input) {
        var raw = rawValue(input);
        if (!raw) {
            if (allowEmpty(input)) input.value = '';
            return;
        }
        var value = Number.parseFloat(raw);
        if (!Number.isFinite(value)) return;
        if (allowEmpty(input) && value <= EMPTY_SENTINEL) {
            input.value = '';
            return;
        }
        setValue(input, value);
    }
    function step(input, delta) {
        var current = parseValue(input);
        if (allowEmpty(input)) {
            if (current == null) {
                if (delta > 0) setValue(input, 1);
                return;
            }
            setValue(input, current + delta);
            return;
        }
        setValue(input, (current == null ? 0 : current) + delta);
    }

    document.querySelectorAll('.decimal-stepper').forEach(function(container) {
        var input = container.querySelector('.decimal-number');
        if (!input) return;
        if ((input.name === 'quantity' || input.id === 'food-default-quantity') && !input.dataset.allowEmpty) input.dataset.allowEmpty = 'true';
        normalizeInput(input);
        container.querySelectorAll('[data-decimal-step]').forEach(function(button) {
            button.addEventListener('click', function() {
                step(input, Number.parseFloat(button.dataset.decimalStep) || 0);
                input.focus();
            });
        });
        input.addEventListener('keydown', function(event) {
            if (event.key === 'ArrowUp') { event.preventDefault(); step(input, 1); }
            else if (event.key === 'ArrowDown') { event.preventDefault(); step(input, -1); }
        });
        input.addEventListener('blur', function() { normalizeInput(input); });
        input.addEventListener('paste', function(event) {
            var text = event.clipboardData && event.clipboardData.getData('text');
            if (!text || text.indexOf(',') === -1) return;
            event.preventDefault();
            input.setRangeText(text.replace(',', '.'), input.selectionStart || 0, input.selectionEnd || 0, 'end');
            setTimeout(function() { normalizeInput(input); }, 0);
        });
        // Blank values stay blank during submit. The server now treats blank as
        // "no explicit quantity", so the old visible 0.001 sentinel is unnecessary.
    });
})();
