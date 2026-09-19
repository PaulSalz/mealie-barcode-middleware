/**
 * Search Mealie recipes and select one as the barcode target.
 */
(function () {
    'use strict';

    var input = document.getElementById('recipe-search');
    var results = document.getElementById('recipe-search-results');
    var recipeId = document.getElementById('recipe-id');
    var recipeName = document.getElementById('recipe-name');
    var selectedName = document.getElementById('recipe-selected-name');
    var submit = document.getElementById('recipe-map-button');
    var timeout = null;

    if (!input || !results || !recipeId || !recipeName || !selectedName || !submit) return;

    function clearResults() {
        results.innerHTML = '';
    }

    function selectRecipe(recipe) {
        recipeId.value = recipe.id;
        recipeName.value = recipe.name || recipe.slug || recipe.id;
        selectedName.value = recipeName.value;
        input.value = recipeName.value;
        submit.disabled = false;
        clearResults();
    }

    input.addEventListener('input', function () {
        clearTimeout(timeout);
        var q = this.value.trim();

        recipeId.value = '';
        recipeName.value = '';
        selectedName.value = '';
        submit.disabled = true;

        if (q.length < 2) {
            clearResults();
            return;
        }

        timeout = setTimeout(function () {
            fetch('/recipes-search?q=' + encodeURIComponent(q))
                .then(function (response) {
                    if (!response.ok) throw new Error('Recipe search failed');
                    return response.json();
                })
                .then(function (data) {
                    clearResults();
                    if (!Array.isArray(data) || data.length === 0) {
                        results.innerHTML = '<div class="list-group-item text-secondary">No recipes found</div>';
                        return;
                    }

                    data.forEach(function (recipe) {
                        var button = document.createElement('button');
                        button.type = 'button';
                        button.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';

                        var text = document.createElement('span');
                        text.textContent = recipe.name || recipe.slug || recipe.id;

                        var id = document.createElement('code');
                        id.className = 'small text-secondary ms-3';
                        id.textContent = recipe.id;

                        button.appendChild(text);
                        button.appendChild(id);
                        button.addEventListener('click', function () {
                            selectRecipe(recipe);
                        });
                        results.appendChild(button);
                    });
                })
                .catch(function () {
                    results.innerHTML = '<div class="list-group-item text-danger">Recipe search failed</div>';
                });
        }, 250);
    });
})();
