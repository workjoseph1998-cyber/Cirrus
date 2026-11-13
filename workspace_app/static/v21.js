"use strict";
(() => {
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-copy-quote]');
    if (!button) return;
    const url = new URL(button.dataset.copyQuote, location.origin).href;
    const status = button.closest('.v21-tools')?.querySelector('[data-copy-feedback]');
    try {
      await navigator.clipboard.writeText(url);
      if (status) status.textContent = 'Link copied.';
    } catch (_) {
      if (status) status.textContent = 'Copy unavailable. Select the link below to copy it.';
      const input = document.createElement('input');
      input.value = url; input.readOnly = true; input.setAttribute('aria-label', 'Quotation link to copy');
      button.after(input); input.select();
    }
  });
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      const search = document.querySelector('.global-search input');
      if (search) { event.preventDefault(); search.focus(); search.select(); }
    }
  });
  // Guard ordinary edit forms too; specialized editors retain their existing handlers.
  for (const form of document.querySelectorAll('form[method="post"]')) {
    if (form.matches('[data-unsaved]') || form.id === 'quotation-form' || form.closest('.quotation-editor')) continue;
    if (form.querySelector('textarea,input[type="text"],input:not([type]),input[type="email"],input[type="number"],input[type="date"],input[type="file"]')) form.dataset.unsaved = '';
  }
})();
