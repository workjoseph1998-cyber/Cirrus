'use strict';
(() => {
  // Loaded outside the protected editor only. Storage failures never block navigation.
  const prefix='cw21.1:'+(document.documentElement.dataset.account||'local')+':';
  const read=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(prefix+key))??fallback;}catch(_){return fallback;}};
  const write=(key,value)=>{try{localStorage.setItem(prefix+key,JSON.stringify(value));}catch(_){}};
  const sessionRead=key=>{try{return JSON.parse(sessionStorage.getItem(prefix+key));}catch(_){return null;}};
  const sessionWrite=(key,value)=>{try{sessionStorage.setItem(prefix+key,JSON.stringify(value));}catch(_){}};
  const listing=document.querySelector('[data-listing-key]');
  if(listing){
    const positionKey='position:'+location.pathname+location.search;
    const save=()=>sessionWrite(positionKey,{y:scrollY});
    document.addEventListener('click',e=>{if(e.target.closest('a[href]')){save();sessionWrite('return',{url:location.pathname+location.search});}});
    addEventListener('pagehide',save);
    const position=sessionRead(positionKey);if(position)addEventListener('pageshow',()=>requestAnimationFrame(()=>scrollTo(0,position.y)));
    const filter=document.querySelector('form[data-remember-filters]');
    if(filter){
      const key='list-options:'+listing.dataset.listingKey;
      const names=['sort','per_page'];const prefs=read(key,{});const params=new URLSearchParams(location.search);let restore=false;
      for(const name of names){const field=filter.elements.namedItem(name);if(!field)continue;if(params.has(name))prefs[name]=field.value;else if(prefs[name]&&[...field.options].some(o=>o.value===prefs[name])){params.set(name,prefs[name]);restore=true;}}
      write(key,prefs);if(restore){location.replace(location.pathname+'?'+params);return;}
      filter.addEventListener('submit',()=>{for(const name of names){const field=filter.elements.namedItem(name);if(field)prefs[name]=field.value;}write(key,prefs);});
      document.querySelector('[data-clear-list]')?.addEventListener('click',()=>{write(key,{});});
    }
  }
  for(const back of document.querySelectorAll('[data-smart-back]')){
    const saved=sessionRead('return');
    if(saved){try{const url=new URL(saved.url,location.origin);if(url.origin===location.origin&&url.pathname===new URL(back.href).pathname)back.href=url.pathname+url.search;}catch(_){}}
  }
  // Optional column visibility uses existing table markup and preserves essential columns.
  for(const root of document.querySelectorAll('[data-listing-table]')){
    const table=root.querySelector('table'),headers=[...table.querySelectorAll('thead th')];
    if(headers.length<4||!table.querySelector('tbody tr td:not([colspan])'))continue;
    const key='columns:'+(root.dataset.listingKey||location.pathname),hidden=read(key,[]);
    const menu=document.createElement('details');menu.className='column-menu';
    const title=document.createElement('summary');title.textContent='Columns';const panel=document.createElement('div');panel.className='column-options';menu.append(title,panel);
    const inputs=[];
    headers.forEach((th,index)=>{
      if(index===0||index===1||index===headers.length-1||th.querySelector('input'))return;
      const name=th.textContent.trim(),label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=!hidden.includes(name);check.setAttribute('aria-label','Show '+name);
      const apply=()=>{for(const row of table.rows){if(row.cells.length===headers.length)row.cells[index].hidden=!check.checked;}};
      check.addEventListener('change',()=>{apply();write(key,inputs.filter(i=>!i.check.checked).map(i=>i.name));});
      inputs.push({name,check,apply});label.append(check,document.createTextNode(name));panel.append(label);apply();
    });
    const reset=document.createElement('button');reset.type='button';reset.className='secondary';reset.textContent='Reset to default';reset.onclick=()=>{for(const i of inputs){i.check.checked=true;i.apply();}write(key,[]);};panel.append(reset);
    (document.querySelector('.quotation-table-controls')||root.parentNode).insertBefore(menu,document.querySelector('.quotation-table-controls')?null:root);
  }
  document.querySelectorAll('td>a').forEach(a=>{if(!a.title)a.title=a.textContent.trim();});
  const crumb=document.querySelector('.ux-breadcrumbs [aria-current=page]');if(crumb&&document.querySelector('h1'))crumb.textContent=document.querySelector('h1').textContent;
  const results=[...document.querySelectorAll('.ux-search-result')];
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape'){for(const menu of document.querySelectorAll('.header-menu[open],.column-menu[open]'))menu.open=false;if(document.activeElement.closest('.search-results'))document.querySelector('.global-search input')?.focus();}
    if(results.length&&['ArrowDown','ArrowUp'].includes(e.key)&&(!document.activeElement.matches('input,textarea,select')||document.activeElement.matches('.global-search input'))){e.preventDefault();const current=results.indexOf(document.activeElement);results[current<0?(e.key==='ArrowDown'?0:results.length-1):(current+(e.key==='ArrowDown'?1:-1)+results.length)%results.length].focus();}
  });
  document.addEventListener('click',e=>{for(const menu of document.querySelectorAll('.header-menu[open],.column-menu[open]'))if(!menu.contains(e.target))menu.open=false;});
  // Preserve native submitter values and all existing async handlers.
  const pending=new WeakSet();
  document.addEventListener('submit',e=>{
    const form=e.target;if(form.method.toLowerCase()!=='post')return;
    if(pending.has(form)){e.preventDefault();return;}
    const action=e.submitter?.value;
    if(form.id==='bulk-quotation-form'&&['archive','delete','restore'].includes(action)&&!confirm((action==='delete'?'Permanently delete':action==='archive'?'Archive':'Restore')+' the selected document families and their revisions?')){e.preventDefault();return;}
    queueMicrotask(()=>{if(e.defaultPrevented)return;pending.add(form);form.setAttribute('aria-busy','true');const button=e.submitter;if(button){button.setAttribute('aria-disabled','true');button.dataset.label=button.textContent;button.textContent='Processing…';}});
  });
  addEventListener('pageshow',()=>{for(const form of document.forms){pending.delete(form);form.removeAttribute('aria-busy');for(const b of form.querySelectorAll('[data-label]')){b.textContent=b.dataset.label;b.removeAttribute('aria-disabled');}}});
  const bulk=document.getElementById('bulk-quotation-form');if(bulk){const update=()=>{bulk.dataset.selected=String(bulk.elements.selection_mode.value==='matching'||!!document.querySelector('[data-family-select]:checked'));};document.addEventListener('change',update);document.addEventListener('click',()=>queueMicrotask(update));update();}
  for(const form of document.querySelectorAll('form[data-unsaved]')){
    const first=form.querySelector('input:not([type=hidden]):not([type=checkbox]),textarea,select');
    if(first&&!document.querySelector('.global-search input:focus')&&!location.hash)first.focus({preventScroll:true});
    for(const field of form.querySelectorAll('input,textarea,select')){
      field.addEventListener('invalid',()=>{field.setAttribute('aria-invalid','true');let error=field.nextElementSibling;if(!error?.classList.contains('field-error')){error=document.createElement('small');error.className='field-error';error.id='ux-error-'+Math.random().toString(36).slice(2);field.after(error);field.setAttribute('aria-describedby',error.id);}error.textContent=field.validationMessage;});
      field.addEventListener('input',()=>{if(field.validity.valid){field.removeAttribute('aria-invalid');const error=field.nextElementSibling;if(error?.classList.contains('field-error'))error.textContent='';}});
    }
  }
})();
