from editor_requests import fields_for
"""Revision matching, private costing, explicit application, outcomes and draft recycling."""
import copy,io,json,tempfile,unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from openpyxl import load_workbook
from workspace_app import create_app,store,security,costing,outcomes,comparison,statistics,references
from workspace_app.commercial import amount,fingerprint,percent_difference,line_values
from workspace_app.model import ValidationError
from workspace_app.backup import backup,restore
from test_v5 import quote

PASSWORD='Commercial-tests-only-2026!'


class CalculationTests(unittest.TestCase):
    def test_matching_ids_survives_reorder_and_description_changes(self):
        q=quote();changed=copy.deepcopy(q);rows=changed['document']['sections'][0]['rows'];rows.reverse()
        result=comparison.compare(q,changed);self.assertTrue(all(i['kind']=='unchanged' for i in result['items']))
        rows[1].update(service='Renamed monthly service',quantity='2',unit_price='150')
        result=comparison.compare(q,changed);modified=next(i for i in result['items'] if i['kind']=='modified')
        self.assertIn('quantity',modified['changes']);self.assertIn('service',modified['changes']);self.assertEqual(result['before'],Decimal('1375.00'));self.assertEqual(result['after'],Decimal('4015.00'))
        self.assertEqual(result['usd_delta'],Decimal('2640.00'));self.assertEqual(result['percent'],Decimal('192.00'))

    def test_import_matching_add_remove_and_only_public_fields(self):
        q=quote();changed=copy.deepcopy(q)
        for r in changed['document']['sections'][0]['rows']:r['id']=uuid4().hex
        self.assertTrue(all(i['kind']=='unchanged' for i in comparison.compare(q,changed)['items']))
        changed['document']['sections'][0]['rows'].pop();changed['scope']='New scope';changed['exclusions']='New exclusions';changed['document']['terms'][0]['text']='Changed payment terms'
        result=comparison.compare(q,changed);self.assertEqual(sum(i['kind']=='removed' for i in result['items']),1)
        self.assertTrue({'Scope','Exclusions','Terms'}<={r['label'] for r in result['metadata']})
        self.assertTrue(all('cost' not in r for i in result['items'] for r in (i['before'],i['after']) if r))
        self.assertIsNone(percent_difference(Decimal(0),Decimal(20)))
        changed['currency']='EUR';self.assertIsNone(comparison.compare(q,changed)['usd_delta'])

    def test_cost_once_full_contract_margin_not_markup_and_zero(self):
        record=dict(id='test',kind='quote',data=quote())
        rows=[]
        for index,(_,r) in enumerate(costing.source_rows(record['data'])):
            rows.append(dict(id=r['id'],description=r['service'],quantity='1',supplier='PRIVATE SUPPLIER',supplier_reference='PRIVATE-REF',unit_purchase='60' if index==0 else '10',purchase_basis=r['billing'],shipping='20' if index==0 else '0',documentation='0',implementation='0',other='0',selling_unit=r['unit_price'] if r['method']=='unit' else r['fixed_fee'],target_margin='50',valid_until='',notes='PRIVATE-COST-NOTE'))
        result=costing.calculate_sheet(record,dict(rows=rows))
        self.assertEqual(result['cost'],Decimal('750.00'));self.assertEqual(result['selling'],Decimal('1250.00'));self.assertEqual(result['profit'],Decimal('500.00'));self.assertEqual(result['margin'],Decimal('40.00'))
        self.assertEqual(result['rows'][0]['suggested_unit'],Decimal('123.33'));self.assertEqual(result['rows'][1]['suggested_unit'],Decimal('20.00'))
        payload=dict(rows=rows);costing.validate(payload,record)
        for bad in ('100','101','-1','NaN'):
            invalid=copy.deepcopy(payload);invalid['rows'][0]['target_margin']=bad
            with self.assertRaises(ValidationError):costing.validate(invalid,record)
        for _,r in costing.source_rows(record['data']):r['quantity']='0'
        for r in rows:r.update(quantity='0',unit_purchase='',shipping='0',selling_unit='0')
        result=costing.calculate_sheet(record,dict(rows=rows));self.assertEqual(result['profit'],Decimal('0.00'));self.assertIsNone(result['margin']);self.assertIsNone(result['rows'][0]['suggested_unit'])

    def test_contract_allocations_reconcile_included_tax_and_historical_discount(self):
        from quotation_fixture import fixture
        q=fixture();self.assertEqual(sum(line_values(q).values()),Decimal('7194.80'))
        q['document']['tax']['mode']='included';values=line_values(q)
        from workspace_app.quotation import calculate
        c=calculate(q['document']);self.assertEqual(sum(values.values()),Decimal(c['term'])+Decimal(c['one_time'])-Decimal(c['tax']))
        from workspace_app.quotation import new_row,new_section
        q=quote();d=q['document'];s=new_section('Tiny amounts');s['rows']=[new_row('A',id='a',quantity='1',unit_price='.05'),new_row('B',id='b',quantity='1',unit_price='.05'),new_row('Excluded',id='zz',quantity='1',unit_price='0',state='excluded')]
        d['sections']=[s];d['contract_months']=1;d['discount'].update(enabled=True,percent='10',months=1,targets=['s:'+s['id']]);d['tax'].update(mode='exclusive',rate='0')
        values=line_values(q);self.assertEqual(values['zz'],Decimal('0'));self.assertEqual(sum(values.values()),Decimal('.09'))
        d['discount']['enabled']=False;d['tax'].update(mode='included',rate='10');values=line_values(q)
        self.assertEqual(values['zz'],Decimal('0'));self.assertEqual(sum(values.values()),Decimal('.09'))



class CommercialTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'data';self.app=create_app(self.root,True)
        with store.connect(self.root) as db:
            self.admin=security.create_user(db,'admin',PASSWORD,'Administrator',True);self.editor=security.create_user(db,'editor',PASSWORD,'Editor');self.viewer=security.create_user(db,'viewer',PASSWORD,'Viewer');self.reader=security.create_user(db,'read-only-editor',PASSWORD,'Editor')
        self.c=self.login('admin');self.ident=self.create(quote(status='Draft'))
    def tearDown(self):self.temp.cleanup()
    def login(self,user):
        c=self.app.test_client();c.get('/login')
        with c.session_transaction() as s:csrf=s['csrf']
        self.assertEqual(c.post('/login',data=dict(csrf=csrf,username=user,password=PASSWORD)).status_code,302);return c
    def post(self,path,c=None,**fields):
        c=c or self.c
        with c.session_transaction() as s:csrf=s['csrf']
        return c.post(path,data=dict(csrf=csrf,**fields_for(c,path,fields)))
    def create(self,q):
        response=self.post('/quotes/new',quotation=json.dumps(q));self.assertEqual(response.status_code,302,response.data[:500]);return response.location.split('/')[-2]
    def record(self,ident=None):
        with store.connect(self.root) as db:return next(r for r in store.records(db) if r['id']==(ident or self.ident))
    def worksheet(self,ident=None):
        with store.connect(self.root) as db:return costing.load(db,self.record(ident))
    def save_cost(self,rows=None,action='save',ident=None,**overrides):
        ident=ident or self.ident;sheet=self.worksheet(ident);rows=rows or sheet['rows'];payload={'rows':[{k:r[k] for k in ('id',*costing.EDITABLE)} for r in rows]}
        fields=dict(version=str(sheet['version']),quote_hash=sheet['quote_hash'],costing=json.dumps(payload),action=action);fields.update(overrides)
        return self.post('/quotes/'+ident+'/costing',**fields)
    def outcome(self,status,ident=None,**overrides):
        ident=ident or self.ident;r=self.record(ident)
        with store.connect(self.root) as db:state=outcomes.get(db,references.key(r['data']['number']))
        fields=dict(version=str(state['version']),status=status,reason='Price',notes='Outcome note',outcome_date='2026-10-29',accepted_quote_id=ident);fields.update(overrides)
        return self.post('/quotes/'+ident+'/outcome',**fields)
    def stats(self,period='all',**args):
        with store.connect(self.root) as db:
            records=store.records(db);return statistics.quotations(records,dict(period=period,**args),date(2026,10,29),outcomes.visible(db,records))

    def test_priced_drafts_update_value_and_issue_date_is_basis(self):
        result=self.stats();self.assertEqual(result['value'],'1,375.00');self.assertEqual(result['total'],1);self.assertEqual(result['pending_count'],0)
        q=self.record()['data'];q['date']='2026-09-20';self.assertEqual(self.post('/quotes/'+self.ident+'/edit',quotation=json.dumps(q)).status_code,302)
        self.assertEqual(self.stats('month')['total'],0);self.assertEqual(self.stats('last_month')['total'],1)
        self.assertEqual(self.stats('calendar',filter_year='2026',filter_month='9')['value'],'1,375.00')
        q['document']['sections'][0]['rows'][0]['unit_price']='';self.post('/quotes/'+self.ident+'/edit',quotation=json.dumps(q));self.assertEqual(self.stats()['value'],'0.00');self.assertEqual(self.stats()['missing'],1)

    def test_private_costs_save_without_repricing_then_preview_apply(self):
        rows=self.worksheet()['rows']
        for row in rows:row.update(unit_purchase='60',supplier='PRIVATE SUPPLIER',supplier_reference='PRIVATE-SUPPLIER-REF',notes='PRIVATE-COST-NOTE',selling_unit='120')
        self.assertEqual(self.save_cost(rows).status_code,302);self.assertEqual(amount(self.record()['data']),Decimal('1375.00'))
        preview=self.c.get('/quotes/'+self.ident+'/costing/apply');self.assertIn(b'Review selling price changes',preview.data);self.assertIn(b'120',preview.data)
        sheet=self.worksheet();result=self.post('/quotes/'+self.ident+'/costing/apply',quote_hash=sheet['quote_hash'],version=str(sheet['version']),confirm='yes');self.assertEqual(result.status_code,302)
        self.assertEqual(amount(self.record()['data']),Decimal('1716.00'))
        for path in ['/quotes/'+self.ident+'/print','/quotes/'+self.ident+'/csv','/quotes/'+self.ident+'/xlsx','/export']:
            with self.c.get(path) as response:
                data=response.data
                if path.endswith('/xlsx'):
                    import zipfile
                    with zipfile.ZipFile(io.BytesIO(data)) as z:data=b' '.join(z.read(n) for n in z.namelist())
                for secret in (b'PRIVATE SUPPLIER',b'PRIVATE-SUPPLIER-REF',b'PRIVATE-COST-NOTE'):self.assertNotIn(secret,data)

    def test_target_suggestions_and_stale_save_apply_versions(self):
        rows=self.worksheet()['rows']
        for index,r in enumerate(rows):r.update(unit_purchase='60' if index==0 else '10',target_margin='50',shipping='20' if index==0 else '0')
        before=self.worksheet();self.assertEqual(self.save_cost(rows,action='suggest').status_code,302)
        stored=self.worksheet();self.assertEqual(stored['rows'][0]['selling_unit'],'123.33');self.assertEqual(amount(self.record()['data']),Decimal('1375.00'))
        self.assertEqual(self.save_cost(rows,version=str(before['version'])).status_code,400)
        q=self.record()['data'];q['scope']='Changed after costing preview';self.post('/quotes/'+self.ident+'/edit',quotation=json.dumps(q))
        self.assertEqual(self.post('/quotes/'+self.ident+'/costing/apply',quote_hash=stored['quote_hash'],version=str(stored['version']),confirm='yes').status_code,400)
        self.assertEqual(self.post('/quotes/'+self.ident+'/costing/apply',quote_hash=self.worksheet()['quote_hash'],version=str(stored['version'])).status_code,400)

    def test_costing_permissions_compare_both_and_snapshot_confidentiality(self):
        self.post('/record/'+self.ident+'/access',**{self.viewer:'read',self.reader:'read',self.editor:'edit'})
        viewer=self.login('viewer');reader=self.login('read-only-editor');editor=self.login('editor')
        for client in (viewer,reader):
            for path in ('/costing','/costing/apply'):
                self.assertEqual(client.get('/quotes/'+self.ident+path).status_code,404)
            self.assertIn(self.post('/quotes/'+self.ident+'/costing/calculate',client).status_code,(403,404))
        self.assertEqual(editor.get('/quotes/'+self.ident+'/costing').status_code,200)
        other=self.create(quote('OTHER-PRIVATE'))
        self.assertEqual(viewer.get('/quotes/'+self.ident+'/compare?after='+other).status_code,404)
        self.assertEqual(self.c.get('/quotes/'+self.ident+'/compare?after='+other).status_code,200)
        self.assertEqual(viewer.get('/quotes/'+self.ident+'/compare').status_code,200)

    def test_revision_costs_independent_reorder_and_orphan_preservation(self):
        rows=self.worksheet()['rows'];rows[0].update(supplier='Supplier for original',unit_purchase='50');self.save_cost(rows)
        response=self.post('/record/'+self.ident+'/copy/revision');second=response.location.rsplit('/',1)[-1]
        clone=self.worksheet(second);self.assertEqual(clone['rows'][0]['supplier'],'Supplier for original')
        clone['rows'][0]['supplier']='Supplier for revision';self.save_cost(clone['rows'],ident=second)
        self.assertEqual(self.worksheet()['rows'][0]['supplier'],'Supplier for original')
        q=self.record(second)['data'];q['document']['sections'][0]['rows'].reverse();self.post('/quotes/'+second+'/edit',quotation=json.dumps(q));self.assertEqual(self.worksheet(second)['rows'][1]['supplier'],'Supplier for revision')
        q['document']['sections'][0]['rows'].pop();self.post('/quotes/'+second+'/edit',quotation=json.dumps(q));sheet=self.worksheet(second);self.assertEqual(len(sheet['orphaned']),1)

    def test_outcomes_require_reason_accepted_revision_date_and_actor(self):
        self.assertEqual(self.outcome('Won',reason='').status_code,400);self.assertEqual(self.outcome('Won',accepted_quote_id='').status_code,404)
        self.assertEqual(self.outcome('Lost',outcome_date='2099-01-01').status_code,400)
        self.assertEqual(self.outcome('Won',recorded_by='spoofed-user').status_code,302)
        self.assertEqual(self.outcome('Lost',version='1').status_code,400)
        with store.connect(self.root) as db:
            state=outcomes.get(db,references.key(self.record()['data']['number']));self.assertEqual(state['recorded_by'],self.admin);self.assertEqual(state['accepted_value'],'1375.00')
            self.assertGreaterEqual(db.execute('SELECT COUNT(*) FROM quotation_activity').fetchone()[0],2)
        other=self.create(quote('OTHER'))
        self.assertEqual(self.outcome('Won',accepted_quote_id=other).status_code,400)
        q=self.record()['data'];q['status']='Lost'
        self.assertNotEqual(self.post('/quotes/'+self.ident+'/edit',quotation=json.dumps(q)).status_code,302)

    def test_frozen_won_value_new_revision_and_current_value_not_double_counted(self):
        self.outcome('Won');response=self.post('/record/'+self.ident+'/copy/revision');second=response.location.rsplit('/',1)[-1]
        q=self.record(second)['data'];q['document']['sections'][0]['rows'][0]['unit_price']='200';self.post('/quotes/'+second+'/edit',quotation=json.dumps(q))
        stats=self.stats();self.assertEqual(stats['total'],1);self.assertEqual(stats['value'],'2,695.00');self.assertEqual(stats['won_value'],'1,375.00');self.assertEqual(stats['won_count'],1);self.assertEqual(stats['win_rate'],'100.00')
        self.assertEqual(self.post('/record/'+self.ident+'/delete').status_code,400)
        renamed=self.record()['data'];renamed['number']='RENAMED-ACCEPTED'
        self.assertNotEqual(self.post('/quotes/'+self.ident+'/edit',quotation=json.dumps(renamed)).status_code,302)
        self.assertEqual(self.c.get('/quotes/'+second+'/accepted').status_code,200)
        self.assertIn(b'100',self.c.get('/quotes/'+second+'/accepted').data)
        self.outcome('Won',ident=second,accepted_quote_id=second)
        self.assertEqual(self.stats()['won_value'],'2,695.00')

    def test_outcome_dates_differ_from_issue_filters_and_currency_safe(self):
        q=self.record()['data'];q['date']='2026-09-01';self.post('/quotes/'+self.ident+'/edit',quotation=json.dumps(q));self.outcome('Won')
        stats=self.stats('month');self.assertEqual(stats['total'],0);self.assertEqual(stats['won_count'],1);self.assertEqual(stats['won_value'],'1,375.00')
        other=self.create(quote('EUR-DEAL',currency='EUR'));self.outcome('Lost',ident=other)
        stats=self.stats();self.assertEqual(stats['won_count'],1);self.assertEqual(stats['lost_count'],1);self.assertEqual(stats['lost_value'],'0.00');self.assertEqual(stats['lost_excluded'],1);self.assertEqual(stats['win_rate'],'50.00')
        self.outcome('On hold',ident=other);stats=self.stats();self.assertEqual(stats['pending_count'],1);self.assertEqual(stats['pending_value'],'0.00')

    def test_draft_recycling_sent_protection_and_administrator_review(self):
        self.post('/references',action='reserve',reference='UNUSED-RESERVATION',kind='quotation')
        self.assertEqual(self.post('/references',action='release_reservation',key='UNUSED-RESERVATION').status_code,302)
        self.assertTrue(self.post('/references/check',reference='UNUSED-RESERVATION').json['available'])
        self.post('/references',action='reserve',reference='RESERVED-DRAFT',kind='quotation')
        reserved_id=self.create(quote('RESERVED-DRAFT',status='Draft'));self.assertEqual(self.post('/record/'+reserved_id+'/delete').status_code,302)
        with store.connect(self.root) as db:self.assertFalse(db.execute("SELECT 1 FROM reference_registry WHERE key='reserved-draft'").fetchone())
        reference=self.record()['data']['number'];self.outcome('Under review');self.outcome('Draft');self.assertEqual(self.post('/record/'+self.ident+'/delete').status_code,302)
        with store.connect(self.root) as db:self.assertFalse(db.execute('SELECT 1 FROM reference_registry WHERE key=?',(references.key(reference),)).fetchone())
        self.ident=self.create(quote(status='Draft'));self.outcome('Sent');self.outcome('Draft');self.post('/record/'+self.ident+'/delete')
        with store.connect(self.root) as db:self.assertTrue(db.execute('SELECT 1 FROM reference_registry WHERE key=?',(references.key(reference),)).fetchone())
        self.assertEqual(self.post('/references',action='release',key=references.key(reference),confirm_reference=reference,never_sent='yes').status_code,200)
        old='OLD-UNUSED'
        with store.connect(self.root) as db:db.execute("INSERT INTO reference_registry VALUES (?,?,?,'issued',?,NULL,?,?,?)",(references.key(old),old,'quotation',self.admin,references.stamp(),references.stamp(),'quotation'))
        self.assertEqual(self.post('/references',action='release',key=references.key(old),confirm_reference=old,never_sent='yes').status_code,302)
        with store.connect(self.root) as db:self.assertFalse(db.execute('SELECT 1 FROM reference_registry WHERE key=?',(references.key(old),)).fetchone())

    def test_migration_and_backup_preserve_separate_internal_data(self):
        rows=self.worksheet()['rows'];rows[0]['supplier']='PRIVATE-MIGRATION-SUPPLIER';self.save_cost(rows);self.outcome('Won')
        archive=Path(self.temp.name)/'backup.zip';backup(self.root,archive);restored=Path(self.temp.name)/'restored';restore(archive,restored)
        with store.connect(restored) as db:
            self.assertIn('PRIVATE-MIGRATION-SUPPLIER',db.execute('SELECT data FROM quote_costing').fetchone()[0]);self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],18);self.assertEqual(db.execute('SELECT accepted_value FROM quotation_outcomes').fetchone()[0],'1375.00')

    def test_real_schema5_migration_preserves_records_and_flags_old_drafts_unknown(self):
        before=copy.deepcopy(self.record()['data'])
        with store.connect(self.root) as db:
            db.execute("UPDATE reference_registry SET source='manual'")
            for table in ('quote_costing','quotation_outcomes','quotation_activity','reference_usage'):db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=5')
        store.migrate(self.root)
        self.assertEqual(self.record()['data'],before)
        with store.connect(self.root) as db:
            usage=db.execute('SELECT * FROM reference_usage').fetchone();self.assertEqual(usage['draft_only'],0);self.assertEqual(usage['provenance'],'legacy-unverified')
        self.post('/record/'+self.ident+'/delete')
        with store.connect(self.root) as db:self.assertTrue(db.execute('SELECT 1 FROM reference_registry').fetchone())

    def test_json_import_cannot_invent_won_without_outcome_details(self):
        q=quote('IMPORTED-TERMINAL',status='Won');ident=str(uuid4());when='2026-10-29T00:00:00+00:00'
        payload=dict(format='joseph-workspace',version=3,records=[dict(id=ident,kind='quote',data=q,created=when,updated=when)],settings={},hosting_vms=[])
        self.assertEqual(self.post('/import',payload=json.dumps(payload),confirm='yes').status_code,302)
        with store.connect(self.root) as db:
            state=outcomes.get(db,'imported-terminal');self.assertEqual(state['status'],'Under review');self.assertIsNone(state['accepted_value'])
        self.assertEqual(self.stats()['won_count'],0)

    def test_schema5_retains_older_accepted_revision_under_newer_draft(self):
        original=self.record()['data'];original['status']='Accepted'
        with store.connect(self.root) as db:db.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(original),self.ident))
        newer=copy.deepcopy(original);newer.update(status='Draft',revision=2,currency='EUR');newer['document']['sections'][0]['rows'][0]['unit_price']='200'
        with store.connect(self.root) as db:
            newer_id=store.save(db,'quote',newer,inherit_from=self.ident)
            for table in ('quote_costing','quotation_outcomes','quotation_activity','reference_usage'):db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=5')
        store.migrate(self.root)
        with store.connect(self.root) as db:
            state=outcomes.get(db,references.key(original['number']));self.assertEqual(state['status'],'Won');self.assertEqual(state['accepted_quote_id'],self.ident);self.assertEqual(state['accepted_value'],'1375.00');self.assertEqual(state['accepted_currency'],'USD');self.assertIsNone(state['outcome_date'])
        self.assertEqual(self.record(newer_id)['data']['revision'],2)


if __name__=='__main__':unittest.main()
