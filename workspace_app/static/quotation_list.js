'use strict';
(() => {
 const root=document.querySelector('.quotation-list-workspace');if(!root)return;
 const filterToggle=document.getElementById('toggle-quotation-filters'),advanced=document.getElementById('quotation-advanced-filters');
 filterToggle.addEventListener('click',()=>{advanced.hidden=!advanced.hidden;filterToggle.setAttribute('aria-expanded',String(!advanced.hidden));});
 const controls=root.querySelector('.quotation-table-controls'),density=root.querySelector('.listing-tools');if(density)controls.append(density);
 const drawer=document.getElementById('document-utilities'),opener=document.getElementById('open-document-utilities'),closer=document.getElementById('close-document-utilities');
 function openUtilities(){if(!drawer.open)drawer.showModal();}
 opener.addEventListener('click',openUtilities);closer.addEventListener('click',()=>drawer.close());
 drawer.addEventListener('click',event=>{if(event.target===drawer){const r=drawer.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)drawer.close();}});
 drawer.addEventListener('click',event=>{if(event.target.closest('a[href]'))drawer.close();},true);
 for(const link of drawer.querySelectorAll('[data-management]'))link.setAttribute('aria-disabled','true');
 for(const button of root.querySelectorAll('.pick-document'))button.addEventListener('click',event=>{
  opener.title='Tools & management · '+button.dataset.title;
  for(const link of drawer.querySelectorAll('[data-management]'))link.setAttribute('aria-disabled','false');
  // The existing return-position code restores selection with a programmatic click.
  // Restore that selection without reopening a modal over the user's record list.
  if(event.isTrusted){drawer.querySelector('.sidebar-tools').open=true;openUtilities();}
 });
 const customerSearch=root.querySelector('.quotation-customer-search');
 customerSearch.addEventListener('toggle',()=>{if(customerSearch.open)document.getElementById('quotation-customer-search').focus();});
 document.getElementById('quotation-customer').addEventListener('change',()=>customerSearch.open=false);
 const bulk=root.querySelector('.quotation-bulk-menu'),matching=document.getElementById('select-matching');
 if(Number(matching.dataset.families)===0)matching.disabled=true;
 document.addEventListener('click',event=>{if(!bulk.contains(event.target))bulk.open=false;if(!customerSearch.contains(event.target))customerSearch.open=false;});
})();
