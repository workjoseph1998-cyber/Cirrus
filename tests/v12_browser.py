"""Real synthetic Waitress/Chromium workflow and theme/print checks; no SMTP."""
import json,os,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from workspace_app import store,security
from workspace_app.approvals import SLOTS
from test_v5 import quote
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8012';PASSWORD='Browser-workflow-test-only-2026!'
SCREEN=Path('/workspace/preservation');SCREEN.mkdir(exist_ok=True)

def run():
 with tempfile.TemporaryDirectory() as directory:
  td=Path(directory);data=td/'data';store.migrate(data)
  with store.connect(data) as db:
   ids={name:security.create_user(db,name,PASSWORD,'Administrator' if name=='admin' else 'Editor',name=='admin') for name in ['admin','author','ops1','ops2','commercial']}
   customer=store.save(db,'customer',dict(name='Synthetic customer',contact='Synthetic contact',notes=''))
   q=quote('CIR26-201-1',status='Draft');q.update(customer_id=customer,internal_notes='PRIVATE-WORKFLOW-NOTE');q['document']['sections'][0]['rows'][0]['cost']='731.29'
   ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=?',(ids['author'],))
   db.execute("INSERT INTO settings VALUES ('approval_defaults',?)",(json.dumps(dict(zip(SLOTS,[ids['ops1'],ids['ops2'],ids['commercial']]))),))
  log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(data),'CIRRUS_PORT':'8012','CIRRUS_DISABLE_EMAIL':'1'},stdout=log,stderr=log)
  try:
   for _ in range(100):
    if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
    try:urllib.request.urlopen(BASE).close();break
    except OSError:time.sleep(.1)
   with sync_playwright() as playwright:
    browser=playwright.chromium.launch(executable_path='/usr/bin/chromium');errors=[]
    def login(name):
     context=browser.new_context(viewport={'width':1500,'height':1000});page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/login');page.get_by_label('Username',exact=True).fill(name);page.get_by_label('Password',exact=True).fill(PASSWORD);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(BASE+'/');return page
    author=login('author');author.goto(BASE+'/quotes/'+ident+'/edit');expect(author.locator('#preview-status')).to_contain_text('Preview current')
    assert author.locator('#workspace-nav').bounding_box()['width']==74
    author.locator('.editor-approval-setup summary').click();author.get_by_role('button',name='Save & submit for review',exact=True).click();author.wait_for_url('**/quotes/'+ident+'/edit');expect(author.locator('#editor-workflow-status')).to_contain_text('Awaiting operations')
    author.get_by_role('button',name='Approval & discussion',exact=True).click();chat=author.frame_locator('#editor-approval-dialog iframe');chat.locator('#discussion-body').fill('@ops1 Please review the technical scope.');chat.get_by_role('button',name='Post message',exact=True).click();expect(chat.locator('#discussion-feedback')).to_contain_text('Message posted');author.get_by_role('button',name='Close approval & discussion',exact=True).click()
    # Opening/polling discussion must not change quotation edits or navigation.
    author.get_by_text('Quotation details',exact=True).click();title=author.get_by_label('Document title',exact=True);title.fill('Unsaved title survives polling');author.get_by_role('button',name='Approval & discussion',exact=True).click();expect(chat.locator('#discussion-timeline')).to_contain_text('technical scope');author.wait_for_timeout(5200);chat.locator('#discussion-body').fill('Unsaved discussion draft');author.get_by_role('button',name='Close approval & discussion',exact=True).click();assert title.input_value()=='Unsaved title survives polling';author.get_by_role('button',name='Approval & discussion',exact=True).click();assert chat.locator('#discussion-body').input_value()=='Unsaved discussion draft';chat.locator('#discussion-body').fill('');author.get_by_role('button',name='Close approval & discussion',exact=True).click()
    # Leave test edits deliberately, then inspect the submitted workflow.
    author.on('dialog',lambda d:d.accept());author.goto(BASE+'/quotes/'+ident+'/approval')
    ops1=login('ops1');ops1.goto(BASE+'/approvals');expect(ops1.locator('h1')).to_have_text('Approvals');assert '1 actionable' in ops1.locator('body').inner_text();ops1.get_by_role('link',name='Synthetic quotation',exact=True).click();expect(ops1.locator('#discussion-timeline')).to_contain_text('technical scope')
    commercial=login('commercial');commercial.goto(BASE+'/quotes/'+ident+'/approval');assert commercial.locator('[data-review-decision]').is_hidden()
    ops1.locator('[name=comment]').fill('Technical scope and quantities checked.');ops1.get_by_role('button',name='✓ Approve this version',exact=True).click();expect(ops1.locator('#approval-progress')).to_contain_text('1 of 3')
    ops2=login('ops2');ops2.goto(BASE+'/quotes/'+ident+'/approval');ops2.get_by_role('button',name='✓ Approve this version',exact=True).click();expect(commercial.locator('[data-review-decision]')).to_be_visible(timeout=12000)
    commercial.locator('[name=comment]').fill('Payment terms and customer presentation checked.');commercial.get_by_role('button',name='✓ Approve this version',exact=True).click();expect(commercial.locator('#approval-status')).to_contain_text('Approved by all')
    author.reload();expect(author.locator('[data-artifact-status]')).to_contain_text('success',timeout=30000)
    with author.expect_download() as download:author.get_by_role('link',name='Retained approved PDF',exact=True).first.click()
    pdf=Path(download.value.path()).read_bytes();assert pdf.startswith(b'%PDF-');assert len(pdf)>1000
    author.get_by_role('button',name='Mark as sent to client',exact=True).click();expect(author.locator('#approval-status')).to_contain_text('Sent to client')
    author.screenshot(path=str(SCREEN/'v12-approval-light.png'),full_page=True,animations='disabled')
    author.get_by_label('Portal theme',exact=True).select_option('dark');expect(author.locator('html')).to_have_attribute('data-theme','dark');author.screenshot(path=str(SCREEN/'v12-approval-dark.png'),full_page=True,animations='disabled')
    for path,name in [('/','dashboard'),('/list/quote','quotations'),('/customers/'+customer,'customer'),('/customers/'+customer+'/tenant-pricing','pricing'),('/reports','reports')]:
     author.goto(BASE+path);assert author.locator('html').get_attribute('data-theme')=='dark';assert author.evaluate('document.documentElement.scrollWidth<=innerWidth+3'),path
     author.screenshot(path=str(SCREEN/('v12-'+name+'-dark.png')),full_page=True,animations='disabled')
    # Reviewer access remains quotation-only and cannot see its private cost/notes.
    response=ops1.request.get(BASE+'/quotes/'+ident+'/edit');assert 'PRIVATE-WORKFLOW-NOTE' not in response.text();assert '731.29' not in response.text();assert ops1.request.get(BASE+'/quotes/'+ident+'/pricing-margin').status==404;assert ops1.request.get(BASE+'/customers/'+customer).status==404
    author.goto(BASE+'/quotes/'+ident+'/edit');expect(author.locator('#preview-status')).to_contain_text('Preview current');author.screenshot(path=str(SCREEN/'v12-editor-dark.png'),full_page=True,animations='disabled')
    author.goto(BASE+'/quotes/'+ident+'/print');assert author.locator('link[href="/static/portal.css"]').count()==0;assert author.locator('article').evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)';author.pdf(path=str(td/'customer.pdf'),print_background=True)
    assert (td/'customer.pdf').read_bytes().startswith(b'%PDF-')
    author.set_viewport_size({'width':390,'height':850});author.goto(BASE+'/');author.get_by_role('button',name='Open navigation',exact=True).click();author.wait_for_function("()=>document.getElementById('workspace-nav').getBoundingClientRect().x===0");author.screenshot(path=str(SCREEN/'v12-mobile-drawer.png'),full_page=True,animations='disabled');author.get_by_role('button',name='Close navigation',exact=True).click()
    for path,name in [('/','dashboard'),('/list/quote','quotations'),('/quotes/'+ident+'/approval','approval'),('/customers/'+customer,'customer')]:
     author.goto(BASE+path);assert author.evaluate('document.documentElement.scrollWidth<=innerWidth+3'),path;author.screenshot(path=str(SCREEN/('v12-'+name+'-mobile.png')),full_page=True,animations='disabled')
    author.get_by_label('Portal theme',exact=True).select_option('light');author.goto(BASE+'/');assert author.locator('html').get_attribute('data-theme')=='light';
    author.get_by_label('Portal theme',exact=True).select_option('system');author.emulate_media(color_scheme='dark');assert author.locator('body').evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(17, 27, 40)';author.emulate_media(color_scheme='light');assert author.locator('body').evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(241, 244, 248)';assert not errors,errors
    browser.close();print('PASS: real operations→commercial→approved PDF→manual sent; polling, scoped editing, notifications, persisted themes, desktop/mobile and white customer PDF. No email sent.')
  except Exception:
   print((td/'server.log').read_text()[-12000:]);raise
  finally:server.terminate();server.wait(timeout=20);log.close()

if __name__=='__main__':run()
