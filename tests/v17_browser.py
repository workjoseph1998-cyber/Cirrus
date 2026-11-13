"""Real Chromium + Waitress V17 acceptance checks; SMTP replaced by local capture."""
import json,os,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store,security,notifications
from test_v5 import quote
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8027';PASSWORD='Synthetic-V17-browser-password!'
SCREEN=Path(os.environ.get('CW_BROWSER_ARTIFACTS','/workspace/preservation/v17'));SCREEN.mkdir(parents=True,exist_ok=True)


def run():
 with tempfile.TemporaryDirectory() as temporary:
  td=Path(temporary);data=td/'data';spool=td/'spool';spool.mkdir();reports=td/'reports';reports.mkdir();external=td/'customer-pdfs';external.mkdir();store.migrate(data)
  with store.connect(data) as db:
   ids={n:security.create_user(db,n,PASSWORD,'Administrator' if n=='admin' else 'Editor',n=='admin') for n in ('admin','author','ops1','ops2','commercial')}
   selected=[dict(user_id=ids[n],phase='commercial' if n=='commercial' else 'operations') for n in ('ops1','ops2','commercial')]
   db.execute("INSERT INTO settings VALUES ('approval_defaults',?)",(json.dumps(selected),))
   cfg=dict(notifications.DEFAULTS,enabled=True,host='192.0.2.20',port=2525,security='none',sender='workplace@example.test',base_url='https://workplace.example.test')
   db.execute("INSERT INTO settings VALUES ('workflow_smtp',?)",(json.dumps(cfg),))
   for n,uid in ids.items():db.execute('INSERT INTO account_emails VALUES (?,?,1)',(uid,n+'@example.test'))
   customer=store.save(db,'customer',dict(name='Acme Bank',contact='Synthetic contact',notes='Private customer'))
   q=quote('CIR26-450-1',status='Draft');q.update(customer='Acme Bank',customer_id=customer,title='Acme Bank Cloud Services',internal_notes='PRIVATE-V17-MARKER');q['document']['contract_months']=36
   ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=?',(ids['author'],));db.execute('UPDATE document_management SET created_by=? WHERE record_id=?',(ids['author'],ident))
  bootstrap="""import json,os,runpy,uuid
from pathlib import Path
from workspace_app import notifications
def capture(cfg,to,subject,text,**message):
 root=Path(os.environ['CW_TEST_EMAIL_SPOOL']);name=uuid.uuid4().hex
 temp=root/(name+'.tmp');temp.write_text(json.dumps(dict(to=to,subject=subject,text=text,**message)));temp.rename(root/(name+'.json'))
notifications.send_smtp=capture
runpy.run_path('run.py',run_name='__main__')
"""
  log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'-c',bootstrap],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(data),'CIRRUS_PORT':'8027','CIRRUS_DISABLE_EMAIL':'1','CIRRUS_PDF_NO_SANDBOX':'1','CW_TEST_EMAIL_SPOOL':str(spool)},stdout=log,stderr=log)
  def mail():return [json.loads(p.read_text()) for p in spool.glob('*.json')]
  def wait_mail(count):
   until=time.monotonic()+40
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
      page=browser.new_context(viewport={'width':1536,'height':1024}).new_page();page.set_default_timeout(15000);pages.append(page);page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/login');page.get_by_label('Username',exact=True).fill(name);page.get_by_label('Password',exact=True).fill(PASSWORD);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(BASE+'/');return page
     def post(page,path,fields):
      token=page.locator('input[name=csrf]').first.get_attribute('value');response=page.request.post(BASE+path,form=dict(csrf=token,**fields));assert response.ok,(response.status,response.text()[:1000]);return response
     author=login('author');url=BASE+'/quotes/'+ident;author.goto(url+'/edit');expect(author.locator('#preview-status')).to_contain_text('Preview current');author.locator('#open-quotation-controls').click() if author.locator('#open-quotation-controls').count() and author.locator('#open-quotation-controls').is_visible() else None;author.get_by_role('button',name='Approvers & submission',exact=True).click();dialog=author.locator('#approvers-submission-dialog');expect(dialog.locator('.approver-selection-row')).to_have_count(3);dialog.get_by_role('button',name='Save & submit for approval',exact=True).click();author.wait_for_url(url+'/edit');wait_mail(3)
     ops1=login('ops1');ops1.goto(url+'/approval');ops1.get_by_role('button',name='✓ Approve this version',exact=True).click();ops1.wait_for_url(url+'/approval')
     ops2=login('ops2');ops2.goto(url+'/approval');ops2.get_by_role('button',name='✓ Approve this version',exact=True).click();ops2.wait_for_url(url+'/approval');assert len(mail())==3
     admin=login('admin');admin.goto(BASE+'/reports?report=pending&period=all');expect(admin.locator('.report-table')).to_contain_text('commercial');admin.screenshot(path=str(SCREEN/'pending-light.png'),full_page=True)
     commercial=login('commercial');commercial.goto(url+'/approval');commercial.get_by_role('button',name='✓ Approve this version',exact=True).click();commercial.wait_for_url(url+'/approval');wait_mail(7)
     until=time.monotonic()+45
     while time.monotonic()<until:
      with store.connect(data) as db:artifact=db.execute('SELECT status,pdf FROM approval_artifacts').fetchone()
      if artifact and artifact['status']=='success':break
      time.sleep(.2)
     assert artifact and artifact['status']=='success',(dict(artifact) if artifact else None,(td/'server.log').read_text()[-3000:])
     (SCREEN/'approved-quotation.pdf').write_bytes(artifact['pdf'])
     admin.goto(url+'/approval');admin.get_by_role('button',name='Mark as sent to client',exact=True).click();sent=admin.locator('#sent-dialog');expect(sent).to_be_visible();sent.get_by_label('Recipient name',exact=True).fill('Customer Representative');sent.get_by_label('Recipient email',exact=True).fill('customer@example.test');sent.get_by_label('Sending method',exact=True).select_option('WhatsApp');sent.get_by_label('Optional notes',exact=True).fill('Recorded by the internal team, delivery not verified.');admin.screenshot(path=str(SCREEN/'sent-dialog-light.png'),full_page=True);sent.get_by_role('button',name='Confirm sent record',exact=True).click();admin.wait_for_url(url+'/approval');expect(admin.get_by_text('admin marked this quotation as sent',exact=False)).to_be_visible();messages=wait_mail(11)
     sent_mail=[m for m in messages if m['subject'].startswith('Sent to Client')];assert len(sent_mail)==4 and {m['to'] for m in sent_mail}=={n+'@example.test' for n in ('author','ops1','ops2','commercial')}
     for m in sent_mail:assert 'admin marked this quotation as sent' in m['text'] and 'Delivery is not verified' in m['text'] and 'PRIVATE-V17-MARKER' not in m['text']+m['html']
     with store.connect(data) as db:assert db.execute('SELECT count(*) FROM quotation_sent_events').fetchone()[0]==1
     admin.reload();assert len(mail())==11
     email=browser.new_page(viewport={'width':760,'height':1100});email.set_content(sent_mail[0]['html']);email.screenshot(path=str(SCREEN/'sent-email.png'),full_page=True);email.close()
     admin.goto(BASE+'/list/quote?basis=sent&period=all&archive=all');expect(admin.locator('tr[data-document-id]')).to_have_count(1);expect(admin.locator('tr[data-document-id]')).to_contain_text('2026-')
     admin.goto(BASE+'/reports/settings');admin.get_by_label('Reports folder (absolute Windows or UNC path)',exact=True).fill(str(reports));admin.get_by_role('button',name='Test folder access',exact=True).click();expect(admin.get_by_text('Folder access succeeded.',exact=True)).to_be_visible();admin.get_by_role('button',name='Save Reports folder',exact=True).click();admin.wait_for_url(BASE+'/reports/settings')
     admin.goto(BASE+'/reports?report=register&period=year&year=2026&customer_id='+customer+'&owner='+ids['author']);expect(admin.locator('.report-cards').first).to_contain_text('$100.00');expect(admin.locator('.report-cards')).to_contain_text('$50.00');expect(admin.locator('.report-table')).to_contain_text('Rev 1');assert 'PRIVATE-V17-MARKER' not in admin.content();admin.screenshot(path=str(SCREEN/'register-light.png'),full_page=True)
     with admin.context.expect_page() as popup:admin.get_by_role('link',name='Preview printable report',exact=True).click()
     preview=popup.value;preview.wait_for_load_state();expect(preview.locator('h1')).to_have_text('Quotation register');assert preview.locator('body').evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)';preview.screenshot(path=str(SCREEN/'report-preview.png'),full_page=True);preview.close()
     admin.get_by_role('button',name='Generate & save PDF',exact=True).click();admin.wait_for_url('**/reports?**generated=**',timeout=45000)
     with admin.expect_download() as download_info:admin.get_by_role('link',name='Download generated PDF',exact=True).click()
     download=download_info.value;download.save_as(str(SCREEN/'quotation-register.pdf'));assert (SCREEN/'quotation-register.pdf').read_bytes().startswith(b'%PDF-') and len(list(reports.glob('*.pdf')))==1
     saved_pdf=list(reports.glob('*.pdf'))[0];admin.get_by_label('Portal theme',exact=True).select_option('dark');expect(admin.get_by_role('link',name='Download generated PDF',exact=True)).to_have_css('color','rgb(228, 237, 247)');expect(admin.get_by_role('link',name='Preview printable report',exact=True)).to_have_css('background-color','rgb(34, 51, 72)');admin.screenshot(path=str(SCREEN/'register-dark.png'),full_page=True)
     admin.set_viewport_size({'width':390,'height':850});admin.wait_for_timeout(250);assert admin.locator('#workspace-nav').bounding_box()['x']<=-240;admin.screenshot(path=str(SCREEN/'register-mobile-dark.png'),full_page=True);assert admin.evaluate('document.documentElement.scrollWidth<=innerWidth+3');admin.get_by_label('Portal theme',exact=True).select_option('light');expect(admin.get_by_role('link',name='Download generated PDF',exact=True)).to_have_css('color','rgb(25, 44, 67)');expect(admin.get_by_role('link',name='Preview printable report',exact=True)).to_have_css('background-color','rgb(246, 248, 251)');admin.screenshot(path=str(SCREEN/'register-mobile-light.png'),full_page=True);admin.set_viewport_size({'width':1536,'height':1024})
     # A later revision changes current report values, never the sent event snapshot.
     author.goto(url+'/edit');post(author,'/record/'+ident+'/copy/revision',{})
     with store.connect(data) as db:newid=next(r['id'] for r in store.records(db,unrestricted=True) if r['kind']=='quote' and r['data']['revision']==2)
     author.goto(BASE+'/quotes/'+newid+'/edit');expect(author.locator('#preview-status')).to_contain_text('Preview current');q2=json.loads(author.locator('#initial-quotation').text_content());q2['document']['sections'][0]['rows'][0]['quantity']='2';token=author.locator('input[name=base_hash]').get_attribute('value');post(author,'/quotes/'+newid+'/edit',dict(base_hash=token,quotation=json.dumps(q2)))
     admin.goto(BASE+'/reports?report=register&period=all');expect(admin.locator('.report-table')).to_contain_text('Rev 2');expect(admin.locator('.report-cards')).to_contain_text('$200.00');expect(admin.locator('.report-table tbody tr')).to_have_count(1)
     admin.goto(BASE+'/reports?report=sent&period=all');expect(admin.locator('.report-cards')).to_contain_text('$100.00');expect(admin.locator('.report-table')).to_contain_text('Rev 1');expect(admin.locator('.report-table')).to_contain_text('Customer Representative');admin.screenshot(path=str(SCREEN/'sent-report-light.png'),full_page=True)
     admin.goto(BASE+'/reports?report=overview&period=custom&start=2026-01-01&end=2026-12-31');expect(admin.locator('.report-cards')).to_contain_text('$200.00');expect(admin.locator('.report-cards')).to_contain_text('1');admin.screenshot(path=str(SCREEN/'overview-light.png'),full_page=True)
     # Exact tracked exports from both revisions are removed. An unrelated file/folder/report stays.
     unrelated=external/'unrelated.pdf';unrelated.write_bytes(b'%PDF-unrelated')
     with store.connect(data) as db:
      for rid in (ident,newid):
       path=external/(rid+'.pdf');path.write_bytes(artifact['pdf']);db.execute('INSERT INTO pdf_file_owners(path_key,record_id,path,revision) VALUES (?,?,?,?)',(str(path),rid,str(path),1 if rid==ident else 2))
     admin.goto(BASE+'/list/quote?archive=active&period=all');admin.locator('input[data-family-select]').check();admin.locator('.quotation-bulk-menu > summary').click();admin.get_by_role('button',name='Archive',exact=True).click();admin.get_by_role('button',name='Confirm archive · 1 families',exact=True).click();admin.wait_for_url('**/list/quote?archive=archived');admin.get_by_role('button',name='Delete permanently',exact=True).click();expect(admin.locator('body')).to_contain_text('Revision 2');expect(admin.locator('body')).to_contain_text('Revision 1');admin.get_by_label('Type DELETE to confirm',exact=True).fill('DELETE');admin.screenshot(path=str(SCREEN/'delete-confirmation.png'),full_page=True);admin.get_by_role('button',name='Confirm delete · 1 families',exact=True).click();admin.wait_for_url(BASE+'/quotation-deletions');expect(admin.locator('h2')).to_contain_text('Complete');expect(admin.locator('body')).to_contain_text('2 revisions');admin.screenshot(path=str(SCREEN/'deletion-results.png'),full_page=True)
     assert unrelated.exists() and external.exists() and saved_pdf.exists();assert list(external.glob('*.pdf'))==[unrelated]
     with store.connect(data) as db:
      assert db.execute("SELECT count(*) FROM records WHERE kind='quote'").fetchone()[0]==0;assert db.execute('SELECT count(*) FROM approval_rounds').fetchone()[0]==0;assert db.execute("SELECT state FROM reference_registry WHERE key='cir26-450-1'").fetchone()[0]=='issued'
     admin.goto(BASE+'/reports?report=register&period=all');expect(admin.locator('.report-table')).to_contain_text('No accessible quotations');assert len(mail())==11;assert not errors,errors
     browser.close();print('PASS: real Waitress/Chromium submission → independent operations → commercial → sent dialog; 3 submission + 4 final + 4 sent captured emails, no intermediate/customer SMTP; exact approved PDF; sent listing; four monthly reports, historical sent snapshot vs changed revision, filters, actual PDF folder/download, light/dark 1536/390px, two-revision permanent deletion/owned-file cleanup/reference preservation. No real emails or VM deployment.')
    except Exception:
     for i,page in enumerate(pages):
      try:page.screenshot(path=str(SCREEN/('failure-'+str(i)+'.png')),full_page=True)
      except Exception:pass
     raise
  finally:
   server.terminate();server.wait(timeout=20);log.close();(SCREEN/'server.log').write_text((td/'server.log').read_text())


if __name__=='__main__':run()
