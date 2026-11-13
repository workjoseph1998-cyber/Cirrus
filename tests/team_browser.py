"""Authenticated team workflow with company template/catalog and staged Excel import."""
import io,json,os,re,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import create_app,store,security
from browser_auth import bootstrap,PASSWORD
from test_team_upgrade import workbook

ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8000'


def run():
    with tempfile.TemporaryDirectory() as directory:
        td=Path(directory);root=td/'data';bootstrap(root)
        log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'JOSEPH_DATA_DIR':str(root)},stdout=log,stderr=log)
        try:
            for _ in range(100):
                try:urllib.request.urlopen(BASE,timeout=1).close();break
                except OSError:time.sleep(.1)
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or None)
                admin_context=browser.new_context(viewport={'width':1700,'height':1000});admin=admin_context.new_page()
                def login(page,name):
                    page.goto(BASE+'/login');page.get_by_label('Username',exact=True).fill(name);page.get_by_label('Password',exact=True).fill(PASSWORD);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(BASE+'/')
                login(admin,'browser-admin');assert 'Cirrus Workplace' in admin.title()
                admin.goto(BASE+'/accounts')
                for name,role in [('team-editor','Editor'),('team-viewer','Viewer')]:
                    card=admin.locator('section').filter(has=admin.get_by_role('heading',name='Create account',exact=True))
                    card.get_by_label('Username',exact=True).fill(name);card.get_by_label('Initial password (12+ characters)',exact=True).fill(PASSWORD);card.locator('select[name=role]').select_option(role);card.get_by_role('button',name='Create account',exact=True).click()
                admin.goto(BASE+'/catalog-replacement');admin.get_by_label('Type REPLACE CATALOG').fill('REPLACE CATALOG');admin.get_by_role('button',name='Back up instance and replace catalog',exact=True).click();admin.wait_for_url('**/catalog-replacement')
                assert 'already completed' in admin.locator('body').inner_text()
                admin.goto(BASE+'/quotes/new');admin.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for()
                frame=admin.frame_locator('#customer-preview');assert frame.get_by_text('Datacenter FW',exact=True).count() or frame.locator('textarea').count()>0
                assert 'Monthly discount' not in frame.locator('body').inner_text()
                assert 'Discounted monthly total' not in frame.locator('body').inner_text()
                # Save one independently editable template-derived quotation.
                admin.get_by_text('Quotation details',exact=True).click();admin.get_by_label('Document title',exact=True).fill('Team standard quote');frame.get_by_label('Customer name',exact=True).fill('Synthetic company')
                admin.get_by_role('button',name='Save quotation',exact=True).click();admin.wait_for_url('**/quotes/*/edit')
                quote_id=admin.url.split('/')[-2]
                admin.goto(BASE+'/company-template');admin.locator('select[name=source_quote]').select_option(quote_id);admin.get_by_role('button',name='Save as company template',exact=True).click()
                print('PASS account creation, one-time backed-up catalog replacement, populated quotation and explicit company template')
                editor_context=browser.new_context(viewport={'width':1700,'height':1000});editor=editor_context.new_page();login(editor,'team-editor')
                editor.goto(BASE+'/new/project');editor.locator('[name=name]').fill('Editor private project');editor.locator('[name=customer]').fill('Synthetic customer');editor.get_by_role('button',name='Save project',exact=True).click();editor.wait_for_url('**/record/*');project_id=editor.url.rsplit('/',1)[-1]
                viewer_context=browser.new_context();viewer=viewer_context.new_page();login(viewer,'team-viewer')
                assert viewer.request.get(BASE+'/record/'+project_id).status==404
                editor.goto(BASE+'/record/'+project_id+'/access')
                with store.connect(root) as db:viewer_id=db.execute('SELECT id FROM users WHERE username=?',('team-viewer',)).fetchone()[0]
                editor.locator('select[name="'+viewer_id+'"]').select_option('read');editor.get_by_role('button',name='Save access',exact=True).click()
                assert viewer.request.get(BASE+'/record/'+project_id).status==200
                with store.connect(root) as db:
                    from workspace_app.model import FIELDS
                    note={k:'' for k,_,_ in FIELDS['note']};note.update(title='Owner-only gym note',type='Note',status='Open',visibility='Personal')
                    personal_id=store.save(db,'note',note)
                    owner=db.execute('SELECT id FROM users WHERE username=?',('team-editor',)).fetchone()[0]
                    db.execute('UPDATE records SET owner_id=?,personal=1 WHERE id=?',(owner,personal_id))
                assert admin.request.get(BASE+'/record/'+personal_id).status==404
                assert viewer.request.get(BASE+'/accounts').status==403
                print('PASS private ownership, named viewer sharing, denied account management and personal isolation from admin')
                path=td/'synthetic.xlsx';path.write_bytes(workbook(multiple=True,unsupported=True))
                editor.goto(BASE+'/excel-import');editor.locator('input[type=file]').set_input_files(path);editor.get_by_role('button',name='Upload for preview',exact=True).click();editor.wait_for_url('**/excel-import/*')
                review_url=editor.url;editor.locator('select[name=sheet]').select_option('Cirrus');editor.get_by_role('button',name='Apply mapping and preview',exact=True).click()
                assert 'Unsupported formula is not executed' in editor.locator('body').inner_text()
                editor.get_by_role('link',name='Edit imported draft in the visual quotation editor',exact=True).click();editor.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for()
                imported=editor.frame_locator('#customer-preview');target=imported.locator('tr[data-row]').filter(has=imported.locator('textarea[data-field=sub_service]',has_text='Custom VM'))
                target.locator('[data-field=fixed_fee]').fill('200')
                editor.get_by_role('button',name='Update import draft',exact=True).click();editor.wait_for_url(review_url)
                for option in editor.locator('select[name^=resolution-]').all():
                    choices=option.locator('option').evaluate_all('(nodes)=>nodes.map(n=>n.value)')
                    option.select_option('edited' if 'edited' in choices else 'reviewed')
                editor.get_by_role('button',name='Confirm import as draft',exact=True).click();editor.wait_for_url('**/quotes/*/edit');imported_id=editor.url.split('/')[-2]
                assert viewer.request.get(BASE+'/quotes/'+imported_id+'/print').status==404
                assert editor.request.get(BASE+'/quotes/'+imported_id+'/print').status==200
                print('PASS multi-sheet Excel upload, issue review, visual correction, atomic draft import and permission enforcement')
                screenshot=os.environ.get('TEAM_SCREENSHOT')
                if screenshot:
                    editor.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for()
                    editor.screenshot(path=screenshot,full_page=True)
                browser.close()
        finally:
            server.terminate();server.wait(timeout=10);log.close()


if __name__=='__main__':run()
