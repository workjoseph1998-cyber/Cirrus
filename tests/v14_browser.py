"""Synthetic V14 UI checks: support checkboxes, saved headings/money and deletion."""
import json,os,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store,security
from test_v14 import support_quote
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8014';PASSWORD='V14-browser-test-only-password!'
SCREEN=Path('/workspace/preservation');SCREEN.mkdir(exist_ok=True)


def run():
 with tempfile.TemporaryDirectory() as temporary:
  td=Path(temporary);data=td/'data';store.migrate(data);q=support_quote();d=q['document'];support=d['sections'][-1];fee=support['rows'][0];production=d['sections'][0];hosting=production['rows'][0]
  with store.connect(data) as db:
   admin_id=security.create_user(db,'admin',PASSWORD,'Administrator',True);retiring=security.create_user(db,'retiring-staff',PASSWORD,'Editor');ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=? WHERE id=?',(admin_id,ident))
  log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(data),'CIRRUS_PORT':'8014','CIRRUS_DISABLE_EMAIL':'1'},stdout=log,stderr=log)
  try:
   for _ in range(100):
    if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
    try:urllib.request.urlopen(BASE).close();break
    except OSError:time.sleep(.1)
   with sync_playwright() as driver:
    browser=driver.chromium.launch(executable_path='/usr/bin/chromium');errors=[]
    def login(name):
     page=browser.new_context(viewport={'width':1550,'height':1050}).new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE+'/login');page.get_by_label('Username',exact=True).fill(name);page.get_by_label('Password',exact=True).fill(PASSWORD);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(BASE+'/');return page
    admin=login('admin');url=BASE+'/quotes/'+ident
    def current():expect(admin.locator('#preview-status')).to_contain_text('Preview current')
    def support_controls():
     block=admin.locator('details[data-section-id="'+support['id']+'"]');block.locator(':scope > summary').click();row=block.locator('details[data-row="'+fee['id']+'"]');row.locator(':scope > summary').click();return row
    def open_group(row,name):row.locator('.support-base-group').filter(has=admin.locator('summary',has_text=name)).first.locator(':scope > summary').click()
    admin.goto(url+'/edit');current();row=support_controls();feedback=row.locator('[data-fee-feedback]');expect(feedback).to_contain_text('Selected base: $1,000.00');expect(feedback).to_contain_text('Fee: $50.00')
    open_group(row,'Connectivity');row.get_by_label('Section: Connectivity',exact=True).check();current();expect(feedback).to_contain_text('Selected base: $1,100.00');expect(feedback).to_contain_text('Fee: $55.00')
    open_group(row,'Production');row.get_by_label('Section: Production',exact=True).uncheck();current();expect(feedback).to_contain_text('Selected base: $100.00');expect(feedback).to_contain_text('Fee: $5.00');row.get_by_label('Section: Production',exact=True).check();row.get_by_label('Service: Production / Hosting',exact=True).check();current();expect(feedback).to_contain_text('Fee: $55.00')
    row.get_by_label('Support / fee percentage %',exact=True).fill('10');current();expect(feedback).to_contain_text('Fee: $110.00');row.get_by_label('Support / fee percentage %',exact=True).fill('5');current()
    frame=admin.frame_locator('#customer-preview');quantity=frame.locator('[data-row="'+hosting['id']+'"][data-field="quantity"]');quantity.fill('3');current();expect(feedback).to_contain_text('Selected base: $1,600.00');expect(feedback).to_contain_text('Fee: $80.00');quantity.fill('2');current();expect(feedback).to_contain_text('Fee: $55.00')
    formatting=admin.locator('#editor-controls > details').filter(has=admin.locator('summary',has_text='Formatting, columns & summary')).first;formatting.locator(':scope > summary').click();headings=formatting.locator('details').filter(has=admin.locator('summary',has_text='Fee column headings')).first;headings.locator(':scope > summary').click();headings.get_by_label('Monthly Fee heading',exact=True).fill('Monthly charge');headings.get_by_label('One-Time Fee heading',exact=True).fill('Setup charge');current()
    columns=formatting.locator('details').filter(has=admin.locator('summary',has_text='Customer table columns')).first;columns.locator(':scope > summary').click();columns.get_by_label('unit_price label',exact=True).fill('Price per service');current()
    expect(frame.locator('thead').filter(has_text='Monthly charge').first).to_contain_text('Price per service');expect(frame.locator('thead').filter(has_text='Setup charge').first).to_be_visible()
    amount=frame.locator('[data-computed="row-'+hosting['id']+'"]');expect(amount).to_contain_text('$1,000.00');unit=frame.locator('[data-row="'+hosting['id']+'"] .currency-input').first;expect(unit).to_contain_text('$')
    total=frame.locator('.summary-regular');expect(total).to_contain_text('$1,355.00')
    for selector in ['th','td']:
     assert total.locator(selector).evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(192, 0, 0)';assert total.locator(selector).evaluate('(e)=>getComputedStyle(e).color')=='rgb(255, 255, 255)';assert total.locator(selector).evaluate('(e)=>getComputedStyle(e).fontWeight')=='700'
    admin.screenshot(path=str(SCREEN/'v14-editor-light.png'),full_page=True,animations='disabled');admin.get_by_role('button',name='Save quotation',exact=True).click();admin.wait_for_url(url+'/edit');current();row=support_controls();expect(row.get_by_label('Support / fee percentage %',exact=True)).to_have_value('5');expect(row.locator('[data-fee-feedback]')).to_contain_text('Selected base: $1,100.00');expect(row.locator('[data-fee-feedback]')).to_contain_text('Fee: $55.00')
    admin.get_by_label('Portal theme',exact=True).select_option('dark');admin.screenshot(path=str(SCREEN/'v14-editor-dark.png'),full_page=True,animations='disabled')
    customer=admin.context.new_page();customer.goto(url+'/print');expect(customer.get_by_role('columnheader',name='Price per service',exact=True).first).to_be_visible();expect(customer.get_by_role('columnheader',name='Monthly charge',exact=True).first).to_be_visible();expect(customer.get_by_role('columnheader',name='Setup charge',exact=True).first).to_be_visible();assert 'support-calculations' not in customer.content();assert 'catalog:hosting' not in customer.content();assert customer.locator('article').evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(255, 255, 255)'
    customer.screenshot(path=str(SCREEN/'v14-customer-print.png'),full_page=True,animations='disabled');pdf=customer.pdf(print_background=True,prefer_css_page_size=True);assert pdf.startswith(b'%PDF-');(SCREEN/'v14-customer-output.pdf').write_bytes(pdf)
    # Approval history and comments remain readable after a staff account is deleted.
    admin.goto(url+'/approval');selector=admin.locator('.review-submit form').first;selector.get_by_role('button',name='+ Add approver',exact=True).click();selector.get_by_label('Approver 1',exact=True).select_option(retiring);selector.get_by_role('button',name='Submit for approval',exact=True).click()
    staff=login('retiring-staff');staff.goto(url+'/approval');staff.get_by_label('Review comment',exact=True).fill('Validated the selected services.');staff.get_by_role('button',name='✓ Approve this version',exact=True).click();staff.get_by_label('Message',exact=True).fill('Preserve this author attribution.');staff.get_by_role('button',name='Post message',exact=True).click();expect(staff.locator('#discussion-feedback')).to_contain_text('Message posted')
    admin.goto(BASE+'/accounts');account=admin.locator('.account-row').filter(has_text='retiring-staff');account.locator(':scope > summary').click();account.get_by_role('link',name='Delete account',exact=True).click();expect(admin.get_by_role('heading',name='Delete account',exact=True)).to_be_visible();expect(admin.locator('.page')).to_contain_text('retiring-staff');admin.screenshot(path=str(SCREEN/'v14-delete-account-dark.png'),full_page=True,animations='disabled');admin.get_by_role('checkbox',name='I confirm deletion of retiring-staff.',exact=True).check();admin.get_by_role('button',name='Delete account retiring-staff',exact=True).click();admin.wait_for_url(BASE+'/accounts');expect(admin.locator('.account-row').filter(has_text='retiring-staff')).to_have_count(0)
    staff.goto(url+'/approval');staff.wait_for_url(BASE+'/login');admin.goto(url+'/approval');expect(admin.locator('#reviewer-grid')).to_contain_text('retiring-staff');expect(admin.locator('#reviewer-grid')).to_contain_text('Validated the selected services.');expect(admin.locator('#discussion-timeline')).to_contain_text('Preserve this author attribution.')
    admin.goto(BASE+'/accounts/'+admin_id+'/delete');expect(admin.locator('.error')).to_contain_text('currently signed-in');expect(admin.get_by_role('button',name='Delete account admin',exact=True)).to_have_count(0)
    admin.set_viewport_size({'width':390,'height':850});admin.screenshot(path=str(SCREEN/'v14-delete-account-mobile.png'),full_page=True,animations='disabled');admin.goto(url+'/edit');current();row=support_controls();open_group(row,'Production');assert admin.evaluate('document.documentElement.scrollWidth<=innerWidth+3');admin.screenshot(path=str(SCREEN/'v14-support-mobile.png'),full_page=True,animations='disabled');assert not errors,errors;browser.close()
    print('PASS: support one/multiple/overlapping checkbox selections, percentage/inline quantity recalculation, save/reopen, custom headings, dollars, entire red/white total, real customer PDF, account confirmation/deletion with retained author/approval history, light/dark and mobile. No emails sent.')
  except Exception:
   print((td/'server.log').read_text()[-7000:]);raise
  finally:server.terminate();server.wait(timeout=20);log.close()

if __name__=='__main__':run()
