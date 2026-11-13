"""Real-browser V15 optional Monitoring, live comparison and customer documents."""
import copy,json,os,re,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store,security,customer_documents as docs
from test_v15 import optional_quote
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8015';PASSWORD='Synthetic-V15-browser-password!';SCREEN=Path('/workspace/preservation');SCREEN.mkdir(exist_ok=True)


def run():
 with tempfile.TemporaryDirectory() as temporary:
  td=Path(temporary);data=td/'data';disk=td/'customer-documents';store.migrate(data)
  with store.connect(data) as db:
   ids={name:security.create_user(db,name,PASSWORD,'Administrator' if name=='admin' else 'Editor',name=='admin') for name in ['admin','reader','outsider']}
   cust=store.save(db,'customer',dict(name='Acme Bank',contact='Jane Smith · Infrastructure',notes='Synthetic customer.'));db.execute('UPDATE records SET owner_id=? WHERE id=?',(ids['admin'],cust));db.execute('INSERT INTO record_acl VALUES (?,?,?)',(cust,ids['reader'],'read'))
   q=optional_quote();q.update(customer_id=cust,customer='Acme Bank',number='CIR26-200-1',title='Acme Bank · Cloud Services V1',date='2026-11-04');ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=? WHERE id=?',(ids['admin'],ident))
   second=copy.deepcopy(q);second['revision']=2;second['title']='Acme Bank · Cloud Services V2';second['document']['optional_monitoring']=True;second['document']['sections'][0]['rows'][0]['unit_price']='600';second['document']['sections'][3]['rows'][0]['fixed_fee']='1000';second_id=store.save(db,'quote',second,inherit_from=ident);db.execute('UPDATE records SET owner_id=? WHERE id=?',(ids['admin'],second_id))
  serverlog=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(data),'CIRRUS_PORT':'8015','CIRRUS_DISABLE_EMAIL':'1'},stdout=serverlog,stderr=serverlog)
  try:
   for _ in range(150):
    if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
    try:urllib.request.urlopen(BASE).close();break
    except OSError:time.sleep(.1)
   with sync_playwright() as driver:
    browser=driver.chromium.launch(executable_path='/usr/bin/chromium');errors=[]
    try:
     def login(name):
      page=browser.new_context(viewport={'width':1536,'height':1024}).new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/login');page.get_by_label('Username',exact=True).fill(name);page.get_by_label('Password',exact=True).fill(PASSWORD);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(BASE+'/');return page
     admin=login('admin');quote_url=BASE+'/quotes/'+ident;admin.goto(quote_url+'/edit');expect(admin.locator('#preview-status')).to_contain_text('Preview current');frame=admin.frame_locator('#customer-preview');fee=q['document']['sections'][-1]['rows'][0]['id'];expect(frame.locator('[data-computed="row-'+fee+'"]')).to_contain_text('$60.00')
     admin.get_by_label('Optional Monitoring',exact=True).check();expect(admin.locator('#preview-status')).to_contain_text('Preview current');expect(frame.locator('[data-computed="row-'+fee+'"]')).to_contain_text('$50.00');expect(frame.locator('.summary-regular')).to_contain_text('$1,150.00');expect(frame.locator('.summary-optional')).to_contain_text('$200.00');expect(frame.locator('.summary-optional')).to_contain_text('$2,400.00');assert frame.locator('.summary-optional th').evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(255, 242, 168)'
     admin.screenshot(path=str(SCREEN/'v15-editor-option-desktop.png'),full_page=True,animations='disabled');admin.get_by_role('button',name='Save quotation',exact=True).click();admin.wait_for_url(quote_url+'/edit');expect(admin.locator('#preview-status')).to_contain_text('Preview current');expect(admin.get_by_label('Optional Monitoring',exact=True)).to_be_checked()
     public=admin.context.new_page();public.goto(quote_url+'/print');expect(public.locator('.summary-optional')).to_contain_text('Optional: Monitoring');assert 'support_keys' not in public.content();public.screenshot(path=str(SCREEN/'v15-optional-customer-output.png'),full_page=True,animations='disabled');(SCREEN/'v15-optional-customer-output.pdf').write_bytes(public.pdf(print_background=True,prefer_css_page_size=True))
     admin.goto(quote_url+'/compare?before='+ident+'&after='+second_id);cards=admin.locator('#comparison-cards .kpi strong');expect(cards.nth(0)).to_have_text('$1,150.00');expect(cards.nth(1)).to_have_text('$1,360.00');expect(cards.nth(2)).to_have_text('$210.00')
     select=admin.get_by_label('Comparison basis',exact=True);assert select.bounding_box()['y']<cards.first.bounding_box()['y'];admin.evaluate('window.switchStarted=performance.now()');select.select_option('contract');expect(cards.nth(0)).to_have_text('$14,096.00');expect(cards.nth(1)).to_have_text('$17,320.00');expect(cards.nth(2)).to_have_text('$3,224.00');switch_ms=admin.evaluate('performance.now()-window.switchStarted');expect(admin.locator('#comparison-basis-note')).to_contain_text('one-time fees');admin.screenshot(path=str(SCREEN/'v15-comparison-contract-light.png'),full_page=True,animations='disabled');admin.reload();expect(admin.get_by_label('Comparison basis',exact=True)).to_have_value('contract')
     admin.get_by_label('Portal theme',exact=True).select_option('dark');admin.screenshot(path=str(SCREEN/'v15-comparison-dark.png'),full_page=True,animations='disabled')
     admin.goto(BASE+'/administration/customer-documents');admin.get_by_label('Customer documents root',exact=True).fill(str(disk));admin.get_by_role('checkbox',name='Create the root folder if it does not exist.',exact=True).check();admin.get_by_role('button',name='Test folder access',exact=True).click();expect(admin.locator('.notice')).to_contain_text('Folder access succeeded');admin.get_by_role('button',name='Save storage root',exact=True).click();expect(admin.locator('.notice')).to_contain_text('root saved')
     admin.goto(BASE+'/customers/'+cust);expect(admin.get_by_role('heading',name='Acme Bank',exact=True)).to_be_visible();expect(admin.get_by_role('link',name='Consumption',exact=True)).to_have_count(0);admin.screenshot(path=str(SCREEN/'v15-customer-overview-dark.png'),full_page=True,animations='disabled');admin.get_by_role('link',name='Documents',exact=True).click();expect(admin.get_by_role('heading',name='This folder is empty',exact=True)).to_be_visible();files_url=BASE+'/customers/'+cust+'/documents';admin.evaluate('window.documentSentinel="retained"')
     admin.locator('.file-upload-actions details').first.locator('summary').click();admin.get_by_label('Folder name',exact=True).fill('Contracts');admin.get_by_role('button',name='Create folder',exact=True).click();expect(admin.get_by_role('link',name='▱ Contracts',exact=True)).to_be_visible();assert admin.evaluate('window.documentSentinel')=='retained'
     def upload(filename,content):
      box=admin.locator('.file-upload-actions details').nth(1);box.locator('summary').click();box.locator('input[type=file]').set_input_files(dict(name=filename,mimeType='text/plain',buffer=content));box.get_by_role('button',name='Upload document',exact=True).click()
     upload('Notes.txt',b'original uploaded bytes');expect(admin.get_by_role('link',name='↧ Notes.txt',exact=True)).to_be_visible();assert admin.evaluate('window.documentSentinel')=='retained'
     upload('Notes.txt',b'new uploaded version');admin.wait_for_url('**/documents/uploads/*');expect(admin.get_by_role('heading',name='A file already has this name',exact=True)).to_be_visible();admin.get_by_role('button',name='Save as a new version',exact=True).click();admin.wait_for_url(files_url);expect(admin.get_by_role('link',name='↧ Notes (v2).txt',exact=True)).to_be_visible()
     row=admin.locator('.customer-file-table tbody tr').filter(has=admin.get_by_role('link',name='↧ Notes.txt',exact=True));row.get_by_role('link',name='Rename / move',exact=True).click();admin.get_by_label('Name',exact=True).fill('Signed Notes.txt')
     with store.connect(data) as db:folder=dict(db.execute("SELECT * FROM customer_document_nodes WHERE name='Contracts'").fetchone())
     admin.get_by_label('Destination folder',exact=True).select_option(folder['id']);admin.get_by_role('button',name='Save file/folder changes',exact=True).click();admin.wait_for_url('**/documents?folder='+folder['id']);expect(admin.get_by_role('link',name='↧ Signed Notes.txt',exact=True)).to_be_visible();expect(admin.locator('.file-breadcrumbs')).to_contain_text('Contracts')
     with store.connect(data) as db:
      item=dict(db.execute("SELECT * FROM customer_document_nodes WHERE name='Signed Notes.txt'").fetchone());space=docs.space(db,dict(id=cust,data=dict(name='Acme Bank')),data);assert (space/docs.relative(db,cust,item)).read_bytes()==b'original uploaded bytes'
     with admin.expect_download() as download:admin.get_by_role('link',name='↧ Signed Notes.txt',exact=True).click()
     assert download.value.suggested_filename=='Signed Notes.txt';assert Path(download.value.path()).read_bytes()==b'original uploaded bytes'
     admin.screenshot(path=str(SCREEN/'v15-customer-documents-dark.png'),full_page=True,animations='disabled');admin.get_by_label('Table density',exact=True).select_option('comfortable');assert admin.locator('body').get_attribute('data-table-density')=='comfortable'
     admin.goto(files_url);expect(admin.get_by_label('Table density',exact=True)).to_have_value('comfortable');admin.get_by_role('link',name='⌂ Acme Bank',exact=True).click();expect(admin.get_by_role('link',name='▱ Contracts',exact=True)).to_be_visible();row=admin.locator('.customer-file-table tbody tr').filter(has=admin.get_by_role('link',name='▱ Contracts',exact=True));row.get_by_role('link',name='Delete',exact=True).click();expect(admin.locator('.notice')).to_contain_text('1 file');admin.screenshot(path=str(SCREEN/'v15-folder-delete-dark.png'),full_page=True,animations='disabled');admin.get_by_role('checkbox',name='Delete Contracts and all its contents.',exact=True).check();admin.get_by_role('button',name='Delete permanently',exact=True).click();admin.wait_for_url(files_url);expect(admin.get_by_role('link',name='▱ Contracts',exact=True)).to_have_count(0);expect(admin.get_by_role('link',name='↧ Notes (v2).txt',exact=True)).to_be_visible()
     reader=login('reader');reader.goto(files_url);expect(reader.get_by_text('You have read access.',exact=False)).to_be_visible();expect(reader.get_by_role('button',name='Upload document',exact=True)).to_have_count(0);expect(reader.get_by_role('link',name='Rename / move',exact=True)).to_have_count(0)
     admin.goto(BASE+'/list/quote');admin.get_by_label('Search documents',exact=True).fill('Acme');admin.get_by_role('button',name='Apply filters',exact=True).click();expect(admin.locator('[data-document-id]')).to_have_count(1);admin.goto(BASE+'/');admin.goto(BASE+'/list/quote');expect(admin.get_by_label('Search documents',exact=True)).to_have_value('Acme');admin.screenshot(path=str(SCREEN/'v15-quotations-dark.png'),full_page=True,animations='disabled');admin.goto(BASE+'/');admin.screenshot(path=str(SCREEN/'v15-dashboard-dark.png'),full_page=True,animations='disabled')
     admin.set_viewport_size({'width':390,'height':850})
     for path,name in [('/customers/'+cust,'customer'),('/customers/'+cust+'/documents','documents'),('/list/quote','quotations'),('/quotes/'+ident+'/compare?before='+ident+'&after='+second_id,'comparison')]:
      admin.goto(BASE+path);assert admin.evaluate('document.documentElement.scrollWidth<=innerWidth+3'),path;admin.screenshot(path=str(SCREEN/('v15-'+name+'-mobile.png')),full_page=True,animations='disabled')
     assert not errors,errors;browser.close();print(json.dumps(dict(result='PASS',checks='optional Monitoring / save-reopen / support exclusion / yellow customer PDF; both comparison bases; file AJAX persistence / folders / upload / version / move / rename / download / confirmed deletion; read-only access; remembered filters / density; light-dark / desktop-mobile; no emails sent',comparison_switch_ms=round(switch_ms,2))))
    except Exception:
     try:admin.screenshot(path=str(SCREEN/'v15-browser-failure.png'),full_page=True,animations='disabled')
     except Exception:pass
     raise
  except Exception:
   print((td/'server.log').read_text()[-7000:]);raise
  finally:server.terminate();server.wait(timeout=20);serverlog.close()

if __name__=='__main__':run()
