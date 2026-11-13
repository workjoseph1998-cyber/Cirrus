"""Synthetic desktop/mobile checks with system Chromium; no production profile."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from workspace_app import create_app,store,security
from quotation_fixture import fixture
from playwright.sync_api import sync_playwright,expect
from waitress import create_server
ART=Path(os.environ.get('CW_BROWSER_ARTIFACTS','/tmp/cirrus-v21-browser'));ART.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:8041'
with tempfile.TemporaryDirectory() as td:
    root=Path(td)/'data';app=create_app(root,testing=True)
    with store.connect(root) as db:
        admin=security.create_user(db,'browser-admin','Synthetic-browser-password-21!','Administrator',True)
        viewer=security.create_user(db,'browser-viewer','Synthetic-browser-password-21!','Viewer')
        customer=store.save(db,'customer',dict(name='Synthetic V21 customer',contact='',notes=''))
        q=fixture();q.update(customer_id=customer,number='V21-BROWSER',valid_until='2026-11-18')
        ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=?',(admin,))
        db.execute('INSERT INTO record_acl VALUES (?,?,?)',(ident,viewer,'view'))
    server=create_server(app,host='127.0.0.1',port=8041,threads=4)
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        with sync_playwright() as driver:
            browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            context=browser.new_context(viewport=dict(width=1440,height=1000),permissions=['clipboard-read','clipboard-write'])
            page=context.new_page();errors=[]
            page.on('pageerror',lambda exc:errors.append(str(exc)))
            page.goto(BASE+'/login');page.get_by_label('Username',exact=True).fill('browser-admin');page.get_by_label('Password',exact=True).fill('Synthetic-browser-password-21!');page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(BASE+'/')
            expect(page.get_by_text('Needs Your Attention',exact=True)).to_be_visible()
            page.screenshot(path=str(ART/'dashboard-light.png'),full_page=True)
            page.goto(BASE+'/list/quote');page.get_by_role('button',name='Copy link',exact=True).click();expect(page.get_by_text('Link copied.',exact=True)).to_be_visible()
            assert page.evaluate('navigator.clipboard.readText()')==BASE+'/record/'+ident
            page.get_by_role('button',name='☆ Favorite',exact=True).click();page.wait_for_url(BASE+'/v21/shortcuts');expect(page.get_by_role('heading',name='Favorites',exact=True)).to_be_visible()
            page.goto(BASE+'/quotes/'+ident+'/internal-notes');page.locator('textarea[name=body]').fill('Synthetic internal browser note')
            page.get_by_role('button',name='Add internal note',exact=True).click();expect(page.get_by_text('Synthetic internal browser note',exact=True)).to_be_visible()
            # Dirty forms warn only after editing and stop warning when restored.
            page.locator('textarea[name=body]').fill('unsaved draft')
            dialogs=[]
            def dismiss(dialog):dialogs.append(dialog.type);dialog.dismiss()
            page.on('dialog',dismiss)
            page.get_by_role('link',name='← Quotation',exact=True).click();assert dialogs==['beforeunload']
            page.locator('textarea[name=body]').fill('');page.remove_listener('dialog',dismiss)
            page.get_by_role('link',name='← Quotation',exact=True).click();page.wait_for_url(BASE+'/quotes/'+ident+'/edit')
            page.goto(BASE+'/customers/'+customer+'/activity');expect(page.get_by_role('heading',name='Synthetic V21 customer · Activity',exact=True)).to_be_visible()
            page.locator('#portal-theme').select_option('dark');page.wait_for_timeout(300)
            page.screenshot(path=str(ART/'activity-dark.png'),full_page=True)
            page.set_viewport_size(dict(width=390,height=844));page.goto(BASE+'/v21/shortcuts');page.screenshot(path=str(ART/'shortcuts-mobile-dark.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
            page.goto(BASE+'/quotes/'+ident+'/edit');expect(page.locator('#quotation-form')).to_be_attached();page.locator('#show-preview').click();expect(page.locator('#customer-preview')).to_be_visible();page.screenshot(path=str(ART/'editor-mobile-dark.png'),full_page=True)
            page.set_viewport_size(dict(width=1440,height=1000));page.goto(BASE+'/quotes/'+ident+'/pre-send');expect(page.get_by_text('All required approvers approved',exact=False)).to_be_visible()
            page.keyboard.press('Control+k');expect(page.locator('.global-search input')).to_be_focused()
            assert not errors, errors
            browser.close()
            (ART/'results.json').write_text(json.dumps(dict(passed=['desktop dashboard','clipboard link','favorite save','internal note save','dirty and clean navigation','customer activity','dark mode','mobile shortcuts without page overflow','existing mobile editor','pre-send panel','Ctrl+K search'],javascript_errors=errors),indent=2))
            print('Browser checks passed; artifacts: '+str(ART))
    finally:server.close()
