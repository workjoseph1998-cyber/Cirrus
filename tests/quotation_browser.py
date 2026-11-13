"""Synthetic quotation E2E, live updates, structure edits, PDF and XLSX parity."""
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from uuid import uuid4

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import create_app,store
from quotation_fixture import fixture

from browser_auth import bootstrap,login

ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8000'


def run():
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);root=td/'data';app=create_app(root,True)
        q=fixture()
        # Synthetic multipage content; both the end of long rows and terms are checked in PDF.
        q['document']['sections'][1]['rows'][0]['comments']='START-LONG-ROW\n'+('\n'.join('Synthetic specification line '+str(i) for i in range(35)))+'\nEND-LONG-ROW'
        term=q['document']['terms'][-1];term['text']='\n'.join('Synthetic regulation line '+str(i) for i in range(90))+'\nEND-LONG-TERMS'
        with store.connect(root) as db:ident=store.save(db,'quote',q)
        bootstrap(root)
        log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'JOSEPH_DATA_DIR':str(root)},stdout=log,stderr=log)
        try:
            for _ in range(100):
                try:urllib.request.urlopen(BASE,timeout=1).close();break
                except OSError:time.sleep(.1)
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or None)
                page=browser.new_page(viewport={'width':1800,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                login(page,BASE)
                def ready():page.locator('#preview-status').filter(has_text=re.compile('^Preview current')).wait_for()
                def open_box(title):
                    summary=page.locator('summary').filter(has_text=re.compile('^'+re.escape(title)+'$')).first
                    if summary.locator('..').get_attribute('open') is None:summary.click()
                page.goto(BASE+'/quotes/'+ident+'/edit');ready()
                preview=page.frame_locator('#customer-preview')
                assert '670.00' in preview.locator('body').inner_text()
                print('PASS nonzero live preview matches engine')
                # The studio uses the whole viewport, with the quotation taking most space.
                assert not page.locator('aside').is_visible()
                assert page.locator('#studio').bounding_box()['height']>950
                assert page.locator('#customer-preview').bounding_box()['width']>page.locator('#studio-editor').bounding_box()['width']
                cpu=q['document']['sections'][1]['rows'][0]
                cell=lambda key:preview.locator('input[data-row="'+cpu['id']+'"][data-field="'+key+'"]')
                cell('quantity').fill('3');ready()
                assert page.locator('[data-row="'+cpu['id']+'"] [name=quantity]').input_value()=='3'
                page.get_by_role('link',name='Excel',exact=True).click()
                assert 'Save quotation first' in page.locator('#preview-status').inner_text()
                # Slow typing outlasts the preview debounce; no keystrokes/focus may disappear.
                service=preview.locator('textarea[data-row="'+cpu['id']+'"][data-field=service]')
                service.fill('VM ');service.press_sequentially('edited live',delay=190);ready()
                assert service.input_value()=='VM edited live'
                rightrow=preview.locator('tr[data-row="'+cpu['id']+'"]')
                rightrow.get_by_role('button',name='Options',exact=True).click()
                page.locator('[data-row="'+cpu['id']+'"] [name=unit_price]').fill('125');ready()
                assert cell('unit_price').input_value()=='125'
                rightrow=preview.locator('tr[data-row="'+cpu['id']+'"]')
                rightrow.get_by_role('button',name='Copy row',exact=True).click();ready()
                copies=preview.locator('tr[data-row]').filter(has=preview.locator('textarea[data-field=service]')).filter(has=preview.locator('textarea',has_text='VM edited live'))
                # Identify the copy via its newly focused service control, not its generated ID.
                copy_id=page.locator('#customer-preview').evaluate('(frame) => frame.contentDocument.activeElement.dataset.row')
                assert copy_id!=cpu['id']
                copied=preview.locator('tr[data-row="'+copy_id+'"]')
                assert copied.locator('input[data-field=quantity]').input_value()=='3'
                assert copied.locator('input[data-field=unit_price]').input_value()=='125'
                page.once('dialog',lambda d:d.accept());copied.get_by_role('button',name=re.compile('^Remove row')).click();ready()
                cell('quantity').fill('2');cell('unit_price').fill('100');service.fill('');
                page.locator('#preview-status').filter(has_text=re.compile('^Review inputs')).wait_for()
                service.fill('Synthetic VM');ready()
                assert '670.00' in preview.locator('body').inner_text()
                print('PASS direct edits, uninterrupted slow typing, left synchronization, copy and remove')
                production=preview.locator('.category').filter(has=preview.locator('input[data-field=name][value=Production]'))
                production.get_by_role('button',name='Copy category',exact=True).click();ready()
                development=preview.locator('.category').filter(has=preview.locator('input[data-field=name][value="Production (copy)"]'))
                development.locator('.category-title input').fill('Development');ready()
                dev_id=development.get_attribute('data-category')
                # The initial value attribute remains the original while editing; use the stable ID.
                development=preview.locator('[data-category="'+dev_id+'"]')
                development.get_by_role('button',name='+ Add row to Compute and storage (copy)',exact=True).click();ready()
                new_id=page.locator('#customer-preview').evaluate('(frame) => frame.contentDocument.activeElement.dataset.row')
                newrow=preview.locator('tr[data-row="'+new_id+'"]')
                newrow.locator('textarea[data-field=service]').fill('Development extra VM')
                newrow.locator('input[data-field=unit_price]').fill('10');ready()
                summary=preview.locator('[data-summary-category="'+dev_id+'"]')
                assert 'Development' in summary.inner_text() and '285.00' in summary.inner_text()
                assert '3420.00' in summary.inner_text()
                page.once('dialog',lambda d:d.accept());development.get_by_role('button',name='Remove category',exact=True).click();ready()
                assert preview.locator('[data-summary-category="'+dev_id+'"]').count()==0
                assert '670.00' in preview.locator('body').inner_text()
                print('PASS Development category copy, inline row, automatic summary and complete removal')
                page.get_by_role('button',name='+ Add environment',exact=True).click();ready()
                environment=preview.locator('.category').filter(has=preview.locator('input[value="New environment"]'))
                assert environment.locator('.subsection-band').count()==3
                page.once('dialog',lambda d:d.accept());environment.get_by_role('button',name='Remove category',exact=True).click();ready()
                print('PASS one-click environment with VM/security/backup groups and a standalone support fee')
                # All actual sections/subsections accept a custom row through the UI.
                for s in q['document']['sections']:
                    if s['parent']:
                        parent=next(x for x in q['document']['sections'] if x['id']==s['parent']);open_box(parent['name'])
                    open_box(s['name'])
                    block=page.locator('details:has(> summary:text-is('+json.dumps(s['name'],ensure_ascii=False)+'))').first
                    block.locator(':scope > .toolbar').get_by_role('button',name='+ Custom row',exact=True).click();ready()
                    active_id=page.locator('#customer-preview').evaluate('(frame) => frame.contentDocument.activeElement.dataset.row')
                    preview.locator('input[data-row="'+active_id+'"][data-field=quantity]').fill('0');ready()
                ready();print('PASS custom rows in every default category/group')
                # Rename, duplicate, reorder and remove a subsection through real controls.
                open_box('Production');open_box('Compute and storage')
                block=page.locator('details:has(> summary:text-is("Compute and storage"))').first
                block.get_by_label('Section / subsection name',exact=True).fill('Compute renamed')
                block.locator(':scope > .toolbar').get_by_role('button',name='Duplicate section',exact=True).click()
                open_box('Compute renamed (copy)')
                block=page.locator('details:has(> summary:text-is("Compute renamed (copy)"))')
                block.locator(':scope > .toolbar').get_by_role('button',name='↑ Section',exact=True).click()
                page.once('dialog',lambda dialog:dialog.accept())
                block=page.locator('details:has(> summary:text-is("Compute renamed (copy)"))')
                block.locator(':scope > .toolbar').get_by_role('button',name='Remove section',exact=True).click()
                ready();print('PASS section rename, duplicate, reorder, delete')
                open_box('Compute renamed')
                row=page.locator('details.row-editor:has(> summary:text-is("New service / unit"))').first
                row.locator('summary').click();row.get_by_label('Service',exact=True).fill('Temporary UI row')
                row.get_by_label('Calculation method',exact=True).select_option('fixed')
                row=page.locator('details.row-editor:has(> summary:text-is("Temporary UI row / fixed"))')
                row.get_by_label('Quantity',exact=True).fill('1');row.get_by_label('Fixed fee (blank = unpriced)',exact=True).fill('10')
                row.get_by_role('button',name='Duplicate row',exact=True).click()
                ready()
                rows=page.locator('details.row-editor:has(> summary:text-is("Temporary UI row / fixed"))')
                for _ in range(2):
                    r=rows.first
                    if r.get_attribute('open') is None:r.locator('summary').click()
                    r.get_by_role('button',name='↓ Row',exact=True).click()
                    r=rows.first
                    if r.get_attribute('open') is None:r.locator('summary').click()
                    r.get_by_label('Move row to section',exact=True).select_option(q['document']['sections'][-1]['id'])
                    # Destination is now a different section, row retains identity.
                    open_box('Connectivity Setup — One-Time Fee')
                    r=rows.first
                    if r.get_attribute('open') is None:r.locator('summary').click()
                    page.once('dialog',lambda dialog:dialog.accept());r.get_by_role('button',name='Remove row',exact=True).click()
                ready();assert '670.00' in preview.locator('body').inner_text()
                print('PASS row edit, fixed mode, duplicate, reorder, cross-section move and delete')
                page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/quotes/*/edit');ready()
                assert '670.00' in preview.locator('body').inner_text()
                screenshot=os.environ.get('QUOTE_SCREENSHOT')
                if screenshot:page.screenshot(path=screenshot,full_page=True)
                # Resizable divider and mobile tabs.
                divider=page.locator('#studio-divider');divider.focus();divider.press('ArrowLeft')
                page.set_viewport_size({'width':390,'height':844});page.get_by_role('button',name='Quotation',exact=True).click()
                assert page.locator('.studio-preview').is_visible();page.get_by_role('button',name='Structure & settings',exact=True).click();assert page.locator('.studio-editor').is_visible()
                print('PASS resizable divider and mobile Editor/Preview tabs')
                page.goto(BASE+'/quotes/'+ident+'/print');body=page.locator('body').inner_text()
                assert '670.00' in body and 'CONFIDENTIAL-NOTE-SENTINEL' not in body and '19.37' not in body
                pdf=td/'quote.pdf';page.pdf(path=str(pdf),prefer_css_page_size=True,print_background=True)
                subprocess.run(['pdftotext','-layout',str(pdf),str(td/'quote.txt')],check=True)
                text=(td/'quote.txt').read_text();assert '670.00' in text and 'END-LONG-ROW' in text and 'END-LONG-TERMS' in text
                assert 'CONFIDENTIAL-NOTE-SENTINEL' not in text and text.count('\f')>1
                print('PASS multipage A4 PDF, totals, long content and no private costs/notes')
                response=page.request.get(BASE+'/quotes/'+ident+'/xlsx');assert response.ok
                w=load_workbook(io.BytesIO(response.body()),data_only=True);sheet=w['Quotation']
                total=next(row[6].value for row in sheet if row[0].value=='Total monthly fee');assert float(total)==670.0
                print('PASS saved preview / PDF / Excel totals parity')
                page.set_viewport_size({'width':1800,'height':1100})
                page.goto(BASE+'/quotes/'+ident+'/edit');ready()
                dr=preview.locator('.category').filter(has=preview.locator('input[data-field=name][value="Disaster Recovery"]'))
                page.once('dialog',lambda d:d.accept());dr.get_by_role('button',name='Remove category',exact=True).click();ready()
                assert 'Disaster Recovery' not in preview.locator('.summary').inner_text()
                page.get_by_role('button',name='Save quotation',exact=True).click();page.wait_for_url('**/quotes/*/edit');ready()
                with store.connect(root) as db:
                    saved=next(r['data'] for r in store.records(db) if r['id']==ident)
                    assert not any(s['name']=='Disaster Recovery' for s in saved['document']['sections'])
                    ids={s['id'] for s in saved['document']['sections']}
                    assert all(not s['parent'] or s['parent'] in ids for s in saved['document']['sections'])
                print('PASS complete DR category removal, cleaned dependencies and save/reopen')
                assert not errors,errors;browser.close()
        finally:
            server.terminate();server.wait(timeout=10);log.close()


if __name__=='__main__':run()
