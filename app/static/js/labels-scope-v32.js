/* v2026.09.23.32 — let the canonical single-label handler bypass the v30 queue capture. */
(function () {
  'use strict';
  if (window.location.pathname !== '/labels' || window.__b2mLabelScopeV32Loaded) return;
  window.__b2mLabelScopeV32Loaded = true;

  function currentScope() {
    var select = document.getElementById('b21-v2-print-scope');
    return select ? String(select.value || 'queue') : 'queue';
  }

  /* labels-fixes-v30 registers a document-level capture handler after this file
     and treats every #label-niim-print click as a whole-queue print. For Current
     label only, hide that id only for the document-capture phase. The body
     capture phase restores it before the button's canonical v2 click handler
     runs, so submitPrintJob() can use its normal single-label path unchanged. */
  document.addEventListener('click', function (event) {
    if (currentScope() !== 'current') return;
    var button = event.target && event.target.closest && event.target.closest('#label-niim-print');
    if (!button) return;
    button.dataset.b2mScopeRestore = '1';
    button.id = 'label-niim-print-current-v32';
  }, true);

  document.body.addEventListener('click', function (event) {
    var button = event.target && event.target.closest && event.target.closest('[data-b2m-scope-restore="1"]');
    if (!button) return;
    button.id = 'label-niim-print';
    delete button.dataset.b2mScopeRestore;
  }, true);
})();
