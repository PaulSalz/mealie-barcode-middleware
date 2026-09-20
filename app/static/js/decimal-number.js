(function() {
    'use strict';

    function parseValue(input) {
        var value = String(input.value || '').trim().replace(',', '.');
        var number = Number.parseFloat(value);
        return Number.isFinite(number) ? number : 0;
    }

    function formatValue(value) {
        var rounded = Math.round((value + Number.EPSILON) * 1000) / 1000;
        return String(rounded);
    }

    function setValue(input, value) {
        var min = Number.parseFloat(input.dataset.min || '0.001');
        if (!Number.isFinite(min)) min = 0.001;
        input.value = formatValue(Math.max(value, min));
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function normalizeInput(input) {
        var raw = String(input.value || '').trim();
        if (!raw) return;
        var value = Number.parseFloat(raw.replace(',', '.'));
        if (!Number.isFinite(value)) return;
        setValue(input, value);
    }

    function step(input, delta) {
        setValue(input, parseValue(input) + delta);
    }

    document.querySelectorAll('.decimal-stepper').forEach(function(container) {
        var input = container.querySelector('.decimal-number');
        if (!input) return;

        container.querySelectorAll('[data-decimal-step]').forEach(function(button) {
            button.addEventListener('click', function() {
                step(input, Number.parseFloat(button.dataset.decimalStep) || 0);
                input.focus();
            });
        });

        input.addEventListener('keydown', function(event) {
            if (event.key === 'ArrowUp') {
                event.preventDefault();
                step(input, 1);
            } else if (event.key === 'ArrowDown') {
                event.preventDefault();
                step(input, -1);
            }
        });

        input.addEventListener('blur', function() {
            normalizeInput(input);
        });

        input.addEventListener('paste', function(event) {
            var text = event.clipboardData && event.clipboardData.getData('text');
            if (!text || text.indexOf(',') === -1) return;
            event.preventDefault();
            var normalized = text.replace(',', '.');
            input.setRangeText(normalized, input.selectionStart || 0, input.selectionEnd || 0, 'end');
            setTimeout(function() { normalizeInput(input); }, 0);
        });
    });
})();
