"""Quotation display/catalog refinements; synthetic inputs only."""
import copy,io,json,re,tempfile,unittest
from pathlib import Path
from openpyxl import load_workbook
from workspace_app import store,create_app
from workspace_app.company import standard_template
from workspace_app.quotation import new_row,new_section,calculate,validate_document,public_document,clean_vm_comments
from workspace_app.quotation_defaults import initialize,default_items,catalog_for_code
from workspace_app.quotation_presentation import visible_totals
from workspace_app.quote_excel import export_excel
from workspace_app.model import ValidationError
from test_v5 import quote

class Refinements(unittest.TestCase):
 def test_visible_totals_preserve_unpriced(self):
  self.assertEqual(visible_totals('5482','0'),[('Monthly','5482')])
  self.assertEqual(visible_totals('0','500'),[('One-time','500')])
  self.assertEqual(visible_totals('12','34'),[('Monthly','12'),('One-time','34')])
  self.assertEqual(visible_totals('0.00','0'),[('Total','0.00')])
  self.assertEqual(visible_totals(None,'0'),[('Monthly',None)])
 def test_generated_os_cleanup_and_immutable_snapshot(self):
  comment='VM Size: Medium V1\nOperating system: Microsoft Windows\nVM Specs: 4 vCPU, 7.5 GB RAM\nManual licensing: Windows included'
  cleaned=clean_vm_comments(comment)
  self.assertNotIn('Operating system:',cleaned);self.assertIn('Manual licensing: Windows included',cleaned)
  self.assertEqual(clean_vm_comments('Operating system: manual note'),'Operating system: manual note')
  q=quote();r=q['document']['sections'][0]['rows'][0];r['comments']=comment
  before=copy.deepcopy(q);projected=public_document(q['document'])
  self.assertNotIn('Operating system:',projected['sections'][0]['rows'][0]['comments']);self.assertEqual(q,before)
 def test_complete_catalog_custom_defaults_and_template_mapping(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);store.migrate(root)
   with store.connect(root) as db:
    initialize(db);items=store.records(db,unrestricted=True);self.assertEqual(len(items),19)
    for item in items:self.assertEqual(item['data']['quantity'],'1')
    setup=catalog_for_code(items,'CIR-SETUP');self.assertEqual(setup['data']['billing'],'one_time');self.assertEqual(setup['data']['fixed_fee'],'')
    support=catalog_for_code(items,'CIR-SUPPORT');self.assertEqual(support['data']['method'],'percent');self.assertEqual(support['data']['support_percent'],'20')
    for code in ['CIR-INTERNET','CIR-REPLICATION-LINK','CIR-VPN-NODE']:self.assertEqual(catalog_for_code(items,code)['data']['price'],'')
    storage=catalog_for_code(items,'CIR-STORAGE');storage['data'].update(quantity='3',price='91',comments='Customized');store.save(db,'catalog',storage['data'],storage['id']);initialize(db)
    refreshed=store.records(db,unrestricted=True);self.assertEqual(len(items),len(refreshed));self.assertEqual(catalog_for_code(refreshed,'CIR-STORAGE')['data']['quantity'],'3')
    for section in standard_template()['sections']:
     for row in section['rows']:self.assertIsNotNone(catalog_for_code(refreshed,row['item_key'][5:]),row['item_key'])
   app=create_app(root,testing=True);app.config['AUTH_TEST_BYPASS']=True
   with app.test_client() as client:
    html=client.get('/quotes/new').get_data(as_text=True);document=json.loads(re.search(r'id="initial-quotation">(.*?)</script>',html,re.S).group(1))['document']
    rows=[r for s in document['sections'] for r in s['rows']]
    storage=next(r for r in rows if r['sub_service']=='Storage');self.assertEqual((storage['quantity'],storage['unit_price'],storage['comments']),('3','91','Customized'))
    self.assertEqual(next(r for r in rows if r['sub_service']=='One-Time fee')['billing'],'one_time')
 def test_catalog_unknown_foreign_currency_and_equivalent_codes(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);store.migrate(root)
   with store.connect(root) as db:
    values=next(v for v in default_items() if v['code']=='CIR-STORAGE')
    values.update(code='CUSTOM-STORAGE',name='Cirrus Compute',currency='EUR',price='',quantity='7',comments='Keep me')
    ident=store.save(db,'catalog',values);initialize(db);initialize(db)
    items=store.records(db,unrestricted=True);self.assertEqual(len(items),19)
    matched=catalog_for_code(items,'CIR-STORAGE');self.assertEqual(matched['id'],ident)
    self.assertEqual((matched['data']['currency'],matched['data']['price'],matched['data']['quantity']),('EUR','','7'))
 def test_setup_monthly_support_save_copy_pdf_and_excel(self):
  q=quote(status='Draft');prod=q['document']['sections'][0];prod['rows']=[new_row('Compute',quantity='1',unit_price='100')]
  setup=new_section('Connectivity Setup — One-Time Fee');setup['rows']=[new_row('Connectivity Setup',sub_service='One-Time fee',quantity='1',method='fixed',fixed_fee='500',billing='one_time')]
  support=new_section('8×5 Request Fulfillment');support['rows']=[new_row('Managed Services',quantity='1',method='percent',percent='20',targets=['s:'+prod['id']])]
  dr=new_section('Disaster Recovery');dr['rows']=[new_row('DR VM',quantity='1',unit='VM',unit_price='228',dr_mode='replication',dr_percent='50',comments='VM Size: Medium\nOperating system: Linux\nVM Specs: 4 vCPU, 8 GB RAM')]
  q['document']['sections'] += [setup,support,dr];c=calculate(q['document']);self.assertEqual(c['regular'],'234.00');self.assertEqual(c['one_time'],'500.00');self.assertEqual(c['rows'][support['rows'][0]['id']],'20.00')
  broken=copy.deepcopy(q['document']);broken['sections'][2]['rows'][0]['targets'].append('s:'+setup['id'])
  with self.assertRaises(ValidationError):validate_document(broken)
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);app=create_app(root,testing=True);app.config['AUTH_TEST_BYPASS']=True
   with store.connect(root) as db:ident=store.save(db,'quote',q)
   client=app.test_client();client.get('/')
   with client.session_transaction() as sess:csrf=sess['csrf']
   for mode in ['duplicate','revision']:
    self.assertEqual(client.post('/record/'+ident+'/copy/'+mode,data={'csrf':csrf}).status_code,302)
   with store.connect(root) as db:
    for r in store.records(db):
     self.assertEqual(calculate(r['data']['document'])['one_time'],'500.00');self.assertEqual(calculate(r['data']['document'])['regular'],'234.00')
   html=client.get('/quotes/'+ident+'/print').get_data(as_text=True)
   strip=re.search(r'data-computed="category-'+setup['id']+r'">(.*?)</div>',html,re.S).group(1)
   self.assertIn('One-time: $500.00',strip);self.assertNotIn('Monthly:',strip)
   self.assertIn('VM Replication',html);self.assertNotIn('Operating system:',html);self.assertNotIn('Replication ·',html)
   payload=client.get('/quotes/'+ident+'/xlsx').data
   book=load_workbook(io.BytesIO(payload),data_only=True);sheet=book['Quotation']
   row=next(i for i in range(1,sheet.max_row+1) if sheet.cell(i,1).value=='Connectivity Setup');self.assertEqual(sheet.cell(row,7).value,500)
   self.assertIn('One-Time Fee',str([c.value for row in sheet for c in row]))
   rich=load_workbook(io.BytesIO(payload),rich_text=True)
   labels=[c for row in rich['Quotation'] for c in row if 'VM Replication' in str(c.value)]
   self.assertTrue(labels);self.assertTrue(any(getattr(part,'font',None) and part.font.color.rgb=='00C00000' for part in labels[0].value))
   self.assertNotIn('Operating system:',str([c.value for row in sheet for c in row]))
