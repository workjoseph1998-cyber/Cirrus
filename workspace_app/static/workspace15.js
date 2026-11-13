'use strict';
(()=>{
 const account=document.documentElement.dataset.account||'local',prefix='cw15:'+account+':',isEditor=!!document.getElementById('studio');
 const read=key=>{try{return JSON.parse(sessionStorage.getItem(prefix+key)||'null');}catch(_){return null;}},write=(key,value)=>{try{sessionStorage.setItem(prefix+key,JSON.stringify(value));}catch(_){}};
 let busy=false,loadSerial=0,allowFileLeave=false;
 function fileDraftDirty(){return [...document.querySelectorAll('.customer-files form[data-file-async]')].some(form=>Boolean(form.querySelector('[name=name]')?.value.trim()||form.querySelector('[type=file]')?.files.length));}
 addEventListener('beforeunload',event=>{if(!allowFileLeave&&fileDraftDirty()){event.preventDefault();event.returnValue='';}});addEventListener('pageshow',()=>{allowFileLeave=false;});
 document.addEventListener('input',event=>{if(event.target.matches('.customer-files [name=name]'))message('Folder details are not saved yet. Create the folder to save them.');});
 document.addEventListener('change',event=>{if(event.target.matches('.customer-files input[type=file]'))message('File selected. Click Upload document to save it.');});
 function listing(){return document.querySelector('[data-listing-key]');}
 function message(text,error=false){const target=document.querySelector('.file-feedback');if(target){target.textContent=text;target.className='file-feedback '+(error?'error':'notice');target.setAttribute('role',error?'alert':'status');}}
 function setupTables(){
  if(isEditor||location.pathname.startsWith('/hosting-vms')||location.pathname.includes('/tenant-pricing'))return;
  const tables=[...document.querySelectorAll('[data-listing-table]')];if(!tables.length)return;
  let density='compact';try{density=localStorage.getItem(prefix+'density')||'compact';}catch(_){}
  document.body.dataset.tableDensity=density==='comfortable'?'comfortable':'compact';
  if(!document.querySelector('.listing-density')){const bar=document.createElement('div');bar.className='listing-tools';const label=document.createElement('label');label.textContent='Table density ';const select=document.createElement('select');select.className='listing-density';select.setAttribute('aria-label','Table density');select.add(new Option('Compact','compact'));select.add(new Option('Comfortable','comfortable'));label.append(select);bar.append(label);tables[0].before(bar);}
  document.querySelectorAll('.listing-density').forEach(s=>s.value=document.body.dataset.tableDensity);
 }
 function savePosition(){const root=listing();if(!root)return;write('position:'+location.pathname+location.search,{y:scrollY,scroll:root.scrollTop});}
 function restorePosition(){const value=read('position:'+location.pathname+location.search);if(value)setTimeout(()=>{window.scrollTo(0,value.y);const root=listing();if(root)root.scrollTop=value.scroll;},40);}
 const root=listing();if(root&&!isEditor){const key='filters:'+root.dataset.listingKey,stored=read(key);if((!location.search||[...new URLSearchParams(location.search).keys()].every(k=>k==='tab'))&&stored&&stored.query&&stored.query!==location.search){location.replace(location.pathname+stored.query);return;}write(key,{query:location.search});restorePosition();}
 setupTables();
 document.addEventListener('change',event=>{if(!event.target.matches('.listing-density'))return;const value=event.target.value;document.body.dataset.tableDensity=value;try{localStorage.setItem(prefix+'density',value);}catch(_){}document.querySelectorAll('.listing-density').forEach(s=>s.value=value);});
 async function updateFiles(url,push=true,response=null){
  const serial=++loadSerial;
  if(!response)response=await fetch(url,{headers:{'X-Requested-With':'fetch'}});
  const html=await response.text(),parsed=new DOMParser().parseFromString(html,'text/html');if(serial!==loadSerial)return;
  if(!response.ok)throw Error(parsed.querySelector('.error')?.textContent?.trim()||'The action could not be completed. Your inputs are retained.');
  const next=parsed.querySelector('.customer-files');if(!next){allowFileLeave=true;location.assign(response.url||url);return;}
  document.querySelector('.customer-files').replaceWith(next);if(push)history.pushState(null,'',response.url||url);
  const notices=[...parsed.querySelectorAll('.notice[role=status]')].map(n=>n.textContent.trim());if(notices.length)message(notices.join(' '));
  setupTables();const current=listing();if(current)write('filters:'+current.dataset.listingKey,{query:location.search});
 }
 document.addEventListener('click',async event=>{
  const clear=event.target.closest('[data-clear-list]');if(clear){const root=listing();if(root)try{sessionStorage.removeItem(prefix+'filters:'+root.dataset.listingKey);sessionStorage.removeItem('cirrus.quotation.return');}catch(_){} }
  const link=event.target.closest('a[data-file-browse],.customer-files .listing-pagination a');if(!link||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
  event.preventDefault();if(busy)return;if(fileDraftDirty()&&!confirm('Discard the unsubmitted folder details or selected upload?'))return;busy=true;document.body.dataset.loading='true';savePosition();
  try{await updateFiles(link.href);}catch(e){message(e.message,true);}finally{busy=false;delete document.body.dataset.loading;}
 },true);
 document.addEventListener('submit',async event=>{
  const form=event.target,method=(form.getAttribute('method')||'get').toLowerCase();
  if(method==='get'&&form.hasAttribute('data-remember-filters')){const root=listing();const params=new URLSearchParams(new FormData(form));if(root)write('filters:'+root.dataset.listingKey,{query:'?'+params});}
  if(!form.matches('.customer-files form[data-file-async],.customer-files form[data-remember-filters]'))return;
  event.preventDefault();if(busy)return;if(method==='get'&&fileDraftDirty()&&!confirm('Discard the unsubmitted folder details or selected upload?'))return;busy=true;const started=location.href,data=new FormData(form,event.submitter),button=event.submitter,label=button?.textContent;document.body.dataset.loading='true';form.setAttribute('aria-busy','true');if(button){button.disabled=true;button.textContent=method==='post'?'Saving…':'Loading…';}message(method==='post'?'Saving your document changes…':'Loading documents…');
  try{const url=method==='get'?location.pathname+'?'+new URLSearchParams(data):form.action;const response=await fetch(url,{method:method.toUpperCase(),...(method==='post'?{body:data}:{}),headers:{'X-Requested-With':'fetch'}});if(location.href!==started)await updateFiles(location.href,false);else await updateFiles(response.url||url,true,response);}
  catch(e){message(e.message,true);}finally{busy=false;delete document.body.dataset.loading;form.removeAttribute('aria-busy');if(button){button.disabled=false;button.textContent=label;}}
 },true);
 addEventListener('popstate',()=>{if(document.querySelector('.customer-files'))updateFiles(location.href,false).catch(e=>message(e.message,true));});
 document.addEventListener('click',event=>{if(event.target.closest('a[href]'))savePosition();});addEventListener('pagehide',savePosition);
 document.querySelector('form[action="/logout"]')?.addEventListener('submit',()=>{try{for(const key of Object.keys(sessionStorage))if(key.startsWith(prefix))sessionStorage.removeItem(key);sessionStorage.removeItem('cirrus.quotation.return');}catch(_){}});
})();
