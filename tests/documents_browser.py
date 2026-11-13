"""Document workspace journeys on a disposable Waitress instance; no live data."""
import copy,json,os,re,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store,security
from workspace_app.model import FIELDS
from test_v5 import quote
from browser_auth import bootstrap,login
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8006'


def run():
 with tempfile.TemporaryDirectory() as temp:
  td=Path(temp);root=td/'data';bootstrap(root)
  with store.connect(root) as db:
   owner=db.execute('SELECT id FROM users').fetchone()[0];customer=store.save(db,'customer',dict(name='Synthetic Bank',contact='Example contact',notes=''))
   first=quote('CIR26-148-1',status='Draft');first.update(title='CIR26-148-1_Bank-Cloud Services Quotation_V1.0',customer_id=customer,customer='Synthetic Bank');qid=store.save(db,'quote',first)
   second=copy.deepcopy(first);second['revision']=2;second['title']='Manually edited quotation title';second['document']['sections'][0]['rows'][0]['unit_price']='200';qrev=store.save(db,'quote',second,inherit_from=qid)
   other=quote('CIR26-149-1',price='300');other.update(title='Other customer cloud quotation',customer_id=customer,customer='Synthetic Bank',scope='Different scope');qother=store.save(db,'quote',other)
   for i in range(9):
    q=quote('DEMO-'+str(i),status='Draft');q.update(title='Sample document '+str(i),customer_id=customer,customer='Synthetic Bank');store.save(db,'quote',q)
   db.execute('UPDATE records SET owner_id=?',(owner,))
  log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(root),'CIRRUS_PORT':'8006'},stdout=log,stderr=log)
  try:
   for _ in range(100):
    if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
    try:urllib.request.urlopen(BASE,timeout=1).close();break
    except OSError:time.sleep(.1)
   with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium');page=browser.new_page(viewport={'width':1600,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    login(page,BASE);page.goto(BASE+'/list/quote');page.locator('.document-table').wait_for()
    table=page.locator('.document-list').bounding_box();sidebar=page.locator('.document-sidebar').bounding_box();assert table['width']>sidebar['width']*2.7,(table,sidebar);assert table['y']<330;assert page.locator('.document-table').bounding_box()['y']<600
    assert page.locator('[data-family-select]').count()==11;assert not page.locator('.monthly-statistics').get_attribute('open');assert page.locator('.document-table th').all_text_contents()==['','Document title','Customer','Document type','Created','Owner','Status','Actions']
    page.locator('[data-document-id="'+qrev+'"] .pick-document').click();assert page.locator('[data-tool="compare"]').get_attribute('href')=='/quotes/'+qrev+'/compare';assert page.locator('[data-tool="costing"]').get_attribute('aria-disabled')=='false'
    page.get_by_role('link',name='⇄ Compare',exact=True).click();page.get_by_label('New quotation / revision',exact=True).select_option(qother);page.get_by_role('button',name='Compare revisions',exact=True).click();assert 'Different scope' in page.locator('body').inner_text();assert 'Initial recurring monthly fee' in page.locator('body').inner_text()
    print('PASS dominant compact list, collapsed small charts, preserved tools, cross-quotation comparison')
    page.goto(BASE+'/list/quote');page.get_by_label('Search documents',exact=True).fill('CIR26-148-1');page.get_by_role('button',name='Apply filters',exact=True).click();assert page.locator('[data-family-select]').count()==1
    row=page.locator('[data-document-id="'+qrev+'"]');row.locator('.rename-title summary').click();row.get_by_label('Editable title',exact=True).fill('Manual custom title / keep');row.get_by_role('button',name='Save title',exact=True).click();page.wait_for_load_state();assert 'Manual custom title / keep' in page.locator('.document-table').inner_text()
    page.goto(BASE+'/documents/new');page.get_by_label('1 · Document type',exact=True).select_option('SLA');page.get_by_label('2 · Customer',exact=True).select_option(customer);page.get_by_label('3 · Subject',exact=True).fill('Managed Cloud');page.get_by_role('button',name='Continue',exact=True).click();page.wait_for_url('**/documents/*/edit');generic_id=page.url.split('/')[-2]
    assert 'Managed Cloud SLA_V1.0' in page.get_by_label('Document title',exact=True).input_value();assert page.get_by_text('Contract duration (months)',exact=True).count()==0
    page.get_by_label('Content',exact=True).fill('Service availability and responsibilities.');page.get_by_label('Document title',exact=True).fill('My edited SLA title');page.get_by_role('button',name='Save document',exact=True).click();page.wait_for_load_state();assert page.get_by_label('Document title',exact=True).input_value()=='My edited SLA title'
    page.get_by_role('link',name='Management & history',exact=True).click();page.get_by_label('Next follow-up',exact=True).fill('2026-11-01');page.get_by_label('Follow-up note',exact=True).fill('Review scope with customer');page.get_by_label('Link existing documents',exact=True).select_option(qother);page.get_by_role('button',name='Save management',exact=True).click();page.wait_for_load_state();assert 'Management updated' in page.locator('body').inner_text();assert 'Created' in page.locator('body').inner_text()
    page.goto(BASE+'/documents/'+generic_id+'/edit');page.get_by_role('link',name='Print / Save PDF',exact=True).click();assert page.title()=='My edited SLA title';assert page.locator('.header-logo').is_visible();page.pdf(path=str(td/'sla.pdf'),print_background=True)
    print('PASS type-first creation, editable content/title, preserved title, management, follow-up, links, history and generic print/PDF')
    page.goto(BASE+'/quotes/'+qrev+'/edit');page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for();frame=page.frame_locator('#customer-preview');assert frame.locator('.header-logo').is_visible();assert frame.locator('.document-strip').inner_text()=='Quotation'
    page.get_by_label('Show 12-month column',exact=True).uncheck();page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for();assert frame.locator('.summary thead th').all_text_contents()==['Category / summary','Monthly (USD)','One-time (USD)']
    page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_load_state();page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for();assert not page.get_by_label('Show 12-month column',exact=True).is_checked()
    page.goto(BASE+'/quotes/'+qrev+'/print');assert page.title()=='Manual custom title _ keep';assert page.locator('.summary thead th').count()==3;assert page.locator('.header-fields.header-right').inner_text().count('Ref')==1
    page.pdf(path=str(td/'quote.pdf'),print_background=True);assert (td/'quote.pdf').stat().st_size>10000
    page.goto(BASE+'/quotes/'+qrev+'/edit');page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for()
    with page.expect_download() as dl:page.get_by_role('link',name='Excel',exact=True).click()
    assert dl.value.suggested_filename=='Manual custom title _ keep.xlsx'
    print('PASS saved 12-month toggle, no-gap summary, proportional logo/header, saved title export filenames and PDF')
    page.goto(BASE+'/list/quote');page.get_by_text('View monthly statistics · Insights',exact=False).click();assert page.locator('.mini-chart').first.is_visible()
    screenshot=os.environ.get('DOCUMENT_SCREENSHOT')
    if screenshot:
     page.evaluate('window.scrollTo(0,0)');page.screenshot(path=screenshot,full_page=True)
    for width in (1000,760,390):
     page.set_viewport_size({'width':width,'height':900});page.goto(BASE+'/list/quote');page.locator('.document-table').wait_for();l=page.locator('.document-list').bounding_box();s=page.locator('.document-sidebar').bounding_box()
     if width<=850:assert s['y']>l['y']+l['height']-3,(width,l,s)
     assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth+2'),(width,page.evaluate('document.documentElement.scrollWidth'))
    assert not errors,errors
    print('PASS filters/reference search, responsive sidebar stacking at tablet/mobile, no JavaScript errors')
    browser.close()
  finally:
   server.terminate();server.wait(timeout=15);log.close()

if __name__=='__main__':run()
