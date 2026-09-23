(function () {
  'use strict';

  document.addEventListener('click', async function (event) {
    var button = event.target.closest && event.target.closest('[data-ui-language]');
    if (!button) return;
    event.preventDefault();
    var language = button.dataset.uiLanguage;
    button.setAttribute('aria-busy', 'true');
    try {
      var response = await fetch('/api/ui-language', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
        body: JSON.stringify({language: language})
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok) throw new Error(data.error || 'Language could not be saved');
      window.location.reload();
    } catch (error) {
      button.removeAttribute('aria-busy');
      window.alert(error.message);
    }
  });
})();
