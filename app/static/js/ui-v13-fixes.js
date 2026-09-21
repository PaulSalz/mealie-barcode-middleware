/* v2026.09.21.13: label designer preset + readable generic code fixes. */
(function () {
  'use strict';

  if (window.__b2mUiV13FixesLoaded) return;
  window.__b2mUiV13FixesLoaded = true;

  const $ = (id) => document.getElementById(id);

  function transliterateCodeText(value) {
    return String(value == null ? '' : value)
      .replace(/Ä/g, 'Ae').replace(/Ö/g, 'Oe').replace(/Ü/g, 'Ue')
      .replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue')
      .replace(/ß/g, 'ss')
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^\x20-\x7E]/g, '');
  }

  /* labels-page.js owns the queue in a closure. Keep that state intact and only
     substitute the first encodeURIComponent call made by genericCode(). */
  function runWithGenericTransliteration(callback) {
    const nativeEncode = window.encodeURIComponent;
    let first = true;
    window.encodeURIComponent = function (value) {
      if (first) {
        first = false;
        return nativeEncode(transliterateCodeText(value));
      }
      return nativeEncode(value);
    };
    try {
      callback();
    } finally {
      window.encodeURIComponent = nativeEncode;
    }
  }

  function replaceClickTarget(node) {
    if (!node || node.dataset.b2mV13Generic === '1') return;
    const original = node;
    const replacement = original.cloneNode(true);
    replacement.dataset.b2mV13Generic = '1';
    original.replaceWith(replacement);
    replacement.addEventListener('click', function (event) {
      event.preventDefault();
      runWithGenericTransliteration(function () { original.click(); });
    });
  }

  function installGenericCodeFix() {
    if (window.location.pathname !== '/labels') return;
    replaceClickTarget($('generic-add'));
    document.querySelectorAll('.generic-example').forEach(replaceClickTarget);

    const input = $('generic-text');
    if (input) {
      const pane = input.closest('.generator-pane');
      const hint = pane && pane.querySelector('.form-hint');
      if (hint) {
        hint.innerHTML = 'The printed text keeps its spelling; the code ID is ASCII-safe. German umlauts are transliterated, e.g. <code>Brötchen → GENERIC:Broetchen</code>.';
      }
    }
  }

  const PRESETS = {
    stacked: {
      code: {visible:true,x:50,y:38,w:86,h:54,rotation:0},
      label:{visible:true,x:50,y:81,w:88,h:20,rotation:0,fontSizePt:14},
      value:{visible:false}
    },
    left: {
      code:{visible:true,x:28,y:50,w:50,h:80,rotation:0},
      label:{visible:true,x:75,y:50,w:42,h:42,rotation:0,fontSizePt:14},
      value:{visible:false}
    },
    right: {
      code:{visible:true,x:72,y:50,w:50,h:80,rotation:0},
      label:{visible:true,x:25,y:50,w:42,h:42,rotation:0,fontSizePt:14},
      value:{visible:false}
    },
    code: {
      code:{visible:true,x:50,y:50,w:92,h:86,rotation:0},
      label:{visible:false},
      value:{visible:false}
    },
    text: {
      code:{visible:false},
      label:{visible:true,x:50,y:50,w:90,h:70,rotation:0,fontSizePt:20},
      value:{visible:false}
    }
  };

  function optionExists(select, value) {
    return !!select && Array.from(select.options || []).some(function (option) { return option.value === value; });
  }

  function setInspectorValue(key, value) {
    const input = $('b21-v2-' + key);
    if (!input || value == null) return;
    input.value = String(value);
    input.dispatchEvent(new Event('input', {bubbles:true}));
  }

  /* Drive the v2 inspector instead of writing localStorage behind its back. The
     inspector owns the live in-memory state and persists/renders on each input. */
  function patchDesignerElement(id, patch) {
    const select = $('b21-v2-element-select');
    if (!select || !optionExists(select, id) || !patch) return;

    select.value = id;
    select.dispatchEvent(new Event('change', {bubbles:true}));

    if (Object.prototype.hasOwnProperty.call(patch, 'visible')) {
      const visible = $('b21-v2-visible');
      if (visible) {
        visible.checked = !!patch.visible;
        visible.dispatchEvent(new Event('change', {bubbles:true}));
      }
    }

    ['x','y','w','h','rotation','fontSizePt','lineWidthMm'].forEach(function (key) {
      if (Object.prototype.hasOwnProperty.call(patch, key)) setInspectorValue(key, patch[key]);
    });
  }

  function applyPreset(name) {
    const preset = PRESETS[name];
    if (!preset) return;
    patchDesignerElement('code', preset.code);
    patchDesignerElement('label', preset.label);
    patchDesignerElement('value', preset.value);

    const select = $('b21-v2-element-select');
    const preferred = preset.code.visible === false ? 'label' : 'code';
    if (select && optionExists(select, preferred)) {
      select.value = preferred;
      select.dispatchEvent(new Event('change', {bubbles:true}));
    }

    document.querySelectorAll('#b21-v4-presets [data-preset]').forEach(function (button) {
      button.classList.toggle('active', button.dataset.preset === name);
    });
  }

  function presetCard(name, icon, title, subtitle) {
    return '<button class="btn btn-outline-secondary b21-v13-preset" type="button" data-preset="' + name + '">' +
      '<i class="ti ' + icon + ' b21-v13-preset-icon"></i>' +
      '<span><strong>' + title + '</strong><small>' + subtitle + '</small></span>' +
    '</button>';
  }

  function installPresetFix() {
    if (window.location.pathname !== '/labels') return true;
    const section = $('b21-v4-presets');
    const inspector = $('b21-v2-inspector');
    if (!section || !inspector || !$('b21-v2-element-select')) return false;
    if (section.dataset.b2mV13 === '1') return true;

    section.dataset.b2mV13 = '1';
    /* Replacing the contents also removes the old localStorage-only handlers. */
    section.innerHTML = '<div class="d-flex align-items-center justify-content-between gap-2 mb-2">' +
      '<div><div class="fw-semibold">Layout presets</div><div class="text-secondary small">Apply a starting layout, then fine-tune it below.</div></div>' +
      '</div><div class="b21-v13-preset-grid">' +
      presetCard('stacked','ti-layout-rows','Stacked','Code above text') +
      presetCard('left','ti-layout-sidebar-left','Code left','Text on the right') +
      presetCard('right','ti-layout-sidebar-right','Code right','Text on the left') +
      presetCard('code','ti-barcode','Code only','Maximum code area') +
      presetCard('text','ti-letter-t','Text only','No barcode / QR') +
      '</div>';

    section.querySelectorAll('[data-preset]').forEach(function (button) {
      button.addEventListener('click', function () { applyPreset(button.dataset.preset); });
    });
    return true;
  }

  function start() {
    installGenericCodeFix();
    if (window.location.pathname !== '/labels') return;
    let attempts = 0;
    (function waitForDesigner() {
      if (installPresetFix()) return;
      if (attempts++ < 80) window.setTimeout(waitForDesigner, 100);
    })();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once:true});
  else start();
})();
