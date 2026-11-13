"""Synthetic document workspace regression, migration and concurrent allocation tests."""
import copy,io,json,re,unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from unittest.mock import patch
from openpyxl import load_workbook
from workspace_app import store,documents,statistics,outcomes
from workspace_app.commercial import fingerprint
from workspace_app.quotation import calculate,validate_document
from workspace_app.backup import backup,restore
from test_v5 import quote
import test_v8 as v8


class DocumentTests(unittest.TestCase):
    def setUp(self):
        for target in ('workspace_app.statistics.today_local','workspace_app.relationships.today_local'):
            p=patch(target,return_value=date(2026,11,2));p.start();self.addCleanup(p.stop)
        v8.V8Tests.setUp(self)
    def doc(self,typ='SLA',subject='Cloud services',client=None):
        response=self.post('/documents/new',client=client,type=typ,subject=subject,customer_id=self.customer)
        self.assertEqual(response.status_code,302,response.data[:1500]);return response.location.split('/')[-2]
    def test_all_types_and_atomic_initial_flow(self):
        for typ in documents.TYPES:
            if typ=='Quotation':continue
            ident=self.doc(typ);r=self.record(ident);self.assertEqual(r['data']['type'],typ);self.assertNotIn('document',r['data']);self.assertEqual(self.c.get('/documents/'+ident+'/edit').status_code,200)
        res=self.post('/documents/new',type='Quotation',subject='Cloud Services',customer_id=self.customer)
        self.assertIn('/quotes/new?',res.location);html=self.c.get(res.location).data
        q=json.loads(re.search(rb'id="initial-quotation">(.*?)</script>',html,re.S)[1]);self.assertIn('Synthetic Bank-Cloud Services Quotation_V1.0',q['title']);self.assertTrue(q['number'].startswith('CIR26-'))
        with store.connect(self.root) as db:
            reservations=db.execute("SELECT * FROM reference_registry WHERE state='reserved'").fetchall();self.assertEqual(len(reservations),1);self.assertEqual(reservations[0]['reference'],q['number'])
        # Initial catalog defaults require explicit VM selection and minimum correction.
        for section in q['document']['sections']:
            for row in section['rows']:
                if row.get('vm_selection_required'):row['state']='excluded'
                if float(row['quantity'])<float(row.get('minimum_quantity','0')):row['quantity']=row['minimum_quantity']
        self.assertEqual(self.post('/quotes/new',quotation=json.dumps(q)).status_code,302)
    def test_concurrent_new_documents_and_draft_reservations_never_duplicate(self):
        # Reuse authenticated session cookies in independent test clients, each own SQLite connection.
        with self.c.session_transaction() as sess:auth=dict(sess)
        def create(index):
            c=self.app.test_client()
            with c.session_transaction() as sess:sess.update(auth)
            r=self.post('/documents/new',client=c,type='Quotation' if index%2 else 'PO',subject='Concurrent '+str(index),customer_id=self.customer)
            return r.status_code,r.location
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(create,range(6)))
        self.assertTrue(all(r[0]==302 for r in results),results)
        with store.connect(self.root) as db:
            refs=[r[0] for r in db.execute('SELECT reference FROM reference_registry')];self.assertEqual(len(refs),6);self.assertEqual(len(set(refs)),6)
    def test_title_persistence_export_names_and_deliberate_regeneration(self):
        ident=self.doc();r=self.record(ident);d=r['data'];d.update(title='Custom : SLA / name?',content='Terms retained')
        payload={k:d[k] for k in ('title','contact','date','subject','content','status','number')};payload['snapshot']=fingerprint(r['data'])
        # fingerprint must reflect the database, not locally changed data
        payload['snapshot']=fingerprint(self.record(ident)['data'])
        self.assertEqual(self.post('/documents/'+ident+'/edit',**payload).status_code,302)
        content=self.c.get('/documents/'+ident+'/txt');self.assertIn('Custom _ SLA _ name_.txt',content.headers['Content-Disposition']);self.assertIn(b'Terms retained',content.data)
        saved=self.record(ident);payload.update(snapshot=fingerprint(saved['data']),content='Other edit');self.assertEqual(self.post('/documents/'+ident+'/edit',**payload).status_code,302);self.assertEqual(self.record(ident)['data']['title'],d['title'])
        payload.update(snapshot=fingerprint(self.record(ident)['data']),regenerate='yes');self.post('/documents/'+ident+'/edit',**payload);self.assertIn('_V1.0',self.record(ident)['data']['title'])
        qid=self.create_quote(quote('TITLE-EXPORT'));q=self.record(qid)['data'];q['title']='Edited title : KEEP';self.post('/quotes/'+qid+'/edit',quotation=json.dumps(q))
        for ext in ('xlsx','csv'):
            response=self.c.get('/quotes/'+qid+'/'+ext);self.assertEqual(response.status_code,200);self.assertIn('Edited title _ KEEP.'+ext,response.headers['Content-Disposition'])
        self.assertIn(b'<title>Edited title _ KEEP</title>',self.c.get('/quotes/'+qid+'/print').data)
    def test_date_basis_search_owner_type_status_and_pagination_combine(self):
        qid=self.create_quote(quote('DATE-REF'));docid=self.doc('PO')
        with store.connect(self.root) as db:
            db.execute('UPDATE records SET created=?,updated=? WHERE id=?',('2025-02-03T10:00:00+00:00','2026-11-02T10:00:00+00:00',qid))
            rows,stats,counts,_=documents.workspace(db,dict(q='DATE-REF',filter_year='2025',filter_month='2',type='Quotation',owner=self.admin,status='Sent'))
            self.assertEqual([r['id'] for r in rows],[qid]);self.assertEqual(counts['documents'],1)
            self.assertFalse(documents.workspace(db,dict(q='DATE-REF',filter_year='2025',filter_month='2',basis='date'))[0])
            self.assertEqual(documents.workspace(db,dict(q='DATE-REF',filter_year='2026',filter_month='10',basis='date'))[0][0]['id'],qid)
            self.assertEqual(documents.workspace(db,dict(q='DATE-REF',filter_year='2026',filter_month='11',basis='updated'))[0][0]['id'],qid)
        for n in range(28):self.create_quote(quote('PAG-'+str(n)))
        self.assertEqual(self.c.get('/list/quote?per_page=25').data.count(b'data-family-select'),25)
        self.assertEqual(self.c.get('/list/quote?per_page=50').data.count(b'data-family-select'),30)
        self.assertEqual(self.c.get('/list/quote?per_page=100').status_code,200);self.assertEqual(self.c.get('/list/quote?per_page=500').status_code,400)
    def test_sales_latest_only_not_other_document_types_cancelled_missing_or_zero(self):
        a=self.create_quote(quote('SALES'));self.post('/record/'+a+'/copy/revision');self.doc('PO');self.create_quote(quote('CANCELLED',status='Cancelled'))
        z=quote('ZERO',price='0');z['document']['sections'][0]['rows'][1]['fixed_fee']='0';self.create_quote(z);self.create_quote(quote('UNKNOWN',price=''));self.won(a)
        with store.connect(self.root) as db:
            rows,stats,counts,_=documents.workspace(db,{})
            self.assertEqual(counts['documents'],5);self.assertEqual(stats['total'],3);self.assertEqual(stats['missing'],1);self.assertEqual(stats['zero_count'],1);self.assertEqual(stats['value'],'1,375.00');self.assertEqual(stats['won_value'],'1,375.00');self.assertEqual(sum(m['count'] for m in stats['months']),4)
            self.assertEqual(documents.workspace(db,dict(type='PO'))[1]['value'],'0.00')
    def test_compare_unrelated_structures_and_permissions(self):
        a=self.create_quote(quote('COMPARE-A'));b=quote('COMPARE-B',price='250');b['scope']='Different scope';b['internal_notes']='PRIVATE-COST-SENTINEL';b['document']['sections'][0]['rows'][0]['service']='Different VM';bid=self.create_quote(b)
        html=self.c.get('/quotes/'+a+'/compare?before='+a+'&after='+bid);self.assertEqual(html.status_code,200);self.assertIn(b'Different scope',html.data);self.assertIn(b'Added',html.data);self.assertIn(b'Removed',html.data);self.assertIn(b'Initial recurring monthly fee',html.data);self.assertNotIn(b'PRIVATE-COST-SENTINEL',html.data)
        editor=self.login('editor');self.assertEqual(editor.get('/quotes/'+a+'/compare?after='+bid).status_code,404)
        self.post('/record/'+a+'/access',**{self.viewer:'read'});viewer=self.login('viewer');self.assertEqual(viewer.get('/quotes/'+a+'/compare?after='+bid).status_code,404);self.assertEqual(viewer.get('/quotes/'+a+'/costing').status_code,404)
    def test_twelve_month_toggle_all_projections_and_no_math_change(self):
        qid=self.create_quote(quote('TOGGLE'));q=self.record(qid)['data'];before=calculate(q['document']);self.assertTrue(validate_document(q['document'])['show_12_month'])
        for enabled in (False,True):
            q['document']['show_12_month']=enabled;self.assertEqual(self.post('/quotes/'+qid+'/edit',quotation=json.dumps(q)).status_code,302)
            self.assertEqual(calculate(q['document']),before);self.assertEqual(self.record(qid)['data']['document']['show_12_month'],enabled)
            html=self.c.get('/quotes/'+qid+'/print').data.decode();self.assertEqual('<th>12 months</th>' in html,enabled)
            csv=self.c.get('/quotes/'+qid+'/csv').data.decode('utf-8-sig');self.assertEqual('12 months' in csv,enabled)
            book=load_workbook(io.BytesIO(self.c.get('/quotes/'+qid+'/xlsx').data),data_only=True);ws=book['Quotation'];self.assertEqual(any(c.value=='12 months' for row in ws for c in row),enabled)
            if not enabled:
                header=next(row[0].row for row in ws if row[0].value=='Category');self.assertEqual(ws.cell(header,6).value,'One-Time Fee');self.assertIsNotNone(ws.cell(header+1,6).value)
            for phrase in ('Yearly recurring total (first 12 months)','Contract recurring total','Contract tax','Rev nb','Prices provided exclude VAT'):self.assertNotIn(phrase,html)
    def test_management_followup_links_owner_history_and_stale_protection(self):
        ident=self.doc('PO');second=self.doc('SLA')
        with store.connect(self.root) as db:
            meta=dict(db.execute('SELECT * FROM document_management WHERE record_id=?',(ident,)).fetchone());self.assertEqual(meta['created_by'],self.admin)
        payload=dict(version=str(meta['version']),snapshot=fingerprint(self.record(ident)['data']),follow_date='2026-11-01',follow_note='Call customer',links=[second],owner=self.editor)
        self.assertEqual(self.post('/documents/'+ident+'/manage',**payload).status_code,302);self.assertEqual(self.post('/documents/'+ident+'/manage',**payload).status_code,400)
        page=self.c.get('/documents/'+ident+'/manage');self.assertIn(b'Call customer',page.data);self.assertIn(b'Owner changed',page.data);self.assertIn(self.record(second)['data']['title'].encode(),page.data);self.assertIn(b'Overdue',self.c.get('/list/quote').data)
        editor=self.login('editor');self.assertEqual(editor.get('/documents/'+ident+'/edit').status_code,200);self.assertEqual(editor.get('/documents/'+second+'/edit').status_code,404)
        self.c.get('/documents/'+ident+'/txt')
        with store.connect(self.root) as db:self.assertTrue(db.execute("SELECT 1 FROM document_activity WHERE record_id=? AND action='Exported'",(ident,)).fetchone())
    def test_generic_revisions_archive_delete_and_reference_protection(self):
        ident=self.doc('SOW');number=self.record(ident)['data']['number'];response=self.post('/record/'+ident+'/copy/revision');self.assertEqual(response.status_code,302);revision=response.location.rsplit('/',1)[-1]
        self.assertEqual(self.record(revision)['data']['number'],number);self.assertEqual(self.record(revision)['data']['revision'],2)
        self.bulk([number],confirm=True)
        preview=self.post('/quotes/bulk',action='delete',references=[number],archive_view='archived');self.assertIn(b'Revision 2',preview.data)
        digest=re.search(rb'name="selection_hash" value="([^"]+)"',preview.data)[1].decode()
        self.assertEqual(self.post('/quotes/bulk',action='delete',references=[number],archive_view='archived',confirm='yes',selection_hash=digest,delete_phrase='DELETE').status_code,302)
        with store.connect(self.root) as db:
            self.assertFalse(db.execute('SELECT 1 FROM records WHERE id=?',(ident,)).fetchone());self.assertTrue(db.execute('SELECT 1 FROM reference_registry WHERE key=?',(number.casefold(),)).fetchone());self.assertFalse(db.execute('SELECT 1 FROM document_management WHERE record_id=?',(ident,)).fetchone())
    def test_schema8_upgrade_is_additive_unknown_creators_and_full_backup(self):
        ident=self.create_quote()
        with store.connect(self.root) as db:
            before=[tuple(r) for r in db.execute('SELECT * FROM records ORDER BY id')]
            for table in ('document_links','document_management','document_activity'):db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=8')
        store.migrate(self.root)
        with store.connect(self.root) as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM records ORDER BY id')],before);self.assertIsNone(db.execute('SELECT created_by FROM document_management WHERE record_id=?',(ident,)).fetchone()[0]);self.assertFalse(db.execute('SELECT 1 FROM document_activity').fetchone())
        archive=Path(self.temp.name)/'all.zip';backup(self.root,archive);restore(archive,Path(self.temp.name)/'restored')
        with store.connect(Path(self.temp.name)/'restored') as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],18)
    def test_followup_and_links_carry_forward_to_revision_without_new_family(self):
        ident=self.doc();other=self.doc('PO')
        payload=dict(version='1',snapshot=fingerprint(self.record(ident)['data']),follow_date='2026-11-10',follow_note='Retain this follow-up',links=[other],owner=self.admin)
        self.assertEqual(self.post('/documents/'+ident+'/manage',**payload).status_code,302)
        response=self.post('/record/'+ident+'/copy/revision');revision=response.location.rsplit('/',1)[-1]
        with store.connect(self.root) as db:
            self.assertEqual(db.execute('SELECT follow_note FROM document_management WHERE record_id=?',(revision,)).fetchone()[0],'Retain this follow-up');self.assertTrue(db.execute('SELECT 1 FROM document_links WHERE source_id=? AND target_id=?',(revision,other)).fetchone())
        self.assertEqual(self.record(ident)['data']['number'],self.record(revision)['data']['number'])

    def test_generic_custom_reference_case_uniqueness_and_identity(self):
        a=self.doc('PO');b=self.doc('SLA');d=self.record(a)['data'];d['number']='Customer/Custom-Reference'
        with store.connect(self.root) as db:store.save(db,'document',d,a)
        d2=self.record(b)['data'];d2['number']='customer/custom-reference'
        from workspace_app.model import ValidationError
        with self.assertRaises(ValidationError):
            with store.connect(self.root) as db:store.save(db,'document',d2,b)
    def test_cannot_link_hidden_documents_or_manage_as_viewer(self):
        a=self.doc();b=self.doc('PO');self.assertEqual(self.post('/record/'+a+'/access',**{self.editor:'edit',self.viewer:'read'}).status_code,302)
        editor=self.login('editor');viewer=self.login('viewer');r=self.record(a)
        payload=dict(version='1',snapshot=fingerprint(r['data']),follow_date='',follow_note='',links=[b])
        self.assertEqual(self.post('/documents/'+a+'/manage',client=editor,**payload).status_code,404)
        self.assertEqual(self.post('/documents/'+a+'/manage',client=viewer,**payload).status_code,403)
        self.assertTrue(viewer.get('/record/'+a).location.endswith('/print'));self.assertEqual(viewer.get('/documents/'+a+'/print').status_code,200)
        html=viewer.get('/documents/'+a+'/manage');self.assertNotIn(self.record(b)['data']['title'].encode(),html.data)
    def test_unknown_creation_date_is_not_fabricated_or_used_as_document_month(self):
        ident=self.create_quote()
        with store.connect(self.root) as db:
            db.execute("UPDATE records SET created='' WHERE id=?",(ident,))
            rows,stats,_,_=documents.workspace(db,{})
            self.assertEqual(rows[0]['family_created_display'],'Unknown');self.assertEqual(stats['value'],'1,375.00');self.assertEqual(stats['unknown_chart_dates'],1);self.assertEqual(sum(m['count'] for m in stats['months']),0)
            self.assertFalse(documents.workspace(db,dict(filter_year='2026'))[0])

    def test_revision_retains_custom_subject_and_manual_title(self):
        q=quote('TITLE-SUBJECT');q['title']='TITLE-SUBJECT_Bank-Custom security Quotation_V1.0';ident=self.create_quote(q)
        response=self.post('/record/'+ident+'/copy/revision');revision=response.location.rsplit('/',1)[-1]
        self.assertEqual(self.record(revision)['data']['title'],'TITLE-SUBJECT_Bank-Custom security Quotation_V2.0')
        d=self.record(revision)['data'];d['title']='Fully manual title';self.post('/quotes/'+revision+'/edit',quotation=json.dumps(d));response=self.post('/record/'+revision+'/copy/revision');next_id=response.location.rsplit('/',1)[-1];self.assertEqual(self.record(next_id)['data']['title'],'Fully manual title')

    def test_inline_title_stale_guard_and_workflow_does_not_reopen(self):
        qid=self.create_quote();self.won(qid);r=self.record(qid)
        self.assertEqual(self.post('/documents/'+qid+'/title',snapshot=fingerprint(r['data']),title='Won manual title').status_code,302)
        with store.connect(self.root) as db:self.assertEqual(outcomes.get(db,key_for(r))['status'],'Won')
        self.assertEqual(self.post('/documents/'+qid+'/title',snapshot=fingerprint(r['data']),title='Stale').status_code,400)


def key_for(r):return r['data']['number'].casefold()
for name in ('tearDown','login','post','create_quote','record','won','bulk'):
    setattr(DocumentTests,name,getattr(v8.V8Tests,name))
if __name__=='__main__':unittest.main()
