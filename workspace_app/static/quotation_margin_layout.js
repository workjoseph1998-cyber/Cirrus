'use strict';
(() => {
 const saved=document.querySelector('.quotation-save-toast');if(saved){document.getElementById('dismiss-quotation-saved')?.addEventListener('click',()=>saved.remove());setTimeout(()=>saved.remove(),12000);}
 const layout=document.querySelector('.editor-margin-layout');if(!layout)return;
 const studio=document.getElementById('studio'),preview=layout.querySelector('.studio-preview'),frame=document.getElementById('customer-preview');
 const source=document.getElementById('quotation-action-source'),primary=source.querySelector('.studio-primary-actions'),secondary=source.querySelector('.studio-heading-actions');
 const dialog=document.getElementById('quotation-controls-dialog'),body=document.getElementById('quotation-controls-body'),opener=document.getElementById('open-quotation-controls');
 const header=document.querySelector('main>header.portal-header'),left=document.createElement('div'),right=document.createElement('div');
 left.className=right.className='quotation-margin-rail';left.hidden=right.hidden=true;preview.append(left,right);
 let marginMode=false,scheduled=false;
 function closeControls(){if(dialog.open)dialog.close();}
 opener.addEventListener('click',()=>{if(!dialog.open){dialog.showModal();opener.setAttribute('aria-expanded','true');}});
 document.getElementById('close-quotation-controls').addEventListener('click',closeControls);
 dialog.addEventListener('close',()=>{opener.setAttribute('aria-expanded','false');if(!opener.hidden)opener.focus();});
 // Preserve the same live controls, forms and listeners across responsive modes.
 dialog.addEventListener('click',event=>{if(event.target.closest('#toggle-structure,#toggle-quotation-options,#open-approvers-submission'))closeControls();},true);
 const closeStructure=document.createElement('button');closeStructure.type='button';closeStructure.className='secondary quotation-structure-close';closeStructure.textContent='Close settings ✕';closeStructure.addEventListener('click',()=>{if(!studio.classList.contains('structure-collapsed'))document.getElementById('toggle-structure').click();});
 document.querySelector('.studio-editor>.pane-heading').prepend(closeStructure);
 document.getElementById('show-editor').addEventListener('click',()=>{if(studio.classList.contains('structure-collapsed'))document.getElementById('toggle-structure').click();});
 document.getElementById('show-preview').addEventListener('click',()=>{if(!studio.classList.contains('structure-collapsed'))document.getElementById('toggle-structure').click();});
 for(const modal of [document.getElementById('studio-options-dialog'),document.getElementById('approvers-submission-dialog')])modal?.addEventListener('close',()=>{if(!marginMode&&!dialog.open)opener.focus();});
 function arrange(){
  scheduled=false;document.documentElement.style.setProperty('--quotation-header-height',header.getBoundingClientRect().height+'px');
  const article=frame.contentDocument?.querySelector('article');if(!article)return;
  const sheet=article.getBoundingClientRect(),host=preview.getBoundingClientRect(),iframe=frame.getBoundingClientRect();
  const sheetLeft=iframe.left-host.left+sheet.left,sheetRight=iframe.left-host.left+sheet.right;
  const enough=sheetLeft>=200&&host.width-sheetRight>=200;
  if(enough){
   closeControls();if(primary.parentElement!==right){left.append(secondary);right.append(primary);}
   left.hidden=right.hidden=false;opener.hidden=true;
   left.style.left=(sheetLeft-188)+'px';right.style.left=(sheetRight+12)+'px';
   left.style.top=right.style.top=Math.max(12,iframe.top-host.top+12)+'px';
  }else{
   left.hidden=right.hidden=true;opener.hidden=false;
   if(primary.parentElement!==body)body.append(primary,secondary);
  }
  marginMode=enough;layout.dataset.controlsMode=marginMode?'margins':'dialog';
 }
 function schedule(){if(!scheduled){scheduled=true;requestAnimationFrame(arrange);}}
 frame.addEventListener('load',()=>{schedule();frame.contentWindow?.addEventListener('scroll',schedule,{passive:true});});
 new ResizeObserver(schedule).observe(preview);new ResizeObserver(schedule).observe(header);
 window.addEventListener('resize',schedule);schedule();
})();
