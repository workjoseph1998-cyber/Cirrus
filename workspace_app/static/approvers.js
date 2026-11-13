'use strict';
(() => {
  for(const editor of document.querySelectorAll('.approvers-editor')){
    const field=editor.querySelector('[name=approvers]'),rows=editor.querySelector('.approver-rows'),choices=JSON.parse(editor.querySelector('.approver-choices').textContent);let selected=JSON.parse(field.value);
    function changed(){field.value=JSON.stringify(selected);editor.closest('form')?.dispatchEvent(new Event('change',{bubbles:true}));}
    function render(){rows.replaceChildren();selected.forEach((item,index)=>{
      const row=document.createElement('div');row.className='approver-selection-row';
      const label=document.createElement('label');label.textContent='Approver '+(index+1);const select=document.createElement('select');select.setAttribute('aria-label','Approver '+(index+1));select.add(new Option('Choose active staff…',''));
      for(const user of choices){const option=new Option(user.username,user.id);option.disabled=selected.some((other,i)=>i!==index&&other.user_id===user.id);select.add(option);}
      if(item.user_id&&!choices.some(u=>u.id===item.user_id))select.add(new Option('Unavailable account · select replacement',item.user_id));select.value=item.user_id;
      select.onchange=()=>{item.user_id=select.value;changed();render();};label.append(select);
      const stageLabel=document.createElement('label');stageLabel.textContent='Stage';const stage=document.createElement('select');stage.setAttribute('aria-label','Stage for approver '+(index+1));stage.add(new Option('Operations (parallel)','operations'));stage.add(new Option('Commercial (after operations)','commercial'));stage.value=item.phase;stage.onchange=()=>{item.phase=stage.value;changed();};stageLabel.append(stage);
      const controls=document.createElement('div');controls.className='approver-row-tools';for(const [text,delta] of [['↑',-1],['↓',1]]){const move=document.createElement('button');move.type='button';move.className='secondary';move.textContent=text;move.setAttribute('aria-label','Move approver '+(index+1)+(delta<0?' up':' down'));move.disabled=index+delta<0||index+delta>=selected.length;move.onclick=()=>{const target=index+delta;[selected[index],selected[target]]=[selected[target],selected[index]];changed();render();};controls.append(move);}
      const remove=document.createElement('button');remove.type='button';remove.className='secondary';remove.textContent='Remove';remove.setAttribute('aria-label','Remove approver '+(index+1));remove.onclick=()=>{selected.splice(index,1);changed();render();};controls.append(remove);row.append(label,stageLabel,controls);rows.append(row);
    });editor.querySelector('.approver-selection-feedback').textContent=selected.length+' selected';}
    editor.querySelector('.add-approver').onclick=()=>{selected.push({user_id:'',phase:'operations'});changed();render();rows.lastElementChild?.querySelector('select')?.focus();};render();
    editor.closest('form')?.addEventListener('submit',e=>{if(editor.closest('#creation-approvers')?.hidden)return;if(selected.some(x=>!x.user_id)||new Set(selected.map(x=>x.user_id)).size!==selected.length){e.preventDefault();editor.querySelector('.approver-selection-feedback').textContent='Choose each approver once, or remove incomplete rows.';}field.value=JSON.stringify(selected);});
  }
  const type=document.querySelector('.document-create [name=type]'),panel=document.getElementById('creation-approvers');if(type&&panel){const update=()=>{panel.hidden=type.value!=='Quotation';};type.addEventListener('change',update);update();}
})();
