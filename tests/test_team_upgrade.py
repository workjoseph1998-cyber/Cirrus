from editor_requests import fields_for
import copy,io,json,tempfile,unittest,zipfile
from pathlib import Path
from openpyxl import Workbook,load_workbook
from workspace_app import create_app,store,security
from workspace_app.company import standard_template,catalog_items
from workspace_app.excel_import import parse,load
from workspace_app.quotation import calculate,new_row,new_section,validate_document,public_document
from workspace_app.quote_excel import export_excel
from workspace_app.model import ValidationError
from quotation_fixture import fixture
from test_workspace import data
from test_security import PASSWORD


def workbook(multiple=False,unsupported=False):
    w=Workbook();s=w.active;s.title='Cirrus'
    s['C2']='Synthetic customer';s['C3']='Synthetic contact';s['C4']='Synthetic project';s['H3']='SYNTHETIC-IMPORT'
    s['A6']='Production';headers=['Service','Sub Service','Type','Quantity','Pricing Model','Unit Price','Monthly Fee','Comments']
    s.append([])
    for col,value in enumerate(headers,1):s.cell(7,col,value)
    for col,value in enumerate(['Cirrus Compute','Custom VM','IaaS',2,'Per VM/month',100,'=D8*F8','VM specs'],1):s.cell(8,col,value)
    s['A9']='Backup Services'
    for col,value in enumerate(['Backup as a Service','Managed Backup','BkaaS',1,'Per agent',20,'=D10*F10',''],1):s.cell(10,col,value)
    for col,value in enumerate([None,'Backup Storage','BkaaS',1,'Per TB',5,'=D11*F11',''],1):s.cell(11,col,value)
    s.merge_cells('A10:A11');s['A12']='8×5 Request Fulfillment'
    for col,value in enumerate(['Managed Services','Working hours Support','Support','-','-',None,'=SUM(G8:G11)*0.2','internal basis'],1):s.cell(13,col,value)
    if unsupported:s['G8']='=WEBSERVICE("https://example.invalid")'
    s['A14']='Connectivity Setup — One-Time Fee'
    for col,value in enumerate(['Connectivity Setup','One-time','CaaS',1,'Fixed',None,50,''],1):s.cell(15,col,value)
    s['A16']='Cost Summary';s['A17']='Total Monthly Fee';s['D17']='=SUM(G8:G13)';s['E17']='=D17*12'
    if multiple:w.create_sheet('Other')
    out=io.BytesIO();w.save(out);return out.getvalue()


class ImportEngineTests(unittest.TestCase):
    def test_merged_backup_formula_support_and_no_subtotals(self):
        parsed=parse(workbook());doc=parsed['quotation']['document'];rows=[r for s in doc['sections'] for r in s['rows']]
        self.assertEqual(len(rows),5)
        backup=[r for r in rows if r['type']=='BkaaS'];self.assertEqual(len(backup),2)
        self.assertEqual([r['service'] for r in backup],['Backup as a Service']*2)
        self.assertEqual(calculate(doc)['regular'],'270.00')
        self.assertEqual(calculate(doc)['one_time'],'50.00')
        self.assertTrue(any(i['kind']=='summary' for i in parsed['issues']))

    def test_missing_cache_and_unknown_formula_are_not_zero(self):
        parsed=parse(workbook(unsupported=True));row=next(r for s in parsed['quotation']['document']['sections'] for r in s['rows'] if r['sub_service']=='Custom VM')
        self.assertEqual(row['fixed_fee'],'');self.assertIsNone(calculate(parsed['quotation']['document'])['regular'])
        self.assertTrue(any(i['row_id']==row['id'] and i['kind']=='price' for i in parsed['issues']))

    def test_multiple_sheets_mapping_limits_and_unsupported(self):
        self.assertEqual(load(workbook(True))[0].sheetnames,['Cirrus','Other'])
        with self.assertRaises(ValidationError):parse(workbook(True),'Other')
        parsed=parse(workbook());mapping=parsed['mapping'];mapping['headers']['customer']='ZZ9999'
        with self.assertRaises(ValidationError):parse(workbook(),mapping=mapping)
        with self.assertRaises(ValidationError):load(b'x'*(10*1024*1024+1))
        expanded=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(workbook())) as original,zipfile.ZipFile(expanded,'w') as changed:
            for name in original.namelist():
                content=original.read(name)
                if name=='xl/worksheets/sheet1.xml':content=content.replace(b'A10:A11',b'A10:XFD1048576')
                changed.writestr(name,content)
        with self.assertRaises(ValidationError):load(expanded.getvalue())
        w=Workbook();w.active['A1']='Not a quotation';out=io.BytesIO();w.save(out)
        with self.assertRaises(ValidationError):parse(out.getvalue())

    def test_company_structure_and_support_privacy(self):
        d=standard_template()
        for name in ('Production','Disaster Recovery'):
            top=next(s for s in d['sections'] if s['name']==name)
            children=[s for s in d['sections'] if s['parent']==top['id']]
            self.assertTrue(any(s['name']=='Backup Services' for s in children))
            security_rows=next(s['rows'] for s in children if s['name']=='Security Services')
            self.assertTrue({'Datacenter FW','Perimeter FW','Load Balancer','WAF','EDR'}<={r['sub_service'] for r in security_rows})
        vpn=[x for x in catalog_items() if x['type']=='VPNaaS'];self.assertEqual({x['unit'] for x in vpn},{'user','node'})
        self.assertTrue(all(r['quantity']=='1' and r['unit_price']=='' for s in d['sections'] for r in s['rows']))
        q=fixture();support=next(r for s in q['document']['sections'] for r in s['rows'] if r['type']=='Support')
        support['comments']='INTERNAL-BASIS-SECRET'
        exported=export_excel(q).getvalue();w=load_workbook(io.BytesIO(exported),data_only=False)
        text=' '.join(str(c.value) for sheet in w for row in sheet for c in row)
        self.assertNotIn('INTERNAL-BASIS-SECRET',text)
        support_methods=[row[2].value for row in w['Pricing settings'] if row[0].value and 'Working hours Support' in str(row[0].value)]
        self.assertTrue(all(method=='fixed' for method in support_methods))
        for row in w['Quotation']:
            if row[1].value=='Working hours Support':
                self.assertIsNone(row[5].value);self.assertNotEqual(row[6].data_type,'f')
        for row in w['Quotation']:
            if row[0].value in ('Monthly discount','Discounted monthly total'):self.assertTrue(w['Quotation'].row_dimensions[row[0].row].hidden)


class UpgradeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'data';self.app=create_app(self.root,True)
        with store.connect(self.root) as db:
            self.uid=security.create_user(db,'admin',PASSWORD,'Administrator',True)
            self.other=security.create_user(db,'editor',PASSWORD,'Editor')
        self.c=self.login('admin')
    def tearDown(self):self.temp.cleanup()
    def login(self,name):
        c=self.app.test_client();c.get('/login')
        with c.session_transaction() as s:csrf=s['csrf']
        c.post('/login',data={'csrf':csrf,'username':name,'password':PASSWORD});return c
    def post(self,path,client=None,**fields):
        c=client or self.c
        with c.session_transaction() as s:csrf=s['csrf']
        return c.post(path,data={'csrf':csrf,**fields_for(c,path,fields)})
    def test_catalog_backup_replacement_once_and_template_copy(self):
        with store.connect(self.root) as db:
            old=store.save(db,'catalog',data('catalog',code='OLD',name='Old',unit='day',currency='USD',status='Active'))
            q=fixture();ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=?',(self.uid,))
            before=copy.deepcopy(next(r for r in store.records(db) if r['id']==ident)['data'])
        self.assertEqual(self.post('/catalog-replacement',confirm='REPLACE CATALOG').status_code,302)
        with store.connect(self.root) as db:
            rows=store.records(db);items=[r for r in rows if r['kind']=='catalog']
            self.assertEqual(len(items),len(catalog_items()));self.assertNotIn(old,{r['id'] for r in rows})
            self.assertEqual(next(r for r in rows if r['id']==ident)['data'],before)
        self.assertEqual(len(list((self.root/'backups').glob('*.zip'))),1)
        self.post('/catalog-replacement',confirm='REPLACE CATALOG')
        self.assertEqual(len(list((self.root/'backups').glob('*.zip'))),1)
        self.assertEqual(self.post('/company-template',document=json.dumps(standard_template())).status_code,302)
        first=self.c.get('/quotes/new').data
        self.assertIn(b'Datacenter FW',first);self.assertIn(b'Backup Storage',first)
        with store.connect(self.root) as db:
            from workspace_app.company import load_template
            a=load_template(db);a['sections'][0]['name']='Changed copy';b=load_template(db)
            self.assertEqual(b['sections'][0]['name'],'Production')

    def test_excel_preview_cancel_confirm_duplicates_and_atomicity(self):
        result=self.post('/excel-import',file=(io.BytesIO(workbook(unsupported=True)),'synthetic.xlsx'))
        self.assertEqual(result.status_code,302);path=result.location
        with store.connect(self.root) as db:
            staged=json.loads(db.execute('SELECT data FROM import_jobs').fetchone()[0]);self.assertEqual(store.records(db),[])
        other=self.login('editor');self.assertEqual(other.get(path).status_code,404)
        parsed=staged['parsed'];fields={'action':'confirm','quotation':json.dumps(parsed['quotation']),'mode':'new'}
        # Missing issue decisions cannot partially save a quote.
        self.assertEqual(self.post(path,**fields).status_code,400)
        with store.connect(self.root) as db:self.assertEqual(store.records(db),[])
        for issue in parsed['issues']:fields['resolution-'+issue['id']]='unpriced' if issue['kind']=='price' else 'reviewed'
        result=self.post(path,**fields);self.assertEqual(result.status_code,302,result.data)
        self.assertEqual(self.post(path,**fields).status_code,404)
        with store.connect(self.root) as db:
            rows=store.records(db);self.assertEqual(len(rows),1)
            self.assertEqual(db.execute('SELECT owner_id FROM records').fetchone()[0],self.uid)
        second=self.post('/excel-import',file=(io.BytesIO(workbook(unsupported=True)),'again.xlsx'))
        self.assertIn(b'imported before',self.c.get(second.location).data)
        self.post(second.location,action='cancel')
        with store.connect(self.root) as db:self.assertEqual(len(store.records(db)),1)

    def test_support_hidden_in_customer_html_preview_and_csv_and_demo_mask(self):
        q=fixture();support=next(r for s in q['document']['sections'] for r in s['rows'] if r['type']=='Support')
        support.update(percent='23.75',comments='INTERNAL-ELIGIBILITY-BASIS')
        with store.connect(self.root) as db:
            ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.uid,ident))
        for path in ['/quotes/'+ident+'/print','/quotes/'+ident+'/csv']:
            result=self.c.get(path)
            self.assertEqual(result.status_code,200)
            self.assertNotIn(b'23.75',result.data);self.assertNotIn(b'INTERNAL-ELIGIBILITY-BASIS',result.data)
        preview=self.post('/quotes/preview',quotation=json.dumps(q))
        self.assertNotIn(b'23.75',preview.data);self.assertNotIn(b'INTERNAL-ELIGIBILITY-BASIS',preview.data)
        row=q['document']['sections'][1]['rows'][0]
        row.pop('unverified_price',None);row['comments']='VM Size: Large V1\nOS: manually typed\n[DEMO PRICE — replace before sending]'
        doc=validate_document(q['document']);self.assertIsNone(calculate(doc)['regular'])
        public=public_document(doc)
        copied=public['sections'][1]['rows'][0]
        self.assertEqual(copied['unit_price'],'');self.assertNotIn('DEMO',copied['comments'])
        self.assertIn('OS: manually typed',copied['comments'])
        row.update(method='fixed',fixed_fee='175',unverified_price=True)
        result=self.post('/quotes/catalog',item=json.dumps({'row':row,'code':'UNVERIFIED-FIXED','currency':'USD'}))
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json['item']['data']['fixed_fee'],'')

    def test_redacted_zero_requires_explicit_choice_and_revisions_are_new(self):
        w=load_workbook(io.BytesIO(workbook()));w.active['F8']=0;out=io.BytesIO();w.save(out)
        result=self.post('/excel-import',file=(io.BytesIO(out.getvalue()),'zero.xlsx'));path=result.location
        with store.connect(self.root) as db:parsed=json.loads(db.execute('SELECT data FROM import_jobs').fetchone()[0])['parsed']
        self.assertTrue(parsed['zero_rows'])
        fields={'action':'confirm','quotation':json.dumps(parsed['quotation']),'mode':'new','zero_unpriced':parsed['zero_rows']}
        for issue in parsed['issues']:fields['resolution-'+issue['id']]='reviewed' if issue['kind']!='price' else 'unpriced'
        self.assertEqual(self.post(path,**fields).status_code,400)
        fields['redacted']='yes';self.assertEqual(self.post(path,**fields).status_code,302)
        with store.connect(self.root) as db:
            record=store.records(db)[0];old=copy.deepcopy(record['data']);self.assertIsNone(calculate(old['document'])['regular'])
        again=self.post('/excel-import',file=(io.BytesIO(out.getvalue()),'zero-again.xlsx'))
        with store.connect(self.root) as db:parsed=json.loads(db.execute('SELECT data FROM import_jobs').fetchone()[0])['parsed']
        fields=dict(action='confirm',quotation=json.dumps(parsed['quotation']),mode='revision',revision_of=record['id'],duplicate_ack='yes')
        for issue in parsed['issues']:fields['resolution-'+issue['id']]='reviewed' if issue['kind']!='price' else 'unpriced'
        self.assertEqual(self.post(again.location,**fields).status_code,302)
        with store.connect(self.root) as db:
            records=store.records(db);self.assertEqual(len(records),2)
            self.assertEqual(next(r['data'] for r in records if r['id']==record['id']),old)
            self.assertEqual(sorted(r['data']['revision'] for r in records),[1,2])
