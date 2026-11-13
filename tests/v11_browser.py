import os,sys,tempfile,subprocess,time,urllib.request,json
from pathlib import Path
from openpyxl import Workbook
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store
from test_v5 import quote
from browser_auth import bootstrap,login
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8008'
def run():
 with tempfile.TemporaryDirectory() as temp:
  td=Path(temp);data=td/'data';bootstrap(data)
  with store.connect(data) as db:
   customer=store.save(db,'customer',dict(name='Synthetic customer',contact='Contact A',notes=''))
   for n in range(6):
    q=quote('VISUAL-'+str(n));q.update(title='Synthetic customer cloud quotation '+str(n),customer_id=customer);store.save(db,'quote',q)
   db.execute('UPDATE records SET owner_id=(SELECT id FROM users LIMIT 1)')
  b=Workbook();w=b.active;w.append(['Item','VM','Date','Qty','Unit Price','Total']);w.append(['Production']);w.merge_cells('A2:F2');w.append(['Security Services']);w.append([1,'VM1','February',1,10,15]);w.append(['DR']);w.append(['Security Services']);w.append([1,'VM1','May',0,0,0]);fixture=td/'consumption.xlsx';b.save(fixture)
  log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(data),'CIRRUS_PORT':'8008'},stdout=log,stderr=log)
  try:
   for _ in range(100):
    if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
    try:urllib.request.urlopen(BASE).close();break
    except OSError:time.sleep(.1)
   with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium');page=browser.new_page(viewport={'width':1500,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));login(page,BASE)
    assert page.locator('.top-workspace').is_visible();assert page.get_by_role('heading',name='Your working day').is_visible();page.screenshot(path='/workspace/preservation/v11-dashboard.png',full_page=True)
    page.goto(BASE+'/customers/'+customer);assert page.get_by_role('heading',name='Customer snapshot').is_visible();page.screenshot(path='/workspace/preservation/v11-customer.png',full_page=True)
    page.goto(BASE+'/list/quote');page.locator('.pick-document').first.click();page.get_by_role('link',name='Follow-up',exact=True).click();frame=page.frame_locator('dialog iframe')
    frame.get_by_role('heading',name='Follow-up ·',exact=False).wait_for()
    version=int(frame.locator('[name=version]').input_value());frame.get_by_label('Next follow-up',exact=True).fill('2026-12-01');frame.get_by_label('Follow-up note',exact=True).fill('Synthetic follow-up')
    with page.expect_response(lambda r:'/documents/' in r.url and '/manage' in r.url and r.request.method=='POST') as saved_response:
     frame.get_by_role('button',name='Save management',exact=True).click()
    assert saved_response.value.status==302,saved_response.value.text()
    frame.locator('[name=version][value="'+str(version+1)+'"]').wait_for(state='attached');assert frame.locator('[name=follow_note]').input_value()=='Synthetic follow-up'
    page.get_by_role('button',name='Close',exact=True).click();page.evaluate('scrollTo(0,0)');page.screenshot(path='/workspace/preservation/v11-quotations.png',full_page=True)
    page.goto(BASE+'/customers/'+customer+'/consumption/import');page.locator('[name=month]').fill('2026-11');page.locator('[name=file]').set_input_files(str(fixture));page.get_by_role('button',name='Upload workbook',exact=True).click();page.get_by_role('button',name='Review mapped rows',exact=True).click();page.locator('#consumption-table tbody tr').first.wait_for();assert page.locator('#consumption-table tbody tr').count()==2
    text=page.locator('#consumption-table').inner_text();assert 'differs' in text
    page.locator('#consumption-table input[aria-label="Item VM1"]').first.fill('Edited item');page.locator('#consumption-table input[aria-label="Item VM1"]').first.press('Tab');page.wait_for_timeout(500)
    page.locator('[name=confirm]').check();page.get_by_role('button',name='Save confirmed snapshot',exact=True).click();page.wait_for_url('**/consumption?month=2026-11');assert 'snapshot saved' in page.locator('body').inner_text()
    exported=page.request.get(BASE+'/customers/'+customer+'/consumption/export/pdf?month=2026-11');assert exported.status==200,exported.text()[:500];assert exported.body().startswith(b'%PDF-');assert page.request.get(BASE+'/customers/'+customer+'/consumption/export/xlsx?month=2026-11').status==200
    page.screenshot(path='/workspace/preservation/v11-consumption-desktop.png',full_page=True)
    page.goto(BASE+'/customers/'+customer+'/tenant-pricing');assert page.locator('.vm-family').count()==5
    page.goto(BASE+'/hosting-vms');assert page.locator('.top-workspace').count()==0;assert page.locator('.vm-family').count()==5
    page.set_viewport_size({'width':390,'height':850});page.goto(BASE+'/customers/'+customer+'/consumption?month=2026-11');page.locator('#consumption-table tbody tr').first.wait_for();page.screenshot(path='/workspace/preservation/v11-consumption-mobile.png',full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+3');
    for path,name in [('/','dashboard'),('/customers/'+customer,'customer'),('/list/quote','quotations')]:
     page.goto(BASE+path);page.evaluate('scrollTo(0,0)');page.screenshot(path='/workspace/preservation/v11-'+name+'-mobile.png',full_page=True);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+3'),name
    assert not errors,errors;browser.close();print('PASS dashboard/customer tabs/import mapping/preview/edit/save/tenant catalog/general-library isolation; desktop/mobile screenshots and no JS errors')
  finally:server.terminate();server.wait(timeout=15);log.close()
if __name__=='__main__':run()
