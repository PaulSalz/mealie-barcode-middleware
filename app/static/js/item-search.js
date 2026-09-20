/**
 * Ranked Food search on a barcode detail page.
 * Quantity/unit are copied into whichever Food link form is submitted.
 */
(function () {
    'use strict';

    var EMPTY_SENTINEL = '0.001';
    var searchInput = document.getElementById('item-search');
    var tbody = document.getElementById('item-assign-tbody');
    var table = document.getElementById('item-assign-table');
    var quantityInput = document.getElementById('food-default-quantity');
    var unitSelect = document.getElementById('food-default-unit');
    var timeout = null;

    if (!searchInput || !tbody || !table) return;

    var barcode = table.dataset.barcode;
    var originalRows = tbody.innerHTML;

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
    }

    function setDefaults(form) {
        var quantity = form.querySelector('input[name="quantity"]');
        var unit = form.querySelector('input[name="unit_id"]');
        if (quantity && quantityInput) {
            var rawQuantity = String(quantityInput.value || '').trim();
            quantity.value = rawQuantity === '' ? EMPTY_SENTINEL : rawQuantity;
        }
        if (unit && unitSelect) unit.value = unitSelect.value || '';
    }

    document.addEventListener('submit', function (event) {
        var form = event.target.closest('.food-link-form');
        if (form) setDefaults(form);
    });

    function buildRow(item) {
        var scoreClass = item.exact ? 'green' : item.score >= 85 ? 'green' : item.score >= 60 ? 'yellow' : 'secondary';
        var matchText = item.exact ? 'Exact' : item.score + '%';
        return '<tr>' +
            '<td><a href="/items/' + encodeURIComponent(item.id) + '">' + esc(item.name) + '</a></td>' +
            '<td><span class="badge bg-' + scoreClass + '-lt">' + matchText + '</span></td>' +
            '<td><form method="post" action="/barcodes/' + encodeURIComponent(barcode) + '/map" class="food-link-form">' +
            '<input type="hidden" name="item_id" value="' + esc(item.id) + '">' +
            '<input type="hidden" name="quantity" value="1"><input type="hidden" name="unit_id" value="">' +
            '<button type="submit" class="btn btn-sm btn-primary"><i class="ti ti-link icon"></i> Link</button></form></td>' +
            '</tr>';
    }

    searchInput.addEventListener('input', function () {
        clearTimeout(timeout);
        var q = this.value.trim();
        if (q.length < 2) {
            tbody.innerHTML = originalRows;
            return;
        }
        timeout = setTimeout(function () {
            fetch('/api/foods/search?q=' + encodeURIComponent(q) + '&limit=6')
                .then(function (response) {
                    if (!response.ok) throw new Error('Food search failed');
                    return response.json();
                })
                .then(function (data) {
                    var items = data.items || [];
                    tbody.innerHTML = items.length
                        ? items.map(buildRow).join('')
                        : '<tr><td colspan="3" class="text-center text-secondary">No matching Mealie Foods</td></tr>';
                })
                .catch(function () {
                    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-danger">Food search failed</td></tr>';
                });
        }, 180);
    });
})();
