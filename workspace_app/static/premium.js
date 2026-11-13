'use strict';
(() => {
  if(!document.body.classList.contains('premium-ui'))return;
  // Presentational enhancements only: existing links/forms remain the source of behavior.
  const paths={home:'M3 10 12 3l9 7v11h-6v-7H9v7H3z',quote:'M6 3h9l4 4v14H6z M14 3v5h5 M9 12h7 M9 16h7',users:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8',report:'M5 3h10l4 4v14H5z M9 17v-4 M12 17v-7 M15 17v-5',grid:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z'};
  const path=location.pathname;
  const type=path==='/'?'home':path.includes('customer')?'users':path.includes('report')?'report':path.includes('quote')||path.includes('document')||path.includes('approval')?'quote':'grid';
  function icon(kind){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');for(const [k,v] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'1.7','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true',class:'ui-icon'}))svg.setAttribute(k,v);const p=document.createElementNS(svg.namespaceURI,'path');p.setAttribute('d',paths[kind]||paths.grid);svg.append(p);return svg;}
  const heading=document.querySelector('.page h1');
  if(heading&&!heading.closest('.customer-workspace-header')){const row=document.createElement('div');row.className='premium-title-row';const symbol=document.createElement('span');symbol.className='page-symbol';symbol.append(icon(type));heading.before(row);row.append(symbol,heading);}
  const page=document.querySelector('.page');
  if(heading&&path!=='/'&&!page.querySelector('.breadcrumbs,.ux-breadcrumbs')){const nav=document.createElement('nav');nav.className='ux-breadcrumbs';nav.setAttribute('aria-label','Breadcrumb');const home=document.createElement('a');home.href='/';home.textContent='Home';const divider=document.createElement('span');divider.textContent='›';const current=document.createElement('span');current.setAttribute('aria-current','page');current.textContent=heading.textContent;nav.append(home,divider,current);page.prepend(nav);}
  document.querySelectorAll('.kpi').forEach((card,index)=>{if(card.querySelector('.metric-icon'))return;const badge=document.createElement('span');badge.className='metric-icon';badge.append(icon(index===0?'quote':index===3?'grid':'report'));card.prepend(badge);});
  document.querySelectorAll('.document-table td').forEach(cell=>{if(!cell.querySelector('a,button,input'))cell.title=cell.textContent.trim();});
  const toggle=document.getElementById('collapse-sidebar');const sync=()=>toggle?.setAttribute('aria-expanded',String(!document.body.classList.contains('nav-collapsed')));sync();toggle?.addEventListener('click',()=>queueMicrotask(sync));
  // In icon mode, open a chosen group by expanding the existing account-aware sidebar.
  document.querySelectorAll('.premium-nav-section>summary').forEach(summary=>summary.addEventListener('click',event=>{if(document.body.classList.contains('nav-collapsed')&&!document.body.classList.contains('nav-open')){event.preventDefault();toggle?.click();summary.parentElement.open=true;}}));
  document.querySelectorAll('.premium-navigation a[href]').forEach(link=>{const url=new URL(link.href);if(url.pathname===path&&!url.search){link.classList.add('active');link.setAttribute('aria-current','page');}if(!link.title)link.title=link.textContent.trim();});
})();
