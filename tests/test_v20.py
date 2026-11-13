"""Version 20 catalog/template source-of-truth, isolation and save feedback."""
import copy,json,re,tempfile,unittest
from pathlib import Path
from workspace_app import create_app,store
from workspace_app.model import FIELDS,ValidationError
from workspace_app.quotation_setup import ensure,materialize,validate,fingerprint
from workspace_app.quotation_defaults import bindings,catalog_for_code
from workspace_app.quotation import calculate,validate_document
from workspace_app.support import defaults

class Version20(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.app=create_app(self.root,testing=True)
  from workspace_app import security
  with store.connect(self.root) as db:security.create_user(db,'v20-admin','V20-tests-only-password!','Administrator',True)
  self.client=self.app.test_client();self.client.get('/login')
  with self.client.session_transaction() as sess:token=sess['csrf']
  self.client.post('/login',data=dict(csrf=token,username='v20-admin',password='V20-tests-only-password!'))
  with self.client.session_transaction() as sess:self.csrf=sess['csrf']
 def tearDown(self):self.temp.cleanup()
 def record(self,kind,**values):
  data={k:'' for k,_,_ in FIELDS[kind]};data.update(values)
  with store.connect(self.root) as db:return store.save(db,kind,data)
 def new(self,customer):
  response=self.client.get('/quotes/new?customer_id='+customer);self.assertEqual(response.status_code,200)
  return json.loads(re.search(r'id="initial-quotation">(.*?)</script>',response.get_data(as_text=True),re.S).group(1))
 def test_legacy_five_items_are_reused_and_custom_prices_preserved(self):
  old=[('Security Datacenter FW','Datacenter FW','700'),('BackUp - Managed Backup (Agent)','Managed Backup (Agent)','19'),('Performance - NOC','NOC','25'),('Cirrus Compute VM','VM',''),('Security - Collector VM','Collector VM','300')]
  ids=[]
  for name,description,price in old:ids.append(self.record('catalog',code=name,name=name,description=description,unit='unit',price=price,currency='USD',billing='monthly',method='unit',quantity='1',status='Active'))
  with store.connect(self.root) as db:
   for row in db.execute("SELECT id,data FROM records WHERE kind='catalog'").fetchall():
    d=json.loads(row['data']);d.pop('service',None);d.pop('sub_service',None);db.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(d),row['id']))
   setup=ensure(db);ensure(db);records=store.records(db,unrestricted=True);self.assertEqual(len(records),19)
   self.assertEqual(bindings(db)['CIR-DCFW'],ids[0]);item=next(r for r in records if r['id']==ids[0]);self.assertEqual(item['data']['price'],'700');self.assertEqual(item['data']['unit'],'environment');self.assertEqual(item['data']['service'],'Security');self.assertEqual(next(r for r in records if r['id']==ids[2])['data']['minimum_quantity'],'50')
 def test_actual_flow_two_customers_catalog_change_and_snapshot_isolation(self):
  a=self.record('customer',name='Synthetic A');b=self.record('customer',name='Synthetic B')
  self.client.get('/quotation-defaults')
  with store.connect(self.root) as db:
   catalog=next(r for r in store.records(db,unrestricted=True) if r['id']==bindings(db)['CIR-STORAGE']);ident=catalog['id'];data=catalog['data'];data.update(quantity='3',price='91',comments='Current catalog comment')
  response=self.client.post('/edit/catalog/'+ident,data=dict(data,csrf=self.csrf));self.assertEqual(response.status_code,302)
  response=self.client.get('/quotation-defaults');self.assertIn(b'Default quotation setup',response.data)
  with store.connect(self.root) as db:s=ensure(db)
  # Assign the catalog item through the real saved-setup endpoint, with no prices.
  cyber=next(x for x in s['sections'] if x['role']=='cyber');cyber['items'].append(dict(catalog_id=ident,enabled=True))
  with store.connect(self.root) as db:base=fingerprint(ensure(db))
  self.assertEqual(self.client.post('/quotation-defaults',data=dict(csrf=self.csrf,base_hash=base,setup=json.dumps(s))).status_code,302)
  qa=self.new(a);qb=self.new(b)
  self.assertEqual([x['name'] for x in qa['document']['sections'] if not x['parent']],['Main Site','DR Site','Monitoring','Cybersecurity Services','Connectivity Services','Connectivity Setup — One-Time Fee','8×5 Request Fulfillment'])
  for q in [qa,qb]:
   rows=[r for x in q['document']['sections'] for r in x['rows'] if r['item_key']=='catalog:'+ident];self.assertEqual(len(rows),3);self.assertTrue(all((r['quantity'],r['unit_price'],r['comments'])==('3','91','Current catalog comment') for r in rows))
   edr=[x for x in q['document']['sections'] if any(r['sub_service']=='EDR' for r in x['rows'])];self.assertEqual([x['name'] for x in edr],['Cybersecurity Services'])
   self.assertEqual(q['document']['monitoring_ids'],[x['id'] for x in q['document']['sections'] if x['role']=='monitoring'])
   for x in q['document']['sections']:
    for r in x['rows']:
     if r.get('vm_selection_required'):r['state']='excluded'
     if float(r['quantity'])<float(r.get('minimum_quantity','0')):r['quantity']=r['minimum_quantity']
  self.client.post('/references/check',data=dict(csrf=self.csrf,reference=qa['number'],reserve='yes'))
  response=self.client.post('/quotes/new?customer_id='+a,data=dict(csrf=self.csrf,quotation=json.dumps(qa)));self.assertEqual(response.status_code,302,re.findall(r'<div class="error">(.*?)</div>',response.get_data(as_text=True)));saved=response.location.split('/')[-2]
  with store.connect(self.root) as db:before=copy.deepcopy(next(r for r in store.records(db,unrestricted=True) if r['id']==saved)['data']);data['price']='99';data['quantity']='4';store.save(db,'catalog',data,ident)
  qc=self.new(b);self.assertTrue(all((r['quantity'],r['unit_price'])==('4','99') for x in qc['document']['sections'] for r in x['rows'] if r['item_key']=='catalog:'+ident))
  with store.connect(self.root) as db:self.assertEqual(next(r for r in store.records(db,unrestricted=True) if r['id']==saved)['data'],before)
 def test_setup_has_no_prices_and_requires_vm_and_minimum_corrections(self):
  with store.connect(self.root) as db:
   s=ensure(db);d=materialize(db,s,defaults(db,''));self.assertNotIn('unit_price',json.dumps(s));self.assertNotIn('quantity',json.dumps(s))
   broken=copy.deepcopy(s);broken['sections'][0]['price']='100'
   with self.assertRaises(ValidationError):validate(broken,db)
  with self.assertRaises(ValidationError):validate_document(d,enforce_minimum=True)
  dr=next(x for x in d['sections'] if x.get('role')=='dr');vm=next(r for x in d['sections'] if x['parent']==dr['id'] for r in x['rows'] if r.get('vm_selection_required'))
  self.assertEqual((vm['dr_mode'],vm['dr_percent'],vm['unit_price']),('replication','50',''))
  customer=self.record('customer',name='VM selection test');q=self.new(customer)
  for section in q['document']['sections']:
   for row in section['rows']:
    if row.get('vm_selection_required'):row.update(vm_selection_required=False,unit_price='999')
    if float(row['quantity'])<float(row.get('minimum_quantity','0')):row['quantity']=row['minimum_quantity']
  response=self.client.post('/quotes/new?customer_id='+customer,data=dict(csrf=self.csrf,quotation=json.dumps(q)));self.assertIn(b'Choose a customer VM size',response.data);self.assertNotIn(b'Quotation saved successfully',response.data)
  setup=next(x for x in d['sections'] if x.get('role')=='setup');self.assertTrue(all(r['billing']=='one_time' for r in setup['rows']))
 def test_monitoring_monthly_one_time_support_dr_links_and_duplication(self):
  from workspace_app.quotation import duplicate_document
  with store.connect(self.root) as db:
   s=ensure(db);code=bindings(db)
   for key,price in [('CIR-VPN-NODE','11'),('CIR-INTERNET','9'),('CIR-REPLICATION-LINK','7'),('CIR-STORAGE','91')]:
    item=next(r for r in store.records(db,unrestricted=True) if r['id']==code[key]);item['data']['price']=price
    if key=='CIR-STORAGE':item['data']['quantity']='3'
    store.save(db,'catalog',item['data'],item['id'])
   item=next(r for r in store.records(db,unrestricted=True) if r['id']==code['CIR-SETUP']);item['data']['fixed_fee']='500';store.save(db,'catalog',item['data'],item['id'])
   d=materialize(db,s,defaults(db,''))
  roots={x['id']:x for x in d['sections'] if not x['parent']};vms={}
  for section in d['sections']:
   for row in section['rows']:
    if float(row['quantity'])<float(row.get('minimum_quantity','0')):row['quantity']=row['minimum_quantity']
    if row.get('vm_selection_required'):
     row.update(vm_selection_required=False,item_key='vm:synthetic:a',unit_price='100',unverified_price=False);vms[roots[section['parent']]['role']]=row
  d=validate_document(d);calc=calculate(d);self.assertEqual(calc['regular'],'4931.00');self.assertEqual(calc['one_time'],'500.00')
  support=next(r for x in d['sections'] for r in x['rows'] if r['method']=='percent');self.assertEqual(calc['rows'][support['id']],'392.00')
  d['optional_monitoring']=True;calc=calculate(d);self.assertEqual(calc['optional']['monthly'],'1000.00');self.assertEqual(calc['regular'],'3931.00');self.assertEqual(calc['rows'][support['id']],'392.00');d['optional_monitoring']=False
  # Stable roles preserve links when environment names are edited.
  main=next(x for x in d['sections'] if x.get('role')=='main');main['name']='Renamed HQ'
  dr=next(x for x in d['sections'] if x.get('role')=='dr');dr['name']='Continuity Site'
  vm_main=next(r for x in d['sections'] if x['parent']==main['id'] for r in x['rows'] if r['item_key'].startswith('vm:'));vm_dr=next(r for x in d['sections'] if x['parent']==dr['id'] for r in x['rows'] if r['item_key'].startswith('vm:'))
  vm_dr['dr_link']=vm_main['id'];vm_main['unit_price']='120';d=validate_document(d);self.assertEqual(calculate(d)['regular'],'4967.00')
  copy_doc=validate_document(duplicate_document(d));self.assertEqual(calculate(copy_doc)['regular'],'4967.00');self.assertEqual(calculate(copy_doc)['one_time'],'500.00')
  drrow=next(r for x in copy_doc['sections'] for r in x['rows'] if r.get('dr_link'));drrow.update(dr_mode='running',dr_percent='100');self.assertEqual(calculate(copy_doc)['rows'][drrow['id']],'120.00')
 def test_schema17_migration_and_setup_backup_restore(self):
  from workspace_app.backup import backup,restore
  from test_v5 import quote
  with store.connect(self.root) as db:
   ident=store.save(db,'quote',quote(status='Draft'));before=copy.deepcopy(next(r for r in store.records(db,unrestricted=True) if r['id']==ident))
   db.execute('DROP TABLE quotation_default_setup');db.execute('DROP TABLE standard_catalog_bindings');db.execute('PRAGMA user_version=16')
  store.migrate(self.root)
  with store.connect(self.root) as db:
   self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],18);setup=ensure(db);self.assertEqual(next(r for r in store.records(db,unrestricted=True) if r['id']==ident),before)
  with tempfile.TemporaryDirectory() as out:
   archive=Path(out)/'full-test.zip';backup(self.root,archive);target=Path(out)/'restored';restore(archive,target)
   with store.connect(target) as db:self.assertEqual(ensure(db),setup);self.assertEqual(len(bindings(db)),19)
 def test_compact_catalog_and_saved_toast_only_on_success(self):
  self.client.get('/list/catalog')
  with store.connect(self.root) as db:ident=bindings(db)['CIR-DCFW']
  response=self.client.get('/edit/catalog/'+ident);self.assertIn(b'catalog-fields',response.data);self.assertIn(b'Save catalog',response.data);self.assertNotIn(b'class="grid"',response.data)
  from test_v5 import quote
  from workspace_app.commercial import fingerprint as quote_hash
  q=quote(status='Draft')
  with store.connect(self.root) as db:qid=store.save(db,'quote',q);q=next(r for r in store.records(db) if r['id']==qid)['data']
  response=self.client.post('/quotes/'+qid+'/edit',data=dict(csrf=self.csrf,quotation=json.dumps(q),base_hash=quote_hash(q)),follow_redirects=True);self.assertIn(b'Quotation saved successfully',response.data);self.assertIn(b'quotation-save-toast',response.data)
  response=self.client.post('/quotes/'+qid+'/edit',data=dict(csrf=self.csrf,quotation=json.dumps(q),base_hash='stale'),follow_redirects=True);self.assertNotIn(b'Quotation saved successfully',response.data)
