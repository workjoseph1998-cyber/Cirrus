"""Synthetic real-browser acceptance for the Version 18 refinements."""
import json,os,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from browser_auth import bootstrap,login
from test_v5 import quote
from workspace_app import store
from workspace_app.quotation import new_row,new_section
from workspace_app.quotation_defaults import initialize,catalog_for_code
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8034'
ART=Path(os.environ.get('CW_BROWSER_ARTIFACTS','/tmp/cirrus-refinement-artifacts'));ART.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory() as td:
 data=Path(td)/'data';bootstrap(data)
 with store.connect(data) as db:
  initialize(db);items=store.records(db,unrestricted=True);catalog=catalog_for_code(items,'CIR-STORAGE');catalog['data'].update(quantity='3',price='91',comments='Custom catalog storage');store.save(db,'catalog',catalog['data'],catalog['id'])
  q=quote(status='Draft');prod=q['document']['sections'][0];prod['name']='Main Site'
  comments='VM Size: Medium V1\nOperating system: Microsoft Windows\nVM Specs: 4 vCPU, 7.5 GB RAM\nManual note retained'
  prod['rows']=[new_row('Cirrus Compute',sub_service='Application VM',unit='VM',quantity='1',unit_price='228',comments=comments),new_row('Storage as a Service',sub_service='Storage',unit='TB',quantity='2',unit_price='83')]
  dr=new_section('Disaster Recovery');group=new_section('Compute and storage',dr['id']);replica=new_row('Cirrus Compute',unit='VM',sub_service='DR Application VM',quantity='1',unit_price='228',dr_mode='replication',dr_percent='50',comments=comments);group['rows']=[replica]
  setup=new_section('Connectivity Setup — One-Time Fee');setup['rows']=[new_row('Connectivity Setup',sub_service='One-Time fee',type='CaaS',quantity='1',method='fixed',fixed_fee='500',billing='one_time')]
  empty=new_section('Empty environment');q['document']['sections'] += [dr,group,setup,empty]
  ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=(SELECT id FROM users WHERE username=?) WHERE id=?',('browser-admin',ident))
 log=open('/tmp/cirrus-refinements-server.log','w');server=subprocess.Popen([str(ROOT/'.venv/bin/python'),'run.py'],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(data),'CIRRUS_PORT':'8034','CIRRUS_DISABLE_EMAIL':'1'},stdout=log,stderr=log)
 try:
  for _ in range(100):
   if server.poll() is not None:raise RuntimeError(Path('/tmp/cirrus-refinements-server.log').read_text())
   try:urllib.request.urlopen(BASE+'/login');break
   except OSError:time.sleep(.1)
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium');context=browser.new_context(viewport={'width':1920,'height':1080});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));login(page,BASE)
   page.goto(BASE+'/quotes/new');expect(page.locator('#preview-status')).to_contain_text('Preview current')
   draft=json.loads(page.locator('#quotation-data').input_value());rows=[r for s in draft['document']['sections'] for r in s['rows']]
   storage=next(r for r in rows if r['sub_service']=='Storage');assert storage['quantity']=='3' and storage['unit_price']=='91'
   assert next(r for r in rows if r['sub_service']=='Protected Link')['unit_price']==''
   page.goto(BASE+'/quotes/'+ident+'/edit');expect(page.locator('#preview-status')).to_contain_text('Preview current');frame=page.frame_locator('#customer-preview')
   primary=page.get_by_role('group',name='Save and approval').bounding_box();settings=page.get_by_role('group',name='Editor settings and exports').bounding_box();assert primary['x']<settings['x']
   article=frame.locator('article').bounding_box();assert article['width']<=1360
   for r in [prod['rows'][0],replica]:
    field=frame.locator('textarea[data-field=comments][data-row="'+r['id']+'"]');assert 'Operating system:' not in field.input_value();assert 'Manual note retained' in field.input_value()
   label=frame.locator('tr[data-row="'+replica['id']+'"] .dr-replication');expect(label).to_have_text('VM Replication');expect(label).to_have_css('color','rgb(185, 28, 28)')
   monthly=frame.locator('[data-computed="category-'+prod['id']+'"]');expect(monthly).to_contain_text('Monthly: $394.00');assert 'One-time:' not in monthly.inner_text()
   once=frame.locator('[data-computed="category-'+setup['id']+'"]');expect(once).to_contain_text('One-time: $500.00');assert 'Monthly:' not in once.inner_text()
   expect(frame.locator('[data-computed="category-'+empty['id']+'"]')).to_contain_text('Total: $0.00')
   page.screenshot(path=str(ART/'refined-toolbar-and-quotation.png'),full_page=True)
   label.scroll_into_view_if_needed();page.screenshot(path=str(ART/'refined-dr-comments.png'),full_page=True)
   once.scroll_into_view_if_needed();page.screenshot(path=str(ART/'refined-one-time-subtotal.png'),full_page=True)
   frame.locator('[data-action=explain][data-row="'+replica['id']+'"]').click();expect(frame.locator('.calculation-popover')).to_contain_text('50%');frame.locator('.calculation-popover button').last.click()
   frame.locator('[data-action=row-settings][data-row="'+replica['id']+'"]').click();row_settings=page.locator('#editor-controls details[data-row="'+replica['id']+'"]');row_settings.get_by_label('DR mode',exact=True).select_option('running');expect(page.locator('#preview-status')).to_contain_text('Preview current');expect(frame.locator('[data-computed="row-'+replica['id']+'"]')).to_contain_text('$228.00');assert 'Running' in frame.locator('tr[data-row="'+replica['id']+'"]').inner_text()
   row_settings.get_by_label('DR mode',exact=True).select_option('replication');expect(page.locator('#preview-status')).to_contain_text('Preview current')
   # Newly added catalog row copies the edited quantity and price.
   frame.locator('[data-action=catalog-row][data-section="'+prod['id']+'"]').click();pick=page.locator('select[aria-label="Catalog for Main Site"]');pick.select_option(catalog['id']);section=page.locator('[data-section-id="'+prod['id']+'"]');section.get_by_role('button',name='Copy catalog row',exact=True).click();expect(section.locator(':scope > details.row-editor')).to_have_count(3);expect(page.locator('#preview-status')).to_contain_text('Preview current');draft=json.loads(page.locator('#quotation-data').input_value());added=draft['document']['sections'][0]['rows'][-1];assert (added['quantity'],added['unit_price'],added['comments'])==('3','91','Custom catalog storage'),added
   page.locator('#toggle-structure').click();page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_load_state();expect(page.locator('#preview-status')).to_contain_text('Preview current');page.reload();expect(page.locator('#preview-status')).to_contain_text('Preview current');reopened=json.loads(page.locator('#quotation-data').input_value());saved_setup=next(s for s in reopened['document']['sections'] if s['id']==setup['id']);assert saved_setup['rows'][0]['billing']=='one_time'
   printed=context.new_page();printed.goto(BASE+'/quotes/'+ident+'/print');assert 'VM Replication' in printed.locator('body').inner_text();assert 'Operating system:' not in printed.locator('body').inner_text();assert 'Monthly:' not in printed.locator('[data-computed="category-'+setup['id']+'"]').inner_text();assert printed.pdf().startswith(b'%PDF-');printed.close()
   page.set_viewport_size({'width':390,'height':844});expect(page.locator('#workspace-nav')).to_have_css('transform','matrix(1, 0, 0, 1, -245, 0)');page.locator('#show-preview').click();expect(page.locator('#customer-preview')).to_be_visible();page.screenshot(path=str(ART/'refined-mobile-toolbar.png'),full_page=True);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');buttons=page.locator('.studio-toolbar button,.studio-toolbar a.button');bounds=[buttons.nth(i).bounding_box() for i in range(buttons.count())];assert all(b is None or (b['x']>=0 and b['x']+b['width']<=391) for b in bounds)
   assert not errors,errors;print('PASS: catalog quantities/prices, toolbar groups, centered width, exact red VM Replication, OS cleanup/manual notes, Running/Replication fees, applicable subtotals, save/reopen one-time billing, PDF, mobile toolbar. No JavaScript errors.');browser.close()
 finally:server.terminate();server.wait();log.close()
