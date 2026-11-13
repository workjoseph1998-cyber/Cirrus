import copy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from openpyxl import load_workbook
from workspace_app import create_app as real_create_app,store
from workspace_app.model import ValidationError,totals
from workspace_app.quotation import calculate,validate_document,new_row,new_section,legacy_document
from workspace_app.quote_excel import export_excel
from quotation_fixture import fixture

def create_app(*args,**kwargs):
    app=real_create_app(*args,**kwargs)
    app.config['AUTH_TEST_BYPASS']=True
    return app



class CalculationTests(unittest.TestCase):
    def setUp(self): self.q=fixture();self.d=self.q['document']

    def test_nonzero_reference_totals(self):
        c=calculate(validate_document(self.d))
        self.assertEqual(c['regular'],'670.00')
        self.assertEqual(c['discount'],'154.20')
        self.assertEqual(c['discounted'],'515.80')
        self.assertEqual(c['yearly'],'7114.80')
        self.assertEqual(c['one_time'],'80.00')
        self.assertEqual(c['tax'],'791.43')
        self.assertEqual(c['combined'],'7986.23')
        cyber=next(s for s in self.d['sections'] if s['name']=='Cyber Security Services')
        self.assertEqual(c['sections'][cyber['id']],'126.00')

    def test_fixed_soc_and_no_discount(self):
        soc=next(r for s in self.d['sections'] for r in s['rows'] if r['service']=='Synthetic SOC')
        soc.update(method='fixed',fixed_fee='100')
        self.assertEqual(calculate(self.d)['regular'],'670.00')
        self.d['discount']['enabled']=False
        self.assertEqual(calculate(self.d)['yearly'],'8040.00')
        self.d['discount'].update(enabled=True,months=0)
        self.assertEqual(calculate(self.d)['discount'],'0.00')

    def test_eligibility_deduplicates_and_rejects_cycles(self):
        support=next(s['rows'][0] for s in self.d['sections'] if s['rows'] and s['rows'][0]['method']=='percent')
        base=next(s for s in self.d['sections'] if 's:'+s['id']==support['targets'][0])
        support['targets'].append('r:'+base['rows'][0]['id'])
        self.assertEqual(calculate(validate_document(self.d))['rows'][support['id']],'55.00')
        support['targets'].append('r:'+support['id'])
        with self.assertRaisesRegex(ValidationError,'Circular'): validate_document(self.d)
        support['targets']=['s:'+next(s['id'] for s in self.d['sections'] if s['name']=='8×5 Request Fulfillment')]
        with self.assertRaisesRegex(ValidationError,'Circular'): validate_document(self.d)

    def test_blank_zero_excluded_included_and_zero_quantity(self):
        s=self.d['sections'][1];r=s['rows'][0]
        for state,qty,price,expected in [('priced','1','',None),('priced','1','0','0.00'),('excluded','1','','0.00'),('included','1','','0.00'),('priced','0','','0.00')]:
            with self.subTest(state=state,qty=qty,price=price):
                r.update(state=state,quantity=qty,unit_price=price)
                self.assertEqual(calculate(self.d)['rows'][r['id']],expected)

    def test_rename_reorder_and_custom_rows_in_every_section(self):
        self.d['discount']['enabled']=False
        for s in self.d['sections']:
            s['rows'].append(new_row('Custom',quantity='1',method='fixed',fixed_fee='1'))
            s['name']='Renamed '+s['name'];s['rows'].reverse()
        self.d['sections'].reverse()
        result=calculate(validate_document(self.d))
        self.assertGreater(float(result['regular']),670)

    def test_invalid_duration_and_missing_dependency(self):
        self.d['discount']['months']=13
        with self.assertRaises(ValidationError):validate_document(self.d)
        self.d['discount']['months']=6;self.d['discount']['targets']=['r:gone']
        with self.assertRaises(ValidationError):validate_document(self.d)

    def test_new_category_has_monthly_yearly_and_one_time_totals(self):
        category=new_section('Development')
        category['rows']=[new_row('Dev VM',quantity='1',unit_price='10'),
                          new_row('Dev setup',quantity='1',method='fixed',fixed_fee='25',billing='one_time')]
        self.d['sections'].append(category)
        c=calculate(validate_document(self.d))
        self.assertEqual(c['sections'][category['id']],'10.00')
        self.assertEqual(c['sections_yearly'][category['id']],'120.00')
        self.assertEqual(c['sections_once'][category['id']],'25.00')
        book=load_workbook(export_excel(self.q),data_only=True)
        summary=next(row for row in book['Quotation'] if row[0].value=='Development' and row[3].value is not None)
        self.assertEqual([str(summary[i].value) for i in (3,4,6)],['10.0','120.0','25.0'])

    def test_tax_modes_and_short_contract(self):
        self.d['contract_months']=6
        self.assertEqual(calculate(self.d)['yearly'],'3094.80')
        self.d['tax']['mode']='exclusive';c=calculate(self.d)
        self.assertEqual(c['combined'],'3174.80')
        self.d['tax']['mode']='included';c=calculate(self.d)
        self.assertEqual(c['combined'],'3174.80')
        self.assertEqual(c['tax'],'314.62')

    def test_excel_formulas_caches_and_privacy(self):
        content=export_excel(self.q).getvalue()
        formulas=load_workbook(io.BytesIO(content),data_only=False)
        values=load_workbook(io.BytesIO(content),data_only=True)
        ws=values['Quotation'];found={row[0].value:str(row[6].value) for row in ws if row[0].value in ('Total monthly fee','Total one-time fee')}
        self.assertEqual(found['Total monthly fee'],'670.0')
        self.assertEqual(found['Total one-time fee'],'80.0')
        # Internal cached calculations remain correct despite removed customer labels.
        self.assertTrue(any(str(row[6].value)=='7986.23' and ws.row_dimensions[row[0].row].hidden for row in ws))
        self.assertTrue(any(c.data_type=='f' for row in formulas['Quotation'] for c in row))
        text=' '.join(str(c.value) for sheet in values for row in sheet for c in row)
        self.assertNotIn('CONFIDENTIAL-NOTE-SENTINEL',text)
        self.assertNotIn('19.37',text)
        self.assertEqual(formulas['Quotation'].page_setup.orientation,'landscape')

    def test_excel_text_is_literal_and_unsupported_precision_is_explicit(self):
        self.q['title']='=HYPERLINK("https://example.invalid")'
        self.q['customer']='=1+1'
        workbook=load_workbook(export_excel(self.q),data_only=False)
        self.assertEqual(workbook['Quotation']['A1'].data_type,'s')
        self.assertEqual(workbook['Quotation']['B3'].data_type,'s')
        self.d['sections'][1]['rows'][0]['unit_price']='0.123456789012345678'
        with self.assertRaisesRegex(ValidationError,'Excel cannot faithfully'):
            export_excel(self.q)


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'data';self.app=create_app(self.root,True)
    def tearDown(self): self.temp.cleanup()

    def test_snapshot_and_short_contract_rendering(self):
        q=fixture()
        q['document']['contract_months']=6
        q['document']['branding']['company']='Original company snapshot'
        q['document']['project_name']='Original project snapshot'
        with store.connect(self.root) as db:
            ident=store.save(db,'quote',q)
            db.execute('INSERT INTO settings VALUES (?,?)',('company','Changed global company'))
        result=self.app.test_client().get('/quotes/'+ident+'/print')
        self.assertEqual(result.status_code,200)
        self.assertIn(b'Original company snapshot',result.data)
        self.assertIn(b'Original project snapshot',result.data)
        self.assertNotIn(b'Changed global company',result.data)
        self.assertIn(b'670.00',result.data)
        self.assertNotIn(b'Contract recurring total',result.data)

    def test_separate_customer_tables_automatic_summary_and_no_edit_controls(self):
        q=fixture()
        category=new_section('Development')
        category['rows']=[new_row('VM',quantity='1',unit_price='10')]
        q['document']['sections'].append(category)
        next(x for x in q['document']['summary'] if x['key']=='sections')['visible']=False
        with store.connect(self.root) as db:ident=store.save(db,'quote',q)
        response=self.app.test_client().get('/quotes/'+ident+'/print')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.data.count(b'class="service-table"'),8)
        self.assertIn(('data-summary-category="'+category['id']+'"').encode(),response.data)
        self.assertIn(b'Development',response.data)
        self.assertNotIn(b'<input',response.data)
        self.assertNotIn(b'Copy row',response.data)
        self.assertNotIn(b'data-action=',response.data)

    def test_save_reopen_duplicate_revision_and_export(self):
        q=fixture()
        with store.connect(self.root) as db: ident=store.save(db,'quote',q)
        client=self.app.test_client();client.get('/')
        with client.session_transaction() as sess:csrf=sess['csrf']
        for mode in ('duplicate','revision'):
            response=client.post('/record/'+ident+'/copy/'+mode,data={'csrf':csrf})
            self.assertEqual(response.status_code,302)
        with store.connect(self.root) as db:
            rows=store.records(db);self.assertEqual(len(rows),3)
            for r in rows:self.assertEqual(r['data']['document'],q['document'])
            exported=store.export_data(db)
        target=Path(self.temp.name)/'other';store.migrate(target)
        with store.connect(target) as db:
            db.execute('BEGIN IMMEDIATE');self.assertEqual(store.apply_import(db,copy.deepcopy(exported)),(3,0))
        response=client.get('/quotes/'+ident+'/print')
        self.assertIn(b'670.00',response.data)
        self.assertNotIn(b'Contract total incl.',response.data)
        self.assertNotIn(b'CONFIDENTIAL-NOTE-SENTINEL',response.data)
        self.assertNotIn(b'19.37',response.data)

    def test_migration_and_legacy_import(self):
        q=fixture();q.pop('document');q.update(number='Q-123456ABCDEF',lines=[dict(description='Legacy',quantity='1',unit='day',price='.105',cost='',discount='10')])
        expected=totals(q['lines'],q['tax'])['grand_total']
        with store.connect(self.root) as db:
            ident=store.save(db,'quote',q);payload=store.export_data(db);payload['version']=1
            db.execute('PRAGMA user_version=1')
        store.migrate(self.root)
        with store.connect(self.root) as db:
            record=store.records(db)[0];self.assertEqual(calculate(record['data']['document'])['combined'],expected)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],18)
            self.assertEqual(store.preview_import(db,payload)[1],1)


if __name__=='__main__':unittest.main()
