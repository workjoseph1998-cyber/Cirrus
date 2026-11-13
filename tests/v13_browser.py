"""Synthetic real-browser v13 creation, ordered dots, resubmission and UI checks."""
import json,os,re,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from workspace_app import store,security
from test_v5 import quote
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8013';PASSWORD='V13-browser-test-only-password-2026!'
SCREEN=Path('/workspace/preservation');SCREEN.mkdir(exist_ok=True)

def run():
 with tempfile.TemporaryDirectory() as temporary:
  td=Path(temporary);data=td/'data';store.migrate(data)
  with store.connect(data) as db:
   ids={n:security.create_user(db,n,PASSWORD,'Administrator' if n=='admin' else 'Editor',n=='admin') for n in ['admin','author','ops1','ops2','commercial','extra']}
   customers={name:store.save(db,'customer',dict(name=name,contact='Synthetic contact',notes='')) for name in ['Acme Bank','Beta Bank']}
   db.execute('UPDATE records SET owner_id=?',(ids['author'],))
   db.execute("INSERT INTO settings VALUES ('approval_defaults',?)",(json.dumps(dict(operations_1=ids['ops1'],operations_2=ids['ops2'],commercial=ids['commercial'])),))
  log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(data),'CIRRUS_PORT':'8013','CIRRUS_DISABLE_EMAIL':'1'},stdout=log,stderr=log)
  pages=[]
  try:
   for _ in range(100):
    if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
    try:urllib.request.urlopen(BASE).close();break
    except OSError:time.sleep(.1)
   with sync_playwright() as driver:
    browser=driver.chromium.launch(executable_path='/usr/bin/chromium');errors=[]
    def login(name):
     page=browser.new_context(viewport={'width':1500,'height':1000}).new_page();pages.append(page);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/login');page.get_by_label('Username',exact=True).fill(name);page.get_by_label('Password',exact=True).fill(PASSWORD);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(BASE+'/');return page
    author=login('author');author.goto(BASE+'/documents/new');expect(author.locator('#creation-approvers')).to_be_hidden();author.get_by_label('1 · Document type',exact=True).select_option('Quotation');expect(author.locator('#creation-approvers')).to_be_visible();author.get_by_label('2 · Customer',exact=True).select_option(customers['Acme Bank']);author.get_by_label('3 · Subject',exact=True).fill('Cloud services V13')
    panel=author.locator('#creation-approvers');assert panel.locator('.approver-selection-row').count()==3
    panel.get_by_role('button',name='+ Add approver',exact=True).click();panel.get_by_label('Approver 4',exact=True).select_option(ids['extra']);assert panel.get_by_label('Approver 2',exact=True).locator('option[value="'+ids['ops1']+'"]').evaluate('(e)=>e.disabled');panel.get_by_role('button',name='Remove approver 4',exact=True).click();panel.get_by_role('button',name='Move approver 2 up',exact=True).click();assert panel.get_by_label('Approver 1',exact=True).input_value()==ids['ops2']
    author.screenshot(path=str(SCREEN/'v13-new-document-light.png'),full_page=True,animations='disabled');assert panel.bounding_box()['x']>author.locator('.document-create-grid>.card').first.bounding_box()['x']
    author.get_by_role('button',name='Continue',exact=True).click();author.wait_for_url('**/quotes/new?**');expect(author.locator('#preview-status')).to_contain_text('Preview current');author.get_by_role('button',name='Save quotation',exact=True).click();author.wait_for_url('**/quotes/*/edit');ident=author.url.split('/')[-2];url=BASE+'/quotes/'+ident
    with store.connect(data) as db:
     selected=json.loads(db.execute('SELECT data FROM quotation_approvers WHERE quote_id=?',(ident,)).fetchone()[0]);assert [r['user_id'] for r in selected]==[ids['ops2'],ids['ops1'],ids['commercial']];assert db.execute('SELECT count(*) FROM portal_notifications').fetchone()[0]==0
    author.locator('.editor-approval-setup summary').click();author.get_by_role('button',name='Save & submit for approval',exact=True).click();author.wait_for_url('**/quotes/'+ident+'/edit');expect(author.locator('#editor-workflow-status')).to_contain_text('Awaiting operations')
    op1=login('ops1');op1.goto(url+'/approval');op1.get_by_role('button',name='✓ Approve this version',exact=True).click();op2=login('ops2');op2.goto(url+'/approval');op2.get_by_role('button',name='✓ Approve this version',exact=True).click()
    def dots(page,green,white):
     progress=page.locator('[data-approval-progress="'+ident+'"]').first;expect(progress.locator('.approval-dot.is-approved')).to_have_count(green);expect(progress.locator('.approval-dot:not(.is-approved)')).to_have_count(white);expect(progress).to_contain_text(str(green)+' out of '+str(green+white)+' approved');return progress
    author.goto(BASE+'/list/quote');progress=dots(author,2,1);assert progress.locator('.approval-dot').nth(2).evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)';progress.locator('.approval-dot').first.focus();expect(author.locator('.approval-live-tooltip')).to_be_visible();expect(author.locator('.approval-live-tooltip')).to_contain_text('ops2');expect(author.locator('.approval-live-tooltip')).to_contain_text('Approved')
    author.screenshot(path=str(SCREEN/'v13-quotations-light.png'),full_page=True,animations='disabled');author.get_by_label('Portal theme',exact=True).select_option('dark');author.screenshot(path=str(SCREEN/'v13-quotations-dark.png'),full_page=True,animations='disabled');assert progress.locator('.approval-dot').nth(2).evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)'
    author.goto(BASE+'/');dots(author,2,1);author.screenshot(path=str(SCREEN/'v13-dashboard-dark.png'),full_page=True,animations='disabled');author.goto(BASE+'/customers/'+customers['Acme Bank']+'?tab=quotations&period=all');dots(author,2,1);author.screenshot(path=str(SCREEN/'v13-customer-quotations-dark.png'),full_page=True,animations='disabled')
    # Dedicated searchable dropdown combines with the ordinary text query.
    q=quote('BETA-V13',status='Draft');q.update(customer_id=customers['Beta Bank'],customer='Beta Bank',title='Beta only draft',date='2026-11-03')
    csrf=author.locator('body').get_attribute('data-csrf');created=author.request.post(BASE+'/quotes/new',form={'csrf':csrf,'quotation':json.dumps(q)},max_redirects=0);assert created.status==302
    author.goto(BASE+'/list/quote');author.locator('#quotation-customer-search').fill('Acme');author.locator('#quotation-customer').select_option(customers['Acme Bank']);author.get_by_role('button',name='Apply filters',exact=True).click();expect(author.locator('[data-document-id]')).to_have_count(1);assert 'customer_id='+customers['Acme Bank'] in author.url
    author.locator('#quotation-customer-search').fill('Beta');author.locator('#quotation-customer').select_option(customers['Beta Bank']);author.get_by_role('button',name='Apply filters',exact=True).click();expect(author.locator('[data-document-id]')).to_have_count(1);expect(author.locator('.document-title')).to_contain_text('Beta only draft')
    # Selection edits preserve old decisions but clear current dots until resubmission.
    author.goto(url+'/edit');expect(author.locator('#preview-status')).to_contain_text('Preview current');author.locator('.editor-approval-setup summary').click();editor=author.locator('#quotation-form .approvers-editor');editor.get_by_role('button',name='+ Add approver',exact=True).click();editor.get_by_label('Approver 4',exact=True).select_option(ids['extra']);author.get_by_role('button',name='Save quotation',exact=True).click();author.wait_for_url('**/quotes/'+ident+'/edit');expect(author.locator('#preview-status')).to_contain_text('Preview current');dots(author,0,4)
    with store.connect(data) as db:assert not db.execute("SELECT 1 FROM portal_notifications WHERE user_id=? AND kind='Review assignment'",(ids['extra'],)).fetchone()
    author.locator('.editor-approval-setup summary').click();author.get_by_role('button',name='Save & submit for approval',exact=True).click();author.wait_for_url('**/quotes/'+ident+'/edit')
    for page in [op1,op2]:page.goto(url+'/approval');page.get_by_role('button',name='✓ Approve this version',exact=True).click()
    extra=login('extra');extra.goto(url+'/approval');extra.get_by_role('button',name='✓ Approve this version',exact=True).click();commercial=login('commercial');commercial.goto(url+'/approval');commercial.get_by_role('button',name='✓ Approve this version',exact=True).click();expect(commercial.locator('#approval-status')).to_contain_text('Approved by all');dots(commercial,4,0);expect(commercial.locator('#reapproval-notice')).to_be_hidden()
    author.goto(url+'/approval');expect(author.locator('[data-artifact-status]')).to_contain_text('success',timeout=30000);author.screenshot(path=str(SCREEN/'v13-approval-dark.png'),full_page=True,animations='disabled')
    with author.expect_download() as download:author.get_by_role('link',name='Retained approved PDF',exact=True).click()
    assert Path(download.value.path()).read_bytes().startswith(b'%PDF-')
    author.goto(BASE+'/customers');author.screenshot(path=str(SCREEN/'v13-customers-dark.png'),full_page=True,animations='disabled');expect(author.get_by_role('columnheader',name=re.compile('quotation count',re.I))).to_be_visible();expect(author.get_by_role('columnheader',name=re.compile(r'quotation value \(USD\)',re.I))).to_be_visible()
    admin=login('admin');admin.goto(BASE+'/administration/workflow');security_mode=admin.get_by_label('SMTP security',exact=True);assert security_mode.locator('option').count()==3;security_mode.select_option('none');admin.get_by_label('SMTP host',exact=True).fill('192.0.2.17');admin.get_by_label('SMTP port',exact=True).fill('2526');admin.get_by_role('button',name='Save email settings',exact=True).click();expect(admin.get_by_label('SMTP security',exact=True)).to_have_value('none')
    author.set_viewport_size({'width':390,'height':850})
    for path,name in [('/list/quote','quotations'),('/documents/new','new-document'),('/quotes/'+ident+'/approval','approval')]:
     author.goto(BASE+path)
     if path=='/documents/new':author.get_by_label('1 · Document type',exact=True).select_option('Quotation')
     assert author.evaluate('document.documentElement.scrollWidth<=innerWidth+3'),path;author.screenshot(path=str(SCREEN/('v13-'+name+'-mobile.png')),full_page=True,animations='disabled')
    author.goto(url+'/print');assert author.locator('article').evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)';assert not errors,errors;browser.close();print('PASS: real v13 creation/ordered approvers, 2-green/1-white everywhere, keyboard tooltip, variable resubmission/full approval, customer search filter, None SMTP settings, retained PDF, desktop/mobile and light/dark. No emails sent.')
  except Exception:
   for index,page in enumerate(pages):
    try:page.screenshot(path=str(SCREEN/('v13-failure-'+str(index)+'.png')),full_page=True,animations='disabled')
    except Exception:pass
   print((td/'server.log').read_text()[-10000:]);raise
  finally:server.terminate();server.wait(timeout=20);log.close()

if __name__=='__main__':run()
