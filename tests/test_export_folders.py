"""Stable-ID customer folder mappings, explicit creation and no cross-customer fallback."""
import copy,json,sqlite3,unittest
from pathlib import Path
from workspace_app import store,automation,export_folders
from workspace_app.model import ValidationError
from test_v5 import quote
import test_automation as base


class CustomerFolderTests(unittest.TestCase):
    setUp=base.AutomationTests.setUp
    tearDown=base.AutomationTests.tearDown
    login=base.AutomationTests.login
    post=base.AutomationTests.post
    record=base.AutomationTests.record
    settings=base.AutomationTests.settings
    job=base.AutomationTests.job
    renderer=staticmethod(base.AutomationTests.renderer)
    def customer_record(self,name):
        with store.connect(self.root) as db:return store.save(db,'customer',dict(name=name,contact='',notes=''))
    def update_map(self,ident,action='save',**values):
        with store.connect(self.root) as db:ctx=export_folders.context(db,self.record(ident));saved=ctx['folder_mapping']
        return self.post('/customers/'+ident+'/quotation-folder',action=action,version=str(saved['version'] if saved else 0),root_hash=ctx['folder_root_hash'],mapping_hash=ctx['folder_mapping_hash'],**values)
    def save_for(self,customer_id,reference='CUSTOMER-PDF',**changes):
        q=quote(reference,status='Draft');q.update(customer_id=customer_id,**changes)
        response=self.post('/quotes/new',quotation=json.dumps(q));self.assertEqual(response.status_code,302,response.data[:1000]);return response.location.split('/')[-2]
    def test_missing_mapping_and_unlinked_customer_never_fall_back(self):
        pdf,_=self.settings();other=self.customer_record('Another Bank');ident=self.save_for(other)
        automation.process_pdf(self.app,self.renderer);self.assertEqual(self.job(ident)['status'],'not_configured');self.assertEqual(self.job(ident)['error'],'Customer export folder not configured');self.assertEqual(self.c.get('/documents/'+ident+'/pdf-status').json['customer_config_url'],'/customers/'+other+'/quotation-folder')
        self.assertFalse(list(pdf.rglob('*.pdf')))
        unlinked=self.save_for('','UNLINKED',customer='Synthetic Bank');automation.process_pdf(self.app,self.renderer);self.assertEqual(self.job(unlinked)['status'],'not_configured');self.assertFalse(list(pdf.rglob('*.pdf')))
    def test_existing_folder_mapping_survives_customer_rename_and_restart(self):
        pdf,_=self.settings();other=self.customer_record('SaradarBank');folder=pdf/'ExistingFolder';folder.mkdir()
        self.assertEqual(self.update_map(other,quotation_folder=str(folder)).status_code,302)
        self.assertEqual(self.update_map(other,action='test',quotation_folder=str(folder)).status_code,200)
        d=self.record(other)['data'];d['name']='Renamed Customer'
        with store.connect(self.root) as db:store.save(db,'customer',d,other)
        store.migrate(self.root)
        with store.connect(self.root) as db:self.assertEqual(export_folders.mapping(db,other)['folder'],str(folder))
        self.assertFalse((pdf/'Renamed Customer').exists());ident=self.save_for(other);automation.process_pdf(self.app,self.renderer);self.assertEqual(Path(self.job(ident)['destination']).parent,folder)
    def test_explicit_create_sanitizes_suggestion_and_requires_separate_customer_folder(self):
        pdf,_=self.settings();other=self.customer_record('Bank: A / B')
        with store.connect(self.root) as db:ctx=export_folders.context(db,self.record(other))
        self.assertEqual(ctx['suggested_folder'],'Bank_ A _ B');self.assertEqual(self.update_map(other,action='create',folder_name=ctx['suggested_folder']).status_code,302);self.assertTrue((pdf/ctx['suggested_folder']).is_dir())
        self.assertEqual(self.update_map(other,action='create',folder_name='Another').status_code,400);self.assertFalse((pdf/'Another').exists())
        third=self.customer_record('Third');self.assertEqual(self.update_map(third,quotation_folder=str(pdf/ctx['suggested_folder'])).status_code,400);self.assertEqual(self.update_map(third,quotation_folder=str(pdf)).status_code,400);nested=pdf/ctx['suggested_folder']/'nested';nested.mkdir();self.assertEqual(self.update_map(third,quotation_folder=str(nested)).status_code,400);self.assertEqual(self.update_map(third,quotation_folder=str(Path(self.temp.name))).status_code,400)
        self.assertEqual(self.update_map(third,action='create',folder_name='../outside').status_code,400)
    def test_customer_reassignment_and_mapping_change_preserve_old_exports(self):
        pdf,_=self.settings();second=self.customer_record('Second Bank');folder=pdf/'SecondBank';folder.mkdir();self.assertEqual(self.update_map(second,quotation_folder=str(folder)).status_code,302)
        ident=self.save_for(self.customer);automation.process_pdf(self.app,self.renderer);old=Path(self.job(ident)['destination'])
        q=self.record(ident)['data'];q['customer_id']=second;self.assertEqual(self.post('/quotes/'+ident+'/edit',quotation=json.dumps(q)).status_code,302);automation.process_pdf(self.app,self.renderer);new=Path(self.job(ident)['destination']);self.assertEqual(new.parent,folder);self.assertNotEqual(old,new);self.assertTrue(old.is_file());self.assertTrue(new.is_file())
        moved=pdf/'NewSecondBankFolder';moved.mkdir();self.update_map(second,quotation_folder=str(moved));self.post('/documents/'+ident+'/pdf-retry');automation.process_pdf(self.app,self.renderer);self.assertTrue(new.is_file());self.assertTrue(old.is_file());self.assertEqual(Path(self.job(ident)['destination']).parent,moved)
        self.update_map(second,quotation_folder='');self.post('/documents/'+ident+'/pdf-retry');automation.process_pdf(self.app,self.renderer);self.assertEqual(self.job(ident)['status'],'not_configured');self.assertTrue(new.is_file())
    def test_mapping_change_during_render_never_publishes_to_old_destination(self):
        pdf,_=self.settings();ident=self.save_for(self.customer);other=pdf/'ChangedDuringRender';other.mkdir()
        def changing(app,data,path):self.assertEqual(self.update_map(self.customer,quotation_folder=str(other)).status_code,302);self.renderer(app,data,path)
        automation.process_pdf(self.app,changing);self.assertEqual(self.job(ident)['status'],'pending');self.assertFalse(list(pdf.rglob('*.pdf')))
        automation.process_pdf(self.app,self.renderer);self.assertEqual(Path(self.job(ident)['destination']).parent,other)
    def test_folder_actions_require_administrator_and_backend_stale_checks(self):
        pdf,_=self.settings()
        for username in ('editor','viewer'):
            client=self.login(username);self.assertEqual(client.get('/customers/'+self.customer+'/quotation-folder').status_code,403);self.assertEqual(self.post('/customers/'+self.customer+'/quotation-folder',client=client,action='create').status_code,403)
        with store.connect(self.root) as db:ctx=export_folders.context(db,self.record(self.customer))
        payload=dict(action='save',quotation_folder='',version=str(ctx['folder_mapping']['version']),root_hash=ctx['folder_root_hash'],mapping_hash=ctx['folder_mapping_hash'])
        self.assertEqual(self.post('/customers/'+self.customer+'/quotation-folder',**payload).status_code,302)
        self.assertEqual(self.post('/customers/'+self.customer+'/quotation-folder',**payload).status_code,400)
    def test_windows_unc_mapping_is_case_insensitive_and_constrained_to_root(self):
        a=export_folders.beneath_root(r'Q:\Quotations\SaradarBank',r'Q:\Quotations');b=export_folders.beneath_root(r'q:\quotations\SARADARBANK',r'Q:\Quotations');self.assertEqual(a,b)
        self.assertTrue(export_folders.beneath_root(r'\\server\share\Quotations\Bank',r'\\server\share\Quotations').startswith('windows:'))
        for path in (r'Q:\Quotations',r'Q:\Quotations\..\OtherCustomer',r'Q:\Quotations2\Bank'):
            with self.assertRaises(ValidationError):export_folders.beneath_root(path,r'Q:\Quotations')

if __name__=='__main__':unittest.main()
