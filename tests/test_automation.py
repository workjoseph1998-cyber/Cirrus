"""Automatic export, complete-backup, permissions and filesystem failure tests."""
import copy,io,json,tempfile,threading,unittest,zipfile
from concurrent.futures import ThreadPoolExecutor,TimeoutError
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
from workspace_app import automation,store
from workspace_app.backup import online_safety_backup,restore
from workspace_app.model import ValidationError
from test_v5 import quote
import test_v8 as v8


class AutomationTests(unittest.TestCase):
    setUp=v8.V8Tests.setUp
    tearDown=v8.V8Tests.tearDown
    login=v8.V8Tests.login
    post=v8.V8Tests.post
    create_quote=v8.V8Tests.create_quote
    record=v8.V8Tests.record
    def settings(self,**changes):
        pdf=Path(self.temp.name)/'pdf';backup=Path(self.temp.name)/'backup';pdf.mkdir(exist_ok=True);backup.mkdir(exist_ok=True)
        values=dict(pdf_enabled='yes',pdf_folder=str(pdf),backup_enabled='yes',backup_folder=str(backup),daily_retention='14',weekly_retention='8');values.update(changes)
        response=self.post('/automation/settings',**values);self.assertEqual(response.status_code,302,response.data[:1000])
        from workspace_app import export_folders
        with store.connect(self.root) as db:
            cfg=export_folders.context(db,self.record(self.customer));existing=export_folders.mapping(db,self.customer)
        if not existing:
            destination=pdf/'Synthetic Bank';destination.mkdir(exist_ok=True)
            response=self.post('/customers/'+self.customer+'/quotation-folder',action='save',quotation_folder=str(destination),version='0',root_hash=cfg['folder_root_hash'],mapping_hash=cfg['folder_mapping_hash']);self.assertEqual(response.status_code,302,response.data[:1000])
        return pdf,backup
    @staticmethod
    def renderer(app,data,path):Path(path).write_bytes(b'%PDF-1.4\n'+data['title'].encode()+b' '+b'x'*200)
    def job(self,ident):
        with store.connect(self.root) as db:return dict(db.execute('SELECT * FROM pdf_exports WHERE record_id=?',(ident,)).fetchone())
    def test_absolute_windows_unc_separate_paths_and_server_access(self):
        self.assertEqual(automation.path_kind(r'C:\CirrusPDFs'),'windows');self.assertEqual(automation.path_kind(r'\\fileserver\share\PDFs'),'windows')
        for value in ('relative/path',r'C:relative',r'\root-only'):
            with self.assertRaises(ValidationError):automation.path_kind(value)
        with self.assertRaises(ValidationError):automation.validate_paths({**automation.DEFAULTS,'pdf_folder':r'C:\Exports','backup_folder':r'c:\exports\Backups'},self.root)
        pdf,_=self.settings();automation.test_access(str(pdf));self.assertFalse(list(pdf.glob('.cirrus-access-test-*')))
        bad=self.post('/automation/settings',action='test_pdf',pdf_folder=str(Path(self.temp.name)/'missing'),backup_folder='',daily_retention='14',weekly_retention='8');self.assertEqual(bad.status_code,200);self.assertIn(b'Folder access test failed',bad.data)
    def test_admin_only_settings_tests_download_and_full_private_restore(self):
        for username in ('editor','viewer'):
            client=self.login(username);self.assertEqual(client.get('/automation/settings').status_code,403);self.assertEqual(self.post('/backups/download',client=client).status_code,403)
        ident=self.create_quote();self.post('/record/'+ident+'/attachment',file=(io.BytesIO(b'private attachment'),'private.txt'))
        response=self.post('/backups/download');self.assertEqual(response.status_code,200);raw=response.data;response.close()
        archive=Path(self.temp.name)/'download.zip';archive.write_bytes(raw)
        with zipfile.ZipFile(archive) as z:
            m=json.loads(z.read('manifest.json'));self.assertEqual(m['schema'],18);self.assertEqual(m['application_version'],'21');self.assertEqual(len(m['files']),2)
        target=Path(self.temp.name)/'restored';restore(archive,target)
        with store.connect(target) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0],3);attachment=db.execute('SELECT stored FROM attachments').fetchone()[0];self.assertEqual((target/'attachments'/attachment).read_bytes(),b'private attachment');self.assertTrue(db.execute('SELECT 1 FROM reference_registry').fetchone())
    def test_auto_queue_same_revision_replaces_and_colliding_titles_remain_separate(self):
        self.settings();one=self.create_quote(quote('PDF-1'));two=self.create_quote(quote('PDF-2'))
        self.assertEqual(self.job(one)['status'],'pending');self.assertTrue(automation.process_pdf(self.app,self.renderer));self.assertTrue(automation.process_pdf(self.app,self.renderer))
        a=Path(self.job(one)['destination']);self.assertEqual(self.job(two)['status'],'failed');self.assertIn('conflict',self.job(two)['error']);self.assertEqual(a.name,'Synthetic quotation.pdf');self.assertTrue(a.is_file())
        d=self.record(one)['data'];d['notes']='Changed';self.post('/quotes/'+one+'/edit',quotation=json.dumps(d));automation.process_pdf(self.app,self.renderer);self.assertEqual(Path(self.job(one)['destination']),a);self.assertEqual(len(list(a.parent.glob('*.pdf'))),1)
        response=self.post('/record/'+one+'/copy/revision');revision=response.location.rsplit('/',1)[-1];automation.process_pdf(self.app,self.renderer);self.assertEqual(self.job(revision)['status'],'failed')
    def test_failed_export_preserves_record_previous_pdf_and_can_retry(self):
        self.settings();ident=self.create_quote();automation.process_pdf(self.app,self.renderer);old=self.job(ident);destination=Path(old['destination']);content=destination.read_bytes()
        d=self.record(ident)['data'];d['title']='New name';self.post('/quotes/'+ident+'/edit',quotation=json.dumps(d))
        def broken(app,data,path):Path(path).write_bytes(b'partial');raise OSError('Share unavailable')
        automation.process_pdf(self.app,broken);job=self.job(ident);self.assertEqual(job['status'],'failed');self.assertEqual(job['last_success'],old['last_success']);self.assertEqual(destination.read_bytes(),content);self.assertFalse(list(destination.parent.glob('*.tmp')));self.assertEqual(self.record(ident)['data']['title'],'New name')
        self.assertIn(b'Export failed',self.c.get('/documents/'+ident+'/manage').data);self.assertEqual(self.post('/documents/'+ident+'/pdf-retry').status_code,302)
        automation.process_pdf(self.app,self.renderer);self.assertEqual(self.job(ident)['status'],'success');self.assertTrue(destination.exists());self.assertTrue(Path(self.job(ident)['destination']).is_file())
    def test_stale_running_pdf_never_replaces_newer_save(self):
        self.settings();ident=self.create_quote();old=self.record(ident)['data'];changed=copy.deepcopy(old);changed['title']='New generation'
        def editing_renderer(app,data,path):
            self.post('/quotes/'+ident+'/edit',quotation=json.dumps(changed));self.renderer(app,data,path)
        automation.process_pdf(self.app,editing_renderer);self.assertEqual(self.job(ident)['status'],'pending');self.assertFalse(self.job(ident)['destination'])
        automation.process_pdf(self.app,self.renderer);self.assertEqual(Path(self.job(ident)['destination']).name,'New generation.pdf')
    def test_disabled_export_keeps_saves_fast_and_retry_respects_permissions(self):
        ident=self.create_quote()
        with store.connect(self.root) as db:self.assertFalse(db.execute('SELECT 1 FROM pdf_exports').fetchone())
        self.assertEqual(self.post('/documents/'+ident+'/pdf-retry').status_code,400);self.settings()
        self.assertEqual(self.post('/documents/'+ident+'/pdf-retry',client=self.login('editor')).status_code,404);self.assertEqual(self.post('/documents/'+ident+'/pdf-retry',client=self.login('viewer')).status_code,403)
    def test_daily_weekly_retention_and_restore_do_not_prune_unrelated_files(self):
        _,folder=self.settings(daily_retention='2',weekly_retention='1');self.create_quote();namespace=folder/'Cirrus-Workplace-full-backups';namespace.mkdir();(namespace/'do-not-delete.zip').write_bytes(b'Unrelated')
        for day in (date(2026,10,20),date(2026,10,21),date(2026,10,28),date(2026,11,2)):
            self.assertTrue(automation.run_daily_backup(self.app,day))
        self.assertFalse(automation.run_daily_backup(self.app,date(2026,11,2)));self.assertEqual(len(list(namespace.glob('daily-*.zip'))),2);self.assertEqual(len(list(namespace.glob('weekly-*.zip'))),1);self.assertTrue((namespace/'do-not-delete.zip').exists())
        latest=sorted(namespace.glob('daily-*.zip'))[-1];restore(latest,Path(self.temp.name)/'retention-restored')
    def test_backup_failure_retains_last_success_and_existing_copies(self):
        self.settings();automation.run_daily_backup(self.app,date(2026,11,1))
        with store.connect(self.root) as db:before=automation.backup_state(db)
        with patch('workspace_app.backup.online_safety_backup',side_effect=OSError('Share offline')):automation.run_daily_backup(self.app,date(2026,11,2))
        with store.connect(self.root) as db:
            after=automation.backup_state(db);self.assertEqual(after['status'],'failed');self.assertEqual(after['last_success'],before['last_success']);self.assertEqual(after['destination'],before['destination'])
        self.assertTrue(Path(before['destination']).exists())
    def test_online_snapshot_write_barrier_coordinates_attachment_delete(self):
        ident=self.create_quote();self.post('/record/'+ident+'/attachment',file=(io.BytesIO(b'before delete'),'attached.txt'))
        with store.connect(self.root) as db:file=dict(db.execute('SELECT * FROM attachments').fetchone())
        entered=threading.Event();release=threading.Event();original=__import__('shutil').copyfile
        def copying(src,dst,*args,**kwargs):
            if str(src).endswith(file['stored']):entered.set();self.assertTrue(release.wait(5))
            return original(src,dst,*args,**kwargs)
        def delete():
            with store.connect(self.root) as db:
                db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM attachments WHERE id=?',(file['id'],))
            (self.root/'attachments'/file['stored']).unlink()
        dest=Path(self.temp.name)/'consistent.zip'
        with ThreadPoolExecutor(max_workers=2) as pool,patch('workspace_app.backup.shutil.copyfile',side_effect=copying):
            capturing=pool.submit(online_safety_backup,self.root,dest);self.assertTrue(entered.wait(5));deleting=pool.submit(delete)
            try:
                with self.assertRaises(TimeoutError):deleting.result(timeout=.05)
            finally:release.set()
            capturing.result(timeout=10);deleting.result(timeout=10)
        target=Path(self.temp.name)/'consistent-restored';restore(dest,target);self.assertEqual((target/'attachments'/file['stored']).read_bytes(),b'before delete')
    def test_customer_html_projection_and_renderer_options(self):
        self.settings();ident=self.create_quote();d=self.record(ident)['data'];d['document']['show_12_month']=False;d['internal_notes']='PRIVATE-HTML-SENTINEL'
        from unittest.mock import MagicMock
        page=MagicMock();browser=MagicMock();browser.new_page.return_value=page;driver=MagicMock();driver.chromium.launch.return_value=browser
        def navigate(html,**kwargs):
            self.assertNotIn('PRIVATE-HTML-SENTINEL',html);self.assertNotIn('Contract recurring total',html);self.assertNotIn('<th>12 months</th>',html);self.assertIn('cirrus-document-header',html);self.assertIn('data:image/png;base64',html)
        page.set_content.side_effect=navigate
        page.pdf.side_effect=lambda **kw:Path(kw['path']).write_bytes(b'%PDF-1.4'+b'x'*200)
        context=MagicMock();context.__enter__.return_value=driver
        with patch('workspace_app.automation.browser_path',return_value='/installed/browser'),patch('playwright.sync_api.sync_playwright',return_value=context):
            output=Path(self.temp.name)/'customer.pdf';automation.render_pdf(self.app,d,output);self.assertTrue(output.read_bytes().startswith(b'%PDF-'))
        page.pdf.assert_called_once_with(path=str(output),print_background=True,prefer_css_page_size=True,display_header_footer=False);self.assertTrue(browser.close.called)

if __name__=='__main__':unittest.main()
