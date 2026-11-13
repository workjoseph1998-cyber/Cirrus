'use strict';
(() => {
const isQuotationList=!!document.getElementById('document-filters');const stored=isQuotationList&&sessionStorage.getItem('cirrus.quotation.return');if(stored){try{const saved=JSON.parse(stored);if(location.pathname==='/list/quote'&&!location.search&&saved.url.startsWith('/list/quote?')){location.replace(saved.url);}else if(saved.url===location.pathname+location.search){setTimeout(()=>{document.querySelector('[data-document-id="'+saved.selected+'"] .pick-document')?.click();window.scrollTo(0,saved.scroll);},100);}}catch(e){sessionStorage.removeItem('cirrus.quotation.return');}}
document.addEventListener('click',e=>{if(!isQuotationList)return;const a=e.target.closest('a');if(!a)return;if(a.textContent.trim()==='Clear filters'){sessionStorage.removeItem('cirrus.quotation.return');return;}const selected=document.querySelector('.selected-document');if(a.href&&/\/(quotes|documents|record)\//.test(a.getAttribute('href')||''))sessionStorage.setItem('cirrus.quotation.return',JSON.stringify({url:location.pathname+location.search,scroll:scrollY,selected:selected?.dataset.documentId||''}));});

const dialog=document.createElement('dialog');dialog.className='workspace-dialog';const close=document.createElement('button');close.textContent='Close';const frame=document.createElement('iframe');frame.title='Selected quotation management';dialog.append(close,frame);document.body.append(dialog);close.onclick=()=>dialog.close();document.addEventListener('click',e=>{const a=e.target.closest('[data-management],a[data-tool=manage],a[data-tool=outcome]');if(a?.href){e.preventDefault();frame.src=a.href+'?panel='+encodeURIComponent(a.dataset.management||(a.dataset.tool==='outcome'?'Export & Files':'Status & Owner'));dialog.showModal();}});
const period=document.getElementById('document-period');period?.addEventListener('change',()=>{document.querySelectorAll('[data-custom-date]').forEach(n=>n.hidden=period.value!=='custom');});
for(const btn of document.querySelectorAll('.pick-document'))btn.addEventListener('click',()=>{
 document.querySelectorAll('[data-document-id]').forEach(row=>row.classList.toggle('selected-document',row.dataset.documentId===btn.dataset.id));
 document.getElementById('selected-document').textContent=btn.dataset.title;document.querySelectorAll('[data-management]').forEach(a=>{a.href='/documents/'+btn.dataset.id+'/manage';});
 for(const link of document.querySelectorAll('[data-tool]')){
  const enabled=link.dataset.tool==='manage'||btn.dataset.kind==='quote'&&(link.dataset.tool!=='costing'||btn.dataset.writable==='yes');
  link.setAttribute('aria-disabled',String(!enabled));
  if(enabled)link.href=link.dataset.tool==='manage'?'/documents/'+btn.dataset.id+'/manage':link.dataset.tool==='costing'?'/quotes/'+btn.dataset.id+'/pricing-margin':link.dataset.tool==='outcome'?'/documents/'+btn.dataset.id+'/manage':'/quotes/'+btn.dataset.id+'/'+link.dataset.tool;else link.removeAttribute('href');
 }
});
for(const input of document.querySelectorAll('.selector-search'))input.addEventListener('input',()=>{
 for(const id of input.dataset.select.split(',')){
  const select=document.getElementById(id),term=input.value.toLocaleLowerCase();if(!select)continue;
  for(const opt of select.options)opt.hidden=opt.value!==''&&!opt.textContent.toLocaleLowerCase().includes(term)&&!opt.selected;
 }
});
const form=document.getElementById('sidebar-compare');if(form)form.addEventListener('submit',event=>{
 const id=document.getElementById('compare-before').value;if(!id){event.preventDefault();return;}form.action='/quotes/'+id+'/compare';
});
})();
