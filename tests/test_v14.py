"""V14 account retirement, exact support selections and customer presentation."""
import copy,io,json,re,tempfile,unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch
from flask import g
from openpyxl import load_workbook
from workspace_app import create_app,store,security,approvals as flow
from workspace_app.accounts import deletion_block
from workspace_app.quotation import default_document,new_section,new_row,validate_document,calculate
from workspace_app.quotation_presentation import dollars,price_input,column_heading,EXCEL_DOLLARS
from workspace_app.support import calculation_details
from workspace_app.quote_excel import export_excel
from workspace_app.quote_routes import render_customer
from workspace_app.backup import online_safety_backup,restore
from workspace_app.commercial import fingerprint
import test_v12 as v12
from test_v5 import quote


def support_quote():
    q=quote('V14-SUPPORT',status='Draft');d=q['document']
    production=new_section('Production');monitoring=new_section('Monitoring');connectivity=new_section('Connectivity')
    setup=new_section('Setup');support=new_section('8×5 Request Fulfillment')
    production['rows']=[new_row('Hosting',quantity='2',unit_price='500',item_key='catalog:hosting')]
    monitoring['rows']=[new_row('NOC',quantity='1',unit_price='200')]
    connectivity['rows']=[new_row('Internet',quantity='1',unit_price='100')]
    setup['rows']=[new_row('Activation',quantity='1',fixed_fee='296',method='fixed',billing='one_time')]
    support['rows']=[new_row('Managed Services',sub_service='Working hours Support',type='Support',method='percent',quantity='1',percent='5',targets=['s:'+production['id']])]
    d.update(sections=[production,monitoring,connectivity,setup,support]);d['discount'].update(enabled=False,targets=[])
    q['tax']='0';d['tax'].update(mode='exclusive',rate='0')
    return q


