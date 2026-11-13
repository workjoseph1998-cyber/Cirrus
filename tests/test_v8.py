from editor_requests import fields_for
"""Synthetic Version 8 storage, pricing, contract, consumption and archive checks."""
import copy
import io
import json
import re
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook
from workspace_app import create_app, store, security, relationships as rel, archives, outcomes, statistics
from workspace_app.backup import backup, restore
from workspace_app.commercial import amount, line_values
from workspace_app.model import FIELDS, ValidationError
from workspace_app.quotation import default_document, new_row, new_section, calculate, validate_document
from workspace_app.quote_excel import export_excel
from test_v5 import quote

PASSWORD='Synthetic-test-password-2026'
TABLES=('agreed_prices','price_history','contracts','contract_documents','consumption','consumption_history','quotation_archives','archive_history')


def discount_quote(kind='percent', value='10'):
    q=quote();s=new_section('Services',id='services');s['rows']=[new_row('Monthly service',id='monthly',quantity='2',unit_price='100',discount='10'),new_row('Setup',id='setup',quantity='2',unit_price='50',billing='one_time')]
    d=q['document'];d.update(sections=[s],contract_months=3);d['tax'].update(mode='exclusive',rate='0')
    d['discount'].update(enabled=True,show_summary=True,kind=kind,percent=value if kind=='percent' else '0',amount=value if kind=='fixed' else '0',billing='both',duration='temporary',months=2,targets=['s:services']);return q


