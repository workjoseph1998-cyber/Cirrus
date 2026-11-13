"""Version 8 live UI journey on synthetic data; no production VM involved."""
import io,json,os,re,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store,security,relationships as rel
from workspace_app.model import FIELDS
from test_v5 import quote
from browser_auth import bootstrap,login
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8004'


def run():
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);root=td/'data';bootstrap(root)
        with store.connect(root) as db:
            customer=store.save(db,'customer',dict(name='Synthetic Banking Group',contact='Example contact',notes='UI test'))
            d={k:'' for k,_,_ in FIELDS['project']};d.update(name='Synthetic cloud project',customer='Original customer text',customer_id=customer,status='Active');project=store.save(db,'project',d)
            d={k:'' for k,_,_ in FIELDS['catalog']};d.update(code='SYN-CPU',name='Synthetic Compute',description='Compute',unit='VM',price='100',currency='USD',status='Active',billing='monthly',method='unit',quantity='1',discount='0');catalog=store.save(db,'catalog',d)
            from workspace_app.hosting import entries
            vm=entries(db)[0]['id']
            rel.save_price(db,customer,dict(item_key='vm:'+vm+':a',billing='monthly',currency='USD',price='91',reason='Linux agreed rate'))
            rel.save_price(db,customer,dict(item_key='vm:'+vm+':b',billing='monthly',currency='USD',price='126',reason='Windows agreed rate'))
            q=quote(status='Draft');q.update(project_id=project,customer_id=customer);ident=store.save(db,'quote',q)
            owner=db.execute('SELECT id FROM users').fetchone()[0];db.execute('UPDATE records SET owner_id=?',(owner,))
        log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'JOSEPH_DATA_DIR':str(root),'CIRRUS_PORT':'8004'},stdout=log,stderr=log)
        try:
            for _ in range(100):
                if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
                try:urllib.request.urlopen(BASE,timeout=1).close();break
                except OSError:time.sleep(.1)
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or None);page=browser.new_page(viewport={'width':1600,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept());login(page,BASE)
                def ready():page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for()
                page.goto(BASE+'/customers/'+customer);assert 'Version 9' in page.locator('.brand').inner_text()
                page.get_by_role('link',name='Agreed prices',exact=True).click();page.get_by_role('link',name='Effective dates, currencies & price-change history',exact=True).click()
                form=page.locator('details.card').first.locator('form').first;form.locator('[name=item_key]').select_option('catalog:'+catalog);form.locator('[name=price]').fill('80');form.locator('[name=reason]').fill('Customer contract agreement');form.get_by_role('button',name='Add price',exact=True).click();assert '80.00 USD' in page.locator('body').inner_text()
                page.goto(BASE+'/prices/'+project);form=page.locator('details.card').first.locator('form').first;form.locator('[name=item_key]').select_option('catalog:'+catalog);form.locator('[name=price]').fill('60');form.locator('[name=reason]').fill('Project negotiated price');form.get_by_role('button',name='Add price',exact=True).click()
                page.goto(BASE+'/quotes/'+ident+'/edit');ready();page.locator('[data-section-id] > summary').first.click();picker=page.get_by_label('Catalog for Production',exact=True);picker.select_option(catalog);page.wait_for_function("()=>document.querySelector('[data-price-key]').textContent.includes('Project agreed price')")
                assert '60.00 USD' in picker.locator('option:checked').inner_text();page.get_by_role('button',name='Copy catalog row',exact=True).click();page.wait_for_function("()=>document.querySelector('#customer-preview').contentDocument.querySelectorAll('tr[data-row]').length===3");ready();frame=page.frame_locator('#customer-preview');frame.locator('[data-row][data-field=unit_price]').last.wait_for();assert frame.locator('[data-row][data-field=unit_price]').last.input_value()=='60.00'
                frame.locator('[data-row][data-field=unit_price]').last.fill('63');ready();page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/edit');ready()
                # VM picker keeps Linux and Windows prices separate.
                frame=page.frame_locator('#customer-preview');frame.get_by_role('button',name='Choose VM',exact=True).first.click();page.get_by_label('Operating system',exact=True).select_option('b');vmrow=page.locator('[data-vm="'+vm+'"]');assert '126.00' in vmrow.inner_text();vmrow.get_by_role('button').click();ready();assert frame.locator('[data-field=unit_price]').first.input_value()=='126.00'
                page.locator('#editor-controls > details').filter(has=page.locator('summary',has_text='Contract, discount & tax')).first.locator('summary').first.click()
                page.get_by_label('Show discount in cost summary',exact=True).check();page.get_by_label('Summary discount %',exact=True).fill('10');page.get_by_label('Recurring discount period',exact=True).select_option('temporary');page.get_by_label('Promotional months',exact=True).fill('2');page.get_by_label('Discount eligible items / sections',exact=True).select_option('s:'+q['document']['sections'][0]['id']);ready()
                assert frame.locator('.summary-discount').count()>0;assert 'Regular monthly fee afterward' in frame.locator('.summary').inner_text()
                meta=frame.locator('.quote-metadata').inner_text();assert 'Reference' in meta and 'Revision' not in meta and 'Currency' not in meta and 'Valid until' not in meta
                page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/edit');ready();shot=os.environ.get('V8_QUOTE_SCREENSHOT');
                if shot:page.screenshot(path=shot,full_page=True)
                page.goto(BASE+'/quotes/'+ident+'/print');page.pdf(path=str(td/'customer.pdf'),format='A4',landscape=True,print_background=True)
                pdftext=subprocess.run(['pdftotext','-layout',str(td/'customer.pdf'),'-'],capture_output=True,text=True,check=True).stdout
                assert 'Reference' in pdftext and 'USD' in pdftext and 'promotional' in pdftext
                for hidden in ('Valid until','Revision','Currency','CONFIDENTIAL-NOTE-SENTINEL'):assert hidden not in pdftext
                print('PASS customer/project agreed-price UI, editable quotation snapshots, Linux/Windows picker, opt-in discount and Date/Reference-only customer metadata')
                # Contract agreement entered independently from the quotation.
                page.goto(BASE+'/projects/'+project+'/commercial');page.locator('[data-contract=reference]').fill('CON-SYN-UI');page.locator('[data-contract=start]').fill('2026-01-01');page.locator('[data-contract=end]').fill('2027-12-31');page.locator('[data-contract=renewal]').fill('2026-11-20');page.get_by_role('button',name='+ Add service',exact=True).click()
                page.get_by_label('service for service 1',exact=True).fill('Compute allocation');page.get_by_label('quantity for service 1',exact=True).fill('2');page.get_by_label('unit_price for service 1',exact=True).fill('100');page.get_by_label('discount for service 1',exact=True).fill('10');page.get_by_role('button',name='Save proposed version',exact=True).click();page.wait_for_url('**/commercial?version=*');assert 'Proposed' in page.locator('.notice').last.inner_text()
                page.locator('input[type=file]').set_input_files(dict(name='synthetic-signed.pdf',mimeType='application/pdf',buffer=b'%PDF-1.4 synthetic contract'))
                page.get_by_role('button',name='Upload to this version',exact=True).click();page.wait_for_url('**/commercial?version=*');assert 'Proposed' in page.locator('body').inner_text()
                page.get_by_role('checkbox').check();page.get_by_role('button',name='Approve entered contract → new approved version',exact=True).click();page.wait_for_url('**/commercial?version=*');assert 'Approved' in page.locator('.notice').last.inner_text()
                page.get_by_role('link',name='Monthly consumption',exact=True).click();page.get_by_label('Actual quantity for Compute allocation',exact=True).fill('3');assert '180.00 USD' in page.locator('#consumption-total').inner_text();assert page.locator('.over-consumption').count()==1;page.get_by_role('button',name='Save monthly snapshot',exact=True).click();page.wait_for_url('**/consumption?month=*');assert 'Saved price snapshot' in page.locator('.notice').last.inner_text()
                page.goto(BASE+'/projects/'+project+'/consumption?month=2026-11&copy_previous=yes');assert page.get_by_label('Actual quantity for Compute allocation',exact=True).input_value()=='3'
                page.goto(BASE+'/customers/'+customer+'?tab=contract&period=all');assert 'CON-SYN-UI' in page.locator('body').inner_text();assert 'days remaining' in page.locator('body').inner_text()
                shot=os.environ.get('V8_CUSTOMER_SCREENSHOT');
                if shot:page.screenshot(path=shot,full_page=True)
                print('PASS contract proposed/upload/explicit approval/history and monthly billing, overage highlight, snapshot save, previous-month copy and customer renewal overview')
                page.goto(BASE+'/list/quote?period=all');page.get_by_label('Select all on this page',exact=True).check();assert '1 families · 1 revisions selected' in page.locator('#selection-count').inner_text();page.get_by_role('button',name='Archive selected',exact=True).click();assert 'every revision' in page.locator('.notice').inner_text();page.get_by_role('button',name='Confirm archive · 1 families',exact=True).click();page.wait_for_url('**/list/quote?archive=archived');assert page.locator('[data-family-select]').count()==1
                page.get_by_role('button',name='Select all 1 matching families',exact=True).click();page.get_by_role('button',name='Restore selected',exact=True).click();page.get_by_role('button',name='Confirm restore · 1 families',exact=True).click();page.wait_for_url('**/list/quote?archive=active');assert page.locator('[data-family-select]').count()==1
                page.set_viewport_size({'width':430,'height':900});page.goto(BASE+'/customers/'+customer);assert page.locator('main').evaluate('(e)=>e.getBoundingClientRect().width')<=435
                assert not errors,errors;browser.close();print('PASS bulk family archive/restore, all-matching selection, mobile customer layout and no JavaScript errors')
        finally:server.terminate();server.wait(timeout=10);log.close()

if __name__=='__main__':run()
