"""Synthetic editor-only layout acceptance and same-viewport baseline comparison."""
import json,os,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from browser_auth import bootstrap,login
from test_v5 import quote
from workspace_app import store
from workspace_app.company import standard_template
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8035'
ART=Path(os.environ.get('CW_BROWSER_ARTIFACTS','/tmp/cirrus-margin-layout'));ART.mkdir(parents=True,exist_ok=True)
BASELINE=os.environ.get('LAYOUT_BASELINE')=='1'
with tempfile.TemporaryDirectory() as td:
 data=Path(td)/'data';bootstrap(data)
 with store.connect(data) as db:
  q=quote(status='Draft');q['document']=standard_template();q['number']='LAYOUT-001'
  for section in q['document']['sections']:
   for row in section['rows']:
    if row['sub_service']=='VM':row.update(quantity='25',unit_price='50',comments='VM Size: Small V1\nVM Specs: 2 vCPU, 3.75 GB RAM')
    if row['sub_service']=='Storage':row.update(quantity='5',unit_price='83')
    if row['sub_service']=='SOC 24/7 monitoring':row.update(quantity='250',unit_price='5')
    if row['sub_service']=='NOC':row.update(quantity='50',unit_price='20')
  ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=(SELECT id FROM users WHERE username=?) WHERE id=?',('browser-admin',ident))
 log=open('/tmp/cirrus-margin-layout-server.log','w');server=subprocess.Popen([str(ROOT/'.venv/bin/python'),'run.py'],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(data),'CIRRUS_PORT':'8035','CIRRUS_DISABLE_EMAIL':'1'},stdout=log,stderr=log)
 try:
  for _ in range(100):
   if server.poll() is not None:raise RuntimeError(Path('/tmp/cirrus-margin-layout-server.log').read_text())
   try:urllib.request.urlopen(BASE+'/login');break
   except OSError:time.sleep(.1)
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium');context=browser.new_context(viewport={'width':1908,'height':960},device_scale_factor=1);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));login(page,BASE);page.goto(BASE+'/quotes/'+ident+'/edit');expect(page.locator('#preview-status')).to_contain_text('Preview current');frame=page.frame_locator('#customer-preview')
   def metrics():
    result=frame.locator('article').evaluate('''article=>{const rect=article.getBoundingClientRect(),round=n=>Math.round(n*1000)/1000;return {width:round(rect.width),font:getComputedStyle(document.body).font,columns:[...article.querySelectorAll('.service-table thead')][0]? [...article.querySelector('.service-table thead tr').children].map(n=>round(n.getBoundingClientRect().width)):[],rowHeights:[...article.querySelectorAll('tr[data-row]')].slice(0,12).map(n=>round(n.getBoundingClientRect().height)),cellFont:getComputedStyle(article.querySelector('textarea[data-row]')).font,visibleRows:[...article.querySelectorAll('tr[data-row]')].filter(n=>n.getBoundingClientRect().bottom<=innerHeight&&n.getBoundingClientRect().top>=0).length,frameHeight:innerHeight};}''')
    result['sheetTop']=page.locator('#customer-preview').bounding_box()['y']+frame.locator('article').bounding_box()['y']-page.locator('#customer-preview').bounding_box()['y']
    return result
   current=metrics()
   if BASELINE:
    (ART/'baseline-metrics.json').write_text(json.dumps(current,indent=2));page.screenshot(path=str(ART/'before-1908x960.png'),full_page=True);print(json.dumps(current));browser.close()
   else:
    baseline_path=ART/'baseline-metrics.json'
    if baseline_path.exists():
     before=json.loads(baseline_path.read_text())
     for key in ['width','font','columns','rowHeights','cellFont']:assert current[key]==before[key],(key,before[key],current[key])
     assert before['sheetTop']-current['sheetTop']>=150
     assert current['frameHeight']-before['frameHeight']>=150
     assert current['visibleRows']>before['visibleRows']
    expect(page.locator('.editor-margin-layout')).to_have_attribute('data-controls-mode','margins')
    expect(page.get_by_role('group',name='Save and approval').locator(':scope > button')).to_have_count(2)
    expect(page.get_by_role('group',name='Editor settings and exports').locator(':scope > button, :scope > a, :scope > details')).to_have_count(6)
    sheet=frame.locator('article').bounding_box();left=page.get_by_role('group',name='Editor settings and exports').bounding_box();right=page.get_by_role('group',name='Save and approval').bounding_box()
    assert left['x']+left['width']<sheet['x'] and right['x']>sheet['x']+sheet['width']
    assert left['x']>=74 and right['x']+right['width']<=1908
    expect(page.locator('.quotation-nav-context h1')).to_have_text('Quotation studio')
    expect(page.locator('.studio-heading,.studio-toolbar,.studio-preview>.pane-heading')).to_have_count(0)
    assert page.locator('main>header').bounding_box()['height']==56
    (ART/'after-metrics.json').write_text(json.dumps(current,indent=2));page.screenshot(path=str(ART/'after-1908x960.png'),full_page=True)
    # The margin controls stay put as the iframe's quotation content scrolls.
    frame.locator('.category').last.scroll_into_view_if_needed();assert page.get_by_role('group',name='Save and approval').bounding_box()['y']==right['y']
    frame.locator('article').evaluate('a=>a.ownerDocument.defaultView.scrollTo(0,0)')
    quantity=frame.locator('[data-field=quantity]').first;quantity.fill('26');expect(page.locator('#preview-status')).to_contain_text('unsaved changes')
    page.locator('#toggle-structure').click();expect(page.locator('.studio-editor')).to_be_visible();assert metrics()['width']==current['width'];page.locator('.quotation-structure-close').click()
    page.locator('#toggle-quotation-options').click();expect(page.locator('#studio-options-dialog')).to_be_visible();page.locator('#close-quotation-options').click();expect(quantity).to_have_value('26')
    page.get_by_role('button',name='Approvers & submission',exact=True).click();expect(page.locator('#approvers-submission-dialog')).to_be_visible();page.locator('[data-close-submission]').first.click();expect(quantity).to_have_value('26')
    more=page.locator('.more-actions');more.locator('summary').click()
    for action in [more.get_by_role('link',name='Export CSV'),more.get_by_role('button',name='Duplicate quotation'),more.get_by_role('button',name='New revision')]:
     action.scroll_into_view_if_needed();bounds=action.bounding_box();assert bounds['x']>=74 and bounds['x']+bounds['width']<sheet['x']
    more.locator('summary').click()
    page.get_by_role('link',name='Print / PDF',exact=True).click();expect(page.locator('#preview-status')).to_contain_text('Save quotation first');assert len(context.pages)==1
    page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_load_state();expect(page.locator('#preview-status')).to_contain_text('Preview current');page.reload();expect(page.locator('#preview-status')).to_contain_text('Preview current');expect(frame.locator('[data-field=quantity]').first).to_have_value('26')
    assert '$1,300.00' in frame.locator('[data-computed^=row-]').first.inner_text()
    printed=context.new_page();printed.goto(BASE+'/quotes/'+ident+'/print');assert printed.locator('.quotation-margin-rail').count()==0;assert printed.pdf().startswith(b'%PDF-');printed.close()
    exported=page.request.get(BASE+'/quotes/'+ident+'/xlsx');assert exported.status==200
    from openpyxl import load_workbook
    import io
    book=load_workbook(io.BytesIO(exported.body()),data_only=True);ws=book['Quotation'];n=next(i for i in range(1,ws.max_row+1) if ws.cell(i,1).value=='Cirrus Compute' and ws.cell(i,2).value=='VM');assert ws.cell(n,7).value==1300
    # No sheet scaling or clipped controls when the margins no longer fit.
    page.set_viewport_size({'width':1536,'height':960});expect(page.locator('.editor-margin-layout')).to_have_attribute('data-controls-mode','dialog');expect(page.locator('#open-quotation-controls')).to_be_visible();assert metrics()['width']==current['width']
    page.locator('#open-quotation-controls').click();expect(page.get_by_role('button',name='Save quotation',exact=True)).to_be_visible();page.locator('#toggle-structure').click();expect(page.locator('#quotation-controls-dialog')).not_to_be_visible();expect(page.locator('.studio-editor')).to_be_visible();page.locator('.quotation-structure-close').click()
    frame.locator('[data-field=quantity]').first.fill('27');expect(page.locator('#preview-status')).to_contain_text('unsaved changes');page.locator('#open-quotation-controls').click();page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_load_state();expect(page.locator('#preview-status')).to_contain_text('Preview current');page.reload();expect(page.locator('#preview-status')).to_contain_text('Preview current');expect(frame.locator('[data-field=quantity]').first).to_have_value('27')
    page.set_viewport_size({'width':390,'height':844});expect(page.locator('#workspace-nav')).to_have_css('transform','matrix(1, 0, 0, 1, -245, 0)');page.locator('#show-preview').click();page.locator('#open-quotation-controls').click();expect(page.locator('#quotation-controls-dialog')).to_be_visible()
    for control in page.locator('#quotation-controls-body button,#quotation-controls-body a.button').all():
     bounds=control.bounding_box();assert bounds and bounds['x']>=0 and bounds['x']+bounds['width']<=391,bounds
    page.screenshot(path=str(ART/'mobile-controls-390x844.png'),full_page=True)
    page.locator('#toggle-quotation-options').click();expect(page.locator('#studio-options-dialog')).to_be_visible();page.locator('#close-quotation-options').click();page.locator('#open-quotation-controls').click();page.keyboard.press('Escape');expect(page.locator('#quotation-controls-dialog')).not_to_be_visible();page.screenshot(path=str(ART/'mobile-sheet-390x844.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1');assert not errors,errors
    # Shared navigation and login remain unaffected outside the editor.
    page.set_viewport_size({'width':1908,'height':960});page.goto(BASE+'/');assert page.locator('.quotation-nav-context').count()==0;assert page.locator('main>header').bounding_box()['height']==68
    print('PASS: quotation sheet metrics; save/approvers right and six controls left; non-overlapping margin rails; scrolling; unsaved edits through settings/options/approval; save/reopen; PDF/Excel; responsive dialogs and Escape; unrelated navigation unchanged.');browser.close()
 finally:server.terminate();server.wait();log.close()
