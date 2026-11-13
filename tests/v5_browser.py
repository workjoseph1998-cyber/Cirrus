"""V5 UI regression: actual statistics, date filters, shared references and cleanup."""
import copy,io,os,re,subprocess,sys,tempfile,time,urllib.request
from datetime import datetime,timedelta,timezone
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store,security,statistics
from browser_auth import bootstrap,PASSWORD,login
from test_v5 import quote

ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8001'


def run():
    with tempfile.TemporaryDirectory() as temp:
        td=Path(temp);root=td/'data';bootstrap(root);today=statistics.today_local();year=str(today.year)[-2:]
        now=datetime.now(timezone.utc).isoformat();last=(today.replace(day=1)-timedelta(days=1)).isoformat()+'T10:00:00+00:00'
        with store.connect(root) as db:
            owner=db.execute('SELECT id FROM users').fetchone()[0];security.create_user(db,'v5-colleague',PASSWORD,'Editor')
            original=quote(f'CIR{year}-148-1');original['date']=last[:10];first=store.save(db,'quote',original)
            revised=quote(f'CIR{year}-148-1',price='200',status='Accepted',revision=2);revised['date']=last[:10];second=store.save(db,'quote',revised,inherit_from=first)
            db.execute('UPDATE records SET created=? WHERE id=?',(last,first))
            for ref,status,currency in [('149','Draft','USD'),('150','Sent','EUR'),('151','Cancelled','USD')]:
                data=quote(f'CIR{year}-{ref}-1',status=status,currency=currency);data['date']=today.isoformat();ident=store.save(db,'quote',data);db.execute('UPDATE records SET created=? WHERE id=?',(now,ident))
            db.execute('UPDATE records SET owner_id=?',(owner,))
        log=(td/'server.log').open('w');env={**os.environ,'JOSEPH_DATA_DIR':str(root),'CIRRUS_PORT':'8001'}
        server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env=env,stdout=log,stderr=log)
        try:
            for _ in range(100):
                if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
                try:urllib.request.urlopen(BASE,timeout=1).close();break
                except OSError:time.sleep(.1)
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or None)
                context=browser.new_context(viewport={'width':1560,'height':1000});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                login(page,BASE);assert page.title()=='Cirrus Workplace'
                assert not page.locator('nav a[href="/list/note"], nav a[href="/list/personal"], nav a[href="/list/inbox"]').count()
                page.goto(BASE+'/list/quote?period=all')
                def kpi(label):return page.locator('.kpi').filter(has=page.get_by_text(label,exact=True)).locator('strong').inner_text()
                assert kpi('Quotations')=='4';assert kpi('Quoted value · USD')=='5,445.00'
                assert page.locator('.mini-chart').count()==2;page.get_by_text('View monthly statistics',exact=True).click()
                left,right=page.locator('.mini-chart').all();assert right.bounding_box()['x']>left.bounding_box()['x']
                page.locator('select[name=period]').select_option('last_month');page.get_by_role('button',name='Apply filters',exact=True).click();assert kpi('Quotations')=='1';assert kpi('Quoted value · USD')=='2,695.00'
                page.locator('select[name=period]').select_option('month');page.get_by_role('button',name='Apply filters',exact=True).click();assert kpi('Quotations')=='3';assert kpi('Quoted value · USD')=='2,750.00'
                page.locator('select[name=period]').select_option('custom');page.locator('input[name=start]').fill(today.isoformat());page.locator('input[name=end]').fill(today.isoformat());page.get_by_role('button',name='Apply filters',exact=True).click();assert kpi('Quotations')=='3'
                page.goto(BASE+'/list/quote?period=all&q=148');assert kpi('Quotations')=='1';assert page.locator('tbody tr').count()==1
                print('PASS revision-deduplicated USD statistics, explicit exclusions, monthly charts, date filters and reference search')
                page.goto(BASE+'/references/import');path=td/'references.csv';path.write_text('Reference\nCIR'+year+'-155-1\n')
                page.locator('input[type=file]').set_input_files(path);page.get_by_role('button',name='Preview references',exact=True).click();page.get_by_role('button',name='Confirm historical import',exact=True).click();page.wait_for_url('**/references')
                assert page.get_by_text(f'CIR{year}-156-1',exact=True).count()
                page.get_by_label('Reference',exact=True).fill('Proposal/CUSTOM-2026');page.get_by_label('Document type',exact=True).select_option('proposal');page.get_by_role('button',name='Reserve entered reference',exact=True).click()
                row=page.locator('tbody tr').filter(has=page.get_by_text('Proposal/CUSTOM-2026',exact=True));row.get_by_role('button',name='Renew 30 minutes',exact=True).click();row=page.locator('tbody tr').filter(has=page.get_by_text('Proposal/CUSTOM-2026',exact=True));row.get_by_role('button',name='Mark issued',exact=True).click()
                colleague=browser.new_context().new_page();colleague.goto(BASE+'/login');colleague.get_by_label('Username',exact=True).fill('v5-colleague');colleague.get_by_label('Password',exact=True).fill(PASSWORD);colleague.get_by_role('button',name='Sign in',exact=True).click();colleague.wait_for_url(BASE+'/')
                colleague.goto(BASE+'/list/quote?period=all');assert 'Synthetic quotation' not in colleague.locator('body').inner_text()
                colleague.goto(BASE+'/references');colleague.get_by_label('Reference',exact=True).fill('proposal/custom-2026');colleague.get_by_role('button',name='Reserve entered reference',exact=True).click();assert 'already issued' in colleague.locator('[role=alert]').inner_text()
                print('PASS historical CSV preview/import, suggested CIR, custom proposal reservation/renewal/issue and cross-user duplicate warning')
                page.goto(BASE+'/quotes/new?blank=1');page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for()
                page.locator('summary').filter(has_text=re.compile('^Quotation details$')).click();page.get_by_role('button',name='Reserve / renew this reference',exact=True).click();page.locator('.reference-status').filter(has_text=re.compile('reserved by you')).wait_for()
                frame=page.frame_locator('#customer-preview');frame.get_by_label('Document title',exact=True).fill('V5 browser quotation');frame.get_by_label('Customer name',exact=True).fill('Synthetic V5 customer')
                frame.get_by_role('button',name='+ Add row to Services',exact=True).click();page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for()
                row=frame.locator('tr[data-row]').first;row.locator('input[data-field=unit_price]').fill('100');page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for()
                page.get_by_label('Status',exact=True).select_option('Sent');page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/quotes/*/edit');page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for();ident=page.url.split('/')[-2]
                body=frame.locator('body').inner_text()
                for text in ('Yearly recurring total','Contract recurring total','Contract tax','Contract total incl.','Monthly discount','Discounted monthly total','30% discount','Prices provided exclude VAT','VAT / tax conditions'):assert text not in body,text
                page.goto(BASE+'/list/quote?period=all');assert kpi('Quotations')=='5';assert kpi('Quoted value · USD')=='6,645.00';assert kpi('Last used CIR · '+str(today.year))==f'CIR{year}-156-1'
                screenshot=os.environ.get('V5_SCREENSHOT')
                if screenshot:page.screenshot(path=screenshot,full_page=True)
                page.set_viewport_size({'width':390,'height':844});page.get_by_text('View monthly statistics',exact=True).click();assert page.locator('.mini-chart').nth(1).bounding_box()['y']>page.locator('.mini-chart').first.bounding_box()['y']
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                print('PASS reserved reference assignment in direct editor, cleaned customer output, saved statistics refresh and compact mobile charts')
                for endpoint in ('/list/project','/list/catalog','/hosting-vms','/accounts'):
                    page.goto(BASE+endpoint);assert page.locator('.kpi').count()>=4
                assert not errors,errors;browser.close()
                print('PASS project/catalog/hosting/administration KPIs and no JavaScript errors')
        finally:server.terminate();server.wait(timeout=10);log.close()


if __name__=='__main__':run()
