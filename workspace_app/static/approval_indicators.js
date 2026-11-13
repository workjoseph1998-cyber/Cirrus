'use strict';
(() => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  window.CirrusApprovals={render(container,p){
    const signature=JSON.stringify(p);if(container.dataset.progressSignature===signature)return;container.dataset.progressSignature=signature;
    let link=container.matches('a.approval-progress-summary')?container:container.querySelector('a.approval-progress-summary');
    if(!link){link=node('a',undefined,'approval-progress-summary');container.replaceChildren(link);}link.href='/quotes/'+p.quote_id+'/approval';link.dataset.approvalProgress=p.quote_id;
    const dots=node('span',undefined,'approval-dots');dots.setAttribute('aria-label','Approvers');for(const d of p.dots){const wrap=node('span',undefined,'approval-dot-wrap'),dot=node('span',undefined,'approval-dot'+(d.approved?' is-approved':''));dot.tabIndex=0;dot.setAttribute('role','img');dot.setAttribute('aria-label',d.tooltip);dot.title=d.tooltip;wrap.append(dot,node('span',d.tooltip,'approval-dot-tooltip'));dots.append(wrap);}const children=[dots,node('span',p.approved+' out of '+p.total+' approved','approval-progress-count')];
    if(p.label)children.push(node('span',p.label,'approval-progress-label'));else if(['Declined','Changes requested'].includes(p.status))children.push(node('span',p.status,'badge flow-attention'));link.replaceChildren(...children);
  }};
  let tooltip;
  function hide(){if(tooltip)tooltip.hidden=true;}
  function show(event){const dot=event.target.closest('.approval-dot');if(!dot)return;if(!tooltip){tooltip=node('div',undefined,'approval-live-tooltip');tooltip.setAttribute('role','tooltip');document.body.append(tooltip);}tooltip.textContent=dot.getAttribute('aria-label');tooltip.hidden=false;const box=dot.getBoundingClientRect();tooltip.style.left=Math.max(8,Math.min(innerWidth-tooltip.offsetWidth-8,box.left))+'px';tooltip.style.top=Math.max(8,box.top-tooltip.offsetHeight-8)+'px';}
  document.addEventListener('focusin',show);document.addEventListener('mouseover',show);document.addEventListener('focusout',hide);document.addEventListener('mouseout',e=>{if(e.target.closest('.approval-dot'))hide();});window.addEventListener('scroll',hide,true);window.addEventListener('resize',hide);
})();
