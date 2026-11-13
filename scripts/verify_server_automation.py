"""Run under the Windows account that runs Workplace; no live records are changed."""
import argparse
from pathlib import Path
import sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import create_app,data_directory,store,automation,statistics
from workspace_app.model import FIELDS
from workspace_app.quotation import default_document,new_section,new_row


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--data-dir',type=Path);parser.add_argument('--customer-folders',action='store_true',help='Test every configured customer folder under this server account');args=parser.parse_args()
    root=args.data_dir or data_directory()
    if not (root/'workspace.sqlite').is_file():parser.error('Existing workspace database was not found; check the service data-directory environment.')
    with store.connect(root) as db:cfg=automation.config(db)
    automation.validate_paths(cfg,root)
    print('Checking configured server destinations under the current Windows/OS account.')
    for kind in ('pdf','backup'):
        if cfg[kind+'_enabled']:
            automation.test_access(cfg[kind+'_folder']);print(kind.upper()+' folder: create/write/flush/rename/delete passed.')
        else:print(kind.upper()+' automation is disabled; folder test skipped.')
    if args.customer_folders:
        from workspace_app.export_folders import beneath_root
        with store.connect(root) as db:folders=[dict(r) for r in db.execute('SELECT customer_id,folder FROM customer_export_folders')]
        for row in folders:
            beneath_root(row['folder'],cfg['pdf_folder']);automation.test_access(row['folder']);print('Customer '+row['customer_id']+': folder access passed.')
    if cfg['pdf_enabled']:
        print('Renderer: '+automation.browser_path())
        with tempfile.TemporaryDirectory(prefix='cirrus-server-check-') as temporary:
            scratch=Path(temporary);app=create_app(scratch/'scratch-data',testing=True)
            d={k:'' for k,_,_ in FIELDS['quote']};d.update(title='Server PDF diagnostic',number='SERVER-CHECK',revision=1,customer='Diagnostic only',date=statistics.today_local().isoformat(),currency='USD',status='Draft',tax='0',lines=[],document=default_document())
            d['document']['sections']=[new_section('Diagnostic services',rows=[new_row('Diagnostic service',quantity='1',unit_price='0')])];d['document']['discount']['targets']=[];d['document']['show_12_month']=False
            output=scratch/'check.pdf';automation.render_pdf(app,d,output);print('Customer PDF rendering passed ('+str(output.stat().st_size)+' bytes). Temporary diagnostic files removed.')
    print('Live records, attachments, settings, binding and data location were not modified.')

if __name__=='__main__':main()
