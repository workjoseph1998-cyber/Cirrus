'use strict';
(() => {
const node=document.getElementById('auto-pdf-state'),retry=document.getElementById('retry-auto-pdf');if(!node)return;
async function refresh(){
 try{
  const response=await fetch(node.dataset.statusUrl);if(!response.ok)throw new Error();const status=await response.json();
  node.replaceChildren();const title=document.createElement('strong');title.textContent=!status.enabled?'Automatic PDF export disabled':status.status==='not_configured'?'Customer export folder not configured':status.status==='failed'?'Automatic PDF export failed — quotation saved successfully':status.status==='success'?'Automatic PDF export complete':'Automatic PDF export: '+status.status.replaceAll('_',' ');node.append(title);
  if(status.error){const error=document.createElement('small');error.textContent=status.error;node.append(error);}
  if(status.customer_config_url){const link=document.createElement('a');link.href=status.customer_config_url;link.textContent='Configure customer quotation folder';node.append(link);}
  if(status.last_success){const details=document.createElement('small');details.textContent='Last successful export: '+status.last_success+' · '+status.destination;node.append(details);}
  if(retry)retry.hidden=!status.enabled||!['failed','not_configured'].includes(status.status);
  if(status.enabled&&['pending','running'].includes(status.status))setTimeout(refresh,3000);
 }catch(error){node.textContent='PDF status unavailable. The quotation remains saved; see document management.';}
}refresh();
})();
