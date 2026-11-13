"""Synthetic V21.1 UX checks. Run from repository root; no production profile."""
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
ART=Path(os.environ.get('CW_BROWSER_ARTIFACTS','/tmp/cirrus-v21-1-browser'));ART.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:8042'
with tempfile.TemporaryDirectory() as td:
    root=Path(td)/'data';app=create_app(root,testing=True)
    with store.connect(root) as db:
        admin=security.create_user(db,'browser-admin','Synthetic-browser-password-21!','Administrator',True)
        viewer=security.create_user(db,'browser-viewer','Synthetic-browser-password-21!','Viewer')
        customer=store.save(db,'customer',dict(name='Synthetic V21 customer',contact='',notes=''))
        for i in range(30):
            q=fixture();q.update(title='Synthetic cloud quotation '+str(i),customer_id=customer,number='V21-BROWSER-'+str(i),valid_until='2026-11-18')
            ident=store.save(db,'quote',q)
        db.execute('UPDATE records SET owner_id=?',(admin,))
        db.execute('INSERT INTO record_acl VALUES (?,?,?)',(ident,viewer,'view'))
    server=create_server(app,host='127.0.0.1',port=8042,threads=4)
    threading.Thread(target=server.run,daemon=True).start()
    checks=[]
    try:
        with sync_playwright() as driver:
            browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            context=browser.new_context(viewport=dict(width=1440,height=900),permissions=['clipboard-read','clipboard-write'])
            page=context.new_page();errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
            def login(name):
                page.goto(BASE+'/login');page.get_by_label('Username',exact=True).fill(name);page.get_by_label('Password',exact=True).fill('Synthetic-browser-password-21!');page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(BASE+'/')
            login('browser-admin')
            page.goto(BASE+'/list/quote?q=Synthetic&sort=title&per_page=50')
            expect(page.locator('[data-copy-quote]')).to_have_count(0)
            expect(page.locator('[data-document-id]')).to_have_count(30)
            compact=page.locator('[data-document-id]').first.bounding_box()['height']
            page.screenshot(path=str(ART/'quotations-light.png'),full_page=True)
            page.get_by_label('Table density',exact=True).select_option('comfortable')
            comfortable=page.locator('[data-document-id]').first.bounding_box()['height'];assert comfortable>compact,(compact,comfortable)
            page.get_by_label('Table density',exact=True).select_option('compact')
            checks.append('30 compact quotation rows; comfortable density increases row height')
            page.locator('.column-menu summary').click();page.get_by_label('Show Owner',exact=True).uncheck();page.reload()
            assert not page.locator('th',has_text='Owner').is_visible()
            page.locator('.column-menu summary').click();page.get_by_role('button',name='Reset to default',exact=True).click();assert page.locator('th',has_text='Owner').is_visible();page.locator('.column-menu summary').click()
            checks.append('column persistence and reset')
            page.locator('[data-family-select]').first.check();assert page.locator('#bulk-quotation-form').get_attribute('data-selected')=='true'
            page.locator('.quotation-bulk-menu summary').click()
            dialogs=[]
            def dismiss(dialog):dialogs.append(dialog.type);dialog.dismiss()
            page.on('dialog',dismiss);page.get_by_role('button',name='Archive',exact=True).click();assert dialogs==['confirm'];page.remove_listener('dialog',dismiss)
            page.get_by_role('button',name='Clear',exact=True).click();checks.append('bulk count, clear, destructive confirmation cancel')
            page.locator('.quotation-bulk-menu summary').click()
            page.locator('[data-document-id] a',has_text='Manage').first.click()
            page.get_by_role('button',name='Copy link',exact=True).click();expect(page.get_by_text('Link copied.',exact=True)).to_be_visible()
            checks.append('Manage clipboard copy')
            page.get_by_role('link',name='Quotations',exact=True).last.click();page.wait_for_url('**/list/quote?**');assert 'q=Synthetic' in page.url and 'sort=title' in page.url and 'per_page=50' in page.url
            checks.append('Back retains query, sorting and page size')
            page.goto(BASE+'/documents/'+ident+'/manage');page.get_by_role('button',name='☆ Favorite',exact=True).click();page.wait_for_url('**/v21/shortcuts')
            page.goto(BASE+'/documents/'+ident+'/manage');expect(page.get_by_role('button',name='★ Remove favorite',exact=True)).to_be_visible()
            page.get_by_role('link',name='Internal notes',exact=True).click();page.locator('textarea[name=body]').fill('Synthetic internal browser note');page.get_by_role('button',name='Add internal note',exact=True).click();expect(page.get_by_text('Synthetic internal browser note',exact=True)).to_be_visible();checks.append('favorite state and internal note save')
            page.locator('textarea[name=body]').fill('unsaved draft');dialogs=[];page.on('dialog',dismiss);page.get_by_role('link',name='← Quotation',exact=True).click();assert dialogs==['beforeunload'];page.locator('textarea[name=body]').fill('');page.remove_listener('dialog',dismiss)
            checks.append('unsaved changes guard')
            page.goto(BASE+'/quotes/'+ident+'/pre-send');expect(page.get_by_text('All required approvers approved',exact=False)).to_be_visible();checks.append('pre-send verification')
            page.keyboard.press('Control+k');expect(page.locator('.global-search input')).to_be_focused();page.locator('.global-search input').fill('Synthetic');page.locator('.global-search input').press('Enter');expect(page.locator('.ux-search-result').first).to_be_visible();page.locator('.ux-search-result').first.focus();page.keyboard.press('ArrowDown');expect(page.locator('.ux-search-result').nth(1)).to_be_focused();page.keyboard.press('Escape');expect(page.locator('.global-search input')).to_be_focused();checks.append('grouped search, Ctrl+K, arrows and Escape')
            for width,height in [(1440,900),(1366,768),(1024,768),(768,1024)]:
                page.set_viewport_size(dict(width=width,height=height))
                for theme in ['light','dark']:
                    page.goto(BASE+'/list/quote');page.locator('#portal-theme').select_option(theme);page.wait_for_timeout(150)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'),(width,theme)
                    page.screenshot(path=str(ART/f'quotations-{width}-{theme}.png'),full_page=True)
            checks.append('light/dark at desktop, laptop and tablet widths without page overflow')
            page.set_viewport_size(dict(width=1440,height=900));page.goto(BASE+'/');page.locator('#collapse-sidebar').click();page.reload();expect(page.locator('body')).to_have_class(__import__('re').compile('nav-collapsed'));checks.append('sidebar account persistence')
            page.goto(BASE+'/quotes/'+ident+'/edit');expect(page.locator('#quotation-form')).to_be_attached();expect(page.locator('link[href="/static/ux21.css"]')).to_have_count(0);page.screenshot(path=str(ART/'editor-unchanged.png'),full_page=True);checks.append('editor excludes new styles/scripts')
            assert not errors,errors
            browser.close();(ART/'results.json').write_text(json.dumps(dict(passed=checks,compact_row_px=compact,comfortable_row_px=comfortable,javascript_errors=errors),indent=2));print(json.dumps(checks,indent=2))
    finally:server.close()
