"""Verify the agreed V21 tools against a copied synthetic V20 live workspace."""
import json
import os
from pathlib import Path
import sys
import threading
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
from test_v21_live_copy import LiveCopy21, PASSWORD
from workspace_app import create_app
from playwright.sync_api import sync_playwright, expect
from waitress import create_server
ART=Path(os.environ.get('CW_BROWSER_ARTIFACTS','/tmp/cirrus-v21-live-browser'));ART.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:8042'
fixture=LiveCopy21('test_live_copy_retains_login_records_configuration_and_files');fixture.setUp()
try:
    root=fixture.copy()
    with patch('workspace_app.automation.start'):app=create_app(root)
    server=create_server(app,host='127.0.0.1',port=8042,threads=4)
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        with sync_playwright() as driver:
            browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            context=browser.new_context(viewport=dict(width=1440,height=1000),permissions=['clipboard-read','clipboard-write'])
            page=context.new_page();errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
            page.goto(BASE+'/login');page.get_by_label('Username',exact=True).fill('original-admin');page.get_by_label('Password',exact=True).fill(PASSWORD);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(BASE+'/')
            expect(page.locator('.nav-footer')).to_contain_text('Version 21 · Live')
            expect(page.get_by_text('Needs Your Attention',exact=True)).to_be_visible()
            page.screenshot(path=str(ART/'live-dashboard.png'),full_page=True)
            page.goto(BASE+'/v21/whats-new');expect(page.get_by_role('heading',name='What’s new in Version 21',exact=True)).to_be_visible();page.screenshot(path=str(ART/'whats-new.png'),full_page=True)
            result=page.request.get(BASE+'/v21/version').json();assert result['mode']=='live' and len(result['features'])==11
            page.goto(BASE+'/list/quote');expect(page.get_by_role('link',name='Synthetic cloud quotation',exact=True)).to_be_visible()
            page.get_by_role('button',name='Copy link',exact=True).click();expect(page.get_by_text('Link copied.',exact=True)).to_be_visible()
            page.get_by_role('button',name='☆ Favorite',exact=True).click();page.wait_for_url(BASE+'/v21/shortcuts')
            page.goto(BASE+'/quotes/'+fixture.quote+'/edit');page.get_by_role('button',name='Controls',exact=True).click()
            page.locator('.more-actions summary').click();expect(page.get_by_role('link',name='Internal notes',exact=True)).to_be_visible();expect(page.get_by_role('link',name='Pre-send check',exact=True)).to_be_visible()
            page.get_by_role('link',name='Internal notes',exact=True).click();page.locator('textarea[name=body]').fill('V21 copied live workspace internal note');page.get_by_role('button',name='Add internal note',exact=True).click();expect(page.get_by_text('V21 copied live workspace internal note',exact=True)).to_be_visible()
            page.goto(BASE+'/quotes/'+fixture.quote+'/approval');expect(page.get_by_role('button',name='Remind Pending Approvers',exact=True)).to_be_visible();assert 'Test email delivery is disabled.' not in page.locator('body').inner_text()
            page.goto(BASE+'/quotes/'+fixture.quote+'/pre-send');expect(page.get_by_role('heading',name='Pre-send verification',exact=True)).to_be_visible()
            page.goto(BASE+'/customers/'+fixture.customer);page.get_by_role('link',name='Activity timeline',exact=True).click();expect(page.get_by_role('heading',name='Existing customer · Activity',exact=True)).to_be_visible()
            page.locator('#portal-theme').select_option('dark');page.set_viewport_size(dict(width=390,height=844));page.goto(BASE+'/v21/whats-new');page.screenshot(path=str(ART/'live-mobile-dark.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2')
            assert not errors,errors
            browser.close()
        assert fixture.fingerprints()==fixture.original,'V20 fallback files changed'
        (ART/'results.json').write_text(json.dumps(dict(passed=['existing V20 login','live version identity','feature manifest','copied quotations','dashboard attention','visible feature guide','copy link','favorite','editor feature links','internal notes','reminder button and live messaging','pre-send panel','customer timeline','mobile dark mode','V20 source files unchanged'],javascript_errors=errors),indent=2))
        print('Live-copy browser checks passed: '+str(ART))
    finally:server.close()
finally:fixture.tearDown()
