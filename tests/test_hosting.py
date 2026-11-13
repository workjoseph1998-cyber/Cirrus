import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from workspace_app import create_app as real_create_app,store,hosting
from workspace_app.model import ValidationError,FIELDS
from workspace_app.backup import backup,restore
from quotation_fixture import fixture

def create_app(*args,**kwargs):
    app=real_create_app(*args,**kwargs)
    app.config['AUTH_TEST_BYPASS']=True
    return app



class HostingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'data'
        self.app=create_app(self.root,True);self.client=self.app.test_client();self.client.get('/')
        with self.client.session_transaction() as session:self.csrf=session['csrf']
    def tearDown(self):self.temp.cleanup()
    def post(self,path,**fields):return self.client.post(path,data={'csrf':self.csrf,**fields})

    def test_exact_sizes_demo_prices_and_repeatable_migration(self):
        with store.connect(self.root) as db:
            rows=hosting.entries(db)
            self.assertEqual(len(rows),33)
            self.assertEqual([sum(r['data']['family']==family for r in rows) for family in hosting.FAMILIES],[6,7,8,6,6])
            large=next(r for r in rows if r['data']['name']=='Large V1')
            self.assertEqual((large['data']['vcpu'],large['data']['ram_gb']),('8','15'))
            small=next(r for r in rows if r['data']['name']=='Small V1')
            self.assertEqual(small['data']['ram_gb'],'3.75')
            self.assertTrue(all(r['data']['price_status']=='Demo' and r['data']['cost_a']==r['data']['cost_b']=='' for r in rows))
            large['data'].update(cost_a='124.00',cost_b='150.00',price_status='Confirmed')
            hosting.save(db,large['data'],large['id'])
            db.execute('DELETE FROM hosting_vms WHERE id=?',(small['id'],))
        store.migrate(self.root)
        with store.connect(self.root) as db:
            rows=hosting.entries(db);self.assertEqual(len(rows),32)
            self.assertEqual(next(r for r in rows if r['id']==large['id'])['data']['cost_a'],'124.00')

    def test_catalog_keeps_all_reusable_row_fields(self):
        row=fixture()['document']['sections'][1]['rows'][0]
        row.update(service='Cirrus Compute',sub_service='Control-plane Nodes',type='Iaas',quantity='1',unit_price='124',pricing_model='Per unit',comments='VM Size: Large V1\nVM Specs: 8 vCPU, 15 GB RAM')
        response=self.post('/quotes/catalog',item=json.dumps({'row':row,'code':'VM-TEST','currency':'USD'}))
        self.assertEqual(response.status_code,200,response.data)
        saved=response.json['item']['data']
        for key in ('type','comments','pricing_model','billing','quantity','discount'):
            self.assertEqual(saved[key],row[key])
        with store.connect(self.root) as db:
            catalog=store.records(db)[0]['data']
            self.assertEqual(catalog['comments'],row['comments'])
            catalog['comments']='Edited specs';store.save(db,'catalog',catalog,response.json['id'])
        again=create_app(self.root,True)
        with store.connect(again.config['DATA_DIR']) as db:self.assertEqual(store.records(db)[0]['data']['comments'],'Edited specs')

    def test_vm_edit_validation_and_atomic_price_form(self):
        with store.connect(self.root) as db:rows=hosting.entries(db)
        item=rows[0];bad=dict(item['data'],vcpu='2.5')
        with self.assertRaises(ValidationError):hosting.validate_vm(bad)
        for key,value in [('ram_gb','0'),('cost_a','NaN'),('cost_b','-1')]:
            with self.assertRaises(ValidationError):hosting.validate_vm(dict(item['data'],**{key:value}))
        fields={item['id']+'-cost_a':'123',item['id']+'-cost_b':'456',item['id']+'-price_status':'Confirmed',
                rows[1]['id']+'-cost_a':'bad',rows[1]['id']+'-cost_b':'1',rows[1]['id']+'-price_status':'Confirmed'}
        self.assertEqual(self.post('/hosting-vms/prices',**fields).status_code,400)
        with store.connect(self.root) as db:self.assertEqual(hosting.entries(db)[0]['data']['cost_a'],item['data']['cost_a'])

    def test_vm_profile_create_edit_delete_routes(self):
        vm=dict(name='Custom VM',family='Custom',vcpu='12',ram_gb='24',cost_a='90',cost_b='120',price_status='Confirmed')
        self.assertEqual(self.post('/hosting-vms/new',**vm).status_code,302)
        with store.connect(self.root) as db:item=next(r for r in hosting.entries(db) if r['data']['name']=='Custom VM')
        vm['ram_gb']='32'
        self.assertEqual(self.post('/hosting-vms/'+item['id']+'/edit',**vm).status_code,302)
        with store.connect(self.root) as db:self.assertEqual(next(r for r in hosting.entries(db) if r['id']==item['id'])['data']['ram_gb'],'32')
        self.assertEqual(self.post('/hosting-vms/'+item['id']+'/delete').status_code,302)
        with store.connect(self.root) as db:self.assertEqual(len(hosting.entries(db)),33)

    def test_export_import_edits_defaults_conflicts_and_backup(self):
        with store.connect(self.root) as db:
            item=hosting.entries(db)[0];item['data'].update(cost_a='124.00',cost_b='180.00',price_status='Confirmed');hosting.save(db,item['data'],item['id'])
            payload=store.export_data(db)
        other=Path(self.temp.name)/'other';store.migrate(other)
        with store.connect(other) as db:
            db.execute('BEGIN IMMEDIATE');store.apply_import(db,copy.deepcopy(payload))
        with store.connect(other) as db:
            self.assertEqual(store.export_data(db),payload)
            bad=copy.deepcopy(payload);bad['hosting_vms'][0]['data']['cost_a']='999.00'
            with self.assertRaises(ValidationError):store.preview_import(db,bad)
        archive=Path(self.temp.name)/'backup.zip';backup(self.root,archive);restored=Path(self.temp.name)/'restored';restore(archive,restored)
        with store.connect(restored) as db:self.assertEqual(store.export_data(db),payload)

    def test_v2_catalog_migration_is_additive(self):
        with store.connect(self.root) as db:
            old={k:'' for k,_,_ in FIELDS['catalog']}
            for k in ('type','comments','pricing_model','billing','method','fixed_fee','quantity','discount'):old.pop(k)
            old.update(code='OLD',name='Legacy catalog',unit='day',currency='USD',status='Active')
            db.execute('INSERT INTO records (id,kind,data,created,updated) VALUES (?,?,?,?,?)',('old','catalog',json.dumps(old),'old-date','old-date'))
            db.execute('DROP TABLE hosting_vms');db.execute('PRAGMA user_version=2')
        store.migrate(self.root)
        with store.connect(self.root) as db:
            record=store.records(db)[0]
            self.assertEqual(record['id'],'old');self.assertEqual(record['created'],'old-date')
            self.assertEqual(record['data']['type'],'');self.assertEqual(record['data']['comments'],'')
            self.assertEqual(record['data']['quantity'],'1')
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],18)
            self.assertEqual(len(hosting.entries(db)),33)


if __name__=='__main__':unittest.main()
