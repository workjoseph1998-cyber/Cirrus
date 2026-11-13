"""Hosting/library/catalog integration through the actual compact quotation UI."""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import create_app,store,hosting
from quotation_fixture import fixture

from browser_auth import bootstrap,login

ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8000'


def main():
    with tempfile.TemporaryDirectory() as directory:
        td=Path(directory);root=td/'data';create_app(root,True)
        q=fixture();cpu=q['document']['sections'][1]['rows'][0]
        cpu.update(service='Cirrus Compute',sub_service='Control-plane Nodes',type='Iaas',quantity='1',unit_price='124',comments='VM Size: Old size\nVM Specs: old specification\nKeep backup schedule.\nOS: manually entered licensing note')
        with store.connect(root) as db:
            ident=store.save(db,'quote',q)
            vm=next(v for v in hosting.entries(db) if v['data']['name']=='Large V1')
        bootstrap(root)
        log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'JOSEPH_DATA_DIR':str(root)},stdout=log,stderr=log)
        try:
            for _ in range(100):
                try:urllib.request.urlopen(BASE,timeout=1).close();break
                except OSError:time.sleep(.1)
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or None)
                page=browser.new_page(viewport={'width':1800,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('dialog',lambda d:d.accept('HOST-CPU') if d.type=='prompt' else d.accept())
                login(page,BASE)
                page.goto(BASE+'/hosting-vms')
                assert page.locator('.vm-family tbody tr').count()==33
                page.get_by_label('Linux cost for Large V1',exact=True).fill('124')
                page.get_by_label('Microsoft Windows cost for Large V1',exact=True).fill('180')
                page.get_by_label('Pricing status for Large V1',exact=True).select_option('Confirmed')
                page.get_by_role('button',name='Save visible VM prices').click();page.wait_for_url('**/hosting-vms')
                assert page.get_by_label('Linux cost for Large V1',exact=True).input_value()=='124.00'
                print('PASS hosting portal has all 33 sizes and persists separate Linux/Windows prices')
                page.goto(BASE+'/quotes/'+ident+'/edit')
                def ready():page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for()
                ready();preview=page.frame_locator('#customer-preview')
                def row():return preview.locator('tr[data-row="'+cpu['id']+'"]')
                def choose(basis):
                    row().get_by_role('button',name='Choose VM',exact=True).click()
                    dialog=page.get_by_role('dialog',name='Choose a Cirrus Hosting VM')
                    dialog.get_by_label('Operating system',exact=True).select_option(basis)
                    dialog.get_by_role('button',name='Large',exact=True).click()
                    assert dialog.locator('tbody tr').count()==8
                    dialog.get_by_role('button',name='Use Large V1',exact=True).click();ready()
                row().locator('[data-field=quantity]').fill('0');ready()
                choose('a')
                assert row().locator('[data-field=quantity]').input_value()=='0'
                assert '0.00' in row().locator('[data-computed]').inner_text()
                row().locator('[data-field=quantity]').fill('1');ready()
                assert row().locator('[data-field=unit_price]').input_value()=='124.00'
                comments=row().locator('[data-field=comments]').input_value()
                assert 'VM Size: Large V1' in comments and '8 vCPU, 15 GB RAM' in comments and 'OS: Linux' not in comments
                assert 'Keep backup schedule.' in comments and 'Old size' not in comments and 'DEMO' not in comments
                choose('b');assert row().locator('[data-field=unit_price]').input_value()=='180.00'
                assert 'OS: Microsoft Windows' not in row().locator('[data-field=comments]').input_value()
                row().get_by_role('button',name='Choose VM',exact=True).click()
                remembered=page.get_by_role('dialog',name='Choose a Cirrus Hosting VM')
                assert remembered.get_by_label('Operating system',exact=True).input_value()=='b'
                assert remembered.locator('tbody tr').count()==8
                remembered.get_by_role('button',name='Close',exact=True).click()
                row().locator('[data-field=unit_price]').fill('175');ready()
                assert '175.00' in row().locator('[data-computed]').inner_text()
                assert row().bounding_box()['height']<85, row().bounding_box()
                print('PASS family picker, Linux/Windows selection, VM comments, retained notes, exception price and compact rows')
                row().get_by_role('button',name='Options',exact=True).click()
                left=page.locator('details[data-row="'+cpu['id']+'"]')
                left.get_by_role('button',name='Save as catalog item',exact=True).click();ready()
                section=q['document']['sections'][1]
                block=page.locator('[data-section-id="'+section['id']+'"]')
                picker=block.get_by_label('Catalog for Compute and storage',exact=True)
                picker.select_option(picker.locator('option').filter(has_text='HOST-CPU — Cirrus Compute').get_attribute('value'))
                old_count=preview.locator('tr[data-row]').count()
                block.locator(':scope > .toolbar').get_by_role('button',name='Copy catalog row',exact=True).click()
                from playwright.sync_api import expect
                expect(preview.locator('tr[data-row]')).to_have_count(old_count+1);ready()
                copied_id=page.locator('#customer-preview').evaluate('(frame)=>frame.contentDocument.activeElement.dataset.row')
                assert copied_id and copied_id!=cpu['id']
                copied=preview.locator('tr[data-row="'+copied_id+'"]')
                assert copied.locator('[data-field=type]').input_value()=='Iaas'
                assert copied.locator('[data-field=comments]').input_value()==row().locator('[data-field=comments]').input_value()
                assert copied.locator('[data-field=unit_price]').input_value()=='175'
                assert copied.locator('[data-field=sub_service]').input_value()=='Control-plane Nodes'
                print('PASS catalog save/copy retains Type, full VM Comments, Sub Service and exception price without reload')
                page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/quotes/*/edit');ready()
                with store.connect(root) as db:
                    machine=next(v for v in hosting.entries(db) if v['id']==vm['id']);machine['data']['cost_b']='220.00';hosting.save(db,machine['data'],vm['id'])
                row().get_by_role('button',name='Choose VM',exact=True).click()
                current_prices=page.get_by_role('dialog',name='Choose a Cirrus Hosting VM')
                current_prices.get_by_label('Operating system',exact=True).select_option('b')
                assert '220.00' in current_prices.locator('tbody tr').filter(has=page.get_by_role('button',name='Use Large V1',exact=True)).inner_text()
                current_prices.get_by_role('button',name='Close',exact=True).click()
                assert row().locator('[data-field=unit_price]').input_value()=='175'
                page.reload();ready()
                assert row().locator('[data-field=unit_price]').input_value()=='175'
                assert preview.locator('tr[data-row="'+copied_id+'"] [data-field=type]').input_value()=='Iaas'
                screenshot=os.environ.get('HOSTING_SCREENSHOT')
                if screenshot:page.screenshot(path=screenshot,full_page=True)
                page.goto(BASE+'/quotes/'+ident+'/print')
                text=page.locator('body').inner_text()
                assert 'OS: manually entered licensing note' in text and 'OS: Microsoft Windows' not in text and '8 vCPU, 15 GB RAM' in text and '175.00' in text
                assert page.locator('input,textarea,[data-action]').count()==0
                print('PASS save/reopen, VM master-price changes do not overwrite quote snapshots, and clean customer output')
                assert not errors,errors;browser.close()
        finally:
            server.terminate();server.wait(timeout=10);log.close()


if __name__=='__main__':main()
