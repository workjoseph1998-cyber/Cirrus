'use strict';
document.addEventListener('submit',event=>{if(event.defaultPrevented||(event.target.getAttribute('method')||'get').toLowerCase()!=='post')return;const form=event.target;if(form.dataset.submitting==='yes'){event.preventDefault();return;}form.dataset.submitting='yes';form.setAttribute('aria-busy','true');const button=event.submitter;if(button)button.textContent='Working…';});
