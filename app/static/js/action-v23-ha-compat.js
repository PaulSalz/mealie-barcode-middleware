(function () {
  'use strict';
  if (!(window.location.pathname === '/actions/new' || /^\/actions\/[^/]+$/.test(window.location.pathname))) return;

  const $ = (id) => document.getElementById(id);
  let cleaning = false;

  function payload() {
    try {
      const value = JSON.parse(($('action-payload-json') || {}).value || '{}');
      return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    } catch (e) { return {}; }
  }

  function sanitizeYaml() {
    const area = $('action-ha-yaml');
    if (!area || String(payload().kind || '') !== 'automation') return;
    area.value = area.value.replace(/\n\s+variables:\s+"\{\{ trigger\.json\.variables[^\n]*\}\}"/g, '');
  }

  function cleanAutomationExample() {
    if (cleaning) return;
    const textarea = $('action-payload-json');
    if (!textarea) return;
    const data = payload();
    if (String(data.kind || '') !== 'automation') return;

    if (Object.prototype.hasOwnProperty.call(data, 'variables')) {
      cleaning = true;
      delete data.variables;
      textarea.value = JSON.stringify(data, null, 2);
      textarea.dispatchEvent(new Event('change', {bubbles:true}));
      cleaning = false;
    }
    // Home Assistant's automation.trigger action accepts skip_condition but no
    // arbitrary variables service field. Data-passing has its own Data example.
    setTimeout(sanitizeYaml, 0);
    setTimeout(sanitizeYaml, 30);
  }

  function install() {
    if (!$('action-v22-builder') || !$('action-ha-yaml')) {
      setTimeout(install, 80);
      return;
    }
    document.querySelectorAll('.b2m-action-preset').forEach((button) => {
      button.addEventListener('click', function () { setTimeout(cleanAutomationExample, 10); });
    });
    ['action-payload-json'].forEach((id) => {
      const field = $(id);
      if (field) {
        field.addEventListener('change', function () { setTimeout(cleanAutomationExample, 0); });
        field.addEventListener('input', function () { setTimeout(sanitizeYaml, 0); });
      }
    });
    ['name','action_id','webhook_url'].forEach((name) => {
      const field = document.querySelector('[name="' + name + '"]');
      if (field) field.addEventListener('input', function () { setTimeout(sanitizeYaml, 0); });
    });
    cleanAutomationExample();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { setTimeout(install, 0); }, {once:true});
  else setTimeout(install, 0);
})();
