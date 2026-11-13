"""Login-only acceptance: real Waitress/Chromium; temporary synthetic accounts.
No SMTP, customer records or deployment changes. Requires existing Playwright.
"""
import json,os,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store,security
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8031';PASSWORD='Synthetic-login-redesign-password!'
OUT=Path(os.environ.get('CW_LOGIN_ARTIFACTS','/workspace/login-redesign-artifacts'));OUT.mkdir(parents=True,exist_ok=True)


def run():
 with tempfile.TemporaryDirectory() as temporary:
  td=Path(temporary);data=td/'data';store.migrate(data)
  with store.connect(data) as db:
   security.create_user(db,'review-user',PASSWORD,'Administrator',True)
   disabled=security.create_user(db,'disabled-user',PASSWORD,'Editor');db.execute('UPDATE users SET active=0 WHERE id=?',(disabled,))
  log=(td/'server.log').open('w');server=subprocess.Popen([sys.executable,'run.py'],cwd=ROOT,env={**os.environ,'CIRRUS_DATA_DIR':str(data),'CIRRUS_PORT':'8031','CIRRUS_DISABLE_EMAIL':'1'},stdout=log,stderr=log)
  errors=[];requests=[];pages=[];results={}
  try:
   for _ in range(100):
    if server.poll() is not None:raise RuntimeError((td/'server.log').read_text())
    try:urllib.request.urlopen(BASE+'/login').close();break
    except OSError:time.sleep(.1)
   with sync_playwright() as driver:
    browser=driver.chromium.launch(executable_path='/usr/bin/chromium')
    def new_page(**options):
     context=browser.new_context(**options);page=context.new_page();page.set_default_timeout(10000);pages.append(page)
     page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text+' '+str(m.location)) if m.type=='error' and not (m.location.get('url','').endswith('/favicon.ico') and not page.url.startswith(BASE+'/login')) and '400 (BAD REQUEST)' not in m.text and '400 (Bad Request)' not in m.text else None)
     page.on('request',lambda r:requests.append(r.url));page.on('response',lambda r:errors.append('404: '+r.url) if r.status==404 else None);page.add_init_script("window.__loginDraws=0;const clearCanvas=CanvasRenderingContext2D.prototype.clearRect;CanvasRenderingContext2D.prototype.clearRect=function(...args){window.__loginDraws++;return clearCanvas.apply(this,args);};window.__loginFrames=0;const originalRAF=window.requestAnimationFrame;window.requestAnimationFrame=(fn)=>originalRAF.call(window,t=>{window.__loginFrames++;fn(t);});")
     return page
    page=new_page(viewport=dict(width=1536,height=960));response=page.goto(BASE+'/login');assert response.status==200;assert "style-src 'self'" in response.headers['content-security-policy'] and 'unsafe-inline' not in response.headers['content-security-policy']
    expect(page.get_by_role('heading',name='Welcome to Cirrus Workplace',exact=True)).to_be_visible();expect(page.get_by_text('Your workspace, connected.',exact=True)).to_be_visible();assert 'Version 10' not in page.content();assert page.locator('link[rel=stylesheet]').count()==1;assert page.locator('link[rel=stylesheet]').get_attribute('href')=='/static/login.css'
    expect(page.get_by_label('Username',exact=True)).to_have_attribute('autocomplete','username');expect(page.get_by_label('Password',exact=True)).to_have_attribute('autocomplete','current-password')
    page.mouse.move(180,300);page.wait_for_timeout(500);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert page.locator('.login-cloud-plane-near').evaluate('e=>getComputedStyle(e).transform')!='matrix(1, 0, 0, 1, 0, 0)'
    page.screenshot(path=str(OUT/'Cirrus-Workplace-Login-Desktop.png'),full_page=True)
    # Camera-independent frame counts bound the animation work; interaction does not submit.
    draws=page.evaluate('window.__loginDraws');frames=page.evaluate('window.__loginFrames');session=page.context.new_cdp_session(page);session.send('Performance.enable');before={x['name']:x['value'] for x in session.send('Performance.getMetrics')['metrics']};page.wait_for_timeout(1000);after={x['name']:x['value'] for x in session.send('Performance.getMetrics')['metrics']};results['desktop_canvas_draws_in_one_second']=page.evaluate('window.__loginDraws')-draws;results['desktop_animation_callbacks_in_one_second']=page.evaluate('window.__loginFrames')-frames;results['desktop_main_thread_ms_in_one_second']=round((after['TaskDuration']-before['TaskDuration'])*1000,1);assert results['desktop_canvas_draws_in_one_second']<=31
    page.get_by_label('Username',exact=True).fill('review-user');page.get_by_label('Password',exact=True).fill('Wrong-password')
    page.get_by_label('Username',exact=True).focus();page.keyboard.press('Tab');expect(page.get_by_label('Password',exact=True)).to_be_focused();page.keyboard.press('Tab');toggle=page.get_by_role('button',name='Show password',exact=True);expect(toggle).to_be_focused();page.keyboard.press('Space');expect(page.get_by_label('Password',exact=True)).to_have_attribute('type','text');expect(page.get_by_role('button',name='Hide password',exact=True)).to_have_attribute('aria-pressed','true');page.keyboard.press('Space');expect(page.get_by_label('Password',exact=True)).to_have_attribute('type','password')
    # Intercept the native default at document bubbling, after the production
    # form listener. This lets us inspect busy state without a pending navigation.
    page.evaluate("window.__acceptedSubmits=0;document.addEventListener('submit',e=>{if(!e.defaultPrevented){window.__acceptedSubmits++;window.__submittedFields=[...new FormData(e.target).keys()];}e.preventDefault();});")
    page.get_by_role('button',name='Sign in',exact=True).click()
    expect(page.get_by_role('button',name='Signing in…',exact=True)).to_be_disabled();expect(page.locator('#login-form')).to_have_attribute('aria-busy','true');page.locator('#login-form').evaluate('(form)=>form.requestSubmit()');assert page.evaluate('window.__acceptedSubmits')==1;assert page.evaluate('window.__submittedFields')==['csrf','username','password']
    page.reload();page.get_by_label('Username',exact=True).fill('review-user');page.get_by_label('Password',exact=True).fill('Wrong-password')
    with page.expect_navigation(wait_until='load') as failed:page.get_by_role('button',name='Sign in',exact=True).click()
    assert failed.value.status==400;expect(page.get_by_role('alert')).to_contain_text('Invalid username/password or disabled account.');expect(page.get_by_label('Username',exact=True)).to_have_value('review-user');expect(page.get_by_label('Password',exact=True)).to_have_value('');expect(page.get_by_role('button',name='Sign in',exact=True)).to_be_enabled();assert page.locator('#login-error').evaluate('e=>document.activeElement===e');page.screenshot(path=str(OUT/'Cirrus-Workplace-Login-Error.png'),full_page=True)
    page.get_by_label('Password',exact=True).fill(PASSWORD);page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(BASE+'/');expect(page.get_by_role('heading',name='Your working day',exact=True)).to_be_visible();assert page.locator('script[src="/static/login.js"]').count()==0 and page.locator('link[href="/static/login.css"]').count()==0
    # Protected redirect and CSRF stay on the existing server path.
    anonymous=new_page(viewport=dict(width=1366,height=768));anonymous.goto(BASE+'/accounts');anonymous.wait_for_url(BASE+'/login');assert anonymous.request.post(BASE+'/login',form=dict(username='review-user',password=PASSWORD)).status==400
    token=anonymous.locator('input[name=csrf]').get_attribute('value');assert anonymous.request.post(BASE+'/login',form=dict(csrf=token,username='disabled-user',password=PASSWORD)).status==400
    anonymous.screenshot(path=str(OUT/'Cirrus-Workplace-Login-Laptop.png'),full_page=True)
    # Reduced motion has static clouds/canvas and no animation-frame loop.
    reduced=new_page(viewport=dict(width=1366,height=850),reduced_motion='reduce');reduced.goto(BASE+'/login');reduced.wait_for_timeout(250);assert reduced.evaluate('window.__loginFrames')==0;assert reduced.locator('.login-cloud-plane img').first.evaluate('e=>getComputedStyle(e).animationName')=='none';reduced.mouse.move(950,600);assert reduced.locator('.login-cloud-plane-near').evaluate('e=>getComputedStyle(e).transform')=='matrix(1, 0, 0, 1, 0, 0)'
    reduced.bring_to_front();reduced.emulate_media(reduced_motion='no-preference');reduced.wait_for_function('()=>window.__loginFrames>0',polling=50)
    # Simulate visibilitychange deterministically; no fake data enters the app.
    reduced.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'));")
    expect(reduced.locator('body')).to_have_attribute('data-animation-paused','true');assert reduced.locator('.login-cloud-plane img').first.evaluate('e=>getComputedStyle(e).animationPlayState')=='paused';stopped=reduced.evaluate('window.__loginFrames');reduced.wait_for_timeout(200);assert reduced.evaluate('window.__loginFrames')==stopped
    reduced.evaluate("delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));");reduced.wait_for_function('(value)=>window.__loginFrames>value',arg=stopped)
    mobile=new_page(viewport=dict(width=390,height=844),device_scale_factor=2,is_mobile=True,has_touch=True);mobile.goto(BASE+'/login');mobile.wait_for_timeout(200);assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth');expect(mobile.get_by_role('button',name='Sign in',exact=True)).to_be_visible();mobile.screenshot(path=str(OUT/'Cirrus-Workplace-Login-Mobile.png'),full_page=True)
    expect(mobile.locator('.login-cloud-plane-far img')).to_have_css('animation-name','none');expect(mobile.get_by_label('Password',exact=True)).to_have_css('font-size','16px');mobile.get_by_label('Username',exact=True).fill('review-user');mobile.get_by_label('Password',exact=True).fill(PASSWORD);mobile.get_by_role('button',name='Show password',exact=True).click();expect(mobile.get_by_label('Password',exact=True)).to_have_attribute('type','text');mobile.get_by_role('button',name='Sign in',exact=True).click();mobile.wait_for_url(BASE+'/')
    tiny=new_page(viewport=dict(width=320,height=640),is_mobile=True,has_touch=True,reduced_motion='reduce');tiny.goto(BASE+'/login');assert tiny.evaluate('document.documentElement.scrollWidth<=innerWidth');expect(tiny.get_by_role('button',name='Sign in',exact=True)).to_be_visible();tiny.screenshot(path=str(OUT/'Cirrus-Workplace-Login-Small-Mobile.png'),full_page=True)
    # Native sign-in also works with JavaScript disabled.
    native=new_page(viewport=dict(width=1366,height=768),java_script_enabled=False);native.goto(BASE+'/login');expect(native.get_by_role('button',name='Show password',exact=True)).to_have_count(0);native.get_by_label('Username',exact=True).fill('review-user');native.get_by_label('Password',exact=True).fill(PASSWORD);native.get_by_role('button',name='Sign in',exact=True).click();native.wait_for_url(BASE+'/')
    assert not [url for url in requests if not url.startswith(BASE+'/')],requests;assert not errors,errors
    results.update(checks='PASS',desktop='1536x960 and 1366x768',mobile='390x844 and 320x640',authentication='success, incorrect password, disabled account, missing CSRF, anonymous redirect, no-JS native POST',interaction='password toggle/keyboard, preserved username/no password echo, loading and duplicate prevention, isolated assets, reduced motion, simulated hidden-tab pause/resume',smtp='No real email; temporary synthetic accounts only')
    (OUT/'checks.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2));browser.close()
  except Exception:
   for index,page in enumerate(pages):
    try:page.screenshot(path=str(OUT/('failure-'+str(index)+'.png')),full_page=True)
    except Exception:pass
   raise
  finally:server.terminate();server.wait(timeout=20);log.close();(OUT/'server.log').write_text((td/'server.log').read_text())


if __name__=='__main__':run()