class V8Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'data';self.app=create_app(self.root,True)
        with store.connect(self.root) as db:
            self.admin=security.create_user(db,'admin',PASSWORD,'Administrator',True)
            self.editor=security.create_user(db,'editor',PASSWORD,'Editor');self.viewer=security.create_user(db,'viewer',PASSWORD,'Viewer')
            self.customer=store.save(db,'customer',dict(name='Synthetic Bank',contact='Synthetic contact',notes=''))
            d={k:'' for k,_,_ in FIELDS['project']};d.update(name='Cloud project',customer='Legacy bank text',customer_id=self.customer,status='Active');self.project=store.save(db,'project',d)
            d={k:'' for k,_,_ in FIELDS['catalog']};d.update(code='SYN-CPU',name='Synthetic compute',description='Compute',unit='VM',price='100',currency='USD',status='Active',billing='monthly',method='unit',quantity='1',discount='0');self.catalog=store.save(db,'catalog',d)
            self.vm=db.execute('SELECT id FROM hosting_vms LIMIT 1').fetchone()[0]
        self.c=self.login('admin')
    def tearDown(self):self.temp.cleanup()
    def login(self,user):
        c=self.app.test_client();c.get('/login')
        with c.session_transaction() as s:token=s['csrf']
        self.assertEqual(c.post('/login',data=dict(csrf=token,username=user,password=PASSWORD)).status_code,302);return c
    def post(self,path,client=None,**values):
        client=client or self.c
        with client.session_transaction() as s:token=s['csrf']
        return client.post(path,data=dict(csrf=token,**fields_for(client,path,values)))
    def create_quote(self,q=None):
        q=copy.deepcopy(q or quote());q.update(project_id=self.project,customer_id=self.customer)
        r=self.post('/quotes/new',quotation=json.dumps(q));self.assertEqual(r.status_code,302,r.data[:1000]);return r.location.split('/')[-2]
    def record(self,ident):
        with store.connect(self.root) as db:return rel.record(db,ident)
    def price(self,scope=None,item=None,**changes):
        d=dict(item_key=item or 'catalog:'+self.catalog,billing='monthly',currency='USD',price='80',start='',finish='',notes='Agreed rate',reason='Annual agreement',active='yes');d.update(changes)
        return self.post('/prices/'+(scope or self.customer),**d)
    def resolved(self,project=True,**args):
        values=dict(currency='USD',date='2026-10-29');values.update(dict(project_id=self.project) if project else dict(customer_id=self.customer));values.update(args)
        r=self.c.get('/pricing/options',query_string=values);self.assertEqual(r.status_code,200,r.data[:500]);return r.json['prices']
    def contract(self,services=None,**changes):
        d=dict(reference='CON-SYN-001',currency='USD',start='2026-01-01',end='2027-12-31',renewal='2026-11-20',notes='',initial_quote_id='',accepted_quote_id='',services=services or [dict(id='cpu',service='Compute',quantity='2',unit_price='100',discount='10',billing='monthly',basis='fixed',method='unit',notes='',item_key='catalog:'+self.catalog),dict(id='storage',service='Storage',quantity='1',unit_price='50',discount='0',billing='monthly',basis='actual',method='unit',notes='',item_key=''),dict(id='install',service='Installation',quantity='1',unit_price='200',discount='0',billing='one_time',basis='fixed',method='fixed',notes='',item_key='')]);d.update(changes);return d
    def save_contract(self,d=None,action='save',version=None,**changes):
        if version is None:
            with store.connect(self.root) as db:c=rel.latest_contract(db,self.project);version=c['version'] if c else 0
        return self.post('/projects/'+self.project+'/commercial',contract=json.dumps(d or self.contract()),version=str(version),action=action,confirm='yes',**changes)
    def current_contract(self):
        with store.connect(self.root) as db:return rel.latest_contract(db,self.project)
    def save_consumption(self,month='2026-10',actuals=None,**changes):
        with store.connect(self.root) as db:sheet=rel.consumption_data(db,self.project,month)
        d=dict(month=month,version=str(sheet['version']),contract_id=sheet['contract_id'],consumption=json.dumps(dict(actuals=actuals or {'cpu':'3','storage':'4'},notes='Synthetic month')));d.update(changes)
        return self.post('/projects/'+self.project+'/consumption',**d)
    def won(self,ident):
        q=self.record(ident)['data']
        with store.connect(self.root) as db:s=outcomes.get(db,q['number'].casefold())
        return self.post('/quotes/'+ident+'/outcome',version=str(s['version']),status='Won',reason='Technical solution',notes='',outcome_date='2026-10-29',accepted_quote_id=ident)
    def bulk(self,refs,action='archive',confirm=False,client=None):
        r=self.post('/quotes/bulk',client=client,action=action,references=refs)
        if not confirm:return r
        digest=re.search(rb'name="selection_hash" value="([^"]+)"',r.data)
        self.assertIsNotNone(digest,r.data[:1000])
        return self.post('/quotes/bulk',client=client,action=action,references=refs,selection_mode='individual',selection_hash=digest[1].decode(),confirm='yes')

    def test_additive_schema6_migration_preserves_raw_data_attachments_and_owners(self):
        ident=self.create_quote()
        with store.connect(self.root) as db:
            before=[tuple(r) for r in db.execute('SELECT * FROM records ORDER BY id')]
            for table in reversed(TABLES):db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=6')
        store.migrate(self.root)
        with store.connect(self.root) as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM records ORDER BY id')],before)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],18)
        self.assertEqual(self.record(self.project)['data']['customer'],'Legacy bank text')

    def test_pricing_precedence_dates_zero_currency_and_saved_snapshot(self):
        key='catalog:'+self.catalog
        self.assertEqual(self.resolved()[key]['price'],'100');self.assertEqual(self.price().status_code,302)
        self.assertEqual(self.resolved()[key]['source'],'Customer agreed price');self.assertEqual(self.resolved()[key]['price'],'80.00')
        self.assertEqual(self.price(self.project,price='0',start='2026-10-01',finish='2026-10-31').status_code,302)
        self.assertEqual(self.resolved()[key]['price'],'0.00');self.assertEqual(self.resolved(date='2026-11-01')[key]['price'],'80.00')
        self.assertEqual(self.resolved(currency='EUR')[key]['price'],'')
        q=quote();row=q['document']['sections'][0]['rows'][0];row.update(unit_price='0',item_key=key,price_source='Project agreed price');ident=self.create_quote(q)
        self.price(self.project,price='110',start='2027-01-01');self.assertEqual(self.record(ident)['data']['document']['sections'][0]['rows'][0]['unit_price'],'0')
        self.assertEqual(self.price(self.project,price='200',start='2026-10-29').status_code,400)
        self.assertEqual(self.c.get('/prices/'+self.customer).status_code,200)

    def test_vm_os_prices_use_same_precedence_and_are_separate(self):
        linux='vm:'+self.vm+':a';windows='vm:'+self.vm+':b'
        self.price(item=linux,price='90');self.price(item=windows,price='125')
        resolved=self.resolved();self.assertEqual(resolved[linux]['price'],'90.00');self.assertEqual(resolved[windows]['price'],'125.00')
        self.price(self.project,item=windows,price='120');self.assertEqual(self.resolved()[windows]['source'],'Project agreed price')

    def test_price_history_stale_save_and_atomic_overlap(self):
        self.price()
        with store.connect(self.root) as db:p=rel.price_rows(db,self.customer)[0]
        self.assertEqual(self.price(id=p['id'],version='1',price='75',reason='Revised negotiation').status_code,302)
        self.assertEqual(self.price(id=p['id'],version='1',price='65').status_code,400)
        page=self.c.get('/prices/'+self.customer);self.assertIn(b'Revised negotiation',page.data);self.assertIn(b'80.00',page.data);self.assertIn(b'75.00',page.data)
        def add():
            try:
                with store.connect(self.root) as db:
                    db.execute('BEGIN IMMEDIATE');rel.save_price(db,self.project,dict(item_key='catalog:'+self.catalog,billing='monthly',currency='USD',price='50',reason='Concurrent agreement'))
                return 'ok'
            except ValidationError:return 'blocked'
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:add(),range(2)))
        self.assertCountEqual(results,['ok','blocked'])

    def test_contract_upload_approval_history_and_explicit_accepted_copy(self):
        ident=self.create_quote();self.assertEqual(self.won(ident).status_code,302)
        self.assertEqual(self.save_contract(self.contract(initial_quote_id=ident,accepted_quote_id=ident),action='copy').status_code,302)
        c=self.current_contract();self.assertEqual(c['status'],'Proposed');self.assertTrue(c['data']['services'])
        result=self.post('/contracts/'+c['id']+'/documents',file=(io.BytesIO(b'%PDF-1.4\nSynthetic signed contract'),'signed.pdf'),label='Signed contract');self.assertEqual(result.status_code,302)
        self.assertEqual(self.current_contract()['status'],'Proposed')
        self.assertEqual(self.save_contract(c['data'],action='approve').status_code,302)
        self.assertEqual(self.current_contract()['status'],'Approved')
        with store.connect(self.root) as db:
            self.assertEqual(len(rel.contract_rows(db,self.project)),2);attachment=db.execute('SELECT attachment_id FROM contract_documents LIMIT 1').fetchone()[0]
            self.assertEqual(db.execute('SELECT COUNT(*) FROM contract_documents').fetchone()[0],2)
        self.assertEqual(self.post('/attachment/'+attachment+'/delete').status_code,400)
        self.assertEqual(self.post('/record/'+ident+'/delete').status_code,400)
        self.assertEqual(self.c.get('/projects/'+self.project+'/commercial').status_code,200)
        self.assertEqual(self.save_contract(version=0).status_code,400)
        self.assertEqual(self.post('/projects/'+self.project+'/commercial',contract=json.dumps(c['data']),version='2',action='approve').status_code,400)

    def test_consumption_fixed_actual_copy_and_price_snapshots(self):
        # Historical calculation remains usable for handover; the portal is retired.
        self.save_contract(action='approve')
        with store.connect(self.root) as db:
            saved=rel.consumption_data(db,self.project,'2026-10')
            self.assertEqual(len(saved['data']['rows']),2)
        self.assertEqual(self.save_consumption().status_code,410)
        self.assertEqual(self.c.get('/projects/'+self.project+'/consumption?month=2026-10').status_code,410)
        self.assertEqual(self.c.get('/customers/'+self.customer).status_code,200)

    def test_contract_and_price_permissions_and_document_download(self):
        self.save_contract(action='approve');c=self.current_contract()
        self.post('/contracts/'+c['id']+'/documents',file=(io.BytesIO(b'%PDF-1.4 synthetic'),'signed.pdf'))
        with store.connect(self.root) as db:a=db.execute('SELECT id FROM attachments').fetchone()[0]
        editor=self.login('editor');viewer=self.login('viewer')
        for client in (editor,viewer):
            for path in ['/prices/'+self.project,'/projects/'+self.project+'/commercial','/projects/'+self.project+'/consumption','/attachment/'+a,'/customers/'+self.customer]:self.assertEqual(client.get(path).status_code,410 if '/consumption' in path else 404,path)
        self.post('/record/'+self.project+'/access',**{self.editor:'read',self.viewer:'read'})
        self.assertEqual(editor.get('/projects/'+self.project+'/commercial').status_code,200)
        self.assertEqual(self.price(self.project,reason='No write access').status_code,302)
        self.assertEqual(self.post('/prices/'+self.project,client=editor,item_key='catalog:'+self.catalog).status_code,404)
        with viewer.get('/attachment/'+a) as response:self.assertEqual(response.status_code,200)
        self.assertEqual(editor.get('/customers/'+self.customer).status_code,404)
        # Project access allows its inherited selling prices without granting the
        # customer's documents or other projects.
        self.price();r=editor.get('/pricing/options',query_string=dict(project_id=self.project,date='2026-10-29',currency='USD'));self.assertEqual(r.status_code,200)

    def test_summary_percentage_net_basis_one_time_temporary_and_costing_reconcile(self):
        q=discount_quote();c=calculate(validate_document(q['document']))
        self.assertEqual(c['regular'],'180.00');self.assertEqual(c['discount'],'18.00');self.assertEqual(c['discounted'],'162.00');self.assertEqual(c['one_time_discount'],'10.00');self.assertEqual(c['combined'],'594.00')
        self.assertEqual(sum(line_values(q).values()),Decimal('594.00'))
        q['document']['tax'].update(mode='included',rate='10');c=calculate(q['document']);self.assertEqual(sum(line_values(q).values()),Decimal(c['term'])+Decimal(c['one_time'])-Decimal(c['tax']))
        q['document']['discount'].update(duration='full',billing='one_time');self.assertEqual(calculate(q['document'])['term'],'540.00')

    def test_fixed_budget_caps_and_cent_tiers_never_negative(self):
        q=discount_quote('fixed','50');c=calculate(q['document']);self.assertEqual(c['combined'],'590.00');self.assertEqual(c['recurring_discount_total'],'39.13');self.assertEqual(c['one_time_discount'],'10.87');self.assertEqual(c['discount_extra_months'],'1');self.assertEqual(sum(line_values(q).values()),Decimal('590.00'))
        q['document']['discount']['amount']='9999';c=calculate(q['document']);self.assertEqual(c['term'],'180.00');self.assertEqual(c['one_time'],'0.00')
        q['document']['contract_months']=1200;q['document']['discount'].update(amount='11.99',billing='monthly',duration='full',months=0)
        q['document']['sections'][0]['rows'][0].update(quantity='1',unit_price='.01',discount='0');c=calculate(q['document']);self.assertGreaterEqual(Decimal(c['discounted']),0);self.assertEqual(c['discount_extra_months'],'1199')

    def test_customer_metadata_layout_discount_opt_in_and_private_export(self):
        q=discount_quote();q['valid_until']='2026-12-01';ident=self.create_quote(q)
        html=self.c.get('/quotes/'+ident+'/print').data.decode();meta=html.split('class="header-fields header-right"')[1].split('</div>')[0]
        for omitted in ('Revision','Valid until','Currency','Rev '):self.assertNotIn(omitted,meta)
        self.assertIn('Ref',meta);self.assertIn('summary-discount',html);self.assertIn('promotional',html);self.assertIn('Regular monthly fee afterward',html)
        book=load_workbook(io.BytesIO(self.c.get('/quotes/'+ident+'/xlsx').data),data_only=True);sheet=book['Quotation']
        labels={r[0].value for r in sheet};self.assertNotIn('Validity',labels);self.assertNotIn('Revision',{sheet.cell(n,5).value for n in range(1,6)});self.assertNotIn('Currency',{sheet.cell(n,5).value for n in range(1,6)})
        self.assertTrue(any(r[0].value=='Original monthly fee' and not sheet.row_dimensions[r[0].row].hidden for r in sheet))
        discount=next(r[0] for r in sheet if r[0].value=='One-time discount (deduction)');self.assertEqual(discount.font.color.rgb,'00B54B00')
        q['document']['discount'].update(enabled=False,wording='HIDDEN GENERATED SENTINEL');self.post('/quotes/'+ident+'/edit',quotation=json.dumps(dict(q,project_id=self.project,customer_id=self.customer)))
        html=self.c.get('/quotes/'+ident+'/print').data;self.assertNotIn(b'summary-discount"',html);self.assertNotIn(b'HIDDEN GENERATED SENTINEL',html)
        for omitted in ('Yearly recurring total','Contract recurring total','Contract tax','Contract total including','Prices provided exclude VAT'):
            self.assertNotIn(omitted.encode(),html)

    def test_archive_families_restoration_no_statistic_or_reference_changes(self):
        ident=self.create_quote();r=self.post('/record/'+ident+'/copy/revision');second=r.location.rsplit('/',1)[-1]
        self.won(ident)
        with store.connect(self.root) as db:before=statistics.quotations(store.records(db),{'period':'all'},outcomes=outcomes.visible(db,store.records(db)))
        ref=self.record(ident)['data']['number'];self.assertEqual(self.bulk([ref],confirm=True).status_code,302)
        with store.connect(self.root) as db:
            after=statistics.quotations(store.records(db),{'period':'all'},outcomes=outcomes.visible(db,store.records(db)))
            self.assertEqual(before['value'],after['value']);self.assertEqual(before['won_value'],after['won_value']);self.assertTrue(db.execute('SELECT 1 FROM reference_registry WHERE key=?',(ref.casefold(),)).fetchone())
        active=self.c.get('/list/quote?period=all');self.assertNotIn(('Select '+ref).encode(),active.data)
        archived=self.c.get('/list/quote?period=all&archive=archived');self.assertIn(('Select '+ref).encode(),archived.data)
        self.assertEqual(self.c.get('/quotes/'+second+'/compare').status_code,200)
        self.assertEqual(self.bulk([ref],action='restore',confirm=True).status_code,302)

    def test_archive_permissions_all_matching_and_stale_family_confirmation(self):
        first=self.create_quote();r=self.post('/record/'+first+'/copy/revision');second=r.location.rsplit('/',1)[-1];ref=self.record(first)['data']['number']
        self.post('/record/'+second+'/access',**{self.editor:'edit'})
        editor=self.login('editor');r=self.bulk([ref],client=editor);self.assertIn(b'Blocked',r.data);self.assertNotIn(b'Confirm archive',r.data)
        preview=self.bulk([ref]);digest=re.search(rb'name="selection_hash" value="([^"]+)"',preview.data)[1].decode()
        self.post('/record/'+second+'/copy/revision')
        self.assertEqual(self.post('/quotes/bulk',action='archive',references=[ref],selection_hash=digest,confirm='yes').status_code,400)
        r=self.post('/quotes/bulk',action='archive',selection_mode='matching',filters=json.dumps(dict(period='all',archive='active',q=ref)))
        self.assertIn(b'3 revisions',r.data)
        for i in range(26):self.create_quote(quote('PAGE-'+str(i)))
        r=self.c.get('/list/quote?period=all');self.assertEqual(r.data.count(b'data-family-select'),25);self.assertIn(b'Select all 27 matching families',r.data)
        self.assertIn(b'Document pages',r.data)

    def test_full_backup_restores_prices_contracts_months_archive_and_documents(self):
        self.price();self.save_contract(action='approve');c=self.current_contract()
        with store.connect(self.root) as db:
            old=rel.consumption_data(db,self.project,'2026-10');db.execute('INSERT INTO consumption VALUES (?,?,?,?,?,?,?,?)',('retained-month',self.project,'2026-10',old['contract_id'],json.dumps(old['data']),1,'2026-10-29',self.admin))
        self.post('/contracts/'+c['id']+'/documents',file=(io.BytesIO(b'%PDF-1.4 backup document'),'contract.pdf'))
        ident=self.create_quote();self.bulk([self.record(ident)['data']['number']],confirm=True)
        target=Path(self.temp.name)/'full.zip';backup(self.root,target);restored=Path(self.temp.name)/'restored';restore(target,restored)
        with store.connect(self.root) as source,store.connect(restored) as dest:
            for table in TABLES:self.assertEqual([tuple(r) for r in source.execute('SELECT * FROM '+table)],[tuple(r) for r in dest.execute('SELECT * FROM '+table)],table)
            stored=dest.execute('SELECT stored FROM attachments').fetchone()[0]
            self.assertEqual((self.root/'attachments'/stored).read_bytes(),(restored/'attachments'/stored).read_bytes())

    def test_customer_project_json_roundtrip_and_no_automatic_matching(self):
        ident=self.create_quote()
        with store.connect(self.root) as db:data=store.export_data(db)
        other=Path(self.temp.name)/'imported';store.migrate(other)
        with store.connect(other) as db:
            db.execute('BEGIN IMMEDIATE');store.apply_import(db,copy.deepcopy(data));self.assertEqual(rel.record(db,self.project)['data']['customer_id'],self.customer)
        q=quote('LEGACY-TEXT');q['customer']='Synthetic Bank';q['project_id']='';q['customer_id']=''
        with store.connect(self.root) as db:old=store.save(db,'quote',q)
        self.assertEqual(self.record(old)['data']['customer_id'],'')

    def test_quote_only_editor_keeps_standard_picker_without_agreed_price_access(self):
        ident=self.create_quote();self.price(self.project,price='60')
        self.post('/record/'+ident+'/access',**{self.editor:'edit'})
        editor=self.login('editor')
        r=editor.get('/pricing/options',query_string=dict(project_id=self.project,source_quote=ident,date='2026-10-29',currency='USD'))
        self.assertEqual(r.status_code,200);price=r.json['prices']['catalog:'+self.catalog]
        self.assertEqual(price['price'],'100');self.assertIn('requires project/customer access',price['source'])
        self.assertEqual(editor.get('/prices/'+self.project).status_code,404)
        self.assertEqual(self.post('/record/'+ident+'/copy/revision',client=editor).status_code,302)
        q=self.record(ident)['data'];q['scope']='Quote-only assignment can still save'
        self.assertEqual(self.post('/quotes/'+ident+'/edit',client=editor,quotation=json.dumps(q)).status_code,302)

    def test_copy_accepted_contract_uses_frozen_snapshot_and_flags_summary_policy(self):
        ident=self.create_quote(discount_quote());self.won(ident)
        q=self.record(ident)['data'];q['document']['sections'][0]['rows'][0]['unit_price']='999'
        self.assertEqual(self.post('/quotes/'+ident+'/edit',quotation=json.dumps(q)).status_code,302)
        self.assertEqual(self.save_contract(self.contract(initial_quote_id=ident,accepted_quote_id=ident),action='copy').status_code,302)
        current=self.current_contract();self.assertEqual(current['status'],'Proposed');self.assertEqual(current['data']['services'][0]['unit_price'],'100.00');self.assertIn('REVIEW REQUIRED',current['data']['notes'])

    def test_stale_new_month_rejects_changed_approved_contract_and_costing_uses_discount_basis(self):
        from workspace_app import costing
        self.save_contract(action='approve')
        with store.connect(self.root) as db:old=rel.consumption_data(db,self.project,'2026-10')
        self.save_contract(action='approve')
        self.assertEqual(self.save_consumption(contract_id=old['contract_id']).status_code,410)
        ident=self.create_quote(discount_quote());record=self.record(ident)
        with store.connect(self.root) as db:sheet=costing.load(db,record)
        self.assertEqual(costing.calculate_sheet(record,sheet)['selling'],Decimal('594.00'))
        changed=copy.deepcopy(record['data']);changed['document']['discount']['kind']='fixed';changed['document']['discount']['amount']='50'
        record['data']=changed
        self.assertEqual(costing.calculate_sheet(record,sheet)['selling'],Decimal('590.00'))


    def test_edit_assigned_project_retains_restricted_customer_link(self):
        self.post('/record/'+self.project+'/access',**{self.editor:'edit'})
        editor=self.login('editor')
        page=editor.get('/edit/project/'+self.project);self.assertEqual(page.status_code,200)
        self.assertIn(b'Existing linked customer (restricted)',page.data)
        self.assertIn(('value="'+self.customer+'" selected').encode(),page.data)
        values=self.record(self.project)['data'];values['description']='Edited by project assignee'
        self.assertEqual(self.post('/edit/project/'+self.project,client=editor,**values).status_code,302)
        self.assertEqual(self.record(self.project)['data']['customer_id'],self.customer)


if __name__=='__main__':unittest.main()
