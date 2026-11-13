"""Real Chromium PDF rendering, background Waitress jobs and complete restore."""
import copy,io,json,os,re,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store,automation
from workspace_app.backup import restore
from test_v5 import quote
from browser_auth import bootstrap,login
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8007'


def run():
 with tempfile.TemporaryDirectory() as temp:
  td=Path(temp);root=td/'data';pdf=td/'pdf';backups=td/'backups';pdf.mkdir();backups.mkdir();bootstrap(root)
  with store.connect(root) as db:
   owner=db.execute('SELECT id FROM users').fetchone()[0];customer=store.save(db,'customer',dict(name='Synthetic Bank',contact='',notes=''));q=quote('AUTO-PDF',status='Draft');q.update(customer_id=customer,title='Saved : customer / title',internal_notes='INTERNAL-SECRET-SENTINEL');q['document']['show_12_month']=False;q['document']['sections'][0]['rows'][0]['cost']='123.77';ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=?',(owner,))
  log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(root),'CIRRUS_PORT':'8007','CIRRUS_PDF_BROWSER':'/usr/bin/chromium','CIRRUS_PDF_NO_SANDBOX':'1'},stdout=log,stderr=log)
  try:
   for _ in range(100):
    if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
    try:urllib.request.urlopen(BASE,timeout=1).close();break
    except OSError:time.sleep(.1)
   with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium');page=browser.new_page(viewport={'width':1450,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));login(page,BASE)
    page.goto(BASE+'/automation/settings');page.locator('[name=pdf_enabled]').check();page.locator('[name=pdf_folder]').fill(str(pdf));page.locator('[name=backup_enabled]').check();page.locator('[name=backup_folder]').fill(str(backups))
    page.get_by_role('button',name='Test PDF folder access',exact=True).click();assert 'Folder access test passed' in page.locator('body').inner_text();page.get_by_role('button',name='Test backup folder access',exact=True).click();assert 'Folder access test passed' in page.locator('body').inner_text();page.get_by_role('button',name='Save automation settings',exact=True).click()
    page.goto(BASE+'/customers/'+customer+'/quotation-folder');page.get_by_role('button',name='Create customer folder',exact=True).click();page.wait_for_url('**/customers/'+customer)
    page.goto(BASE+'/quotes/'+ident+'/edit');page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for();start=time.monotonic();page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/quotes/'+ident+'/edit');assert time.monotonic()-start<8
    deadline=time.monotonic()+60;job=None;state={}
    while time.monotonic()<deadline:
     with store.connect(root) as db:
      row=db.execute('SELECT * FROM pdf_exports WHERE record_id=?',(ident,)).fetchone();job=dict(row) if row else {};state=automation.backup_state(db)
     if job.get('status')=='failed':raise AssertionError(job)
     if job.get('status')=='success' and state.get('status')=='success':break
     page.wait_for_timeout(500)
    assert job['status']=='success',job;assert state['status']=='success',state;file=Path(job['destination']);assert file.name=='Saved _ customer _ title.pdf';assert file.parent.name=='quotation-'+ident
    text=subprocess.check_output(['pdftotext','-layout',str(file),'-']).decode();assert 'INTERNAL-SECRET-SENTINEL' not in text;assert '123.77' not in text;assert 'Quotation' in text and 'Messrs.' in text and 'Ref' in text;assert '12 months' not in text;assert 'Yearly recurring total' not in text
    print('PASS real background customer-only PDF, title sanitization, saved header/12-month setting and responsive save')
    page.goto(BASE+'/documents/'+ident+'/manage');assert str(file) in page.locator('body').inner_text();assert 'Last successful export' in page.locator('body').inner_text()
    # Change the configured folder to an unavailable share: saving must still succeed.
    customer_folder=pdf/'Synthetic Bank';customer_folder.rename(pdf/'temporarily-unavailable');page.goto(BASE+'/quotes/'+ident+'/edit');page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for();page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/quotes/'+ident+'/edit');page.locator('#auto-pdf-state').filter(has_text='Automatic PDF export failed').wait_for(timeout=20000);assert page.get_by_role('button',name='Retry PDF export',exact=True).is_visible();assert (pdf/'temporarily-unavailable'/file.relative_to(customer_folder)).is_file()
    (pdf/'temporarily-unavailable').rename(pdf/'Synthetic Bank');page.goto(BASE+'/documents/'+ident+'/manage');page.get_by_role('button',name='Retry PDF export',exact=True).click()
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
     with store.connect(root) as db:job=dict(db.execute('SELECT * FROM pdf_exports WHERE record_id=?',(ident,)).fetchone())
     if job['status']=='success':break
     page.wait_for_timeout(500)
    assert job['status']=='success';print('PASS unavailable export folder retains saved quotation and previous PDF; clear failure, status/destination and Retry')
    # Existing customer folder mapping and reassignment must leave old exports intact.
    with store.connect(root) as db:
     second=store.save(db,'customer',dict(name='SaradarBank',contact='',notes=''));missing=store.save(db,'customer',dict(name='No folder bank',contact='',notes=''))
    existing=pdf/'SaradarBank';existing.mkdir()
    page.goto(BASE+'/customers/'+second+'/quotation-folder');page.get_by_label('Quotation folder',exact=True).fill(str(existing));page.get_by_role('button',name='Test folder access',exact=True).click();assert 'Customer folder access test passed' in page.locator('body').inner_text();page.get_by_role('button',name='Save customer folder mapping',exact=True).click()
    page.goto(BASE+'/quotes/'+ident+'/edit');page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for();page.get_by_text('Quotation details',exact=True).click();page.get_by_label('Linked customer (explicit)',exact=True).select_option(second);page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/quotes/'+ident+'/edit')
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
     with store.connect(root) as db:job=dict(db.execute('SELECT * FROM pdf_exports WHERE record_id=?',(ident,)).fetchone())
     if job['status']=='success' and Path(job['destination']).parent.parent==existing:break
     page.wait_for_timeout(500)
    assert Path(job['destination']).parent.parent==existing;assert file.is_file();assert Path(job['destination']).is_file()
    page.goto(BASE+'/quotes/'+ident+'/edit');page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for();page.get_by_text('Quotation details',exact=True).click();page.get_by_label('Linked customer (explicit)',exact=True).select_option(missing);page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/quotes/'+ident+'/edit');page.locator('#auto-pdf-state').filter(has_text='Customer export folder not configured').wait_for(timeout=20000);assert page.get_by_role('link',name='Configure customer quotation folder',exact=True).is_visible();assert file.is_file()
    print('PASS explicit customer folder creation/mapping, reassignment to existing customer folder, old PDF retention and missing-mapping message with no fallback')
    page.goto(BASE+'/settings')
    with page.expect_download() as download:page.get_by_role('button',name='Download full backup',exact=True).click()
    full=td/'download.zip';download.value.save_as(full);target=td/'restored';restore(full,target)
    with store.connect(target) as db:assert db.execute('SELECT 1 FROM records WHERE id=?',(ident,)).fetchone();assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==1;assert db.execute('PRAGMA user_version').fetchone()[0]==9
    assert len(list((backups/'Cirrus-Workplace-full-backups').glob('daily-*.zip')))==1;assert len(list((backups/'Cirrus-Workplace-full-backups').glob('weekly-*.zip')))==1
    assert not errors,errors;print('PASS administrator folder tests/settings, automatic daily+weekly backups, portal full download and complete restore')
    browser.close()
  finally:
   server.terminate();server.wait(timeout=15);log.close()

if __name__=='__main__':run()
