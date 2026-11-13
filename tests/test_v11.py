import io,json,unittest,re
from decimal import Decimal
from openpyxl import Workbook
from workspace_app import monthly,store,hosting
from workspace_app.model import ValidationError
import test_v8 as v8

class Calculations(unittest.TestCase):
 def test_unknown_zero_override_and_support(self):
  a=monthly.row({'VM':'one','Qty':'0','Unit Price':'10','environment':'Production','category':'Hosting','billing_unit':'VM','vm_confirmed':True,'NB of Cores':'4','RAM':'8','resource_semantics':'per_vm'})
  b=monthly.row({'VM':'one','Qty':'2','Unit Price':'x','Total':'-','environment':'DR','category':'Hosting'})
  c=monthly.row({'Qty':'2','Unit Price':'5','Total':'20','environment':'Production','category':'AD','billing_unit':'users'})
  ambiguous=monthly.row({'category':'Support Services','Qty':'20','Unit Price':'100'});self.assertIsNone(monthly.summary([ambiguous])['amounts'][ambiguous['id']])
  s=monthly.summary([a,b,c]);self.assertEqual(s['amounts'][a['id']],Decimal('0.00'));self.assertIsNone(s['amounts'][b['id']]);self.assertIn('differs',' '.join(s['warnings'][c['id']]))
  c.update(override='15',override_reason='Agreed exception');self.assertEqual(monthly.summary([c])['total'],'15.00')
  support=monthly.row({'billing_unit':'%','percentage':'10','base_ids':[c['id']]});self.assertEqual(monthly.summary([c,support])['total'],'16.50')
 def test_environment_identity_and_resources(self):
  a=monthly.row({'VM':'repeated','environment':'Production','category':'Hosting','vm_confirmed':True,'Qty':'1','NB of Cores':'4','RAM':'8','resource_semantics':'per_vm','Unit Price':'0'})
  b=dict(a,id='different',environment='DR');ad=monthly.row({'VM':'ad','Qty':'80','category':'AD','billing_unit':'users'})
  s=monthly.summary([a,b,ad]);self.assertEqual(s['vm_count'],2);self.assertEqual(s['cores'],'8');self.assertEqual(s['ram'],'16');self.assertEqual(s['units']['users'],80)
 def test_workbook_context_optional_columns_and_date(self):
  b=Workbook();w=b.active;w.append(['Item','VM','Date','Qty','Unit Price','Total']);w.append(['Production']);w.merge_cells('A2:F2');w.append(['Security Services']);w.append([1,'same','February','x','-',None]);w.append(['DR']);w.append(['security SERVICES']);w.append(['Item','VM','Date','Qty','Unit Price','Total']);w.append([1,'same','May',0,0,0]);w.append([None]*6)
  rows=monthly.parse(b,w.title,dict(zip(['Item','VM','Date','Qty','Unit Price','Total'],map(str,range(1,7)))));self.assertEqual(len(rows),2);self.assertEqual([r['environment'] for r in rows],['Production','DR']);self.assertEqual(rows[0]['Date'],'February');self.assertEqual(rows[1]['Date'],'May');self.assertNotEqual(rows[0]['id'],rows[1]['id']);self.assertEqual(rows[0]['RAM'],'')

