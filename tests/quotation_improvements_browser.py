import sys,os,tempfile,subprocess,time,json,urllib.request
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from browser_auth import bootstrap,login
from test_v5 import quote
from workspace_app import store
from workspace_app.quotation import new_row,new_section
from workspace_app.quotation_defaults import initialize
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8033';ART=Path(os.environ.get('CW_BROWSER_ARTIFACTS','/tmp/cirrus-quotation-artifacts'));ART.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as td:
 data=Path(td)/'data';bootstrap(data)
 with store.connect(data) as db:
  initialize(db);q=quote(status='Draft');prod=q['document']['sections'][0];prod['rows']=[new_row('Compute',sub_service='Customer VM',unit='VM',quantity='1',unit_price='228',comments='VM Size: Customer VM\nOperating system: Linux\nVM Specs: 4 vCPU, 16 GB RAM'),new_row('Storage as a Service',sub_service='Storage',unit='TB',quantity='2',unit_price='83')]
  dr=new_section('Disaster Recovery');group=new_section('Compute and storage',dr['id']);replica=new_row('Compute',unit='VM',sub_service='DR VM',quantity='1',unit_price='228',dr_mode='replication',dr_percent='50',dr_link=prod['rows'][0]['id']);group['rows']=[replica]
  empty=new_section('Security Services',dr['id']);q['document']['sections'] += [dr,group,empty]
  ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=(SELECT id FROM users WHERE username=?) WHERE id=?',('browser-admin',ident))
 log=open('/tmp/cirrus-improvements-server.log','w');server=subprocess.Popen([str(ROOT/'.venv/bin/python'),'run.py'],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(data),'CIRRUS_PORT':'8033','CIRRUS_DISABLE_EMAIL':'1'},stdout=log,stderr=log)
 try:
  for _ in range(100):
   try:urllib.request.urlopen(BASE+'/login');break
   except OSError:time.sleep(.1)
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium');context=browser.new_context(viewport={'width':1536,'height':1024});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));login(page,BASE);page.goto(BASE+'/quotes/new');expect(page.locator('#preview-status')).to_contain_text('Preview current');initial=json.loads(page.locator('#initial-quotation').text_content());standards=[r for section in initial['document']['sections'] for r in section['rows']];assert all(r['quantity']=='1' for r in standards);soc=next(r for r in standards if r['sub_service']=='SOC 24/7 Monitoring');assert soc['unit_price']=='5.00' and soc['minimum_quantity']=='250';noc=next(r for r in standards if r['sub_service']=='NOC');assert noc['unit_price']=='20.00' and noc['minimum_quantity']=='50';page.goto(BASE+'/quotes/'+ident+'/edit');expect(page.locator('#preview-status')).to_contain_text('Preview current')
   frame=page.frame_locator('#customer-preview');expect(frame.locator('[data-computed="row-'+replica['id']+'"]')).to_contain_text('$114.00');expect(page.locator('#studio')).to_have_class(__import__('re').compile('structure-collapsed'))
   frame.locator('[data-action=row-settings][data-row="'+replica['id']+'"]').click();settings=page.locator('#editor-controls details[data-row="'+replica['id']+'"]');settings.get_by_label('DR mode',exact=True).select_option('running');expect(page.locator('#preview-status')).to_contain_text('Preview current');expect(frame.locator('[data-computed="row-'+replica['id']+'"]')).to_contain_text('$228.00');settings.get_by_label('DR mode',exact=True).select_option('replication');expect(page.locator('#preview-status')).to_contain_text('Preview current');expect(frame.locator('[data-computed="row-'+replica['id']+'"]')).to_contain_text('$114.00');page.locator('#toggle-structure').click();expect(page.locator('#studio')).to_have_class(__import__('re').compile('structure-collapsed'))
   page.screenshot(path=str(ART/'quotation-editor.png'),full_page=True)
   frame.locator('[data-row="'+replica['id']+'"][data-action=explain]').click();expect(frame.locator('.calculation-popover')).to_contain_text('50%');page.screenshot(path=str(ART/'calculation-popover.png'),full_page=True);frame.locator('.calculation-popover button').last.click()
   page.locator('#toggle-quotation-options').click();expect(page.locator('#quotation-options')).to_be_visible();page.locator('#optional-monitoring').check();page.locator('#optional-monitoring').uncheck();page.locator('#close-quotation-options').click();expect(page.locator('#preview-status')).to_contain_text('Preview current')
   printed=page.context.new_page();printed.goto(BASE+'/quotes/'+ident+'/print');assert '$114.00' in printed.locator('body').inner_text();assert 'Replication' in printed.locator('body').inner_text();assert printed.locator('[data-action=explain]').count()==0;assert printed.pdf().startswith(b'%PDF-');printed.close()
   # Empty group removal and row-selection deletion; saved round trip.
   frame.locator('[data-action=remove-group][data-section="'+empty['id']+'"]').click();expect(page.locator('#preview-status')).to_contain_text('Preview current');expect(frame.locator('[data-section="'+empty['id']+'"]')).to_have_count(0)
   frame.locator('[data-select-row="'+replica['id']+'"]').check();expect(frame.locator('[data-action=delete-selected][data-section="'+dr['id']+'"]')).to_have_text('Delete selected (1)');frame.locator('[data-action=delete-selected][data-section="'+dr['id']+'"]').click();expect(page.locator('#preview-status')).to_contain_text('Preview current');expect(frame.locator('[data-computed="category-'+dr['id']+'"]')).to_contain_text('$0.00')
   page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_load_state();expect(page.locator('#preview-status')).to_contain_text('Preview current');page.goto(BASE+'/quotes/'+ident+'/edit');expect(page.locator('#preview-status')).to_contain_text('Preview current');expect(page.frame_locator('#customer-preview').locator('[data-select-row="'+replica['id']+'"]')).to_have_count(0)
   page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(ART/'quotation-editor-mobile.png'),full_page=True)
   assert not errors,errors
   print('PASS: real Chromium/Waitress replication calculation, popover, collapsed layout, option toggles, empty group removal, selected deletion, recalculation, save/reopen, mobile rendering; no JavaScript errors.')
   browser.close()
 finally:server.terminate();server.wait();log.close()
