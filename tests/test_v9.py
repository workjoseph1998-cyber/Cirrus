"""Version 9: synthetic family metrics, no-loss support migration and unified workspaces."""
import copy,io,json,re,tempfile,unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from workspace_app import create_app,store,security,statistics,customers,support,outcomes
from workspace_app.quotation import calculate,default_document,new_row,new_section,validate_document
from workspace_app.model import FIELDS,ValidationError
from workspace_app.backup import backup,restore
from test_v5 import quote,record as stats_record
import test_v8 as v8


class MetricsTests(unittest.TestCase):
    def test_latest_monthly_contract_zero_and_unknown_are_distinct(self):
        rows=[stats_record(quote('FAMILY',price='100',revision=1)),stats_record(quote('FAMILY',price='200',revision=2)),stats_record(quote('ZERO',price='0')),stats_record(quote('UNKNOWN',price=''))]
        # A zero contract must also have no one-time fee.
        rows[2]['data']['document']['sections'][0]['rows'][1]['fixed_fee']='0'
        s=statistics.quotations(rows,{'period':'all'},date(2026,10,29))
        self.assertEqual(s['total'],3);self.assertEqual(s['value'],'2,695.00');self.assertEqual(s['monthly_value'],'200.00');self.assertEqual(s['missing'],1);self.assertEqual(s['zero_count'],1);self.assertEqual(s['monthly_missing'],1)
        rows[1]['data']['document']['sections']='invalid';s=statistics.quotations(rows,{'period':'all'},date(2026,10,29));self.assertEqual(s['value'],'0.00');self.assertEqual(s['monthly_value'],'0.00');self.assertEqual(s['missing'],2)

    def test_support_layout_conversion_preserves_every_charge_and_exclusion(self):
        d=default_document();top=next(s for s in d['sections'] if s['name']=='8×5 Request Fulfillment');children=[s for s in d['sections'] if s['parent']==top['id']]
        for child in children:
            parent=next(s for s in d['sections'] if s['name']==child['name'].removesuffix(' support'))
            child['parent']=parent['id'];child['name']='8×5 Request Fulfillment'
        d['sections'].remove(top)
        prod=next(s for s in d['sections'] if s['name']=='Production');vm=next(s for s in d['sections'] if s['parent']==prod['id'] and s['name']=='Compute and storage');vm['rows']=[new_row('VM',quantity='2',unit_price='100')]
        d['discount'].update(enabled=True,percent='10',months=3)
        before=calculate(d);converted,changed=support.standalone(d);self.assertTrue(changed)
        after=calculate(converted)
        for key in ('rows','regular','discount','discounted','term','tax','combined'):self.assertEqual(before[key],after[key],key)
        self.assertFalse(support.standalone(converted)[1]);self.assertEqual(calculate(support.standalone(converted)[0]),after)
        prod['excluded']=True;prod['hidden']=True;before=calculate(d);after=calculate(support.standalone(d)[0]);self.assertEqual(before['rows'],after['rows']);self.assertEqual(before['combined'],after['combined'])

    def test_support_auto_service_keys_deduplicate_with_categories(self):
        d=default_document();prefs=dict(support_percent='15',support_base=['category:Production','catalog:synthetic'],discount=dict(enabled=False))
        d=support.apply_defaults(d,prefs);prod=next(s for s in d['sections'] if s['name']=='Production');prod['rows']=[new_row('VM',quantity='1',unit_price='100',item_key='catalog:synthetic')]
        rows=[r for s in d['sections'] for r in s['rows'] if r['method']=='percent'];self.assertEqual(len(rows),1)
        self.assertEqual(calculate(d)['rows'][rows[0]['id']],'15.00');prod['rows'][0]['quantity']='2';self.assertEqual(calculate(d)['rows'][rows[0]['id']],'30.00')


