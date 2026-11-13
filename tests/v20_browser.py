"""Real catalog → default setup → two customer VM quotations → snapshot isolation."""
import json,os,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from browser_auth import bootstrap,login
from workspace_app import store,hosting
from workspace_app.model import FIELDS
from workspace_app.quotation import calculate
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8036';ART=Path(os.environ.get('CW_BROWSER_ARTIFACTS','/tmp/cirrus-v20'));ART.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as td:
 data=Path(td)/'data';bootstrap(data)
 with store.connect(data) as db:
  customers=[]
  for name,price in [('Synthetic Customer A','100'),('Synthetic Customer B','240')]:
   d={k:'' for k,_,_ in FIELDS['customer']};d['name']=name;cid=store.save(db,'customer',d);db.execute('UPDATE records SET owner_id=(SELECT id FROM users WHERE username=?) WHERE id=?',('browser-admin',cid));customers.append(cid)
   vm=dict(name=name+' VM',family='Small',vcpu='2',ram_gb='8',cost_a=price,cost_b=str(int(price)+50),price_status='Confirmed');vm=hosting.validate_vm(vm);db.execute('INSERT INTO customer_vm_catalog VALUES (?,?,?,1)',(cid,'customer-vm-'+cid,json.dumps(vm)))
 log=open('/tmp/cirrus-v20-server.log','w');server=subprocess.Popen([str(ROOT/'.venv/bin/python'),'run.py'],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(data),'CIRRUS_PORT':'8036','CIRRUS_DISABLE_EMAIL':'1'},stdout=log,stderr=log)
 try:
  for _ in range(100):
   if server.poll() is not None:raise RuntimeError(Path('/tmp/cirrus-v20-server.log').read_text())
   try:urllib.request.urlopen(BASE+'/login');break
   except OSError:time.sleep(.1)
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium');context=browser.new_context(viewport={'width':1908,'height':1080});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));login(page,BASE)
   page.goto(BASE+'/list/catalog')
   with store.connect(data) as db:
    from workspace_app.quotation_defaults import bindings
    ids=bindings(db);assert len([r for r in store.records(db,unrestricted=True) if r['kind']=='catalog'])==19
   page.goto(BASE+'/record/'+ids['CIR-STORAGE']);expect(page.locator('.catalog-fields').first).to_be_visible();page.get_by_label('Default quantity',exact=True).fill('3');page.get_by_label('Default selling price',exact=True).fill('91');page.get_by_label('Default comments',exact=True).fill('Shared storage default');page.get_by_role('button',name='Save catalog',exact=True).click();page.wait_for_load_state();expect(page.get_by_label('Default quantity',exact=True)).to_have_value('3');page.screenshot(path=str(ART/'v20-compact-catalog.png'),full_page=True)
   page.goto(BASE+'/quotation-defaults');setup=json.loads(page.locator('#initial-setup').text_content());cyber=next(s for s in setup['sections'] if s['role']=='cyber');block=page.locator('[data-section="'+cyber['id']+'"]');block.locator('summary').click();block.locator('.setup-add-service select').select_option(ids['CIR-STORAGE']);block.get_by_role('button',name='Assign service',exact=True).click();page.get_by_role('button',name='Save default setup',exact=True).first.click();page.wait_for_load_state();page.screenshot(path=str(ART/'v20-default-quotation-setup.png'),full_page=True)
   saved=[];saved_data=[]
   for index,cid in enumerate(customers):
    page.goto(BASE+'/quotes/new?customer_id='+cid);expect(page.locator('#preview-status')).to_contain_text('Preview current');q=json.loads(page.locator('#quotation-data').input_value());doc=q['document'];tops=[s['name'] for s in doc['sections'] if not s['parent']];assert tops==['Main Site','DR Site','Monitoring','Cybersecurity Services','Connectivity Services','Connectivity Setup — One-Time Fee','8×5 Request Fulfillment']
    storage=[r for s in doc['sections'] for r in s['rows'] if r['item_key']=='catalog:'+ids['CIR-STORAGE']];assert len(storage)==3 and all((r['quantity'],r['unit_price'])==('3','91') for r in storage)
    assert [s['name'] for s in doc['sections'] if any(r['item_key']=='catalog:'+ids['CIR-EDR'] for r in s['rows'])]==['Cybersecurity Services']
    frame=page.frame_locator('#customer-preview')
    # Use the actual customer-specific picker for both the Main and DR VM rows.
    for section in doc['sections']:
     for row in section['rows']:
      if row.get('vm_selection_required'):
       frame.locator('[data-action=vm-picker][data-row="'+row['id']+'"]').click();dialog=page.locator('.hosting-picker');expect(dialog).to_contain_text(('Synthetic Customer A' if index==0 else 'Synthetic Customer B')+' VM');dialog.get_by_role('button',name='Use '+('Synthetic Customer A' if index==0 else 'Synthetic Customer B')+' VM',exact=True).click();expect(page.locator('#preview-status')).to_contain_text('Preview current')
      if float(row['quantity'])<float(row.get('minimum_quantity','0')):
       frame.locator('[data-field=quantity][data-row="'+row['id']+'"]').fill(row['minimum_quantity']);expect(page.locator('#preview-status')).to_contain_text('Preview current')
    current=json.loads(page.locator('#quotation-data').input_value());vmrows=[(s,r) for s in current['document']['sections'] for r in s['rows'] if r['item_key'].startswith('vm:')];assert len(vmrows)==2
    calc=calculate(current['document']);expected_price='100.00' if index==0 else '240.00';assert all(r['unit_price']==expected_price for _,r in vmrows)
    drrow=next(r for s,r in vmrows if s['parent']==next(x['id'] for x in current['document']['sections'] if x.get('role')=='dr'));assert calc['rows'][drrow['id']]==('50.00' if index==0 else '120.00')
    if index==0:page.screenshot(path=str(ART/'v20-generated-quotation.png'),full_page=True)
    page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/quotes/*/edit');expect(page.locator('.quotation-save-toast')).to_contain_text('Quotation saved successfully');page.screenshot(path=str(ART/('v20-saved-confirmation.png' if index==0 else 'v20-customer-b.png')),full_page=True)
    ident=page.url.split('/')[-2];saved.append(ident)
    with store.connect(data) as db:saved_data.append(next(r['data'] for r in store.records(db,unrestricted=True) if r['id']==ident))
   # Future quotations update; both saved quotations retain the old quantity/price.
   page.goto(BASE+'/edit/catalog/'+ids['CIR-STORAGE']);page.get_by_label('Default quantity',exact=True).fill('4');page.get_by_label('Default selling price',exact=True).fill('99');page.get_by_role('button',name='Save catalog',exact=True).click();page.wait_for_load_state();page.goto(BASE+'/quotes/new?customer_id='+customers[0]);expect(page.locator('#preview-status')).to_contain_text('Preview current');fresh=json.loads(page.locator('#quotation-data').input_value());assert all((r['quantity'],r['unit_price'])==('4','99') for s in fresh['document']['sections'] for r in s['rows'] if r['item_key']=='catalog:'+ids['CIR-STORAGE'])
   with store.connect(data) as db:
    for ident,old in zip(saved,saved_data):assert next(r['data'] for r in store.records(db,unrestricted=True) if r['id']==ident)==old
   assert not errors,errors
   print('PASS: real admin catalog edit, setup assignment/save, full automatic structure for two customers, EDR only Cybersecurity, catalog defaults, separate customer VM prices, DR 50%, minima correction, actual successful-save prompt, catalog-change snapshot isolation. No JavaScript errors.');browser.close()
 finally:server.terminate();server.wait();log.close()
