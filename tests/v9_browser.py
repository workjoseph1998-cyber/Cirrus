"""Version 9 user journey on a disposable Waitress database."""
import copy,json,os,re,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store,security,relationships as rel,outcomes,costing
from workspace_app.model import FIELDS
from workspace_app.company import catalog_items
from test_v5 import quote
from browser_auth import bootstrap,login,PASSWORD
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8005'


def run():
    with tempfile.TemporaryDirectory() as temp:
        td=Path(temp);root=td/'data';bootstrap(root)
        with store.connect(root) as db:
            owner=db.execute('SELECT id FROM users').fetchone()[0];viewer_id=security.create_user(db,'v9-viewer',PASSWORD,'Viewer')
            customer=store.save(db,'customer',dict(name='Synthetic Bank',contact='Example contact',notes='Synthetic workspace'))
            d={k:'' for k,_,_ in FIELDS['project']};d.update(name='Bank agreement',customer='Synthetic Bank',customer_id=customer,status='Active');project=store.save(db,'project',d)
            for data in catalog_items():
                if data['code']=='CIR-COMPUTE':data.update(price='100',quantity='0')
                ident=store.save(db,'catalog',data)
                if data['code']=='CIR-COMPUTE':catalog=ident
            first=quote(status='Draft');first.update(project_id=project,customer_id=customer,title='CIR26-148-1_Manually editable title');q1=store.save(db,'quote',first)
            second=copy.deepcopy(first);second['revision']=2;second['document']['sections'][0]['rows'][0]['unit_price']='200';q2=store.save(db,'quote',second,inherit_from=q1)
            state=outcomes.get(db,'cir26-148-1');outcomes.save_outcome(db,dict(id=q2,kind='quote',data=second),dict(version=str(state['version']),status='Won',reason='Technical solution',notes='',outcome_date='2026-10-29',accepted_quote_id=q1))
            zero=quote('TEMPLATE-ZERO',price='0',status='Draft');zero.update(project_id=project,customer_id=customer,title='Template Cirrus');zero['document']['sections'][0]['rows'][1]['fixed_fee']='0';store.save(db,'quote',zero)
            missing=quote('UNPRICED',price='',status='Draft');missing.update(project_id=project,customer_id=customer,title='Unpriced services');store.save(db,'quote',missing)
            deleted=quote('ISSUED-DELETE',price='20',status='Sent');deleted.update(project_id=project,customer_id=customer,title='Remove archived quotation');delete_id=store.save(db,'quote',deleted)
            service_id=first['document']['sections'][0]['rows'][0]['id']
            con=dict(reference='CON-BASE',currency='USD',start='2026-01-01',end='2027-12-31',renewal='2026-11-20',notes='',initial_quote_id=q1,accepted_quote_id=q1,services=[dict(id=service_id,service='Monthly service',quantity='1',unit_price='100',discount='0',billing='monthly',basis='fixed',method='unit',notes='',item_key='')])
            contract=rel.save_contract(db,dict(id=project,kind='project',data=d),con,0,'Approved');sheet=rel.consumption_data(db,project,'2026-09');row=sheet['data']['rows'][0];row.update(actual='3',charge='100.00');sheet['data']['total']='100.00'
            db.execute('INSERT INTO consumption VALUES (?,?,?,?,?,?,?,?)',('previous',project,'2026-09',contract,json.dumps(sheet['data']),1,'2026-09-30','browser-admin'))
            cost=costing.load(db,dict(id=q2,kind='quote',data=second));cost['rows'][0].update(valid_until='2026-10-20',supplier='PRIVATE SUPPLIER');db.execute('INSERT INTO quote_costing VALUES (?,?,?,?,?)',(q2,1,json.dumps(dict(rows=cost['rows'],orphaned=[])),rel.stamp(),owner))
            db.execute('UPDATE records SET owner_id=?',(owner,))
            for rid in (customer,project):db.execute('INSERT INTO record_acl VALUES (?,?,?)',(rid,viewer_id,'read'))
        log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'JOSEPH_DATA_DIR':str(root),'CIRRUS_PORT':'8005'},stdout=log,stderr=log)
        try:
            for _ in range(100):
                if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
                try:urllib.request.urlopen(BASE,timeout=1).close();break
                except OSError:time.sleep(.1)
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or None);page=browser.new_page(viewport={'width':1500,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(BASE+'/login');assert page.locator('img[alt=Cirrus]').is_visible();login(page,BASE);assert page.locator('img[alt=Cirrus]').is_visible()
                def ready():page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for()
                def kpi(name):return page.locator('.kpi').filter(has=page.get_by_text(name,exact=True)).locator('strong').inner_text()
                page.goto(BASE+'/list/quote?period=all');assert kpi('Quoted value · USD')=='3,014.00';assert kpi('Monthly quoted fees · USD')=='220.00';assert kpi('Won value · USD')=='1,375.00';assert kpi('Unpriced quotations')=='1';assert kpi('Zero-priced quotations')=='1'
                assert not page.locator('.chart-grid').is_visible();assert page.locator('.compact-quotations').bounding_box()['y']<650
                assert page.locator('.compact-quotations th').filter(has_text=re.compile('^Type$')).count()==0
                assert page.locator('.compact-quotations small').count()==0;page.locator('.quote-tools summary').first.click();assert page.get_by_role('link',name='Compare revisions',exact=True).first.is_visible()
                page.locator('.quote-tools summary').first.click()
                shot=os.environ.get('V9_LIST_SCREENSHOT')
                if shot:page.screenshot(path=shot,full_page=True)
                page.get_by_placeholder('Reference, customer or quotation title').fill('CIR26-148-1');page.get_by_role('button',name='Apply filters',exact=True).click();assert page.locator('[data-family-select]').count()==1;assert 'CIR26-148-1_Manually editable title' in page.locator('.compact-quotations').inner_text()
                page.get_by_text('View monthly statistics',exact=True).click();assert page.locator('.chart-grid').is_visible()
                print('PASS compact quotations before collapsed charts, reference search/title preservation, latest-revision contract/monthly/frozen Won metrics and zero vs unpriced')
                page.goto(BASE+'/list/quote?period=all');page.get_by_label('Select ISSUED-DELETE',exact=True).check();page.get_by_role('button',name='Archive selected',exact=True).click();page.get_by_role('button',name='Confirm archive · 1 families',exact=True).click();page.get_by_label('Select ISSUED-DELETE',exact=True).check();page.get_by_role('button',name='Delete selected permanently',exact=True).click();assert 'Remove archived quotation' in page.locator('body').inner_text();page.get_by_label('Type DELETE to confirm',exact=True).fill('DELETE');page.get_by_role('button',name='Confirm delete · 1 families',exact=True).click();page.wait_for_url('**/list/quote?archive=archived')
                with store.connect(root) as db:assert db.execute("SELECT 1 FROM reference_registry WHERE key='issued-delete'").fetchone();assert not db.execute('SELECT 1 FROM records WHERE id=?',(delete_id,)).fetchone()
                page.goto(BASE+'/list/quote?period=all');page.get_by_label('Select CIR26-148-1',exact=True).check();page.get_by_role('button',name='Archive selected',exact=True).click();page.get_by_role('button',name='Confirm archive · 1 families',exact=True).click();page.get_by_label('Select CIR26-148-1',exact=True).check();page.get_by_role('button',name='Delete selected permanently',exact=True).click();assert 'accepted' in page.locator('body').inner_text().lower();assert page.get_by_role('button',name='Confirm delete · 1 families',exact=True).count()==0
                page.goto(BASE+'/list/quote?archive=archived&period=all');page.get_by_label('Select CIR26-148-1',exact=True).check();page.get_by_role('button',name='Restore selected',exact=True).click();page.get_by_role('button',name='Confirm restore · 1 families',exact=True).click()
                print('PASS archived permanent deletion confirmation and issued-reference protection; accepted Won family deletion is blocked')
                page.goto(BASE+'/customers/'+customer+'?period=last_month');assert kpi('Quotation count')=='0';assert '100.00 USD' in page.locator('.charge-kpis').inner_text();assert 'Supplier-price expiry' in page.locator('body').inner_text()
                page.get_by_role('link',name='Agreed prices',exact=True).click();assert page.locator('.customer-prices tbody tr:visible').count()==0
                picker=page.get_by_label('Service to add',exact=True);value=picker.locator('option').filter(has_text='CIR-COMPUTE · Cirrus Compute / VM').get_attribute('value');picker.select_option(value);page.get_by_role('button',name='Add / edit service',exact=True).click()
                price=page.get_by_label('Customer price for CIR-COMPUTE · Cirrus Compute / VM',exact=True);price.fill('70');page.once('dialog',lambda d:d.dismiss());page.get_by_role('link',name='Quotations',exact=True).first.click();assert '/customers/' in page.url;assert price.input_value()=='70'
                page.locator('#customer-pricing-form [name=reason]').fill('Customer negotiated rate');page.get_by_label('Default support percentage',exact=True).fill('11');page.once('dialog',lambda d:d.dismiss());page.get_by_role('button',name='Save customer prices',exact=True).click();assert price.input_value()=='70';assert page.get_by_label('Default support percentage',exact=True).input_value()=='11';page.once('dialog',lambda d:d.accept());page.get_by_role('button',name='Save customer prices',exact=True).click();page.wait_for_url('**/customers/*?tab=prices');assert page.get_by_label('Customer price for CIR-COMPUTE · Cirrus Compute / VM',exact=True).input_value()=='70.00'
                page.get_by_label('Default support percentage',exact=True).fill('10');page.get_by_label('Default support base',exact=True).select_option('category:Production');page.get_by_role('button',name='Save quotation defaults',exact=True).click();page.wait_for_url('**/customers/*?tab=prices')
                page.get_by_role('button',name='Create quotation',exact=True).click();page.wait_for_url('**/quotes/new?project_id=*');ready();data=json.loads(page.locator('#initial-quotation').inner_text());prod=next(s for s in data['document']['sections'] if s['name']=='Production');compute=next(r for s in data['document']['sections'] if s['parent']==prod['id'] for r in s['rows'] if r.get('item_key')=='catalog:'+catalog);fee=next(r for s in data['document']['sections'] for r in s['rows'] if r['method']=='percent')
                assert compute['unit_price']=='70.00';assert fee['percent']=='10';assert len([r for s in data['document']['sections'] for r in s['rows'] if r['method']=='percent'])==1
                page.locator('#editor-controls > details').first.locator('summary').first.click();page.get_by_label('Document title',exact=True).fill('Customer workspace quotation');frame=page.frame_locator('#customer-preview');r=frame.locator('tr[data-row="'+compute['id']+'"]');r.locator('[data-field=quantity]').fill('1');ready();r.locator('[data-field=unit_price]').fill('80');ready();support_row=frame.locator('tr[data-row="'+fee['id']+'"]');expect(support_row.locator('[data-computed]')).to_contain_text('8.00')
                support_row.get_by_role('button',name='Options',exact=True).click();left=page.locator('details[data-row="'+fee['id']+'"]');left.get_by_label('Internal fee percentage',exact=True).fill('12.5');ready();expect(support_row.locator('[data-computed]')).to_contain_text('10.00')
                page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/quotes/*/edit');ready();new_id=page.url.split('/')[-2];public=page.request.get(BASE+'/quotes/'+new_id+'/print').text();assert '12.5%' not in public;assert 'Customer workspace quotation' in public
                print('PASS compact customer overrides, pricing unsaved-change protection, create-from-customer prefill, one standalone automatic support fee and editable private percentage')
                page.goto(BASE+'/customers/'+customer+'?tab=consumption&period=all');page.get_by_role('link',name="Duplicate last month's consumption",exact=True).click()
                assert page.get_by_label('Actual quantity for Monthly service',exact=True).input_value()=='3'
                page.get_by_label('Actual quantity for Monthly service',exact=True).fill('4');page.once('dialog',lambda d:d.dismiss());page.get_by_role('link',name='Bank agreement · Contract',exact=True).click();assert '/consumption' in page.url;page.get_by_role('button',name='Save monthly snapshot',exact=True).click();page.wait_for_url('**/consumption?month=*');assert '100.00 USD' in page.locator('#consumption-total').inner_text();assert page.locator('.over-consumption').count()==1
                page.goto(BASE+'/customers/'+customer+'?tab=contract&period=all');assert 'CON-BASE' in page.locator('body').inner_text();page.get_by_role('link',name='Bank agreement · Contract & agreed services',exact=True).click();assert page.get_by_role('link',name='signed.pdf').count()==0
                page.goto(BASE+'/customers/'+customer+'?period=all');assert '200.00 USD' in page.locator('.charge-kpis').inner_text();assert 'days remaining' in page.locator('body').inner_text()
                shot=os.environ.get('V9_CUSTOMER_SCREENSHOT')
                if shot:page.screenshot(path=shot,full_page=True)
                page.goto(BASE+'/customers?q=Synthetic&sort=charges');assert page.get_by_role('link',name='Synthetic Bank',exact=True).is_visible();assert page.locator('aside').get_by_role('link',name='Projects',exact=True).count()==0
                viewer=browser.new_context().new_page();viewer.goto(BASE+'/login');viewer.get_by_label('Username',exact=True).fill('v9-viewer');viewer.get_by_label('Password',exact=True).fill(PASSWORD);viewer.get_by_role('button',name='Sign in',exact=True).click();viewer.wait_for_url(BASE+'/');viewer.goto(BASE+'/customers/'+customer+'?period=all');assert 'Supplier-price expiry' not in viewer.locator('body').inner_text();assert 'PRIVATE SUPPLIER' not in viewer.locator('body').inner_text();assert viewer.request.get(BASE+'/quotes/'+q2+'/costing').status==404
                page.set_viewport_size({'width':430,'height':900});page.goto(BASE+'/customers/'+customer);assert page.locator('main').evaluate('(e)=>e.getBoundingClientRect().width')<=435;assert not errors,errors;browser.close()
                print('PASS customer date-filtered calculated charges, previous-month copy and unsaved protection, expiry indicators, search/sort, private supplier permissions and mobile layout')
        finally:server.terminate();server.wait(timeout=10);log.close()

if __name__=='__main__':run()
