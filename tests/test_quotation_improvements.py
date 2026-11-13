import copy,io,tempfile,unittest
from pathlib import Path
from decimal import Decimal
from openpyxl import load_workbook
from workspace_app import store
from workspace_app.quotation import default_document,new_row,validate_document,calculate,duplicate_document
from workspace_app.model import ValidationError
from workspace_app.quotation_defaults import initialize
from workspace_app.calculation_explanations import explanations

class Improvements(unittest.TestCase):
 def doc(self):
  d=default_document();d['sections']=d['sections'][:3];d['discount']['targets']=[]
  for s in d['sections']:s['rows']=[]
  return d
 def test_dr_decimal_links_override_and_duplicate(self):
  d=self.doc();prod=d['sections'][0];prod['name']='Production';dr=d['sections'][1];dr.update(name='Disaster Recovery',parent='');d['sections']= [prod,dr]
  base=new_row('VM',quantity='1',unit='VM',unit_price='228')
  replica=new_row('VM',quantity='1',unit='VM',unit_price='228',dr_mode='replication',dr_percent='50',dr_link=base['id'])
  prod['rows']=[base];dr['rows']=[replica]
  d=validate_document(d);self.assertEqual(calculate(d)['regular'],'342.00')
  base=d['sections'][0]['rows'][0];replica=d['sections'][1]['rows'][0]
  base['unit_price']='300';d=validate_document(d);self.assertEqual(calculate(d)['rows'][replica['id']],'150.00')
  replica=d['sections'][1]['rows'][0];replica.update(dr_override=True,unit_price='228',quantity='2',dr_percent='75');self.assertEqual(calculate(d)['rows'][replica['id']],'342.00')
  replica.update(dr_mode='running',dr_percent='100',quantity='1');self.assertEqual(calculate(d)['rows'][replica['id']],'228.00')
  duplicate=duplicate_document(d);self.assertNotEqual(duplicate['sections'][0]['rows'][0]['id'],base['id']);self.assertEqual(duplicate['sections'][1]['rows'][0]['dr_link'],duplicate['sections'][0]['rows'][0]['id'])
  self.assertEqual(calculate(duplicate)['regular'],calculate(d)['regular'])
 def test_minimum_legacy_and_explanations(self):
  d=self.doc();soc=new_row('Security',sub_service='SOC',quantity='1',unit_price='5',minimum_quantity='250');d['sections'][0]['rows']=[soc]
  validate_document(d)
  with self.assertRaises(ValidationError):validate_document(d,enforce_minimum=True)
  soc['quantity']='250';validate_document(d,enforce_minimum=True);self.assertEqual(calculate(d)['regular'],'1250.00')
  noc=new_row('NOC',quantity='50',unit_price='20',minimum_quantity='50');d['sections'][0]['rows'].append(noc);self.assertEqual(calculate(d)['regular'],'2250.00')
  storage=new_row('Storage',quantity='2',unit='TB',unit_price='83');d['sections'][0]['rows'].append(storage)
  self.assertIn('Calculation: 2 × $83.00 = $166.00/month',explanations(d)[storage['id']])
  del soc['minimum_quantity'];soc['quantity']='1';legacy=validate_document(d,enforce_minimum=True);self.assertEqual(calculate(legacy)['rows'][soc['id']],'5.00')
 def test_excel_cached_totals_and_explicit_link_formula(self):
  from test_v5 import quote
  from workspace_app.quote_excel import export_excel
  q=quote(status='Draft');d=q['document'];prod=d['sections'][0];prod['rows']=[new_row('Production VM',unit='VM',quantity='1',unit_price='228')]
  from workspace_app.quotation import new_section
  dr=new_section('Disaster Recovery');row=new_row('DR VM',unit='VM',quantity='1',unit_price='228',dr_mode='replication',dr_percent='50',dr_link=prod['rows'][0]['id']);dr['rows']=[row];d['sections'].append(dr)
  payload=export_excel(q).getvalue();values=load_workbook(io.BytesIO(payload),data_only=True);formulas=load_workbook(io.BytesIO(payload),data_only=False)
  sheet=values['Quotation'];n=next(i for i in range(1,sheet.max_row+1) if sheet.cell(i,1).value=='DR VM')
  self.assertEqual(sheet.cell(n,6).value,228);self.assertEqual(sheet.cell(n,7).value,114)
  self.assertTrue(formulas['Quotation'].cell(n,6).value.startswith('=F'))
  self.assertIn('Pricing settings',formulas['Quotation'].cell(n,7).value)
  self.assertIn('Replication',sheet.cell(n,8).value)
 def test_catalog_idempotency_and_custom_price(self):
  with tempfile.TemporaryDirectory() as td:
   store.migrate(Path(td))
   with store.connect(Path(td)) as db:
    initialize(db);initial=store.records(db,unrestricted=True);initialize(db)
    self.assertEqual(len(initial),len(store.records(db,unrestricted=True)))
    storage=next(r for r in initial if r['data']['code']=='CIR-STORAGE');data=storage['data'];data['price']='99';store.save(db,'catalog',data,storage['id']);initialize(db)
    self.assertEqual(next(r for r in store.records(db,unrestricted=True) if r['id']==storage['id'])['data']['price'],'99')
