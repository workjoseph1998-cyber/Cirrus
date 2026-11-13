"""Synthetic cross-page visual evidence and premium-shell checks.
Optional --source captures a separate V21.1 checkout for before screenshots.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path);parser.add_argument('--output',type=Path,default=Path('/tmp/cirrus-v21-2-browser'));args=parser.parse_args()
source=(args.source or Path(__file__).resolve().parents[1]).resolve();sys.path[:0]=[str(source),str(source/'tests')]
from workspace_app import create_app,store,security
from quotation_fixture import fixture
from playwright.sync_api import sync_playwright,expect
from waitress import create_server
args.output.mkdir(parents=True,exist_ok=True);base='http://127.0.0.1:8043';checks=[]
with tempfile.TemporaryDirectory() as td:
 root=Path(td)/'data';app=create_app(root,testing=True)
 with store.connect(root) as db:
  admin=security.create_user(db,'admin','Synthetic-premium-password!','Administrator',True)
  viewer=security.create_user(db,'viewer','Synthetic-premium-password!','Viewer')
  customer=store.save(db,'customer',dict(name='Northstar Financial',contact='Operations team',notes='Synthetic design verification account'))
  project=store.save(db,'project',dict(name='Cloud infrastructure refresh',customer_id=customer,customer='Northstar Financial',status='Active',description='Synthetic project for UI verification'))
  for i in range(12):
   q=fixture();q.update(title=f'CIR26-{210+i} · Northstar Cloud Services · V1.0',number=f'CIR26-{210+i}',customer='Northstar Financial',customer_id=customer,valid_until='2026-12-31')
   quote=store.save(db,'quote',q)
  db.execute('UPDATE records SET owner_id=?',(admin,))
  db.execute('INSERT INTO record_acl VALUES (?,?,?)',(quote,viewer,'view'))
 server=create_server(app,host='127.0.0.1',port=8043,threads=4);threading.Thread(target=server.run,daemon=True).start()
 try:
  with sync_playwright() as driver:
   browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
   context=browser.new_context(viewport=dict(width=1366,height=768));page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   def login(name):
    page.goto(base+'/login');page.get_by_label('Username',exact=True).fill(name);page.get_by_label('Password',exact=True).fill('Synthetic-premium-password!');page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(base+'/')
   login('admin')
   routes={'dashboard':'/','quotations':'/list/quote','customers':'/customers','customer':'/customers/'+customer,'customer-documents':'/customers/'+customer+'/documents','projects':'/list/project','project':'/record/'+project,'reports':'/reports','accounts':'/accounts','settings':'/settings','approvals':'/approvals','notifications':'/notifications','manage':'/documents/'+quote+'/manage'}
   for theme in ['light','dark']:
    page.locator('#portal-theme').select_option(theme);page.wait_for_timeout(200)
    for name,route in routes.items():
     response=page.goto(base+route);assert response.status==200,(route,response.status)
     page.wait_for_timeout(180)
     if not args.source:
      expect(page.locator('body.premium-ui')).to_have_count(1)
      assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2'),(name,theme)
      for card in page.locator('.kpi:has(.metric-icon)').all():
       badge=card.locator('.metric-icon').bounding_box();value=card.locator('strong').first.bounding_box()
       assert value['x']>=badge['x']+badge['width'] or value['y']>=badge['y']+badge['height'],(name,'KPI overlap')
     page.screenshot(path=str(args.output/f'{name}-{theme}.png'),full_page=True)
   checks.append('13 real routes captured in light and dark themes')
   if not args.source:
    for width,height in [(1920,1080),(1366,768),(1024,768),(768,1024),(390,844)]:
     page.set_viewport_size(dict(width=width,height=height));page.goto(base+'/list/quote');expect(page.locator('[data-document-id]')).to_have_count(12)
     assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2'),width
     page.screenshot(path=str(args.output/f'quotations-{width}.png'),full_page=True)
    checks.append('1920, 1366, 1024, 768 and 390px layouts without page overflow')
    page.get_by_role('button',name='Open navigation',exact=True).click();expect(page.locator('#mobile-navigation')).to_have_attribute('aria-expanded','true');page.get_by_role('link',name='Reports',exact=True).click();page.wait_for_url('**/reports');assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+2');checks.append('mobile navigation opens and reaches reports')
    page.set_viewport_size(dict(width=1366,height=768));page.goto(base+'/list/quote')
    expect(page.locator('.premium-metric strong').first).to_have_text('12')
    expect(page.locator('.premium-metric strong').nth(1)).to_have_text('0')
    expect(page.locator('.premium-metric strong').nth(3)).to_have_text('0')
    checks.append('metrics reflect synthetic records and account favorites, no demonstration values')
    page.locator('#collapse-sidebar').click();page.reload();assert 'nav-collapsed' in page.locator('body').get_attribute('class');page.locator('.premium-nav-section summary').first.click();assert 'nav-collapsed' not in page.locator('body').get_attribute('class');checks.append('sidebar collapse persists and groups expand from icon mode')
    page.goto(base+'/quotes/'+quote+'/edit');expect(page.locator('body.premium-ui')).to_have_count(0);expect(page.locator('link[href="/static/premium.css"]')).to_have_count(0);expect(page.locator('#quotation-form')).to_have_count(1);checks.append('protected editor excludes premium shell')
    page.goto(base+'/');page.locator('.profile-menu summary').click();page.get_by_role('button',name='Log out',exact=True).click();login('viewer')
    expect(page.locator('.header-tools .floating-menu a[href="/documents/new"]')).to_have_count(0)
    expect(page.locator('.premium-navigation a[href="/accounts"]')).to_have_count(0)
    page.goto(base+'/documents/'+quote+'/manage');expect(page.get_by_role('link',name='Internal notes',exact=True)).to_have_count(0);checks.append('viewer sees neither Quick Create, Administration nor write-only Manage tools')
   assert not errors,errors
   (args.output/'results.json').write_text(json.dumps(dict(passed=checks,javascript_errors=errors),indent=2));print(json.dumps(checks,indent=2));browser.close()
 finally:server.close()
