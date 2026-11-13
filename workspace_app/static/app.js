'use strict';
document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => { if (!confirm(form.dataset.confirm)) event.preventDefault(); }));
document.getElementById('print')?.addEventListener('click', () => window.print());
const editor = document.getElementById('line-editor');
if (editor) {
  const hidden = document.getElementById('lines');
  let lines = JSON.parse(hidden.value);
  const sync = () => { hidden.value = JSON.stringify(lines); };
  const render = () => {
    editor.replaceChildren();
    lines.forEach((line, index) => {
      const row = document.createElement('div'); row.className = 'line-row';
      for (const [key, title] of [['description','Description'],['unit','Unit'],['quantity','Quantity'],['price','Unit price'],['discount','Discount %'],['cost','Internal cost']]) {
        const label = document.createElement('label'); label.textContent = title;
        const input = document.createElement('input'); input.setAttribute('aria-label', `${title} line ${index + 1}`);
        input.value = line[key] ?? ''; input.type = ['quantity','price','discount','cost'].includes(key) ? 'number' : 'text';
        if (input.type === 'number') { input.step = 'any'; input.min = '0'; }
        input.addEventListener('input', () => { line[key] = input.value; sync(); }); label.append(input); row.append(label);
      }
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remove';
      remove.addEventListener('click', () => { lines.splice(index,1); render(); }); row.append(remove); editor.append(row);
    }); sync();
  };
  document.getElementById('add-line').addEventListener('click', () => { lines.push({description:'', unit:'unit', quantity:'1', price:'', cost:'', discount:'0'}); render(); });
  const catalog = JSON.parse(document.getElementById('catalog-data').textContent);
  document.getElementById('add-catalog').addEventListener('click', () => {
    const item = catalog.find(r => r.id === document.getElementById('catalog-picker').value)?.data;
    if (!item) return;
    if (item.currency !== document.querySelector('[name=currency]').value.toUpperCase()) {
      document.getElementById('line-message').textContent = 'Currency mismatch. Use an item in this quotation currency; no conversion is performed.'; return;
    }
    lines.push({description:item.description || item.name, unit:item.unit, quantity:'1', price:item.price, cost:item.cost, discount:'0'}); render();
    document.getElementById('line-message').textContent = 'Catalog item copied. This line is independent of future catalog edits.';
  }); render();
}
