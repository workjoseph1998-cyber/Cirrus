'use strict';
(() => {
  const app=document.getElementById('approval-app');if(!app)return;
  const url='/quotes/'+app.dataset.quote,csrf=document.body.dataset.csrf,timeline=document.getElementById('discussion-timeline'),form=document.getElementById('discussion-form');
  let lastId=0,busy=false,signature='';if(form)form.elements.request_id.value=crypto.randomUUID();
  const node=(tag,text,cls)=>{const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n;};
  const statusClass=s=>['Approved by all','Sent to client','Approved'].includes(s)?'flow-approved':['Declined','Changes requested'].includes(s)?'flow-attention':s==='Waiting'?'flow-waiting':'flow-pending';
  function reply(message){if(!form)return;form.elements.parent_id.value=message.id;const label=document.getElementById('reply-label');label.textContent='Reply to '+message.username+': '+message.body.slice(0,120);label.hidden=false;document.getElementById('cancel-reply').hidden=false;form.elements.body.focus();}
  function render(data){
    lastId=data.last_id;
    const key=JSON.stringify([data.messages,data.events]);if(key===signature)return;signature=key;
    const scrollBottom=timeline.scrollHeight-timeline.scrollTop-timeline.clientHeight<40,position=timeline.scrollTop;
    const entries=[...data.messages.map(m=>({...m,system:false})),...data.events.map(e=>({...e,system:true}))].sort((a,b)=>a.at.localeCompare(b.at)||a.id-b.id),nodes=[];
    for(const m of entries){const item=node('article','',m.system?'timeline-event':'chat-message');if(!m.system)item.id='message-'+m.id;
      item.append(node('strong',m.username+(m.system?' · Workflow event':'')),node('time',m.at.replace('T',' ').slice(0,19)+' UTC'));
      if(m.reply_to)item.append(node('blockquote',m.reply_to));item.append(node('p',m.body,'preserve'));
      if(m.system&&m.details.length){const details=document.createElement('details');details.append(node('summary','What changed ('+m.details.length+' fields)'));for(const change of m.details){const row=node('p',change.field);row.append(node('small','Before: '+JSON.stringify(change.before)),node('small','After: '+JSON.stringify(change.after)));details.append(row);}item.append(details);}
      if(!m.system&&form){const button=node('button','Reply','secondary');button.type='button';button.onclick=()=>reply(m);item.append(button);}nodes.push(item);
    }
    if(!nodes.length)nodes.push(node('p','Start the discussion. Workflow events will appear here.','muted'));
    timeline.replaceChildren(...nodes);timeline.scrollTop=scrollBottom?timeline.scrollHeight:position;
    if(location.hash.startsWith('#message-'))timeline.querySelector(location.hash)?.scrollIntoView({block:'nearest'});
  }
  async function poll(){if(busy||document.hidden)return;busy=true;try{const res=await fetch(url+'/approval/poll');if(!res.ok)throw Error('Refresh unavailable');const data=await res.json();render(data);
    const changed=String(data.version)!==app.dataset.version||(data.round_id||'')!==app.dataset.round;document.getElementById('approval-update').hidden=!changed;
    const status=document.getElementById('approval-status');status.textContent=changed?'Review updated saved version '+data.version:(['Approved by all','Sent to client'].includes(data.status)?'✅ ':'● ')+data.status;status.className='flow-status '+(changed?'flow-pending':statusClass(data.status));
    window.CirrusApprovals.render(document.getElementById('approval-progress'),data.progress);document.getElementById('reapproval-notice').hidden=!data.reapproval;document.getElementById('discussion-unread').textContent=data.unread+' unread';
    const grid=document.getElementById('reviewer-grid');for(const card of grid.querySelectorAll('[data-review-slot]')){if(!data.reviews.some(r=>r.slot===card.dataset.reviewSlot))card.remove();}for(const r of data.reviews){let card=grid.querySelector('[data-review-slot="'+r.slot+'"]');if(!card){card=node('article','','reviewer-card');card.dataset.reviewSlot=r.slot;card.append(node('strong',''),node('small',''),node('b','','review-state'),node('time',''),node('p','','review-comment preserve'));grid.append(card);}card.querySelector('strong').textContent=r.username;card.querySelector('small').textContent=r.responsibility;const state=card.querySelector('.review-state');state.textContent=(r.decision==='Approved'?'✓ ':'○ ')+r.display_state;state.className='review-state '+statusClass(r.display_state);card.querySelector('time').textContent=r.decided_at||'No decision yet';card.querySelector('.review-comment').textContent=r.comment;}
    const mine=data.reviews.find(r=>r.user_id===app.dataset.user);const action=document.querySelector('[data-review-decision]');if(action)action.hidden=changed||!mine?.actionable;
    if(data.artifacts)for(const artifact of data.artifacts){const label=document.querySelector('[data-artifact-status="'+artifact.id+'"]');if(label)label.textContent=artifact.status;}
  }catch(_){document.getElementById('discussion-feedback')?.replaceChildren(document.createTextNode('Live refresh unavailable. Your draft is retained.'));}finally{busy=false;}}
  render(JSON.parse(document.getElementById('discussion-initial').textContent));setInterval(poll,5000);poll();
  document.getElementById('cancel-reply')?.addEventListener('click',()=>{form.elements.parent_id.value='';document.getElementById('reply-label').hidden=true;document.getElementById('cancel-reply').hidden=true;});
  document.querySelectorAll('[data-mention]').forEach(b=>b.onclick=()=>{form.elements.body.value+=(form.elements.body.value&&!form.elements.body.value.endsWith(' ')?' ':'')+'@'+b.dataset.mention+' ';form.elements.body.dispatchEvent(new Event('input',{bubbles:true}));form.elements.body.focus();});
  form?.addEventListener('submit',async e=>{e.preventDefault();if(form.dataset.sending==='yes')return;form.dataset.sending='yes';const button=form.querySelector('button:not([type=button])'),feedback=document.getElementById('discussion-feedback');button.disabled=true;feedback.textContent='Posting…';try{const response=await fetch(url+'/discussion',{method:'POST',body:new FormData(form)});if(!response.ok){const parsed=new DOMParser().parseFromString(await response.text(),'text/html');throw Error(parsed.querySelector('.error')?.textContent||'Message was not saved. Check the message and mention names.');}form.elements.body.value='';form.elements.parent_id.value='';form.elements.request_id.value=crypto.randomUUID();form.dataset.initialDirty='false';document.getElementById('reply-label').hidden=true;document.getElementById('cancel-reply').hidden=true;feedback.textContent='Message posted.';poll();}catch(error){feedback.textContent=error.message;}finally{form.dataset.sending='no';button.disabled=false;}});
  document.getElementById('read-discussion').onclick=async()=>{const res=await fetch(url+'/discussion/read',{method:'POST',body:new URLSearchParams({csrf,last_id:String(lastId)})});if(res.ok)poll();};
})();
