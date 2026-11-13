"""Real-login commercial workflow: drafts, costing, comparison, accepted snapshots and recycling."""
import os,re,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store,security,statistics
from browser_auth import bootstrap,PASSWORD,login
from test_v5 import quote

ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8002'


def run():
    with tempfile.TemporaryDirectory() as temp:
        td=Path(temp);root=td/'data';bootstrap(root)
        with store.connect(root) as db:
            owner=db.execute('SELECT id FROM users').fetchone()[0];viewer_id=security.create_user(db,'commercial-viewer',PASSWORD,'Viewer')
            ident=store.save(db,'quote',quote(status='Draft'));db.execute('UPDATE records SET owner_id=?',(owner,))
        log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'JOSEPH_DATA_DIR':str(root),'CIRRUS_PORT':'8002'},stdout=log,stderr=log)
        try:
            for _ in range(100):
                if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
                try:urllib.request.urlopen(BASE,timeout=1).close();break
                except OSError:time.sleep(.1)
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or None);page=browser.new_page(viewport={'width':1700,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));login(page,BASE)
                def ready():page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for()
                def kpi(label):return page.locator('.kpi').filter(has=page.get_by_text(label,exact=True)).locator('strong').inner_text()
                page.goto(BASE+'/list/quote?period=all');assert kpi('Quoted value · USD')=='1,375.00';assert kpi('Monthly quoted fees · USD')=='100.00'
                page.locator('.quote-tools summary').first.click();page.get_by_role('link',name='Internal costing',exact=True).click()
                page.get_by_label('Unit purchase cost 1',exact=True).fill('60');page.get_by_label('Shipping 1',exact=True).fill('20');page.get_by_label('Unit purchase cost 2',exact=True).fill('10');page.get_by_label('Supplier 1',exact=True).fill('PRIVATE-COSTING-SUPPLIER');page.get_by_label('Internal notes 1',exact=True).fill('PRIVATE-COSTING-NOTE')
                page.locator('#cost-status').filter(has_text=re.compile('^Calculations current')).wait_for();assert page.locator('[data-summary=cost]').inner_text()=='750.00';assert page.locator('[data-summary=margin]').inner_text()=='40.00'
                page.get_by_role('button',name='Save internal costing',exact=True).click();page.wait_for_url('**/costing')
                page.get_by_label('Target margin 1',exact=True).fill('50');page.get_by_label('Target margin 2',exact=True).fill('50');page.get_by_role('button',name='Save and use target margin suggestions internally',exact=True).click();page.wait_for_url('**/costing')
                assert page.get_by_label('Selling unit price 1',exact=True).input_value()=='123.33'
                assert '100' in page.request.get(BASE+'/quotes/'+ident+'/print').text()
                page.get_by_role('link',name='Preview applying selling prices',exact=True).click();page.get_by_role('checkbox').check();page.get_by_role('button',name='Apply selling prices to quotation',exact=True).click();page.wait_for_url('**/edit');ready()
                for secret in ('PRIVATE-COSTING-SUPPLIER','PRIVATE-COSTING-NOTE'):assert secret not in page.frame_locator('#customer-preview').locator('body').inner_text()
                page.goto(BASE+'/list/quote?period=all');assert kpi('Quoted value · USD')=='1,649.96'
                print('PASS priced drafts update quoted amount; live full-contract costing/margin and explicit price preview/application exclude private data')
                page.goto(BASE+'/quotes/'+ident+'/edit');ready();page.locator('.more-actions summary').click();page.get_by_role('button',name='New revision',exact=True).click();page.wait_for_url('**/quotes/*/edit');ready();second=page.url.split('/')[-2]
                frame=page.frame_locator('#customer-preview');frame.locator('input[data-field=quantity]').first.fill('2');ready();page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/edit');ready()
                page.get_by_role('link',name='Compare revisions',exact=True).click();assert page.locator('.diff-modified').count()>0;page.get_by_role('checkbox',name='Only show changes',exact=True).check();page.get_by_role('button',name='Compare revisions',exact=True).click();assert page.locator('.diff-unchanged').count()==0;text=page.locator('body').inner_text();assert 'quantity' in text.casefold(),text[:4000]
                shot=os.environ.get('COMPARE_SCREENSHOT')
                if shot:page.screenshot(path=shot,full_page=True)
                page.goto(BASE+'/quotes/'+second+'/outcome');page.get_by_label('Outcome status',exact=True).select_option('Won');page.get_by_label('Outcome reason',exact=True).select_option('Technical solution');page.get_by_label('Accepted revision',exact=True).select_option(ident);page.locator('textarea[name=notes]').fill('Accepted the earlier design.');page.get_by_role('button',name='Save outcome',exact=True).click();page.wait_for_url('**/outcome');assert '1649.96 USD' in page.locator('body').inner_text();assert 'browser-admin' in page.locator('body').inner_text()
                page.goto(BASE+'/quotes/'+second+'/edit');ready();page.locator('.more-actions summary').click();page.get_by_role('button',name='New revision',exact=True).click();page.wait_for_url('**/quotes/*/edit');ready();third=page.url.split('/')[-2]
                page.frame_locator('#customer-preview').locator('input[data-field=unit_price]').first.fill('200');ready();page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/edit');ready()
                page.goto(BASE+'/list/quote?period=all');assert kpi('Quotations')=='1';assert kpi('Quoted value · USD')=='5,302.00';assert kpi('Won value · USD')=='1,649.96'
                shot=os.environ.get('COMMERCIAL_SCREENSHOT')
                if shot:page.screenshot(path=shot,full_page=True)
                print('PASS revision comparison and only-changes toggle; accepted revision snapshot stays fixed while newer revisions change quoted amount')
                page.goto(BASE+'/record/'+third+'/access');page.locator('select[name="'+viewer_id+'"]').select_option('read');page.get_by_role('button',name='Save access',exact=True).click()
                viewer=browser.new_context().new_page();viewer.goto(BASE+'/login');viewer.get_by_label('Username',exact=True).fill('commercial-viewer');viewer.get_by_label('Password',exact=True).fill(PASSWORD);viewer.get_by_role('button',name='Sign in',exact=True).click();viewer.wait_for_url(BASE+'/')
                assert viewer.request.get(BASE+'/quotes/'+third+'/costing').status==404;assert viewer.request.get(BASE+'/quotes/'+third+'/accepted').status==404
                assert viewer.request.get(BASE+'/quotes/'+third+'/compare?before='+ident).status==404
                page.goto(BASE+'/list/quote?period=all');csrf=page.locator('input[name=csrf]').first.input_value();draft=quote('UNUSED-BROWSER-DRAFT',status='Draft')
                reserved=page.request.post(BASE+'/references/check',form={'csrf':csrf,'reference':draft['number'],'reserve':'yes'});assert reserved.ok
                response=page.request.post(BASE+'/quotes/new',form={'csrf':csrf,'quotation':__import__('json').dumps(draft)},max_redirects=0);assert response.status==302;draft_id=response.headers['location'].split('/')[-2]
                page.goto(BASE+'/quotes/'+draft_id+'/edit');ready();page.once('dialog',lambda d:d.accept());page.get_by_role('button',name='Delete quotation',exact=True).click();page.wait_for_url('**/list/quote')
                csrf=page.locator('input[name=csrf]').first.input_value();response=page.request.post(BASE+'/references/check',form={'csrf':csrf,'reference':'UNUSED-BROWSER-DRAFT'});assert response.json()['state']=='available'
                page.goto(BASE+'/quotes/'+third+'/costing');shot=os.environ.get('COSTING_SCREENSHOT')
                if shot:page.screenshot(path=shot,full_page=True)
                page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert not errors,errors;print('PASS internal costing/accepted snapshot permissions, unused draft reference recycling, retained responsive theme and no JavaScript errors');browser.close()
        finally:server.terminate();server.wait(timeout=10);log.close()


if __name__=='__main__':run()
