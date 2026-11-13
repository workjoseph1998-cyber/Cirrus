import copy
import io
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
import zipfile

from workspace_app import create_app as real_create_app, store
from workspace_app.backup import backup, restore, workspace_lock
from workspace_app.model import FIELDS, ValidationError, totals

def create_app(*args,**kwargs):
    app=real_create_app(*args,**kwargs)
    app.config['AUTH_TEST_BYPASS']=True
    return app



def data(kind, **values):
    d={k:'' for k,_,_ in FIELDS[kind]}
    defaults={'note':dict(type='Note',status='Open'), 'project':dict(status='Active'),
              'catalog':dict(currency='USD',status='Active'),
              'quote':dict(currency='USD',status='Draft',date='2026-10-28',tax='10',number='Q-ABCDEF123456',revision=1)}
    d.update(defaults.get(kind,{}));d.update(values)
    return d


def line(**values):
    d=dict(description='Implementation',unit='day',quantity='2',price='100',cost='60',discount='10')
    d.update(values);return d


class MoneyTests(unittest.TestCase):
    def test_discount_tax_and_internal_margin(self):
        r=totals([line()], '11')
        self.assertEqual(r['subtotal'],'180.00')
        self.assertEqual(r['tax_amount'],'19.80')
        self.assertEqual(r['grand_total'],'199.80')
        self.assertEqual(r['internal_margin'],'60.00')

    def test_round_half_up_per_line_then_tax(self):
        r=totals([line(quantity='1',price='.105',discount='0'),line(quantity='1',price='.105',discount='0')], '10')
        self.assertEqual(r['subtotal'],'0.22')
        self.assertEqual(r['tax_amount'],'0.02')
        self.assertEqual(r['grand_total'],'0.24')

    def test_blank_and_zero_differ(self):
        self.assertIsNone(totals([line(price='')], '0')['grand_total'])
        self.assertEqual(totals([line(price='0')], '0')['grand_total'],'0.00')
        self.assertIsNone(totals([line(cost='')], '0')['internal_margin'])

    def test_invalid_numeric_fields(self):
        for key,value in [('quantity','0'),('quantity','-1'),('price','-1'),('price','NaN'),('cost','Infinity'),('discount','101'),('quantity',True)]:
            with self.subTest(key=key,value=value), self.assertRaises(ValidationError):
                totals([line(**{key:value})],'10')
        with self.assertRaises(ValidationError):
            totals([line()],'101')


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'data'
        self.app=create_app(self.root,testing=True);self.client=self.app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as sess:
            self.token=sess['csrf']

    def tearDown(self):
        self.temp.cleanup()

    def post(self,url,values):
        return self.client.post(url,data={'csrf':self.token,**values},follow_redirects=True)

    def save(self,kind,**values):
        with store.connect(self.root) as db:
            return store.save(db,kind,data(kind,**values))

    def test_core_persistence_and_restart(self):
        project=self.save('project',name='Refresh',customer='Local test')
        self.save('note',title='Question',type='Question and answer',status='Open',content='How many VMs?',project_id=project)
        self.save('catalog',code='TEST',name='Service',unit='day')
        self.save('quote',title='Proposal',customer='Local test',project_id=project,lines=[line()])
        again=create_app(self.root,testing=True)
        with store.connect(again.config['DATA_DIR']) as db:
            self.assertEqual(len(store.records(db)),4)
        self.assertIn(b'Refresh',again.test_client().get('/').data)

    def test_required_dates_currency_and_relationship_validation(self):
        invalid=[('note',dict(title='')),('project',dict(name='P',customer='C',start_date='2026-12-01',end_date='2026-01-01')),
                 ('catalog',dict(code='A',name='A',unit='day',currency='US')),
                 ('note',dict(title='A',project_id='missing')),('note',dict(title='A',source_url='javascript:alert(1)'))]
        for kind,values in invalid:
            with self.subTest(kind=kind,values=values),self.assertRaises(ValidationError):
                self.save(kind,**values)

    def test_roundtrip_duplicates_atomic_conflict_and_bad_reference(self):
        self.save('project',name='P',customer='C')
        with store.connect(self.root) as db:
            payload=store.export_data(db)
            self.assertEqual(store.preview_import(db,copy.deepcopy(payload))[1],1)
        target=Path(self.temp.name)/'other';store.migrate(target)
        with store.connect(target) as db:
            db.execute('BEGIN IMMEDIATE')
            self.assertEqual(store.apply_import(db,copy.deepcopy(payload)),(1,0))
        with store.connect(target) as db:
            self.assertEqual(store.export_data(db),payload)
            conflict=copy.deepcopy(payload);conflict['records'][0]['data']['name']='Changed'
            with self.assertRaises(ValidationError):
                store.preview_import(db,conflict)
        fresh=Path(self.temp.name)/'fresh';store.migrate(fresh)
        bad=copy.deepcopy(payload);bad['records'].append(dict(id='d4fb54f1-ef20-4d25-b3fe-badcf33a3c80',kind='note',data=data('note',title='Broken',project_id='absent'),created='2026-10-28T00:00:00+00:00',updated='2026-10-28T00:00:00+00:00'))
        with self.assertRaises(ValidationError),store.connect(fresh) as db:
            db.execute('BEGIN IMMEDIATE');store.apply_import(db,bad)
        with store.connect(fresh) as db:
            self.assertEqual(store.records(db),[])

    def test_customer_print_csv_and_revisions(self):
        ident=self.save('quote',title='Proposal',customer='C',lines=[line()],internal_notes='PRIVATE-NOTE')
        response=self.client.get('/quote/'+ident+'/print')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'198.00',response.data)
        self.assertNotIn(b'PRIVATE-NOTE',response.data)
        self.assertNotIn(b'Internal cost',response.data)
        self.assertNotIn(b'Internal margin',response.data)
        self.assertIn(b'Implementation',self.client.get('/quote/'+ident+'/csv').data)
        self.post('/record/'+ident+'/copy/revision',{})
        self.post('/record/'+ident+'/copy/duplicate',{})
        with store.connect(self.root) as db:
            quotes=store.records(db)
            self.assertEqual(len(quotes),3)
            self.assertEqual(sorted(r['data']['revision'] for r in quotes),[1,1,2])
            self.assertEqual(len({r['data']['number'] for r in quotes}),2)

    def test_csrf_escape_attachment_and_safe_deletion(self):
        self.assertEqual(self.client.post('/new/note',data={'title':'x'}).status_code,400)
        self.assertEqual(self.client.get('/',headers={'Host':'evil.example'}).status_code,400)
        ident=self.save('note',title='<script>alert(1)</script>',content='x')
        response=self.client.get('/record/'+ident)
        self.assertNotIn(b'<script>alert(1)</script>',response.data)
        self.assertIn(b'&lt;script&gt;',response.data)
        response=self.post('/record/'+ident+'/attachment',{'file':(io.BytesIO(b'hello'),'../../note.txt')})
        self.assertEqual(response.status_code,200)
        with store.connect(self.root) as db:
            attachment=dict(db.execute('SELECT * FROM attachments').fetchone())
        self.assertNotIn('..',attachment['stored'])
        with self.client.get('/attachment/'+attachment['id']) as downloaded:
            self.assertEqual(downloaded.data,b'hello')
        self.assertEqual(self.post('/record/'+ident+'/attachment',{'file':(io.BytesIO(b'x'),'bad.exe')}).status_code,400)
        project=self.save('project',name='P',customer='C')
        self.save('note',title='Linked',project_id=project)
        self.assertEqual(self.post('/record/'+project+'/delete',{}).status_code,400)

    def test_catalog_snapshot_unchanged(self):
        item=self.save('catalog',code='TEST',name='Service',unit='day',price='100')
        quote=self.save('quote',title='Q',customer='C',lines=[line()])
        with store.connect(self.root) as db:
            store.save(db,'catalog',data('catalog',code='TEST',name='Changed',unit='day',price='900'),item)
            q=next(r for r in store.records(db) if r['id']==quote)
            self.assertEqual(q['data']['lines'][0]['price'],'100')

    def test_seed_import(self):
        with store.connect(self.root) as db:
            for path in Path('examples').glob('*.json'):
                new,skipped=store.preview_import(db,json.loads(path.read_text()))
                self.assertTrue(new)

    def test_edit_delete_and_filters(self):
        category=self.save('category',name='Personal')
        ident=self.save('note',title='Gym routine',content='Squats',category=category,tags='gym, health')
        result=self.post('/edit/note/'+ident,data('note',title='Updated gym routine',content='Squats and rows',category=category,tags='gym, health'))
        self.assertIn(b'Updated gym routine',result.data)
        self.assertEqual(self.client.get('/list/personal?tag=gym').status_code,302)
        self.assertIn(b'Updated gym routine',self.client.get('/record/'+ident).data)
        self.assertNotIn(b'Updated gym routine',self.client.get('/list/note?tag=absent').data)
        with self.client.get('/record/'+ident+'/markdown') as exported:
            self.assertIn(b'Squats and rows',exported.data)
        self.assertEqual(self.post('/record/'+ident+'/delete',{}).status_code,200)
        self.assertEqual(self.client.get('/record/'+ident).status_code,404)

    def test_category_edit_cannot_break_existing_links(self):
        parent=self.save('category',name='Personal')
        other=self.save('category',name='Presales')
        child=self.save('category',name='Gym',parent=parent)
        self.save('note',title='Routine',category=parent,subcategory=child)
        with self.assertRaises(ValidationError),store.connect(self.root) as db:
            store.save(db,'category',data('category',name='Gym',parent=other),child)

    def test_import_http_preview_and_confirm(self):
        payload=Path('examples/chatgpt-import.json').read_text()
        preview=self.post('/import',{'payload':payload})
        self.assertIn(b'Import preview',preview.data)
        with store.connect(self.root) as db:
            self.assertEqual(store.records(db),[])
        self.assertEqual(self.post('/import',{'payload':payload,'confirm':'yes'}).status_code,200)
        with store.connect(self.root) as db:
            self.assertEqual(len(store.records(db)),1)

    def test_backup_restore_integrity_and_safeguards(self):
        ident=self.save('note',title='Keep me')
        self.post('/record/'+ident+'/attachment',{'file':(io.BytesIO(b'important'),'file.txt')})
        archive=Path(self.temp.name)/'backup.zip'
        backup(self.root,archive)
        target=Path(self.temp.name)/'restored'
        restore(archive,target)
        with store.connect(target) as db,store.connect(self.root) as original:
            self.assertEqual(store.export_data(db),store.export_data(original))
            f=db.execute('SELECT stored FROM attachments').fetchone()[0]
            self.assertEqual((target/'attachments'/f).read_bytes(),b'important')
        with self.assertRaises(ValueError):
            restore(archive,target)
        with self.assertRaises(FileExistsError):
            backup(self.root,archive)
        with workspace_lock(self.root),self.assertRaises(RuntimeError):
            backup(self.root,Path(self.temp.name)/'locked.zip')
        corrupt=Path(self.temp.name)/'bad.zip'
        with zipfile.ZipFile(archive) as source,zipfile.ZipFile(corrupt,'w') as out:
            for name in source.namelist():
                out.writestr(name,b'corrupt' if name=='workspace.sqlite' else source.read(name))
        with self.assertRaises(ValueError):
            restore(corrupt,Path(self.temp.name)/'bad-restore')
        self.assertFalse((Path(self.temp.name)/'bad-restore').exists())


if __name__=='__main__':
    unittest.main()