class AccountDeletion(unittest.TestCase):
    setUp=v12.WorkflowTests.setUp;tearDown=v12.WorkflowTests.tearDown
    login=v12.WorkflowTests.login;post=v12.WorkflowTests.post;state=v12.WorkflowTests.state
    raw=v12.WorkflowTests.raw;submit=v12.WorkflowTests.submit;decision=v12.WorkflowTests.decision

    def remove(self,name,**fields):
        return self.post('/accounts/'+self.ids[name]+'/delete',client=self.clients['admin'],**fields)

    def test_confirmation_permissions_self_and_last_admin(self):
        path='/accounts/'+self.ids['ops1']+'/delete'
        page=self.clients['admin'].get(path);self.assertIn(b'ops1',page.data);self.assertIn(b'linked',page.data.lower())
        for name in ['author','viewer']:
            self.assertEqual(self.clients[name].get(path).status_code,403)
            self.assertEqual(self.post(path,client=self.clients[name],confirm='yes',account_name='ops1').status_code,403)
        self.assertEqual(self.remove('ops1').status_code,400)
        self.assertEqual(self.remove('ops1',confirm='yes',account_name='wrong').status_code,400)
        self.assertEqual(self.remove('admin',confirm='yes',account_name='admin').status_code,400)
        with self.app.test_request_context():
            g.user=dict(id=self.ids['author'],role='Administrator')
            with store.connect(self.root) as db:
                target=db.execute('SELECT * FROM users WHERE id=?',(self.ids['admin'],)).fetchone()
                self.assertIn('last active administrator',deletion_block(db,target))
                self.assertEqual(db.execute('SELECT count(*) FROM account_deletions').fetchone()[0],0)

    def test_preserves_records_comments_approval_decisions_and_attribution(self):
        self.submit();self.decision('ops1',comment='Validated technical scope')
        self.post(self.url+'/discussion',client=self.clients['ops1'],body='Preserve this historical author.')
        tables=['records','approval_versions','approval_rounds','approval_reviews','approval_messages','approval_events','record_acl','approval_grants']
        with store.connect(self.root) as db:
            before={name:[tuple(r) for r in db.execute('SELECT * FROM '+name)] for name in tables}
        for name in ['ops1','author']:
            self.assertEqual(self.remove(name,confirm='yes',account_name=name).status_code,302)
        with store.connect(self.root) as db:
            for name in tables:self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM '+name)],before[name],name)
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())
            review=flow.decisions(db,flow.current_round(db,self.ident)['id'])[0]
            self.assertEqual(review['username'],'ops1');self.assertEqual(review['decision'],'Approved')
            self.assertEqual(db.execute('SELECT owner_id FROM records WHERE id=?',(self.project,)).fetchone()[0],self.ids['author'])
        poll=self.clients['admin'].get(self.url+'/approval/poll').json
        self.assertEqual(poll['messages'][0]['username'],'ops1');self.assertEqual(poll['progress']['approved'],1)
        self.assertEqual(self.clients['ops1'].get(self.url+'/edit').location,'/login')
        self.assertEqual(self.clients['author'].get(self.url+'/edit').location,'/login')
        self.assertEqual(self.clients['admin'].get(self.url+'/edit').status_code,200)
        self.assertEqual(self.clients['admin'].get('/record/'+self.project).status_code,200)
        access=self.clients['admin'].get('/record/'+self.project+'/access').data
        self.assertIn(b'Keep current owner: author',access)
        self.assertEqual(self.post('/record/'+self.project+'/access',client=self.clients['admin'],owner='',**{self.ids['ops2']:'edit'}).status_code,302)
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT owner_id FROM records WHERE id=?',(self.project,)).fetchone()[0],self.ids['author'])

    def test_cannot_restore_login_reenable_reset_reuse_name_and_backup_retains_identity(self):
        self.assertEqual(self.remove('ops1',confirm='yes',account_name='ops1').status_code,302)
        for action in ['access','reset']:
            self.assertEqual(self.post('/accounts',client=self.clients['admin'],action=action,id=self.ids['ops1'],active='yes',role='Administrator',password=v12.PASSWORD).status_code,404)
        self.assertEqual(self.clients['admin'].get('/accounts/'+self.ids['ops1']+'/delete').status_code,404)
        page=self.clients['admin'].get('/accounts').data;self.assertNotIn(('/accounts/'+self.ids['ops1']+'/delete').encode(),page)
        anonymous=self.app.test_client();anonymous.get('/login')
        self.assertEqual(self.post('/login',client=anonymous,username='ops1',password=v12.PASSWORD).status_code,400)
        self.assertEqual(self.post('/accounts',client=self.clients['admin'],action='create',username='ops1',password=v12.PASSWORD,role='Editor').status_code,200)
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM users WHERE username=?',('ops1',)).fetchone()[0],1)
        backup=Path(self.temp.name)/'full.zip';online_safety_backup(self.root,backup);target=Path(self.temp.name)/'restored';restore(backup,target)
        with store.connect(target) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM account_deletions').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT username,active FROM users WHERE id=?',(self.ids['ops1'],)).fetchone()[:],('ops1',0))

    def test_concurrent_administrators_cannot_delete_each_other_and_leave_no_admin(self):
        for index,second_action in enumerate(['delete','disable']):
            if index:self.tearDown();self.setUp()
            with store.connect(self.root) as db:self.ids['otheradmin']=security.create_user(db,'otheradmin',v12.PASSWORD,'Administrator')
            self.clients['otheradmin']=self.login('otheradmin')
            def remove(pair):
                sender,target=pair
                if sender=='otheradmin' and second_action=='disable':
                    return self.post('/accounts',client=self.clients[sender],action='access',id=self.ids[target],role='Administrator',active='').status_code
                return self.post('/accounts/'+self.ids[target]+'/delete',client=self.clients[sender],confirm='yes',account_name=target).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(remove,[('admin','otheradmin'),('otheradmin','admin')]))
            with store.connect(self.root) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM users WHERE active=1 AND role='Administrator'").fetchone()[0],1)
                self.assertLessEqual(db.execute('SELECT count(*) FROM account_deletions').fetchone()[0],1)


