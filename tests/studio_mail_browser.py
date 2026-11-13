"""Synthetic real-browser studio placement and two-stage email checks; no SMTP."""
import json,os,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store,security,notifications
from test_v15 import optional_quote
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8024';PASSWORD='Synthetic-studio-email-browser-password!';SCREEN=Path('/workspace/preservation');SCREEN.mkdir(exist_ok=True)


def run():
 with tempfile.TemporaryDirectory() as td:
  td=Path(td);data=td/'data';spool=td/'spool';spool.mkdir();store.migrate(data);q=optional_quote()
  with store.connect(data) as db:
   ids={n:security.create_user(db,n,PASSWORD,'Administrator' if n=='admin' else 'Editor',n=='admin') for n in ['admin','author','ops1','ops2','commercial']}
   selected=[dict(user_id=ids[n],phase='commercial' if n=='commercial' else 'operations') for n in ['ops1','ops2','commercial']]
   db.execute("INSERT INTO settings VALUES ('approval_defaults',?)",(json.dumps(selected),))
   cfg=dict(notifications.DEFAULTS,enabled=True,host='192.0.2.20',port=2525,security='none',sender='workplace@example.test',base_url='https://workplace.example.test')
   db.execute("INSERT INTO settings VALUES ('workflow_smtp',?)",(json.dumps(cfg),))
   for n,uid in ids.items():db.execute('INSERT INTO account_emails VALUES (?,?,1)',(uid,n+'@example.test'))
   customer=store.save(db,'customer',dict(name='Acme Bank',contact='Synthetic contact',notes='Private customer data'))
   q.update(customer='Acme Bank',customer_id=customer,number='CIR26-450-1',title='Acme Bank Cloud Services',internal_notes='PRIVATE-MAIL-MARKER')
   ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=?',(ids['author'],))
  # Replace the SMTP transport in the server with an atomic local JSON capture.
  # The real worker/queue/rendering run normally; no real SMTP can be invoked.
  bootstrap="""import json,os,runpy,uuid
from pathlib import Path
from workspace_app import notifications
def capture(cfg,to,subject,text,**message):
 root=Path(os.environ['CW_TEST_EMAIL_SPOOL']);name=uuid.uuid4().hex
 temp=root/(name+'.tmp');temp.write_text(json.dumps(dict(to=to,subject=subject,text=text,**message)));temp.rename(root/(name+'.json'))
notifications.send_smtp=capture
runpy.run_path('run.py',run_name='__main__')
"""
  log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'-c',bootstrap],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(data),'CIRRUS_PORT':'8024','CIRRUS_DISABLE_EMAIL':'1','CW_TEST_EMAIL_SPOOL':str(spool)},stdout=log,stderr=log)
  def mail():return [json.loads(p.read_text()) for p in sorted(spool.glob('*.json'))]
  def wait_mail(count):
   until=time.monotonic()+35
   while time.monotonic()<until:
    messages=mail()
    if len(messages)==count:return messages
    if len(messages)>count:raise AssertionError(('Duplicate emails',len(messages),count))
    time.sleep(.15)
   raise AssertionError((len(mail()),count,(td/'server.log').read_text()[-3000:]))
  try:
   for _ in range(150):
    if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
    try:urllib.request.urlopen(BASE).close();break
    except OSError:time.sleep(.1)
   with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium');errors=[];pages=[]
    try:
     def login(name):
      page=browser.new_context(viewport={'width':1536,'height':1024}).new_page();page.set_default_timeout(12000);pages.append(page);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/login');page.get_by_label('Username',exact=True).fill(name);page.get_by_label('Password',exact=True).fill(PASSWORD);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(BASE+'/');return page
     author=login('author');url=BASE+'/quotes/'+ident;author.goto(url+'/edit');expect(author.locator('#preview-status')).to_contain_text('Preview current');dialog=author.locator('#approvers-submission-dialog');expect(dialog).not_to_be_visible()
     assert author.locator('.editor-approval-setup').count()==0;assert author.locator('#optional-monitoring').count()==author.locator('#show-12-month').count()==1
     assert author.locator('#quotation-options').bounding_box()['x']>author.locator('.studio-preview').bounding_box()['x'];assert author.locator('#quotation-options').bounding_box()['width']<=190
     save=author.get_by_role('button',name='Save quotation',exact=True);opener=author.get_by_role('button',name='Approvers & submission',exact=True);assert abs(save.bounding_box()['y']-opener.bounding_box()['y'])<10
     opener.click();expect(dialog).to_be_visible();expect(dialog.locator('.approver-selection-row')).to_have_count(3);dialog.get_by_role('button',name='+ Add approver',exact=True).click();dialog.get_by_label('Approver 4',exact=True).select_option(ids['author']);dialog.get_by_role('button',name='Continue editing',exact=True).click();opener.click();expect(dialog.locator('.approver-selection-row')).to_have_count(4);dialog.get_by_role('button',name='Remove approver 4',exact=True).click();dialog.get_by_role('button',name='Continue editing',exact=True).click();assert mail()==[]
     author.get_by_label('Optional Monitoring',exact=True).check();author.get_by_label('Show 12-month column',exact=True).uncheck();expect(author.locator('#preview-status')).to_contain_text('Preview current');frame=author.frame_locator('#customer-preview');expect(frame.locator('.summary-regular')).to_contain_text('$1,150.00');expect(frame.locator('.summary-optional')).to_contain_text('$200.00')
     author.screenshot(path=str(SCREEN/'studio-options-light.png'),full_page=True);save.click();author.wait_for_url(url+'/edit');expect(author.locator('#preview-status')).to_contain_text('Preview current');assert mail()==[]
     with store.connect(data) as db:
      saved=json.loads(db.execute('SELECT data FROM records WHERE id=?',(ident,)).fetchone()[0]);assert saved['document']['optional_monitoring'] and not saved['document']['show_12_month'];assert db.execute('SELECT count(*) FROM approval_email_batches').fetchone()[0]==0
     author.get_by_role('button',name='Approvers & submission',exact=True).click();dialog.get_by_role('button',name='Save & submit for approval',exact=True).click();author.wait_for_url(url+'/edit');expect(author.locator('#preview-status')).to_contain_text('Preview current');messages=wait_mail(3)
     assert {m['to'] for m in messages}=={'ops1@example.test','ops2@example.test','commercial@example.test'};assert all(m['subject']=='Review Required | Acme Bank | CIR26-450-1' for m in messages)
     ops1=login('ops1');ops1.goto(url+'/edit');expect(ops1.get_by_role('button',name='Approvers & submission',exact=True)).to_have_count(0);assert 'PRIVATE-MAIL-MARKER' not in ops1.content();ops1.goto(url+'/approval');ops1.get_by_role('button',name='✓ Approve this version',exact=True).click();ops1.wait_for_url(url+'/approval')
     ops2=login('ops2');ops2.goto(url+'/approval');ops2.get_by_role('button',name='✓ Approve this version',exact=True).click();ops2.wait_for_url(url+'/approval')
     author.reload();expect(author.locator('#preview-status')).to_contain_text('Preview current');author.get_by_role('button',name='Approvers & submission',exact=True).click();expect(dialog.locator('.approval-dot.is-approved')).to_have_count(2);expect(dialog.locator('.approval-dot:not(.is-approved)')).to_have_count(1);dialog.locator('.approval-dot').first.focus();expect(dialog.locator('.approval-live-tooltip')).to_be_visible();author.screenshot(path=str(SCREEN/'studio-approvers-light.png'),full_page=True)
     dialog.get_by_role('button',name='Approval & discussion',exact=True).click();expect(dialog).not_to_be_visible();discussion=author.locator('#editor-approval-dialog');expect(discussion).to_be_visible();discussion.get_by_role('button',name='Close approval & discussion',exact=True).click()
     author.get_by_label('Portal theme',exact=True).select_option('dark');author.get_by_role('button',name='Approvers & submission',exact=True).click();author.screenshot(path=str(SCREEN/'studio-approvers-dark.png'),full_page=True);dialog.get_by_role('button',name='Continue editing',exact=True).click();assert len(mail())==3
     commercial=login('commercial');commercial.goto(url+'/approval');commercial.get_by_role('button',name='✓ Approve this version',exact=True).click();commercial.wait_for_url(url+'/approval');messages=wait_mail(7)
     complete=[m for m in messages if m['subject'].startswith('Fully Approved')];assert len(complete)==4 and {m['to'] for m in complete}=={'author@example.test','ops1@example.test','ops2@example.test','commercial@example.test'}
     author.reload();expect(author.locator('#preview-status')).to_contain_text('Preview current');author.get_by_role('button',name='Approvers & submission',exact=True).click();expect(dialog.locator('#editor-workflow-status')).to_have_text('Approved by all');expect(dialog.locator('.approval-dot.is-approved')).to_have_count(3);dialog.get_by_role('button',name='Continue editing',exact=True).click();author.get_by_role('button',name='Save quotation',exact=True).click();author.wait_for_url(url+'/edit');expect(author.locator('#preview-status')).to_contain_text('Preview current')
     author.get_by_role('button',name='Options',exact=True).click();expect(author.locator('#quotation-options')).to_be_hidden();author.get_by_role('button',name='Options',exact=True).click();expect(author.get_by_label('Optional Monitoring',exact=True)).to_be_checked()
     author.set_viewport_size({'width':390,'height':850});author.wait_for_timeout(250);assert author.evaluate('document.documentElement.scrollWidth<=innerWidth+3');author.get_by_role('button',name='Options',exact=True).click();expect(author.locator('#studio-options-dialog')).to_be_visible();expect(author.get_by_label('Optional Monitoring',exact=True)).to_be_checked();expect(author.get_by_label('Show 12-month column',exact=True)).not_to_be_checked();author.screenshot(path=str(SCREEN/'studio-options-mobile.png'),full_page=True);author.keyboard.press('Escape')
     author.get_by_role('button',name='Approvers & submission',exact=True).click();author.screenshot(path=str(SCREEN/'studio-approvers-mobile.png'),full_page=True);author.keyboard.press('Escape')
     public=author.context.new_page();public.goto(url+'/print');assert public.locator('article').evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)';assert 'Quotation options' not in public.content();assert 'PRIVATE-MAIL-MARKER' not in public.content();(SCREEN/'studio-controls-customer-output.pdf').write_bytes(public.pdf(print_background=True,prefer_css_page_size=True))
     assert len(mail())==7
     author.set_viewport_size({'width':1536,'height':1024});author.goto(BASE+'/quotes/new?customer_id='+customer);expect(author.locator('#preview-status')).to_contain_text('Preview current');author.get_by_role('button',name='Approvers & submission',exact=True).click();newdialog=author.locator('#approvers-submission-dialog');newdialog.get_by_role('button',name='Remove approver 3',exact=True).click();newdialog.get_by_role('button',name='Remove approver 2',exact=True).click();assert len(mail())==7
     newdialog.get_by_role('button',name='Save & submit for approval',exact=True).click();author.wait_for_url('**/quotes/*/edit');newid=author.url.split('/')[-2];assert newid!=ident
     with store.connect(data) as db:assert db.execute('SELECT 1 FROM records WHERE id=?',(newid,)).fetchone() and db.execute('SELECT 1 FROM approval_rounds WHERE quote_id=?',(newid,)).fetchone()
     wait_mail(8)
     for name,message in [('submission',next(m for m in messages if m['subject'].startswith('Review Required'))),('complete',complete[0])]:
      assert 'PRIVATE-MAIL-MARKER' not in message['html']+message['text'];html=SCREEN/('approval-email-'+name+'.html');html.write_text(message['html']);email=browser.new_page(viewport={'width':760,'height':1100});email.set_content(message['html']);email.screenshot(path=str(SCREEN/('approval-email-'+name+'.png')),full_page=True);email.close()
     assert not errors,errors;browser.close();print('PASS: moved studio controls; dialog selection retention; draft saves/opening send no email; exact submission/final recipients and no intermediate email; 2-green/1-white and final dots; reviewer restrictions; saved option behavior and optional/support totals; unsaved save-and-submit; mobile/dark; white customer PDF; HTML email rendering. SMTP replaced by local capture only.')
    except Exception:
     for i,page in enumerate(pages):
      try:page.screenshot(path=str(SCREEN/('studio-email-failure-'+str(i)+'.png')),full_page=True)
      except Exception:pass
     raise
  finally:server.terminate();server.wait(timeout=20);log.close()


if __name__=='__main__':run()
