/** Search Mealie Foods on a barcode detail page. */
(function () {
    'use strict';

    var searchInput = document.getElementById('item-search');
    var tbody = document.getElementById('item-assign-tbody');
    var table = document.getElementById('item-assign-table');
    var quantityInput = document.getElementById('food-default-quantity');
    var unitSelect = document.getElementById('food-default-unit');
    var timeout = null;
    if (!searchInput || !tbody || !table) return;

    var barcode = table.dataset.barcode;
    var originalRows = tbody.innerHTML;

    function selectedUnitFor(item) {
        if (!unitSelect) return item.default_unit_id || '';
        if (unitSelect.value === '__item_default__' || unitSelect.value === '') return item.default_unit_id || '';
        return unitSelect.value;
    }

    function setDefaults(form) {
        var quantity = form.querySelector('input[name="quantity"]');
        var unit = form.querySelector('input[name="unit_id"]');
        var itemUnit = form.dataset.itemUnit || '';
        if (quantity && quantityInput) quantity.value = String(quantityInput.value || '').trim();
        if (unit) {
            if (!unitSelect || unitSelect.value === '__item_default__' || unitSelect.value === '') unit.value = itemUnit;
            else unit.value = unitSelect.value;
        }
    }

    document.addEventListener('submit', function(event) {
        var form = event.target.closest('.food-link-form');
        if (form) setDefaults(form);
    });

    function scoreBadge(item) {
        var score = Number(item.score || 0);
        var color = item.exact ? 'green' : score >= 85 ? 'green' : score >= 65 ? 'yellow' : 'secondary';
        return '<span class="badge bg-' + color + '-lt">' + score + '%' + (item.exact ? ' · exact' : '') + '</span>';
    }

    function buildRow(item) {
        var tr = document.createElement('tr');
        var tdName = document.createElement('td');
        var a = document.createElement('a');
        a.href = '/items/' + encodeURIComponent(item.id);
        a.textContent = item.name;
        tdName.appendChild(a);
        if (item.default_unit_name) {
            var unit = document.createElement('div');
            unit.className = 'text-secondary small';
            unit.textContent = 'Item unit: ' + item.default_unit_name;
            tdName.appendChild(unit);
        }

        var tdScore = document.createElement('td');
        tdScore.innerHTML = scoreBadge(item);
        var tdAction = document.createElement('td');
        var form = document.createElement('form');
        form.method = 'post';
        form.action = '/barcodes/' + encodeURIComponent(barcode) + '/map';
        form.className = 'food-link-form';
        form.dataset.itemUnit = item.default_unit_id || '';
        form.innerHTML =
            '<input type="hidden" name="item_id" value="">' +
            '<input type="hidden" name="quantity" value="">' +
            '<input type="hidden" name="unit_id" value="">' +
            '<button type="submit" class="btn btn-sm btn-primary"><i class="ti ti-link icon"></i> Add target</button>';
        form.querySelector('[name="item_id"]').value = item.id;
        form.querySelector('[name="unit_id"]').value = selectedUnitFor(item);
        tdAction.appendChild(form);
        tr.appendChild(tdName);
        tr.appendChild(tdScore);
        tr.appendChild(tdAction);
        return tr;
    }

    searchInput.addEventListener('input', function() {
        clearTimeout(timeout);
        var q = this.value.trim();
        if (q.length < 2) {
            tbody.innerHTML = originalRows;
            return;
        }
        timeout = setTimeout(function() {
            fetch('/barcodes-search?q=' + encodeURIComponent(q))
                .then(function(response) {
                    if (!response.ok) throw new Error('Food search failed');
                    return response.json();
                })
                .then(function(data) {
                    tbody.innerHTML = '';
                    if (!data.length) {
                        tbody.innerHTML = '<tr><td colspan="3" class="text-center text-secondary">No matching Mealie Foods</td></tr>';
                        return;
                    }
                    data.forEach(function(item) { tbody.appendChild(buildRow(item)); });
                })
                .catch(function() {
                    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-danger">Food search failed</td></tr>';
                });
        }, 180);
    });
})();
