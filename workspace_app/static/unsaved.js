"use strict";
(()=>{
 const forms=[...document.querySelectorAll('form[data-unsaved]')];let submitted=false;
 const state=f=>JSON.stringify([...f.querySelectorAll('input:not([type=hidden]),textarea,select')].map(n=>n.multiple?[...n.selectedOptions].map(o=>o.value):['checkbox','radio'].includes(n.type)?n.checked:n.value));
 const initial=forms.map(state),changed=f=>f.dataset.initialDirty==='true'||state(f)!==initial[forms.indexOf(f)];
 for(const f of forms){
  const update=()=>{const label=f.querySelector('.save-status');if(label)label.textContent=changed(f)?'Unsaved changes':'No unsaved changes';};
  f.addEventListener('input',update);f.addEventListener('change',update);update();
  f.addEventListener('submit',e=>{if(e.defaultPrevented)return;if(forms.some(other=>other!==f&&changed(other))&&!confirm('Other changes on this page have not been saved. Save this form and discard the other changes?')){e.preventDefault();return;}queueMicrotask(()=>{if(!e.defaultPrevented)submitted=true;});});
 }
 window.addEventListener('beforeunload',e=>{if(!submitted&&forms.some(changed)){e.preventDefault();e.returnValue='';}});
})();