class Integration(unittest.TestCase):
 setUp=v8.V8Tests.setUp
 tearDown=v8.V8Tests.tearDown
 post=v8.V8Tests.post
 login=v8.V8Tests.login
 record=v8.V8Tests.record
 def test_snapshot_edit_version_permissions_and_price_isolation(self):
  rows=[monthly.row({'VM':'test','Qty':'2','Unit Price':'20','environment':'Production','category':'Hosting'})]
  with store.connect(self.root) as db:db.execute('INSERT INTO monthly_snapshots VALUES (?,?,?,?,?,?)',(self.customer,'2026-11',1,json.dumps(rows),'2026-11-02',self.admin))
  self.assertEqual(self.post('/customers/'+self.customer+'/consumption',month='2026-11',rows='[]',confirm='yes').status_code,410)
  with store.connect(self.root) as db:self.assertEqual(monthly.summary(monthly.load_snapshot(db,self.customer,'2026-11')['data'])['total'],'40.00')

 def test_complete_catalog_copied_once(self):
  with store.connect(self.root) as db:
   self.assertEqual(db.execute('SELECT count(*) FROM customer_vm_catalog WHERE customer_id=?',(self.customer,)).fetchone()[0],33)
   before=db.execute('SELECT data FROM customer_vm_catalog WHERE customer_id=? AND entry_id=?',(self.customer,self.vm)).fetchone()[0]
   d=json.loads(db.execute('SELECT data FROM hosting_vms WHERE id=?',(self.vm,)).fetchone()[0]);d['cost_a']='999';hosting.save(db,d,self.vm)
   self.assertEqual(db.execute('SELECT data FROM customer_vm_catalog WHERE customer_id=? AND entry_id=?',(self.customer,self.vm)).fetchone()[0],before)
  self.assertEqual(self.c.get('/customers/'+self.customer+'/tenant-pricing').status_code,200)
 def test_import_original_attachment_duplicate_guard_and_merge(self):
  b=Workbook();w=b.active;w.append(monthly.COLUMNS);w.append(['Production']);w.append(['1','VM','February']);data=io.BytesIO();b.save(data)
  rows=monthly.parse(b,w.title,{k:str(i+1) for i,k in enumerate(monthly.COLUMNS)})
  with store.connect(self.root) as db:
   db.execute('INSERT INTO attachments VALUES (?,?,?,?,?)',('retained-workbook',self.customer,'fixture.xlsx','retained.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))
   (self.root/'attachments'/'retained.xlsx').write_bytes(data.getvalue())
   db.execute('INSERT INTO monthly_history(customer_id,month,at,actor,filename,row_count,before_data,after_data,attachment_id) VALUES (?,?,?,?,?,?,?,?,?)',(self.customer,'2026-11','2026-11-02',self.admin,'fixture.xlsx',1,'[]',json.dumps(rows),'retained-workbook'))
  self.assertEqual(self.c.get('/attachment/retained-workbook').data,data.getvalue())
  self.post('/record/'+self.customer+'/access',**{self.viewer:'read'});viewer=self.login('viewer');self.assertEqual(viewer.get('/attachment/retained-workbook').status_code,404)
  self.assertEqual(self.post('/attachment/retained-workbook/delete').status_code,400)
  self.assertEqual(self.post('/customers/'+self.customer+'/consumption/import',file=(io.BytesIO(data.getvalue()),'fixture.xlsx')).status_code,410)

 def test_customer_deletion_guard_and_nav(self):
  response=self.c.get('/customers/'+self.customer+'/delete-review');self.assertIn(b'project:',response.data);self.assertNotIn(b'Delete permanently',response.data)
  self.assertEqual(self.login('editor').get('/customers/'+self.customer+'/delete-review').status_code,403)
  self.assertIn(b'Quotations',self.c.get('/').data);self.assertEqual(self.c.get('/customers/'+self.customer).status_code,200)

 def test_duplicate_import_merge_and_failed_review_preserves_source(self):
  original=b'Retained staged source bytes'
  with store.connect(self.root) as db:db.execute('INSERT INTO monthly_drafts VALUES (?,?,?,?,?,?)',('retained-draft',self.customer,self.admin,'{}',original,'original.xlsx'))
  for mode in ['merge','replace']:
   self.assertEqual(self.post('/customers/'+self.customer+'/consumption',month='2026-11',draft='retained-draft',mode=mode,confirm='yes',rows='[]').status_code,410)
  with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT workbook FROM monthly_drafts WHERE id=?',('retained-draft',)).fetchone()[0],original)

 def test_tenant_stale_edit_and_historical_month_isolation(self):
  url='/customers/'+self.customer+'/tenant-pricing/'+self.vm+'/edit'
  with store.connect(self.root) as db:entry=dict(db.execute('SELECT * FROM customer_vm_catalog WHERE customer_id=? AND entry_id=?',(self.customer,self.vm)).fetchone())
  fields=json.loads(entry['data']);fields.update(version=str(entry['version']),cost_a='123')
  self.assertEqual(self.post(url,**fields).status_code,302)
  fields['cost_a']='456';stale=self.post(url,**fields);self.assertIn(b'Entry changed',stale.data)
  with store.connect(self.root) as db:self.assertEqual(json.loads(db.execute('SELECT data FROM customer_vm_catalog WHERE customer_id=? AND entry_id=?',(self.customer,self.vm)).fetchone()[0])['cost_a'],'123.00')

 def test_compact_margin_and_direct_file_ownership(self):
  from test_v5 import quote
  from workspace_app import costing,automation
  from workspace_app.commercial import fingerprint
  import tempfile
  q=quote('MARGIN');r=self.post('/quotes/new',quotation=json.dumps(q));ident=r.location.split('/')[-2]
  with store.connect(self.root) as db:record=next(x for x in store.records(db) if x['id']==ident);sheet=costing.load(db,record)
  values={x['id']+'-unit_purchase':'5' for x in sheet['rows']};values.update({x['id']+'-selling_unit':x['selling_unit'] for x in sheet['rows']})
  r=self.post('/quotes/'+ident+'/pricing-margin',version=str(sheet['version']),quote_hash=sheet['quote_hash'],**values);self.assertEqual(r.status_code,302,r.data[:1000])
  with store.connect(self.root) as db:self.assertEqual(costing.load(db,record)['rows'][0]['unit_purchase'],'5')
  self.assertEqual(self.login('viewer').get('/quotes/'+ident+'/pricing-margin').status_code,404)
 def test_direct_pdf_sanitization_case_collision_and_untracked_file(self):
  from pathlib import Path
  from workspace_app import automation,export_folders
  from test_v5 import quote
  folder=Path(self.temp.name)/'pdf';folder.mkdir();mapped=folder/'Bank';mapped.mkdir()
  self.assertEqual(self.post('/automation/settings',pdf_enabled='yes',pdf_folder=str(folder),backup_folder='',daily_retention='14',weekly_retention='8').status_code,302)
  with store.connect(self.root) as db:ctx=export_folders.context(db,self.record(self.customer))
  self.assertEqual(self.post('/customers/'+self.customer+'/quotation-folder',quotation_folder=str(mapped),version='0',root_hash=ctx['folder_root_hash'],mapping_hash=ctx['folder_mapping_hash']).status_code,302)
  def render(app,data,path):Path(path).write_bytes(b'%PDF-1.4'+b'x'*200)
  ids=[]
  for index,title in enumerate(['Collision?','collision*','Untouched']):
   q=quote('DIRECT-'+str(index));q.update(title=title,customer_id=self.customer);res=self.post('/quotes/new',quotation=json.dumps(q));self.assertEqual(res.status_code,302);ids.append(res.location.split('/')[-2])
  original=mapped/'Untouched.pdf';original.write_bytes(b'Existing unrelated file')
  for _ in range(3):automation.process_pdf(self.app,render)
  with store.connect(self.root) as db:
   states={r['record_id']:dict(r) for r in db.execute('SELECT * FROM pdf_exports')}
  self.assertEqual(states[ids[0]]['status'],'success');self.assertEqual(Path(states[ids[0]]['destination']).parent,mapped);self.assertEqual(states[ids[1]]['status'],'failed');self.assertIn('conflict',states[ids[1]]['error']);self.assertEqual(states[ids[2]]['status'],'failed');self.assertEqual(original.read_bytes(),b'Existing unrelated file');self.assertFalse(any(p.is_dir() for p in mapped.iterdir()))
 def test_cycle_preserves_editable_rows_and_source_attachment_protection(self):
  a=monthly.row({'percentage':'10'});b=monthly.row({'percentage':'10'});a['base_ids']=[b['id']];b['base_ids']=[a['id']]
  self.assertIn('Circular',monthly.safe_summary([a,b])['wording'])
  self.assertEqual(self.post('/customers/'+self.customer+'/consumption',month='2026-11',rows=json.dumps([a,b]),confirm='yes').status_code,410)
  with store.connect(self.root) as db:self.assertEqual(monthly.load_snapshot(db,self.customer,'2026-11')['version'],0)

 def test_catalog_edit_new_entry_and_delete_admin_guard(self):
  url='/customers/'+self.customer+'/tenant-pricing/new';payload=dict(name='Independent custom VM',family='Custom',vcpu='12',ram_gb='42',cost_a='0',cost_b='90',price_status='Confirmed')
  self.assertEqual(self.post(url,**payload).status_code,302)
  with store.connect(self.root) as db:
   self.assertEqual(db.execute('SELECT count(*) FROM customer_vm_catalog WHERE customer_id=?',(self.customer,)).fetchone()[0],34);self.assertEqual(db.execute('SELECT count(*) FROM hosting_vms').fetchone()[0],33)
  with store.connect(self.root) as db:
   from workspace_app import security
   c=store.save(db,'customer',dict(name='Owned by editor',contact='',notes=''));db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.editor,c))
  editor=self.login('editor');self.assertEqual(self.post('/record/'+c+'/delete',client=editor).status_code,403)

if __name__=='__main__':unittest.main()
