/**
 * Search Mealie Foods on a barcode detail page.
 * Quantity/unit are copied into whichever Food link form is submitted.
 */
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

    function setDefaults(form) {
        var quantity = form.querySelector('input[name="quantity"]');
        var unit = form.querySelector('input[name="unit_id"]');
        if (quantity && quantityInput) quantity.value = quantityInput.value || '1';
        if (unit && unitSelect) unit.value = unitSelect.value || '';
    }

    document.addEventListener('submit', function (event) {
        var form = event.target.closest('.food-link-form');
        if (form) setDefaults(form);
    });

    function buildRow(item) {
        var tr = document.createElement('tr');

        var tdName = document.createElement('td');
        var a = document.createElement('a');
        a.href = '/items/' + encodeURIComponent(item.id);
        a.textContent = item.name;
        tdName.appendChild(a);

        var tdScore = document.createElement('td');
        tdScore.innerHTML = '<span class="text-secondary">—</span>';

        var tdAction = document.createElement('td');
        var form = document.createElement('form');
        form.method = 'post';
        form.action = '/barcodes/' + encodeURIComponent(barcode) + '/map';
        form.className = 'food-link-form';

        var idInput = document.createElement('input');
        idInput.type = 'hidden';
        idInput.name = 'item_id';
        idInput.value = item.id;

        var qtyInput = document.createElement('input');
        qtyInput.type = 'hidden';
        qtyInput.name = 'quantity';
        qtyInput.value = '1';

        var unitInput = document.createElement('input');
        unitInput.type = 'hidden';
        unitInput.name = 'unit_id';
        unitInput.value = '';

        var button = document.createElement('button');
        button.type = 'submit';
        button.className = 'btn btn-sm btn-primary';
        button.innerHTML = '<i class="ti ti-link icon"></i> Link';

        form.appendChild(idInput);
        form.appendChild(qtyInput);
        form.appendChild(unitInput);
        form.appendChild(button);
        tdAction.appendChild(form);

        tr.appendChild(tdName);
        tr.appendChild(tdScore);
        tr.appendChild(tdAction);
        return tr;
    }

    searchInput.addEventListener('input', function () {
        clearTimeout(timeout);
        var q = this.value.trim();

        if (q.length < 2) {
            tbody.innerHTML = originalRows;
            return;
        }

        timeout = setTimeout(function () {
            fetch('/barcodes-search?q=' + encodeURIComponent(q))
                .then(function (response) {
                    if (!response.ok) throw new Error('Food search failed');
                    return response.json();
                })
                .then(function (data) {
                    tbody.innerHTML = '';
                    if (!data.length) {
                        tbody.innerHTML = '<tr><td colspan="3" class="text-center text-secondary">No matching Mealie Foods</td></tr>';
                        return;
                    }
                    data.forEach(function (item) {
                        tbody.appendChild(buildRow(item));
                    });
                })
                .catch(function () {
                    tbody.innerHTML = '<tr><td colspan="3" class="text-center text-danger">Food search failed</td></tr>';
                });
        }, 250);
    });
})();
