"""Optional developer E2E: pip install playwright; playwright install chromium.
Uses temporary data, starts/stops Waitress, and never touches your workspace.
Set CHROMIUM_PATH to use an existing browser installation.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from browser_auth import bootstrap,login

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8000'


def main():
    with tempfile.TemporaryDirectory() as directory:
        directory=Path(directory)
        environment={**os.environ,'JOSEPH_DATA_DIR':str(directory/'data')}
        bootstrap(directory/'data')
        log=(directory/'server.log').open('w')
        server=None
        def start():
            process=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env=environment,stdout=log,stderr=log)
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('Server exited: '+(directory/'server.log').read_text())
                try:
                    urllib.request.urlopen(BASE,timeout=1).close()
                    return process
                except OSError:
                    time.sleep(.1)
            process.terminate();process.wait()
            raise RuntimeError('Server did not become ready')
        def fill(page,values):
            for key,value in values.items():
                page.locator(f'[name="{key}"]').first.fill(value)
        def save(page):
            page.get_by_role('button',name='Save ',exact=False).click()
            page.wait_for_url('**/record/*')
        try:
            server=start()
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or None)
                page=browser.new_page(viewport={'width':1440,'height':1000})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                login(page,BASE)
                page.goto(BASE+'/new/project')
                fill(page,dict(name='Browser refresh',customer='Demo customer',description='Browser smoke project',requirements='24 VMs',architecture='Two-node lab diagram',sizing='Confirm inventory'))
                save(page);project_id=page.url.rsplit('/',1)[-1]
                print('PASS create project')
                # Archived notes remain in storage/exports without a note-creation UI.
                from workspace_app import store
                from workspace_app.model import FIELDS
                with store.connect(directory/'data') as db:
                    for title in ('Discovery notes','What is the retention target?'):
                        note={k:'' for k,_,_ in FIELDS['note']};note.update(title=title,type='Note',status='Open',visibility='Work',project_id=project_id,content='Preserved historical note')
                        ident=store.save(db,'note',note)
                        db.execute('UPDATE records SET owner_id=(SELECT id FROM users WHERE username=?) WHERE id=?',('browser-admin',ident))
                print('PASS archived linked notes remain stored')
                page.goto(BASE+'/new/catalog')
                fill(page,dict(code='BROWSER-001',name='Deployment day',description='Implementation services',vendor='Generic',unit='day',price='100',cost='60'))
                save(page)
                print('PASS catalog item')
                page.goto(BASE+'/new/quote?project_id='+project_id)
                page.locator('summary:text-is("Quotation details")').click()
                fill(page,dict(title='Browser proposal',customer='Demo customer',internal_notes='PRIVATE-ONLY-123'))
                page.locator('summary').filter(has_text=__import__('re').compile('^Production$')).click()
                production=page.locator('details:has(> summary:text-is("Production"))')
                picker=production.get_by_label('Catalog for Production',exact=True)
                picker.select_option(picker.locator('option').filter(has_text='BROWSER-001 — Deployment day').get_attribute('value'))
                production.get_by_role('button',name='Copy catalog row',exact=True).click()
                row=page.locator('details.row-editor').filter(has=page.locator('summary:text-is("Deployment day / Implementation services")'))
                row.locator('summary').first.click()
                row.get_by_label('Quantity',exact=True).fill('2')
                row.get_by_label('Line discount %',exact=True).fill('10')
                page.get_by_role('button',name='Save quotation',exact=True).click()
                page.wait_for_url('**/quotes/*/edit')
                quote_id=page.url.split('/')[-2]
                page.locator('#preview-status').filter(has_text=__import__('re').compile('^Preview current')).wait_for()
                live=page.frame_locator('#customer-preview')
                assert '180.00' in live.locator('body').inner_text()
                assert 'PRIVATE-ONLY-123' not in live.locator('body').inner_text()
                page.goto(BASE+'/quotes/'+quote_id+'/print')
                body=page.locator('body').inner_text()
                assert '180.00' in body and 'PRIVATE-ONLY-123' not in body and 'Internal cost' not in body
                assert 'Implementation services' in body
                print('PASS live quotation preview and private-field-free customer print')
                page.goto(BASE+'/settings')
                with page.expect_download() as download:
                    page.get_by_role('link',name='Export workspace JSON').click()
                export_path=directory/'export.json';download.value.save_as(export_path)
                payload=json.loads(export_path.read_text());assert len(payload['records'])==5
                page.locator('input[name=file]').set_input_files(export_path)
                page.get_by_role('button',name='Preview import').click()
                assert '5 identical records skipped' in page.locator('body').inner_text()
                page.get_by_role('button',name='Confirm atomic import').click()
                assert 'skipped 5 identical records' in page.locator('body').inner_text()
                print('PASS JSON export, preview, and idempotent reimport')
                page.goto(BASE+'/');page.screenshot(path=str(directory/'dashboard.png'),full_page=True)
                artifact=os.environ.get('SMOKE_SCREENSHOT')
                if artifact:
                    import shutil
                    shutil.copyfile(directory/'dashboard.png',artifact)
                server.terminate();server.wait(timeout=10);server=start()
                login(page,BASE)
                page.goto(BASE+'/record/'+quote_id)
                page.locator('#preview-status').filter(has_text=__import__('re').compile('^Preview current')).wait_for()
                assert '180.00' in page.frame_locator('#customer-preview').locator('body').inner_text()
                page.goto(BASE+'/record/'+project_id)
                assert 'What is the retention target?' not in page.locator('body').inner_text()
                page.goto(BASE+'/record/'+ident)
                assert 'What is the retention target?' in page.locator('body').inner_text()
                print('PASS restart persists project, linked entries, and quotation')
                page.set_viewport_size({'width':390,'height':844});page.goto(BASE+'/')
                assert page.locator('body').evaluate('(el) => el.scrollWidth <= window.innerWidth')
                assert not errors,errors
                print('PASS mobile dashboard and no JavaScript errors')
                browser.close()
        finally:
            if server and server.poll() is None:
                server.terminate();server.wait(timeout=10)
            log.close()


if __name__=='__main__':
    main()
