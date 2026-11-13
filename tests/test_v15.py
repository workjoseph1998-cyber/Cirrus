"""V15 exact optional fees, comparison bases and external customer file isolation."""
import copy,io,json,os,re,shutil,stat,tempfile,unittest,zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from openpyxl import load_workbook
from workspace_app import create_app,store,security,approvals as flow
from workspace_app import customer_documents as docs,document_storage as fs
from workspace_app.quotation import calculate,validate_document,new_row,new_section
from workspace_app.quote_excel import export_excel
from workspace_app.comparison import compare
from workspace_app.commercial import amount,line_values,fingerprint
from workspace_app.backup import online_safety_backup,restore
from workspace_app.model import ValidationError
from test_v14 import support_quote

PASSWORD='Synthetic-V15-file-test-password!'


def optional_quote():
    q=support_quote();d=q['document'];monitor=d['sections'][1]
    monitor['name']='Monitoring - 24×7 NOC Services'
    fee=d['sections'][-1]['rows'][0];fee['targets']+=['s:'+monitor['id']]
    return q


class OptionalAndComparison(unittest.TestCase):
    def test_windows_opened_handle_prefix_normalization(self):
        self.assertEqual(fs.windows_handle_path('\\\\?\\Q:\\Customers\\file.pdf'),'Q:\\Customers\\file.pdf')
        self.assertEqual(fs.windows_handle_path('\\\\?\\UNC\\server\\share\\file.pdf'),'\\\\server\\share\\file.pdf')
        self.assertEqual(fs.windows_handle_path('C:\\normal.pdf'),'C:\\normal.pdf')

    def test_optional_all_totals_and_support_base_exclude_monitoring(self):
        q=optional_quote();d=q['document'];fee=d['sections'][-1]['rows'][0]
        before=calculate(d);self.assertEqual(before['rows'][fee['id']],'60.00')
        d['optional_monitoring']=True;d=validate_document(d);c=calculate(d)
        self.assertEqual(c['rows'][fee['id']],'50.00');self.assertEqual(c['regular'],'1150.00')
        self.assertEqual(c['one_time'],'296.00');self.assertEqual(c['yearly'],'13800.00');self.assertEqual(c['term'],'13800.00');self.assertEqual(c['combined'],'14096.00')
        self.assertEqual(c['optional']['monthly'],'200.00');self.assertEqual(c['optional']['yearly'],'2400.00')
        self.assertEqual(sum(line_values(dict(q,document=d)).values()),amount(dict(q,document=d)))
        d['optional_monitoring']=False;self.assertEqual(calculate(d)['regular'],before['regular'])

    def test_optional_one_time_missing_prices_and_indirect_percentage_dependencies(self):
        q=optional_quote();d=q['document'];monitor=d['sections'][1];d['optional_monitoring']=True
        monitor['rows'][0]['unit_price']='';monitor['rows'].append(new_row('NOC setup',quantity='1',billing='one_time',unit_price='80'))
        # A second included percentage depends on support, which also targets NOC.
        other=new_section('Additional managed service');other['rows']=[new_row('Request service',method='percent',quantity='1',percent='10',targets=['r:'+d['sections'][-1]['rows'][0]['id']])];d['sections'].append(other)
        c=calculate(validate_document(d));self.assertIsNotNone(c['regular']);self.assertEqual(c['rows'][other['rows'][0]['id']],'5.00')
        self.assertIsNone(c['optional']['monthly']);self.assertEqual(c['optional']['one_time'],'80.00');self.assertEqual(c['one_time'],'296.00')
        monitor['rows'][0]['unit_price']='0';self.assertEqual(calculate(d)['optional']['monthly'],'0.00')

    def test_optional_checkbox_cannot_silently_ignore_a_missing_monitoring_section(self):
        q=optional_quote();q['document']['sections'][1]['name']='Unclassified service';q['document']['optional_monitoring']=True
        with self.assertRaisesRegex(ValidationError,'no Monitoring section'):validate_document(q['document'])

    def test_optional_discount_does_not_apply_twice_or_reduce_included_fee(self):
        q=optional_quote();d=q['document'];d['optional_monitoring']=True
        d['discount'].update(enabled=True,show_summary=True,kind='fixed',amount='100',duration='full',billing='monthly',targets=['s:'+d['sections'][1]['id']])
        c=calculate(validate_document(d));self.assertEqual(c['discount'],'0.00');self.assertEqual(c['regular'],'1150.00');self.assertEqual(c['optional']['monthly'],'200.00')
        d['discount'].update(kind='percent',percent='10',targets=['s:'+d['sections'][0]['id'],'s:'+d['sections'][1]['id']])
        c=calculate(d);self.assertEqual(c['discount'],'100.00');self.assertEqual(c['discounted'],'1050.00')

    def test_saved_ids_survive_rename_default_hash_unchanged_and_custom_toggle_invalidates(self):
        q=optional_quote();old=copy.deepcopy(q);old['document'].pop('optional_monitoring',None);old['document'].pop('monitoring_ids',None)
        normalized=copy.deepcopy(old);normalized['document']=validate_document(old['document'])
        self.assertEqual(fingerprint(flow.content(old)),fingerprint(flow.content(normalized)))
        normalized['document']['optional_monitoring']=True;checked=validate_document(normalized['document']);monitor=checked['sections'][1];monitor['name']='Customer NOC (renamed)'
        self.assertEqual(calculate(checked)['optional']['monthly'],'200.00')
        self.assertNotEqual(fingerprint(flow.content(dict(normalized,document=checked))),fingerprint(flow.content(old)))

    def test_optional_public_excel_csv_save_copy_revision(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'data';app=create_app(root,True);app.config['AUTH_TEST_BYPASS']=True;client=app.test_client();client.get('/')
            with client.session_transaction() as s:csrf=s['csrf']
            q=optional_quote();q['document']['optional_monitoring']=True
            response=client.post('/quotes/new',data=dict(csrf=csrf,quotation=json.dumps(q)));self.assertEqual(response.status_code,302);ident=response.location.split('/')[-2]
            for suffix in ['/edit','/print']:
                page=client.get('/quotes/'+ident+suffix);self.assertEqual(page.status_code,200)
                if suffix=='/print':
                    self.assertIn(b'Optional: Monitoring - 24',page.data);self.assertIn(b'$200.00',page.data);self.assertIn(b'$2,400.00',page.data)
                    self.assertGreater(page.data.index(b'summary-optional'),page.data.index(b'summary-one_time'))
            for mode in ['duplicate','revision']:
                response=client.post('/record/'+ident+'/copy/'+mode,data=dict(csrf=csrf));self.assertEqual(response.status_code,302);newid=response.location.rsplit('/',1)[-1]
                with store.connect(root) as db:
                    doc=json.loads(db.execute('SELECT data FROM records WHERE id=?',(newid,)).fetchone()[0])['document'];self.assertTrue(doc['optional_monitoring']);self.assertEqual(calculate(doc)['regular'],'1150.00')
            csv=client.get('/quotes/'+ident+'/csv').data;self.assertIn(b'Optional service',csv)
            book=load_workbook(io.BytesIO(client.get('/quotes/'+ident+'/xlsx').data),data_only=True);sheet=book['Quotation']
            optional=next(r for r in sheet if str(r[0].value or '').startswith('Optional: Monitoring') and r[3].value is not None)
            self.assertEqual(optional[3].value,200);self.assertEqual(optional[4].value,2400);self.assertEqual(optional[0].fill.fgColor.rgb,'00FFF2A8');self.assertTrue(optional[0].font.bold)
            regular=next(r for r in sheet if r[0].value=='Total monthly fee');self.assertEqual(regular[6].value,1150)

    def test_both_comparison_modes_direct_monthly_and_contract_with_zero_unknown_currency(self):
        before=optional_quote();after=copy.deepcopy(before);after['document']['sections'][0]['rows'][0]['unit_price']='600';after['document']['optional_monitoring']=True
        result=compare(before,after);self.assertEqual(result['summary_modes']['monthly']['values'][:2],['$1,360.00','$1,360.00'])
        # Existing before includes NOC + its support; the changed after replaces this
        # amount with increased included hosting. No one-time fee is divided by months.
        self.assertEqual(result['before_monthly'],'1360.00');self.assertEqual(result['after_monthly'],'1360.00')
        after['document']['sections'][3]['rows'][0]['fixed_fee']='1000';result=compare(before,after)
        self.assertEqual(result['summary_modes']['monthly']['values'][2],'$0.00');self.assertEqual(result['summary_modes']['contract']['values'][2],'$704.00')
        zero=copy.deepcopy(before)
        for section in zero['document']['sections']:
            for r in section['rows']:r['quantity']='0'
        self.assertIn('previous is zero',compare(zero,after)['summary_modes']['monthly']['values'][3])
        missing=copy.deepcopy(after);missing['document']['sections'][3]['rows'][0]['fixed_fee']=''
        self.assertNotEqual(compare(before,missing)['summary_modes']['monthly']['values'][1],'Unpriced');self.assertEqual(compare(before,missing)['summary_modes']['contract']['values'][1],'Unpriced')
        missing['currency']='EUR';self.assertEqual(compare(before,missing)['summary_modes']['monthly']['values'][2],'—')


class CustomerFiles(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.root=self.base/'data';self.disk=self.base/'documents';self.disk.mkdir();self.app=create_app(self.root,True)
        with store.connect(self.root) as db:
            self.ids={name:security.create_user(db,name,PASSWORD,'Administrator' if name=='admin' else 'Viewer' if name=='viewer' else 'Editor',name=='admin') for name in ['admin','owner','writer','readstaff','viewer','outsider']}
            self.a=store.save(db,'customer',dict(name='Same customer name',contact='A contact',notes=''));self.b=store.save(db,'customer',dict(name='Same customer name',contact='B private contact',notes=''))
            db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.ids['owner'],self.a));db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.ids['outsider'],self.b))
            for name,access in [('writer','edit'),('readstaff','read'),('viewer','read')]:db.execute('INSERT INTO record_acl VALUES (?,?,?)',(self.a,self.ids[name],access))
            db.execute("INSERT INTO settings VALUES ('customer_document_storage',?)",(json.dumps(str(self.disk)),))
        self.clients={name:self.login(name) for name in self.ids};self.c=self.clients['owner'];self.url='/customers/'+self.a+'/documents'
    def tearDown(self):self.temp.cleanup()
    def login(self,name,app=None):
        c=(app or self.app).test_client();c.get('/login')
        with c.session_transaction() as s:csrf=s['csrf']
        self.assertEqual(c.post('/login',data=dict(csrf=csrf,username=name,password=PASSWORD)).status_code,302);return c
    def post(self,path,client=None,**fields):
        client=client or self.c
        with client.session_transaction() as s:csrf=s['csrf']
        return client.post(path,data=dict(csrf=csrf,**fields))
    def upload(self,name='Original Name.txt',data=b'first version',parent='',client=None,url=None):return self.post(url or self.url+'/upload',client,file=(io.BytesIO(data),name),parent_id=parent)
    def rows(self):
        with store.connect(self.root) as db:return [dict(r) for r in db.execute('SELECT * FROM customer_document_nodes WHERE customer_id=?',(self.a,))]
    def find(self,name):return next(r for r in self.rows() if r['name']==name)
    def path(self,item):
        with store.connect(self.root) as db:
            space=db.execute('SELECT folder FROM customer_document_spaces WHERE customer_id=?',(item['customer_id'],)).fetchone()[0]
            return self.disk/space/docs.relative(db,item['customer_id'],item)
    def field(self,response,name):return re.search(('name="'+name+'" value="([^"]*)"').encode(),response.data)[1].decode()
    def resolve(self,response,mode,client=None):
        page=(client or self.c).get(response.location);return self.post(response.location,client,mode=mode,conflict_token=self.field(page,'conflict_token'))
    def edit(self,item,name=None,parent='',client=None,**extra):return self.post(self.url+'/'+item['id']+'/edit',client,name=name or item['name'],parent_id=parent,version=str(item['version']),**extra)

    def test_original_filename_metadata_permissions_and_customer_isolation(self):
        self.assertEqual(self.upload('Contrat français.txt').status_code,302);item=self.find('Contrat français.txt');self.assertEqual(self.path(item).read_bytes(),b'first version')
        page=self.c.get(self.url);self.assertIn(b'owner',page.data);self.assertIn(b'13 B',page.data)
        for name in ['viewer','readstaff']:
            self.assertEqual(self.clients[name].get(self.url).status_code,200)
            response=self.clients[name].get(self.url+'/'+item['id']+'/download');self.assertEqual(response.data,b'first version');self.assertIn('attachment',response.headers['Content-Disposition']);response.close()
            self.assertIn(self.upload(client=self.clients[name]).status_code,(403,404))
            for action in ['edit','delete']:self.assertIn(self.clients[name].get(self.url+'/'+item['id']+'/'+action).status_code,(403,404))
        for suffix in ['', '/'+item['id']+'/download','/'+item['id']+'/delete']:
            self.assertEqual(self.clients['outsider'].get(self.url+suffix).status_code,404)
        self.assertEqual(self.clients['admin'].get('/customers/'+self.b+'/documents/'+item['id']+'/download').status_code,404)
        self.assertEqual(self.edit(item,name='Renamed.txt',client=self.clients['writer']).status_code,302)
        self.assertEqual(self.path(self.find('Renamed.txt')).read_bytes(),b'first version')

    def test_duplicate_replace_new_version_cancel_and_windows_case_collision(self):
        self.upload('Report.pdf',b'original')
        duplicate=self.upload('report.PDF',b'cancelled');self.assertIn('/uploads/',duplicate.location);self.assertEqual(self.resolve(duplicate,'cancel').status_code,302)
        self.assertEqual(self.path(self.find('Report.pdf')).read_bytes(),b'original')
        duplicate=self.upload('Report.pdf',b'second');self.assertEqual(self.resolve(duplicate,'version').status_code,302)
        self.assertEqual(self.path(self.find('Report (v2).pdf')).read_bytes(),b'second')
        duplicate=self.upload('REPORT.PDF',b'replacement');self.assertEqual(self.resolve(duplicate,'replace').status_code,302)
        self.assertEqual(self.path(self.find('REPORT.PDF')).read_bytes(),b'replacement');self.assertEqual(len(self.rows()),2)
        self.assertEqual(self.c.get(self.url+'/'+self.find('REPORT.PDF')['id']+'/download').data,b'replacement')

    def test_folders_subfolders_breadcrumb_rename_move_and_deletion_confirmation(self):
        self.post(self.url+'/folders',name='Contracts');folder=self.find('Contracts')
        self.post(self.url+'/folders',name='2026',parent_id=folder['id']);nested=self.find('2026');self.upload('Terms.txt',parent=nested['id']);item=self.find('Terms.txt');old=self.path(item)
        page=self.c.get(self.url+'?folder='+nested['id']);self.assertIn(b'Contracts',page.data);self.assertIn(b'2026',page.data)
        self.assertEqual(self.edit(folder,name='Agreements').status_code,302);self.assertFalse(old.exists());self.assertTrue(self.path(item).exists())
        self.assertEqual(self.edit(self.find('Agreements'),parent=nested['id']).status_code,409)
        self.assertEqual(self.edit(item,name='Current.txt').status_code,302);self.assertEqual(self.path(self.find('Current.txt')).read_bytes(),b'first version')
        delete=self.url+'/'+self.find('Agreements')['id']+'/delete';page=self.c.get(delete);self.assertIn(b'0 files',page.data)
        self.assertEqual(self.post(delete,confirm='yes',snapshot=self.field(page,'snapshot')).status_code,302);self.assertFalse(any(r['kind']=='folder' for r in self.rows()))

    def test_nonempty_folder_stale_confirmation_and_no_silent_delete(self):
        self.post(self.url+'/folders',name='Filled');folder=self.find('Filled')
        for name in ['one.txt','two.txt']:self.upload(name,parent=folder['id'])
        url=self.url+'/'+folder['id']+'/delete';page=self.c.get(url);self.assertIn(b'2 files',page.data)
        self.assertEqual(self.post(url,snapshot=self.field(page,'snapshot')).status_code,409)
        self.upload('three.txt',parent=folder['id']);self.assertEqual(self.post(url,confirm='yes',snapshot=self.field(page,'snapshot')).status_code,409);self.assertEqual(len(self.rows()),4)
        page=self.c.get(url);self.assertEqual(self.post(url,confirm='yes',snapshot=self.field(page,'snapshot')).status_code,302);self.assertEqual(self.rows(),[]);self.assertFalse(self.path(folder).exists())

    def test_move_duplicate_choices_and_cross_customer_parent_rejected(self):
        self.post(self.url+'/folders',name='A');folder=self.find('A');self.upload('same.txt',b'root');self.upload('same.txt',b'child',parent=folder['id']);item=next(r for r in self.rows() if r['kind']=='file' and r['parent_id'])
        response=self.edit(item);self.assertEqual(response.status_code,409);token=self.field(response,'conflict_token')
        self.assertEqual(self.edit(item,mode='version',conflict_token=token).status_code,302);self.assertEqual(self.path(self.find('same (v2).txt')).read_bytes(),b'child')
        targeturl='/customers/'+self.b+'/documents';self.post(targeturl+'/folders',client=self.clients['outsider'],name='Private')
        with store.connect(self.root) as db:foreign=dict(db.execute('SELECT * FROM customer_document_nodes WHERE customer_id=?',(self.b,)).fetchone())
        self.assertEqual(self.edit(self.find('same.txt'),parent=foreign['id']).status_code,404)
        with store.connect(self.root) as db:self.assertNotEqual(db.execute('SELECT folder FROM customer_document_spaces WHERE customer_id=?',(self.a,)).fetchone()[0],db.execute('SELECT folder FROM customer_document_spaces WHERE customer_id=?',(self.b,)).fetchone()[0])

    def test_duplicate_conflict_token_detects_concurrent_replacement(self):
        self.upload();pending=self.upload(data=b'pending');page=self.c.get(pending.location);old=self.field(page,'conflict_token')
        other=self.upload(data=b'newer',client=self.clients['writer']);self.resolve(other,'replace',client=self.clients['writer'])
        response=self.post(pending.location,mode='replace',conflict_token=old);self.assertEqual(response.status_code,409);self.assertEqual(self.path(self.find('Original Name.txt')).read_bytes(),b'newer')

    def test_filename_traversal_reserved_names_and_unmanaged_disk_files(self):
        for name in ['../outside.txt','C:\\escape.txt','NUL.txt','con .txt','bad:stream','.CW-job-malicious.json','trailing.','name/child.txt']:
            self.assertEqual(self.upload(name).status_code,400,name)
        self.upload('safe.txt');base=self.path(self.find('safe.txt')).parent;(base/'unmanaged.txt').write_bytes(b'keep')
        self.assertEqual(self.upload('UNMANAGED.TXT').status_code,400);self.assertEqual((base/'unmanaged.txt').read_bytes(),b'keep')

    def test_symlinks_junction_flags_hardlinks_and_outside_files_blocked(self):
        self.upload('safe.txt');item=self.find('safe.txt');path=self.path(item);outside=self.base/'private.txt';outside.write_bytes(b'outside private')
        path.unlink();path.symlink_to(outside)
        self.assertEqual(self.c.get(self.url+'/'+item['id']+'/download').status_code,400);self.assertEqual(outside.read_bytes(),b'outside private')
        path.unlink();os.link(outside,path);self.assertEqual(self.c.get(self.url+'/'+item['id']+'/download').status_code,400);path.unlink();path.write_bytes(b'first version')
        self.post(self.url+'/folders',name='Linked');folder=self.find('Linked');folderpath=self.path(folder);folderpath.rmdir();folderpath.symlink_to(self.base,target_is_directory=True)
        self.assertIn(b'junctions',self.c.get(self.url+'?folder='+folder['id']).data)
        original=Path.lstat
        def fake(p,*args,**kwargs):
            if p.name=='junction-test':return SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=0x400)
            return original(p,*args,**kwargs)
        with patch.object(Path,'lstat',fake):
            with self.assertRaisesRegex(ValidationError,'junctions'):fs.check_components(self.base/'junction-test')

    def test_disk_write_failure_rolls_back_metadata_and_keeps_retryable_upload(self):
        self.upload();item=self.find('Original Name.txt');pending=self.upload(data=b'updated');page=self.c.get(pending.location);token=self.field(page,'conflict_token')
        with patch('workspace_app.customer_documents.audit',side_effect=RuntimeError('Injected DB failure')):
            with self.assertRaises(RuntimeError):self.post(pending.location,mode='replace',conflict_token=token)
        self.assertEqual(self.path(item).read_bytes(),b'first version');self.assertEqual(self.find('Original Name.txt')['version'],1)
        self.assertEqual(self.post(pending.location,mode='replace',conflict_token=token).status_code,302);self.assertEqual(self.path(item).read_bytes(),b'updated')

    def test_crash_recovery_uncommitted_moves_and_committed_cleanup(self):
        self.upload();item=self.find('Original Name.txt');pending=self.upload(data=b'pending')
        with store.connect(self.root) as db:draft=dict(db.execute('SELECT * FROM customer_document_uploads').fetchone())
        base=self.path(item).parent;backup=fs.staging_name('backup');job=uuid4().hex
        plan=dict(customer=self.a,moves=[[item['name'],backup],[draft['staged'],item['name']]],mkdir=[],cleanup=[backup])
        (base/('.cw-job-'+job+'.json')).write_text(json.dumps(plan));os.replace(base/item['name'],base/backup);os.replace(base/draft['staged'],base/item['name'])
        self.assertEqual(self.c.get(self.url).status_code,200);self.assertEqual((base/item['name']).read_bytes(),b'first version');self.assertTrue((base/draft['staged']).exists())
        page=self.c.get(pending.location);token=self.field(page,'conflict_token')
        with patch('workspace_app.document_storage._remove',side_effect=OSError('Injected cleanup interruption')):
            self.assertEqual(self.post(pending.location,mode='replace',conflict_token=token).status_code,302)
        self.assertTrue(list(base.glob('.cw-job-*.json')));self.assertEqual(self.c.get(self.url).status_code,200);self.assertFalse(list(base.glob('.cw-job-*.json')));self.assertEqual((base/item['name']).read_bytes(),b'pending')

    def test_persistence_customer_rename_app_restart_and_backup_metadata_only(self):
        self.upload('retained.txt');item=self.find('retained.txt');before=self.path(item)
        self.assertEqual(self.post('/edit/customer/'+self.a,name='Renamed customer',contact='',notes='').status_code,302)
        store.migrate(self.root);again=create_app(self.root,True);client=self.login('owner',again)
        self.assertEqual(client.get(self.url+'/'+item['id']+'/download').data,b'first version');self.assertEqual(before,self.path(item))
        archive=self.base/'backup.zip';online_safety_backup(self.root,archive)
        with zipfile.ZipFile(archive) as zipped:self.assertFalse(any('retained.txt' in n for n in zipped.namelist()))
        restored=self.base/'restored';restore(archive,restored)
        with store.connect(restored) as db:self.assertEqual(db.execute('SELECT count(*) FROM customer_document_nodes').fetchone()[0],1);self.assertEqual(docs.config(db),str(self.disk))
        self.assertEqual(self.clients['admin'].get('/customers/'+self.a+'/delete-review').status_code,200)
        self.assertIn(b'customer document',self.clients['admin'].get('/customers/'+self.a+'/delete-review').data.lower())

    def test_admin_root_settings_test_access_separation_and_relocation_guard(self):
        path='/administration/customer-documents';self.assertEqual(self.c.get(path).status_code,403)
        page=self.clients['admin'].get(path);token=self.field(page,'settings_hash')
        self.assertEqual(self.post(path,self.clients['admin'],root=str(self.disk),settings_hash=token,action='test').status_code,200)
        response=self.post(path,self.clients['admin'],root=str(self.root),settings_hash=token,action='save');self.assertIn(b'separate',response.data)
        self.upload();other=self.base/'new-root';other.mkdir()
        self.assertIn(b'already has assigned',self.post(path,self.clients['admin'],root=str(other),settings_hash=token,action='save').data)
        self.assertIn(b'not included',page.data)
        oldapp=self.base/'older-release';(oldapp/'workspace_app').mkdir(parents=True);(oldapp/'run.py').write_text('# archived application')
        self.assertIn(b'application release folder',self.post(path,self.clients['admin'],root=str(oldapp/'documents'),create='yes',settings_hash=token,action='save').data)

    def test_workflow_quote_grant_does_not_expose_customer_documents(self):
        self.upload();q=optional_quote();q.update(customer_id=self.a,customer='Same customer name')
        saved=self.post('/quotes/new',quotation=json.dumps(q));self.assertEqual(saved.status_code,302);ident=saved.location.split('/')[-2]
        with store.connect(self.root) as db:version=flow.current_version(db,ident);selected=flow.selection(db,ident)
        self.assertEqual(self.post('/quotes/'+ident+'/approval',action='submit',version=str(version['version']),hash=version['hash'],approvers=json.dumps([dict(user_id=self.ids['outsider'],phase='operations')]),approvers_version=str(selected['version'])).status_code,302)
        self.assertEqual(self.clients['outsider'].get('/quotes/'+ident+'/approval').status_code,200)
        self.assertEqual(self.clients['outsider'].get(self.url).status_code,404)
        self.assertEqual(self.clients['outsider'].get(self.url+'/'+self.rows()[0]['id']+'/download').status_code,404)

    def test_oversized_upload_cleans_partial_bytes_and_preserves_existing_documents(self):
        self.upload();before=self.path(self.find('Original Name.txt'))
        response=self.upload('large.bin',b'x'*(fs.MAX_BYTES+1));self.assertEqual(response.status_code,400);self.assertIn(b'10 MiB',response.data)
        self.assertEqual(len(self.rows()),1);self.assertEqual(before.read_bytes(),b'first version');self.assertFalse(list(before.parent.glob('.cw-upload-*')))

    def test_cancel_staged_upload_after_destination_folder_was_deleted(self):
        self.post(self.url+'/folders',name='Temporary');folder=self.find('Temporary');self.upload('same.txt',parent=folder['id']);pending=self.upload('same.txt',b'staged',parent=folder['id'])
        url=self.url+'/'+folder['id']+'/delete';page=self.c.get(url);self.assertEqual(self.post(url,confirm='yes',snapshot=self.field(page,'snapshot')).status_code,302)
        page=self.c.get(pending.location);self.assertEqual(page.status_code,200);self.assertIn(b'destination folder was removed',page.data)
        response=self.post(pending.location,mode='cancel');self.assertEqual(response.status_code,302);self.assertEqual(response.location,self.url)
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM customer_document_uploads').fetchone()[0],0)

    def test_concurrent_same_name_uploads_do_not_overwrite(self):
        def send(name):return self.upload('Concurrent.txt',name.encode(),client=self.clients[name])
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(send,['owner','writer']))
        self.assertEqual(len(self.rows()),1);self.assertEqual(sum('/uploads/' in r.location for r in responses),1)
        self.assertIn(self.path(self.find('Concurrent.txt')).read_bytes(),(b'owner',b'writer'))

if __name__=='__main__':unittest.main()