class SupportAndPresentation(unittest.TestCase):
    def setUp(self):self.q=support_quote();self.d=self.q['document'];self.fee=self.d['sections'][-1]['rows'][0]

    def test_one_multiple_overlapping_services_and_recalculation(self):
        self.assertEqual(calculate(validate_document(self.d))['rows'][self.fee['id']],'50.00')
        self.fee['targets']+=['s:'+self.d['sections'][2]['id'],'r:'+self.d['sections'][0]['rows'][0]['id']]
        self.fee['support_keys']=['catalog:hosting']
        calc=calculate(validate_document(self.d));self.assertEqual(calc['rows'][self.fee['id']],'55.00')
        detail=calculation_details(self.d,calc)[self.fee['id']];self.assertEqual(detail['base'],'1100.00');self.assertEqual(len(detail['services']),2)
        self.fee['percent']='10';self.d['sections'][0]['rows'][0].update(quantity='3',unit_price='600')
        self.assertEqual(calculate(self.d)['rows'][self.fee['id']],'190.00')
        self.d['sections'][2]['excluded']=True;self.assertEqual(calculate(self.d)['rows'][self.fee['id']],'180.00')
        self.fee['targets']=['s:'+self.d['sections'][1]['id']];self.fee['support_keys']=[]
        self.assertEqual(calculate(self.d)['rows'][self.fee['id']],'20.00')

    def test_missing_zero_self_and_billing_safety(self):
        row=self.d['sections'][0]['rows'][0];row['unit_price']=''
        self.assertIsNone(calculate(self.d)['rows'][self.fee['id']]);self.assertIsNone(calculation_details(self.d,calculate(self.d))[self.fee['id']]['base'])
        row['unit_price']='0';self.assertEqual(calculate(self.d)['rows'][self.fee['id']],'0.00')
        self.fee['targets']=['r:'+self.fee['id']]
        with self.assertRaisesRegex(ValueError,'Circular'):validate_document(self.d)
        self.fee['targets']=['s:'+self.d['sections'][-1]['id']]
        with self.assertRaisesRegex(ValueError,'Circular'):validate_document(self.d)
        self.fee['targets']=['s:'+self.d['sections'][3]['id']]
        with self.assertRaisesRegex(ValueError,'billing period'):validate_document(self.d)

    def test_historical_configuration_totals_and_default_approval_hash_unchanged(self):
        self.d.pop('fee_headings');before=copy.deepcopy(self.q);calc=calculate(self.d)
        checked=validate_document(self.d);self.assertEqual(calculate(checked),calc)
        self.assertEqual(checked['sections'],self.d['sections']);self.assertEqual(self.q,before)
        normalized=copy.deepcopy(self.q);normalized['document']=checked
        self.assertEqual(fingerprint(flow.content(normalized)),fingerprint(flow.content(before)))
        normalized['document']['fee_headings']['monthly']='Monthly amount'
        self.assertNotEqual(fingerprint(flow.content(normalized)),fingerprint(flow.content(before)))

    def test_custom_headings_customer_output_dollars_and_no_internal_base(self):
        for c in self.d['columns']:
            if c['key']=='unit_price':c['label']='Unit Price (USD)'
        with tempfile.TemporaryDirectory() as td:
            app=create_app(Path(td)/'data',True)
            with app.test_request_context():
                g.user=None
                html=render_customer(self.q)
                self.assertIn('>Unit Price</th>',html);self.assertIn('>Monthly Fee</th>',html);self.assertIn('>One-Time Fee</th>',html)
                self.assertNotIn('(USD)',html);self.assertIn('$500.00',html);self.assertIn('$296.00',html);self.assertIn('$50.00',html)
                self.assertNotIn('support-calculations',html);self.assertNotIn('1100.00',html);self.assertNotIn('catalog:hosting',html)
                self.d['fee_headings'].update(monthly='Recurring charge',one_time='Activation charge')
                next(c for c in self.d['columns'] if c['key']=='unit_price')['label']='Price per service'
                html=render_customer(self.q)
                for value in ['Recurring charge','Activation charge','Price per service']:self.assertIn(value,html)
                self.assertIn('summary-regular',html);self.assertNotIn('Contract recurring total',html)
                preview=render_customer(self.q,False);self.assertNotIn('support-calculations',preview);self.assertIn('currency-input',preview)
        self.assertEqual(dollars('296'),'$296.00');self.assertEqual(dollars('0'),'$0.00');self.assertEqual(dollars(None),'Unpriced');self.assertEqual(price_input('0.0125'),'0.0125')

    def test_excel_numeric_drivers_cached_amounts_custom_headers_and_entire_red_row(self):
        self.d['fee_headings'].update(monthly='Recurring charge',one_time='Activation charge')
        next(c for c in self.d['columns'] if c['key']=='unit_price')['label']='Rate'
        book=load_workbook(export_excel(self.q));values=load_workbook(export_excel(self.q),data_only=True);sheet=book['Quotation']
        hosting=next(r for r in sheet if r[0].value=='Hosting');n=hosting[0].row
        self.assertIsInstance(hosting[5].value,(int,float));self.assertEqual(hosting[5].number_format,EXCEL_DOLLARS)
        self.assertEqual(hosting[6].data_type,'f');self.assertEqual(hosting[6].number_format,EXCEL_DOLLARS);self.assertEqual(values['Quotation'].cell(n,7).value,1000)
        fee=next(r for r in sheet if r[0].value=='Managed Services');self.assertIsInstance(fee[6].value,(int,float));self.assertEqual(fee[6].number_format,EXCEL_DOLLARS);self.assertIsNone(fee[5].value)
        headings=[c.value for row in sheet for c in row if c.data_type!='f']
        for title in ['Rate','Recurring charge','Activation charge']:self.assertIn(title,headings)
        self.assertFalse(any(isinstance(v,str) and '(USD)' in v for v in headings))
        monthly=next(r for r in sheet if r[0].value=='Total monthly fee')
        for cell in monthly[:8]:
            self.assertEqual(cell.fill.fgColor.rgb,'00C00000');self.assertEqual(cell.font.color.rgb,'00FFFFFF');self.assertTrue(cell.font.bold)
        self.assertNotIn('support_keys',str(headings));self.assertNotIn('catalog:hosting',str(headings))

    def test_discounted_totals_keep_red_white_styling_and_numeric_amounts(self):
        self.d['discount'].update(enabled=True,show_summary=True,duration='full',billing='monthly',percent='10',targets=['s:'+self.d['sections'][0]['id']])
        sheet=load_workbook(export_excel(self.q))['Quotation']
        total=[r for r in sheet if not sheet.row_dimensions[r[0].row].hidden and str(r[0].value or '').startswith('Total monthly fee')]
        self.assertTrue(total)
        for row in total:
            for cell in [row[0],row[6],row[7]]:self.assertEqual(cell.fill.fgColor.rgb,'00C00000');self.assertEqual(cell.font.color.rgb,'00FFFFFF');self.assertTrue(cell.font.bold)


