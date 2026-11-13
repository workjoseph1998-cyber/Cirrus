'use strict';
(() => {
 const form=document.getElementById('quotation-form');if(!form)return;
 const pane=document.getElementById('quotation-options'),optionsDialog=document.getElementById('studio-options-dialog'),optionsButton=document.getElementById('toggle-quotation-options');
 optionsDialog.append(pane);pane.hidden=false;optionsButton.textContent='Quotation options ▾';optionsButton.setAttribute('aria-expanded','false');
 optionsButton.addEventListener('click',()=>{if(optionsDialog.open)optionsDialog.close();else{optionsDialog.showModal();optionsButton.setAttribute('aria-expanded','true');}});
 document.getElementById('close-quotation-options').addEventListener('click',()=>optionsDialog.close());optionsDialog.addEventListener('close',()=>{optionsButton.setAttribute('aria-expanded','false');optionsButton.focus();});
 const studio=document.getElementById('studio'),toggle=document.getElementById('toggle-structure');studio.classList.add('structure-collapsed');toggle.addEventListener('click',()=>{const closed=studio.classList.toggle('structure-collapsed');toggle.setAttribute('aria-expanded',String(!closed));toggle.textContent=closed?'→ Structure & settings':'← Collapse structure';});
 const submission=document.getElementById('approvers-submission-dialog'),open=document.getElementById('open-approvers-submission');if(!submission||!open)return;
 for(const event of ['focusin','mouseover'])submission.addEventListener(event,e=>{if(e.target.closest('.approval-dot'))queueMicrotask(()=>{const tooltip=document.querySelector('.approval-live-tooltip');if(tooltip&&!submission.contains(tooltip))submission.append(tooltip);});});
 submission.addEventListener('close',()=>{const tooltip=submission.querySelector('.approval-live-tooltip');if(tooltip){tooltip.hidden=true;document.body.append(tooltip);}});
 let restoreStructure=false;open.addEventListener('click',()=>{restoreStructure=studio.classList.contains('structure-collapsed');if(restoreStructure)studio.classList.remove('structure-collapsed');if(!submission.open)submission.showModal();});submission.addEventListener('close',()=>{if(restoreStructure)studio.classList.add('structure-collapsed');restoreStructure=false;});submission.querySelectorAll('[data-close-submission]').forEach(b=>b.addEventListener('click',()=>submission.close()));
 submission.addEventListener('click',event=>{if(event.target.closest('#open-approval'))submission.close();},true);
 const selected=form.querySelector('[name=approvers]'),initial=JSON.stringify(JSON.parse(selected.value)),preview=document.getElementById('draft-approver-progress'),choices=JSON.parse(form.querySelector('.approver-choices').textContent);let saving=false;
 function renderSelection(){let people;try{people=JSON.parse(selected.value);}catch(_){people=[];}const changed=JSON.stringify(people)!==initial;preview.hidden=Boolean(form.dataset.saved==='true'&&!changed);preview.replaceChildren();
  if(!preview.hidden){const title=document.createElement('div');title.textContent=changed?'Selected for next submission · Unsaved selection':'Selected approvers · Not submitted';preview.append(title);const dots=document.createElement('span');dots.className='approval-dots';for(const p of people){const name=choices.find(u=>u.id===p.user_id)?.username||'Choose an approver',dot=document.createElement('span');dot.className='approval-dot';dot.tabIndex=0;dot.setAttribute('role','img');dot.title=dot.ariaLabel=name+' · Not approved yet';dots.append(dot);}const count=document.createElement('span');count.textContent='0 out of '+people.length+' approved';preview.append(dots,count);}
  submission.querySelector('[name=intent]').disabled=people.length===0;
 }
 form.addEventListener('change',renderSelection);form.addEventListener('submit',event=>{if(!event.defaultPrevented)saving=true;});
 addEventListener('beforeunload',event=>{if(!saving&&JSON.stringify(JSON.parse(selected.value))!==initial){event.preventDefault();event.returnValue='';}});renderSelection();
})();
