'use strict';
(() => {
  const root = document.documentElement, body = document.body, csrf = body.dataset.csrf;
  const theme = document.getElementById('portal-theme');
  async function savePreferences() {
    if (!root.dataset.account) return;
    try {
      const res = await fetch('/preferences', {method:'POST',keepalive:true, body:new URLSearchParams({csrf,theme:theme.value,collapsed:body.classList.contains('nav-collapsed')?'yes':'no'})});
      if (!res.ok) throw new Error();
    } catch (_) { theme.title='Preference could not be saved to your account. Try again.'; }
  }
  theme?.addEventListener('change', () => {root.dataset.theme=theme.value;savePreferences();});
  document.getElementById('collapse-sidebar')?.addEventListener('click', () => {
    if (body.querySelector('.studio')) body.classList.toggle('editor-nav-expanded');
    else body.classList.toggle('nav-collapsed');
    savePreferences();
  });
  const mobile=document.getElementById('mobile-navigation'),backdrop=document.getElementById('nav-backdrop');
  function drawer(open) {body.classList.toggle('nav-open',open);backdrop.hidden=!open;mobile?.setAttribute('aria-expanded',String(open));if(open)document.querySelector('#workspace-nav a')?.focus();}
  document.getElementById('close-navigation')?.addEventListener('click',()=>drawer(false));
  mobile?.addEventListener('click',()=>drawer(!body.classList.contains('nav-open')));backdrop?.addEventListener('click',()=>drawer(false));
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape')drawer(false);
    if(e.key==='Tab'&&body.classList.contains('nav-open')){
      const items=[...document.querySelectorAll('#workspace-nav a[href],#workspace-nav button,#workspace-nav summary')].filter(n=>n.getClientRects().length);
      const first=items[0],last=items[items.length-1];
      if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
      else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
    }
  });
  const bell=document.getElementById('notification-bell');let updating=false;
  async function notifications(){
    if(!bell||updating||document.hidden)return;updating=true;
    try{
      const response=await fetch('/notifications/poll');if(!response.ok)return;const data=await response.json();
      document.getElementById('notification-unread').textContent=data.unread;
      document.querySelectorAll('[data-pending-badge]').forEach(n=>n.textContent=data.pending);
      const target=document.getElementById('notification-recent'),nodes=[];
      for(const n of data.recent){const a=document.createElement('a');a.href='/notifications/'+n.id+'/open';a.className=n.read_at?'':'unread';const title=document.createElement('b'),small=document.createElement('small'),text=document.createElement('span');title.textContent=n.kind;small.textContent=n.title;text.textContent=n.body.slice(0,140);a.append(title,small,text);nodes.push(a);}
      if(!nodes.length){const p=document.createElement('p');p.textContent='No notifications yet.';nodes.push(p);}target.replaceChildren(...nodes);
    }catch(_){}finally{updating=false;}
  }
  setInterval(notifications,15000);bell?.addEventListener('toggle',()=>{if(bell.open)notifications();});
  document.getElementById('mark-all-notifications')?.addEventListener('click',async()=>{await fetch('/notifications/read',{method:'POST',headers:{'X-Requested-With':'fetch'},body:new URLSearchParams({csrf,all:'yes'})});notifications();});
  const open=document.getElementById('open-approval');
  if(open){setInterval(async()=>{if(document.hidden)return;try{const r=await fetch(open.dataset.url+'/poll');if(r.ok){const s=await r.json();document.getElementById('editor-workflow-status').textContent=s.status+(s.reapproval?' · Reapproval required':'');const progress=document.querySelector('.workflow-mini [data-approval-progress]');if(progress)window.CirrusApprovals.render(progress,s.progress);}}catch(_){}},10000);const dialog=document.getElementById('editor-approval-dialog'),frame=dialog.querySelector('iframe');open.onclick=()=>{if(!frame.getAttribute('src'))frame.src=open.dataset.url+'?embedded=yes';dialog.showModal();};dialog.querySelector('[data-close-approval]').onclick=()=>dialog.close();}
})();