class SavedQuotation(unittest.TestCase):
    setUp=v12.WorkflowTests.setUp;tearDown=v12.WorkflowTests.tearDown
    login=v12.WorkflowTests.login;post=v12.WorkflowTests.post;state=v12.WorkflowTests.state
    raw=v12.WorkflowTests.raw;edit=v12.WorkflowTests.edit

    def test_save_reopen_duplicate_revision_and_customer_exports_keep_base_and_headings(self):
        chosen=support_quote()['document'];chosen['fee_headings'].update(monthly='Recurring charge',one_time='Setup charge')
        chosen['sections'][-1]['rows'][0]['targets'].append('s:'+chosen['sections'][2]['id'])
        self.assertEqual(self.edit(lambda q:q.update(document=chosen)).status_code,302)
        saved=self.raw();self.assertEqual(calculate(saved['document'])['rows'][chosen['sections'][-1]['rows'][0]['id']],'55.00')
        page=self.c.get(self.url+'/edit');initial=json.loads(re.search(rb'id="initial-quotation">(.*?)</script>',page.data,re.S)[1])
        self.assertEqual(initial['document']['sections'],chosen['sections']);self.assertEqual(initial['document']['fee_headings'],chosen['fee_headings'])
        for mode in ['duplicate','revision']:
            result=self.post('/record/'+self.ident+'/copy/'+mode);self.assertEqual(result.status_code,302)
            ident=result.location.rsplit('/',1)[-1]
            with store.connect(self.root) as db:
                q=json.loads(db.execute('SELECT data FROM records WHERE id=?',(ident,)).fetchone()[0])
                self.assertEqual(q['document']['sections'],chosen['sections']);self.assertEqual(q['document']['fee_headings'],chosen['fee_headings'])
        preview=self.post('/quotes/preview',quotation=json.dumps(saved),source_quote=self.ident,editor_calculations='yes');self.assertEqual(preview.status_code,200);self.assertEqual(preview.json['fees'][chosen['sections'][-1]['rows'][0]['id']]['base'],'1100.00');self.assertNotIn('support-calculations',preview.json['html'])
        printed=self.c.get(self.url+'/print').data;self.assertIn(b'Recurring charge',printed);self.assertIn(b'$55.00',printed)
        csv=self.c.get(self.url+'/csv').data;self.assertIn(b'Recurring charge',csv);self.assertIn(b'Setup charge',csv);self.assertNotIn(b'$55.00',csv)
        sheet=load_workbook(io.BytesIO(self.c.get(self.url+'/xlsx').data))['Quotation'];self.assertIn('Recurring charge',[c.value for r in sheet for c in r])


if __name__=='__main__':unittest.main()
