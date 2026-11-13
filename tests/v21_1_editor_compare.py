"""Compare editor pixels against an independently running uploaded baseline.
Usage: python tests/v21_1_editor_compare.py /path/to/extracted/v21
Synthetic databases only. Images and result are saved outside the checkout.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from PIL import Image,ImageChops
baseline=Path(sys.argv[1]).resolve();current=Path(__file__).resolve().parents[1]
art=Path('/tmp/cirrus-v21-1-editor-compare');art.mkdir(exist_ok=True)
server_code='''import sys
from pathlib import Path
sys.path[:0]=[sys.argv[1],str(Path(sys.argv[1])/'tests')]
from workspace_app import create_app,store,security
from quotation_fixture import fixture
from waitress import serve
app=create_app(Path(sys.argv[2]),testing=True)
with store.connect(Path(sys.argv[2])) as db:
    ident=security.create_user(db,'compare-admin','Synthetic-browser-password-21!','Administrator',True)
    q=fixture();q.update(title='Synthetic editor comparison',number='COMPARE-21')
    quote=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=?',(ident,))
Path(sys.argv[2]+'/quote.txt').write_text(quote)
serve(app,host='127.0.0.1',port=int(sys.argv[3]),threads=4)
'''
with tempfile.TemporaryDirectory() as td:
    processes=[]
    try:
        for index,source in enumerate([baseline,current]):
            data=Path(td)/str(index);data.mkdir()
            processes.append(subprocess.Popen([sys.executable,'-c',server_code,str(source),str(data),str(8050+index)],cwd=source,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
        with sync_playwright() as driver:
            browser=driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            for index in range(2):
                base='http://127.0.0.1:'+str(8050+index)
                for attempt in range(60):
                    try:urlopen(base+'/login',timeout=1);break
                    except OSError:time.sleep(.2)
                context=browser.new_context(viewport=dict(width=1440,height=1000));page=context.new_page()
                page.goto(base+'/login');page.get_by_label('Username',exact=True).fill('compare-admin');page.get_by_label('Password',exact=True).fill('Synthetic-browser-password-21!');page.get_by_role('button',name='Sign in',exact=True).click();page.wait_for_url(base+'/')
                quote=(Path(td)/str(index)/'quote.txt').read_text()
                for theme in ['light','dark']:
                    page.goto(base+'/quotes/'+quote+'/edit');page.locator('#portal-theme').select_option(theme)
                    page.frame_locator('#customer-preview').locator('body').wait_for(state='visible')
                    page.wait_for_timeout(800)
                    page.mouse.move(0,0)
                    page.locator('#customer-preview').screenshot(path=str(art/f'{index}-{theme}.png'),animations='disabled',caret='hide')
                context.close()
            browser.close()
        result={}
        for theme in ['light','dark']:
            a,b=[Image.open(art/f'{i}-{theme}.png').convert('RGB') for i in range(2)]
            assert a.size==b.size,(a.size,b.size)
            # Chromium's native scrollbar arrows may vary with focus; exclude its 16px gutter, not application content.
            a=a.crop((0,0,a.width-16,a.height));b=b.crop((0,0,b.width-16,b.height))
            diff=ImageChops.difference(a,b);bounds=diff.getbbox();result[theme]={'identical':bounds is None,'changed_bounds':bounds,'excluded_native_scrollbar_px':16}
            if bounds:diff.save(art/f'difference-{theme}.png')
        (art/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
        assert all(r['identical'] for r in result.values()),'Editor screenshot changed'
    finally:
        for proc in processes:proc.terminate()
        for proc in processes:proc.wait(timeout=10)
