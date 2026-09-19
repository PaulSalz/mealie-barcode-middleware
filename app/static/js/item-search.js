/**
 * Search Mealie/local items on the barcode detail page.
 * The shared quantity/unit controls are copied into every map request.
 */
(function() {
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

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    function defaults() {
        return {
            quantity: quantityInput && quantityInput.value ? quantityInput.value : '1',
            unit: unitSelect && unitSelect.value ? unitSelect.value : ''
        };
    }

    function syncForm(form) {
        if (!form) return;
        var d = defaults();
        var q = form.querySelector('.map-quantity');
        var u = form.querySelector('.map-unit');
        if (q) q.value = d.quantity;
        if (u) u.value = d.unit;
    }

    function buildCreateRow(query) {
        var tr = document.createElement('tr');
        tr.className = 'table-active';
        tr.innerHTML = '<td colspan="3" class="text-muted">' +
            '<i class="ti ti-plus icon"></i> Create <strong>"' + esc(query) + '"</strong> as a new Mealie food' +
            '</td><td><button type="button" class="btn btn-success create-food-shortcut">Use name</button></td>';
        tr.querySelector('.create-food-shortcut').addEventListener('click', function() {
            var nameInput = document.getElementById('create-food-name');
            var card = document.getElementById('create-food-card');
            if (nameInput) {
                nameInput.value = query;
                nameInput.focus();
            }
            if (card) card.scrollIntoView({behavior: 'smooth', block: 'start'});
        });
        return tr;
    }

    function buildRow(item) {
        var tr = document.createElement('tr');
        var tdName = document.createElement('td');
        var a = document.createElement('a');
        a.href = '/items/' + item.id;
        a.textContent = item.name;
        tdName.appendChild(a);

        var tdSource = document.createElement('td');
        tdSource.className = 'text-secondary';
        tdSource.textContent = item.source === 'mealie' ? 'Mealie' : 'Custom';

        var tdScore = document.createElement('td');
        tdScore.innerHTML = '<span class="text-secondary">—</span>';

        var tdAction = document.createElement('td');
        tdAction.innerHTML = '<form method="post" action="/barcodes/' + encodeURIComponent(barcode) + '/map" class="food-map-form d-inline">' +
            '<input type="hidden" name="item_id" value="' + item.id + '">' +
            '<input type="hidden" name="quantity" value="1" class="map-quantity">' +
            '<input type="hidden" name="unit_id" value="" class="map-unit">' +
            '<button type="submit" class="btn btn-sm btn-primary"><i class="ti ti-link icon"></i> Link</button></form>';

        tr.appendChild(tdName);
        tr.appendChild(tdSource);
        tr.appendChild(tdScore);
        tr.appendChild(tdAction);
        return tr;
    }

    tbody.addEventListener('submit', function(event) {
        if (event.target && event.target.classList.contains('food-map-form')) {
            syncForm(event.target);
        }
    });

    searchInput.addEventListener('input', function() {
        clearTimeout(timeout);
        var q = this.value.trim();
        if (q.length < 2) {
            tbody.innerHTML = originalRows;
            return;
        }
        timeout = setTimeout(function() {
            fetch('/barcodes-search?q=' + encodeURIComponent(q))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    tbody.innerHTML = '';
                    if (data.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-secondary">No matching items</td></tr>';
                    } else {
                        data.forEach(function(item) {
                            tbody.appendChild(buildRow(item));
                        });
                    }
                    if (document.getElementById('create-food-form')) {
                        tbody.appendChild(buildCreateRow(q));
                    }
                });
        }, 300);
    });
})();
