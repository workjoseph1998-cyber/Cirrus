'use strict';
(()=>{for(const form of document.querySelectorAll('.date-filters')){const period=form.querySelector('[name=period]');if(!period)continue;const update=()=>form.querySelectorAll('[data-period-field]').forEach(n=>n.hidden=n.dataset.periodField!==period.value);period.addEventListener('change',update);update();}})();