class V9Tests(unittest.TestCase):
    # Reuse setup helpers without repeating inherited Version 8 test cases.
    def deletion_preview(self,refs,client=None):return self.post('/quotes/bulk',client=client,action='delete',references=refs,archive_view='archived')
    def deletion(self,refs,preview=None,client=None,**changes):
        preview=preview or self.deletion_preview(refs,client);m=re.search(rb'name="selection_hash" value="([^"]+)"',preview.data)
        self.assertIsNotNone(m,preview.data[:300]);data=dict(action='delete',references=refs,archive_view='archived',confirm='yes',delete_phrase='DELETE',selection_hash=m[1].decode());data.update(changes);return self.post('/quotes/bulk',client=client,**data)

    def test_archived_delete_requires_all_revisions_confirmation_and_keeps_issued_reference(self):
        ident=self.create_quote(quote('ISSUED-DELETE',status='Sent'));self.post('/record/'+ident+'/copy/revision');self.bulk(['ISSUED-DELETE'],confirm=True)
        preview=self.deletion_preview(['ISSUED-DELETE']);self.assertIn(b'Revision 2',preview.data);self.assertIn(b'Revision 1',preview.data)
        self.assertEqual(self.deletion(['ISSUED-DELETE'],preview,delete_phrase='wrong').status_code,400)
        self.assertEqual(self.deletion(['ISSUED-DELETE'],preview).status_code,302)
        with store.connect(self.root) as db:
            self.assertFalse(any(r['kind']=='quote' for r in store.records(db)));self.assertTrue(db.execute("SELECT 1 FROM reference_registry WHERE key='issued-delete'").fetchone());self.assertTrue(db.execute("SELECT 1 FROM quotation_activity WHERE action='Archived quotation family permanently deleted'").fetchone())

    def test_delete_blocks_active_won_linked_and_stale_families(self):
        ident=self.create_quote(quote('GUARDED',status='Draft'));r=self.deletion_preview(['GUARDED']);self.assertIn(b'only for archived',r.data);self.assertNotIn(b'Confirm delete',r.data)
        self.won(ident);self.bulk(['GUARDED'],confirm=True);r=self.deletion_preview(['GUARDED']);self.assertIn(b'accepted',r.data.lower());self.assertNotIn(b'Confirm delete',r.data)
        with store.connect(self.root) as db:state=outcomes.get(db,'guarded')
        self.post('/quotes/'+ident+'/outcome',version=str(state['version']),status='Draft',reason='',notes='',outcome_date='')
        preview=self.deletion_preview(['GUARDED']);q=self.record(ident)['data'];q['title']='Changed after confirmation';self.post('/quotes/'+ident+'/edit',quotation=json.dumps(q));self.assertEqual(self.deletion(['GUARDED'],preview).status_code,400)
        self.assertEqual(self.deletion(['GUARDED']).status_code,302)
        with store.connect(self.root) as db:self.assertTrue(db.execute("SELECT 1 FROM reference_registry WHERE key='guarded'").fetchone())

    def test_delete_preserves_reservations_and_rejects_partial_editor(self):
        ident=self.create_quote(quote('UNSENT-DELETE',status='Draft'));second=self.post('/record/'+ident+'/copy/revision').location.rsplit('/',1)[-1]
        self.bulk(['UNSENT-DELETE'],confirm=True);self.post('/record/'+second+'/access',**{self.editor:'edit'})
        editor=self.login('editor');r=self.deletion_preview(['UNSENT-DELETE'],editor);self.assertNotIn(b'Confirm delete',r.data)
        self.assertEqual(self.deletion(['UNSENT-DELETE']).status_code,302)
        with store.connect(self.root) as db:self.assertTrue(db.execute("SELECT 1 FROM reference_registry WHERE key='unsent-delete'").fetchone())

    def test_customer_unified_legacy_workspace_and_duplicate_review(self):
        with store.connect(self.root) as db:
            legacy=dict(self.record(self.project)['data'],customer_id='',name='Synthetic Bank');legacy_id=store.save(db,'project',legacy)
        page=self.c.get('/customers');self.assertIn(b'Duplicate name',page.data)
        self.assertEqual(self.c.get('/customers/'+legacy_id).status_code,200)
        self.assertEqual(self.post('/customers/'+legacy_id+'/link',customer_id=self.customer).status_code,400)
        self.assertEqual(self.post('/customers/'+legacy_id+'/link',customer_id=self.customer,confirm='yes').status_code,302)
        self.assertEqual(self.record(legacy_id)['data']['customer_id'],self.customer);self.assertEqual(self.record(legacy_id)['data']['customer'],'Legacy bank text')

    def test_compact_price_blank_inherits_zero_survives_and_policy_is_snapshot(self):
        with store.connect(self.root) as db:
            c=customers.scope(db,self.customer);table=customers.pricing_table(db,c);h=customers.table_hash(db,self.customer)
        values={r['field']:'' for r in table};field=next(r['field'] for r in table if r['item']['key']=='catalog:'+self.catalog);values[field]='0'
        self.assertEqual(self.post('/customers/'+self.customer+'/prices',prices_hash=h,prices=json.dumps(values),reason='Free agreement').status_code,302)
        self.assertEqual(self.resolved()['catalog:'+self.catalog]['price'],'0.00')
        with store.connect(self.root) as db:h=customers.table_hash(db,self.customer)
        values[field]='';self.assertEqual(self.post('/customers/'+self.customer+'/prices',prices_hash=h,prices=json.dumps(values),reason='Return to standard').status_code,302)
        self.assertEqual(self.resolved()['catalog:'+self.catalog]['price'],'100')
        fields=dict(version='0',support_percent='12.5',support_base=['category:Production'],discount_enabled='yes',discount_kind='percent',discount_percent='5',discount_amount='0',discount_billing='monthly',discount_duration='full',discount_months='0')
        self.assertEqual(self.post('/customers/'+self.customer+'/policy',**fields).status_code,302)
        page=self.c.get('/quotes/new?project_id='+self.project);match=re.search(rb'<script type="application/json" id="initial-quotation">(.*?)</script>',page.data,re.S);d=json.loads(match[1]);fees=[r for s in d['document']['sections'] for r in s['rows'] if r['method']=='percent'];self.assertEqual(len(fees),1);self.assertEqual(fees[0]['percent'],'12.5');self.assertTrue(d['document']['discount']['enabled'])
        d['title']='Customer-default quotation'
        # Correct the new default VM/minimum requirements before testing policy snapshots.
        for section in d['document']['sections']:
            for row in section['rows']:
                if row.get('vm_selection_required'):row['state']='excluded'
                if float(row['quantity'])<float(row.get('minimum_quantity','0')):row['quantity']=row['minimum_quantity']
        ident=self.create_quote(d);fields['version']='1';fields['support_percent']='25';self.post('/customers/'+self.customer+'/policy',**fields)
        stored=self.record(ident)['data'];fees=[r for s in stored['document']['sections'] for r in s['rows'] if r['method']=='percent'];self.assertEqual(fees[0]['percent'],'12.5')

    def test_customer_kpis_dates_native_charges_and_private_expiry(self):
        self.save_contract(action='approve');self.save_consumption(month='2026-09');self.save_consumption(month='2026-10');ident=self.create_quote();self.won(ident)
        with store.connect(self.root) as db:
            c=customers.scope(db,self.customer);ps=customers.members(db,c)
            s=customers.indicators(db,c,ps,{'period':'all'});self.assertEqual(s['period_charges']['USD'],Decimal('0'));self.assertEqual(s['monthly']['USD'],Decimal('0'));self.assertEqual(s['qstats']['won_value'],'1,375.00')
            s=customers.indicators(db,c,ps,{'period':'custom','start':'2026-09-01','end':'2026-09-30'});self.assertEqual(s['period_charges']['USD'],Decimal('0'));self.assertEqual(s['anchor'],'2026-09');self.assertEqual(s['qstats']['total'],0)
        self.assertEqual(self.c.get('/customers/'+self.customer+'?tab=prices&period=all').status_code,200)

    def test_quote_list_is_compact_and_charts_follow_list(self):
        ident=self.create_quote();page=self.c.get('/list/quote?period=all').data.decode()
        self.assertNotIn('<th>Type</th>',page);self.assertNotIn(' · Rev ',page);self.assertIn('View monthly statistics',page);self.assertNotIn('<details class="card monthly-statistics" open',page)
        self.assertLess(page.index('compact-quotations'),page.index('View monthly statistics'));self.assertIn('sidebar-tools',page)
        self.assertIn('Synthetic quotation',self.c.get('/list/quote?period=all&q=CIR26-148-1').data.decode())
        self.assertIn(b'cirrus-logo.png',self.c.get('/login').data);self.assertIn(b'cirrus-logo.png',self.c.get('/').data)

    def test_new_customer_direct_create_quote_and_scoped_policy_permissions(self):
        with store.connect(self.root) as db:ident=store.save(db,'customer',dict(name='Fresh customer',contact='',notes=''))
        response=self.post('/customers/'+ident+'/new-quotation');self.assertEqual(response.status_code,302);self.assertIn('project_id=',response.location)
        q=self.c.get(response.location);self.assertEqual(q.status_code,200)
        editor=self.login('editor');self.assertEqual(editor.get('/customers/'+ident).status_code,404);self.assertEqual(self.post('/customers/'+ident+'/policy',client=editor).status_code,404)

    def test_schema7_migration_keeps_support_costs_accepted_value_and_backup(self):
        from workspace_app import costing
        ident=self.create_quote(quote('MIGRATE-SUPPORT',status='Draft'));d=default_document()
        top=next(s for s in d['sections'] if s['name']=='8×5 Request Fulfillment')
        for child in [s for s in d['sections'] if s['parent']==top['id']]:
            parent=next(s for s in d['sections'] if s['name']==child['name'].removesuffix(' support'))
            child['parent']=parent['id'];child['name']='8×5 Request Fulfillment'
        d['sections'].remove(top)
        compute=next(s for s in d['sections'] if s['name']=='Compute and storage');compute['rows']=[new_row('Compute',quantity='1',unit_price='100')]
        q=self.record(ident)['data'];q['document']=d;q['tax']='0'
        with store.connect(self.root) as db:db.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(q),ident))
        self.won(ident)
        with store.connect(self.root) as db:
            sheet=costing.load(db,self.record(ident));sheet['rows'][0]['supplier']='PRIVATE-UNCHANGED-SUPPLIER';private=json.dumps(dict(rows=sheet['rows'],orphaned=[]));db.execute('INSERT INTO quote_costing VALUES (?,?,?,?,?)',(ident,1,private,'2026-10-29','admin'))
            value=db.execute('SELECT accepted_value FROM quotation_outcomes WHERE reference_key=?',('migrate-support',)).fetchone()[0]
            for t in ('customer_policy_history','customer_preferences','support_migrations'):db.execute('DROP TABLE '+t)
            db.execute('PRAGMA user_version=7')
        store.migrate(self.root)
        with store.connect(self.root) as db:
            after=self.record(ident)['data'];self.assertEqual(calculate(after['document'])['combined'],calculate(d)['combined'])
            self.assertEqual(db.execute('SELECT data FROM quote_costing').fetchone()[0],private)
            self.assertEqual(db.execute('SELECT accepted_value FROM quotation_outcomes WHERE reference_key=?',('migrate-support',)).fetchone()[0],value)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM support_migrations').fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],18)
        store.migrate(self.root)
        archive=Path(self.temp.name)/'v9.zip';backup(self.root,archive);target=Path(self.temp.name)/'restored9';restore(archive,target)
        with store.connect(target) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM support_migrations').fetchone()[0],1)

    def test_linking_workspace_preserves_existing_quote_identity_and_revisions(self):
        ident=self.create_quote()
        with store.connect(self.root) as db:target=store.save(db,'customer',dict(name='Reviewed customer',contact='',notes=''))
        self.assertEqual(self.post('/customers/'+self.project+'/link',customer_id=target,confirm='yes').status_code,302)
        q=self.record(ident)['data'];q['title']='Historic customer text retained'
        self.assertEqual(self.post('/quotes/'+ident+'/edit',quotation=json.dumps(q)).status_code,302)
        self.assertEqual(self.post('/record/'+ident+'/copy/revision').status_code,302)
        with store.connect(self.root) as db:
            original=customers.scope(db,self.customer);new=customers.scope(db,target)
            self.assertEqual(customers.indicators(db,original,customers.members(db,original),{'period':'all'})['qstats']['total'],0)
            self.assertEqual(customers.indicators(db,new,customers.members(db,new),{'period':'all'})['qstats']['total'],1)
        self.assertEqual(self.record(ident)['data']['customer_id'],self.customer)

    def test_delete_rechecks_internal_cost_version_and_new_customer_has_agreement(self):
        ident=self.create_quote(quote('COST-STALE',status='Draft'));self.bulk(['COST-STALE'],confirm=True);preview=self.deletion_preview(['COST-STALE'])
        with store.connect(self.root) as db:db.execute('INSERT INTO quote_costing VALUES (?,?,?,?,?)',(ident,1,json.dumps(dict(rows=[],orphaned=[])),'2026-10-29',self.admin))
        self.assertEqual(self.deletion(['COST-STALE'],preview).status_code,400)
        r=self.post('/new/customer',name='New UI customer',contact='',notes='');self.assertEqual(r.status_code,302)
        created=r.location.rsplit('/',1)[-1]
        with store.connect(self.root) as db:self.assertEqual(len(customers.members(db,customers.scope(db,created))),1)

for name in ('tearDown','login','post','create_quote','record','price','resolved','contract','save_contract','current_contract','save_consumption','won','bulk'):
    setattr(V9Tests,name,getattr(v8.V8Tests,name))

def stable_setup(self):
    from unittest.mock import patch
    for target in ('workspace_app.statistics.today_local','workspace_app.relationships.today_local'):
        timer=patch(target,return_value=date(2026,10,29));timer.start();self.addCleanup(timer.stop)
    v8.V8Tests.setUp(self)
V9Tests.setUp=stable_setup

if __name__=='__main__':unittest.main()
