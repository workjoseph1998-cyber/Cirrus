from editor_requests import fields_for
"""V5 persistence, permission-filtered statistics and genuine SQLite races."""
import copy,io,json,sqlite3,tempfile,threading,time,unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from openpyxl import Workbook,load_workbook
from workspace_app import create_app,store,security,references,statistics
from workspace_app.model import ValidationError
from workspace_app.quotation import new_row,new_section,calculate
from workspace_app.quote_excel import export_excel
from workspace_app.backup import backup,restore
from quotation_fixture import fixture

PASSWORD='Synthetic-V5-password-2026!'


def quote(reference='CIR26-148-1',price='100',status='Sent',currency='USD',revision=1):
    q=fixture();doc=q['document'];section=new_section('Production');section['rows']=[new_row('Monthly service',quantity='1',unit_price=price),new_row('Setup',quantity='1',method='fixed',fixed_fee='50',billing='one_time')]
    doc['sections']=[section];doc['discount'].update(enabled=False,percent='0',months=0,targets=[]);doc['tax'].update(mode='added',rate='10')
    q.update(number=reference,title='Synthetic quotation',customer='Synthetic customer',revision=revision,status=status,currency=currency,tax='10')
    return q


def record(q,created='2026-10-01T00:00:00+00:00'):
    return dict(id=str(uuid4()),kind='quote',data=q,created=created,updated=created)


class StatisticsTests(unittest.TestCase):
    def test_latest_revisions_unknown_prices_status_and_currency(self):
        rows=[record(quote(price='10')),record(quote(price='200',revision=2)),record(quote('CUSTOM',status='Draft')),record(quote('EURO',currency='EUR')),record(quote('CANCEL',status='Cancelled')),record(quote('MISSING',price='')),record(quote('ZERO',price='0')),record(quote('REJECT',status='Rejected'))]
        result=statistics.quotations(rows,{'period':'month'},date(2026,10,29))
        # Fully priced USD Sent/Accepted only: (200*12+50)*1.1 + (0*12+50)*1.1.
        self.assertEqual(result['total'],7);self.assertEqual(result['value'],'6,875.00');self.assertEqual(result['average'],'1,375.00');self.assertEqual(result['month_count'],7)
        self.assertEqual(result['missing'],1);self.assertEqual(result['statuses']['Draft'],1);self.assertEqual(result['non_usd']['EUR'],1)
        self.assertEqual(sum(m['count'] for m in result['months']),7)
        self.assertEqual(result['months'][0]['value'],'6,875.00')

    def test_issue_dates_not_creation_timestamps_and_filters(self):
        first=record(quote(),created='2026-09-30T22:30:00+00:00') # Oct 1 in Beirut
        revision=record(quote(revision=2),created='2026-11-01T00:00:00+00:00')
        first['data']['date']='2026-10-01';revision['data']['date']='2026-10-02'
        result=statistics.quotations([first,revision],{'period':'month'},date(2026,10,29))
        self.assertEqual(result['total'],1);self.assertEqual(result['month_count'],1)
        self.assertEqual(statistics.quotations([first],{'period':'last_month'},date(2026,10,29))['total'],0)
        self.assertEqual(statistics.quotations([first],{'period':'custom','start':'2026-10-01','end':'2026-10-01'})['total'],1)
        self.assertEqual(statistics.quotations([first],{'period':'all','q':'cir26-148'},date(2026,10,29))['total'],1)
        self.assertEqual(statistics.quotations([first],{'period':'all','q':'not this customer'})['total'],0)
        with self.assertRaises(ValidationError):statistics.quotations([] ,{'period':'custom','start':'2026-10-31','end':'2026-10-01'})
        statistics.quotations([],{'period':'all'},date(2024,2,29))

    def test_invalid_latest_fallback_and_cancellation_never_revives_value(self):
        old=record(quote());bad=record(quote(revision=2));bad['data']['document']['sections']='bad'
        result=statistics.quotations([old,bad],{'period':'all'},date(2026,10,29));self.assertEqual(result['invalid'],1);self.assertEqual(result['value'],'0.00');self.assertEqual(result['missing'],1)
        bad['data']['status']='Cancelled'
        result=statistics.quotations([old,bad],{'period':'all'},date(2026,10,29));self.assertEqual(result['value'],'0.00');self.assertEqual(result['total'],1)


class V5Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'data';self.app=create_app(self.root,True)
        with store.connect(self.root) as db:
            self.admin=security.create_user(db,'v5-admin',PASSWORD,'Administrator',True)
            self.editor=security.create_user(db,'v5-editor',PASSWORD,'Editor');self.viewer=security.create_user(db,'v5-viewer',PASSWORD,'Viewer')
        self.client=self.login('v5-admin')
    def tearDown(self):self.temp.cleanup()
    def login(self,name):
        c=self.app.test_client();c.get('/login')
        with c.session_transaction() as s:csrf=s['csrf']
        self.assertEqual(c.post('/login',data=dict(csrf=csrf,username=name,password=PASSWORD)).status_code,302)
        return c
    def post(self,path,c=None,**fields):
        c=c or self.client
        with c.session_transaction() as s:csrf=s['csrf']
        return c.post(path,data=dict(csrf=csrf,**fields_for(c,path,fields)))
    def save(self,q,c=None):return self.post('/quotes/new',c,quotation=json.dumps(q))

    def test_shared_registry_reservation_expiry_renewal_and_custom_case(self):
        editor=self.login('v5-editor')
        self.assertEqual(self.post('/references',action='reserve',reference='Custom/AbC',kind='proposal').status_code,302)
        self.assertIn(b'already reserved',self.post('/references',editor,action='reserve',reference='CUSTOM/abc',kind='document').data)
        self.assertEqual(self.post('/references',action='renew',key=references.key('Custom/AbC')).status_code,302)
        with store.connect(self.root) as db:db.execute('UPDATE reference_registry SET expires=?',(time.time()-1,))
        self.assertIn(b'expired',self.post('/references',action='renew',key=references.key('Custom/AbC')).data)
        self.assertEqual(self.post('/references',editor,action='reserve',reference='CUSTOM/abc',kind='document').status_code,302)
        self.assertEqual(self.post('/references',editor,action='issue',key=references.key('Custom/AbC')).status_code,302)
        self.assertIn(b'already issued',self.post('/references',action='reserve',reference='custom/ABC',kind='quotation').data)

    def test_save_revision_idempotence_and_deleted_reference_never_reused(self):
        response=self.save(quote());self.assertEqual(response.status_code,302);ident=response.location.split('/')[-2]
        self.assertEqual(self.save(quote(reference='cir26-148-1')).status_code,200) # editor displays clear validation error
        response=self.post('/record/'+ident+'/copy/revision');new_id=response.location.rsplit('/',1)[-1]
        again=self.post('/record/'+ident+'/copy/revision');self.assertEqual(again.location,response.location)
        with store.connect(self.root) as db:
            self.assertEqual(len([r for r in store.records(db) if r['kind']=='quote']),2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reference_assignments').fetchone()[0],2)
        self.post('/record/'+new_id+'/delete');self.post('/record/'+ident+'/delete')
        result=self.save(quote());self.assertIn(b'already issued',result.data)
        # Deleting a retained legacy collision clears its review flag, not issued history.
        with store.connect(self.root) as db:
            db.execute('INSERT INTO records (id,kind,data,created,updated,owner_id) VALUES (?,?,?,?,?,?)',('legacy-duplicate','quote',json.dumps(quote()),'2026-10-01T00:00:00+00:00','2026-10-01T00:00:00+00:00',self.admin))
            db.execute('INSERT INTO reference_conflicts VALUES (?,?,?)',('legacy-duplicate','cir26-148-1',1))
        self.assertEqual(self.post('/record/legacy-duplicate/delete').status_code,302)
        with store.connect(self.root) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reference_conflicts').fetchone()[0],0)
            self.assertEqual(db.execute("SELECT state FROM reference_registry WHERE key='cir26-148-1'").fetchone()[0],'issued')

    def test_reservations_guard_new_quote_saves_and_assignment_unique_constraint(self):
        editor=self.login('v5-editor');self.post('/references',action='reserve',reference='CIR26-148-1',kind='quotation')
        self.assertIn(b'reserved by another',self.save(quote(),editor).data)
        with store.connect(self.root) as db:db.execute('UPDATE reference_registry SET expires=?',(time.time()-1,))
        self.assertIn(b'Reservation expired',self.save(quote()).data)
        self.post('/references',action='reserve',reference='CIR26-148-1',kind='quotation');self.assertEqual(self.save(quote()).status_code,302)
        with store.connect(self.root) as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('INSERT INTO reference_assignments VALUES (?,?,?)',('collision','CIR26-148-1',1))

    def test_real_sqlite_concurrent_reserve_and_issue(self):
        barrier=threading.Barrier(2)
        def reserve_one(uid):
            try:
                with self.app.test_request_context():
                    from flask import g
                    g.user=dict(id=uid,role='Editor');barrier.wait(timeout=5)
                    with store.connect(self.root) as db:
                        db.execute('BEGIN IMMEDIATE');references.reserve(db,'CIR26-150-1')
                return 'ok'
            except ValidationError:return 'blocked'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve_one,[self.admin,self.editor]))
        self.assertEqual(sorted(results),['blocked','ok'])
        with store.connect(self.root) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reference_registry').fetchone()[0],1)
        # Two different users simultaneously saving the same unreserved reference.
        barrier=threading.Barrier(2)
        def save_one(uid):
            try:
                with self.app.test_request_context():
                    from flask import g
                    g.user=dict(id=uid,role='Editor');barrier.wait(timeout=5)
                    with store.connect(self.root) as db:db.execute('BEGIN IMMEDIATE');store.save(db,'quote',quote('CIR26-151-1'))
                return 'ok'
            except ValidationError:return 'blocked'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save_one,[self.admin,self.editor]))
        self.assertEqual(sorted(results),['blocked','ok'])
        barrier=threading.Barrier(2)
        def next_one(uid):
            with self.app.test_request_context():
                from flask import g
                g.user=dict(id=uid,role='Editor');barrier.wait(timeout=5)
                with store.connect(self.root) as db:
                    db.execute('BEGIN IMMEDIATE');reference=references.overview(db,date(2026,10,29))['next'];references.reserve(db,reference)
                    return reference
        with ThreadPoolExecutor(max_workers=2) as pool:assigned=list(pool.map(next_one,[self.admin,self.editor]))
        self.assertEqual(set(assigned),{'CIR26-152-1','CIR26-153-1'})

    def test_history_csv_excel_preview_atomic_collision_and_next_reference(self):
        result=self.post('/references/import',file=(io.BytesIO(b'Reference,Customer\nCIR26-155-1,ignored\ncir26-155-1,ignored\n'), 'history.csv'))
        self.assertIn(b'Review 1 unique',result.data)
        self.assertEqual(self.post('/references/import',action='confirm',references=json.dumps(['CIR26-155-1'])).status_code,302)
        with store.connect(self.root) as db:
            info=references.overview(db,date(2026,10,29));self.assertEqual(info['last'],'CIR26-155-1');self.assertEqual(info['next'],'CIR26-156-1')
        self.post('/references',action='reserve',reference='CIR26-157-1',kind='document')
        self.assertEqual(self.post('/references/import',action='confirm',references=json.dumps(['CIR26-156-1','CIR26-157-1'])).status_code,400)
        with store.connect(self.root) as db:self.assertFalse(db.execute('SELECT 1 FROM reference_registry WHERE key=?',('cir26-156-1',)).fetchone())
        w=Workbook();w.active.append(['Old Ref']);w.active.append(['CIR25-400-1']);stream=io.BytesIO();w.save(stream)
        self.assertEqual(references.parse_history(stream.getvalue(),'history.xlsx','Old Ref'),['CIR25-400-1'])
        self.assertEqual(self.post('/references/import',action='confirm',references=json.dumps(['CIR26-155-1'])).status_code,302)
        self.assertIn(b'cannot be reused',self.post('/references',action='reserve',reference='cir26-155-1',kind='quotation').data)

    def test_permissions_statistics_registry_and_retired_navigation(self):
        result=self.save(quote(price='987'));self.assertEqual(result.status_code,302)
        editor=self.login('v5-editor');viewer=self.login('v5-viewer')
        with patch('workspace_app.statistics.today_local',return_value=date(2026,10,29)):
            r=editor.get('/list/quote?period=all');self.assertNotIn(b'13,083.40',r.data);self.assertIn(b'0.00',r.data)
        for endpoint in ('/references','/references/import','/references/check'):
            self.assertEqual(self.post(endpoint,viewer,action='reserve',reference='NO',kind='document').status_code,403)
        self.assertEqual(viewer.get('/references').status_code,200)
        for endpoint in ('/list/note','/list/personal','/list/inbox'):self.assertEqual(editor.get(endpoint).status_code,302)
        html=editor.get('/').data
        for link in (b'href="/list/note"',b'href="/list/inbox"',b'href="/list/personal"'):self.assertNotIn(link,html)
        self.assertEqual(editor.get('/new/note').status_code,404)
        self.assertIn(b'Synthetic quotation',self.client.get('/list/quote?period=all&q=cir26-148').data)

    def test_cleanup_both_cases_legacy_html_excel_and_preserved_calculations(self):
        q=fixture();q['document']['terms'].append(dict(id='old-vat',title='VAT / tax conditions',text='The due VAT will be calculated at the current BDL official rate',visible=True));q['document']['bottom_order'].append('old-vat')
        for item in q['document']['summary']:item['visible']=True
        calc=calculate(q['document']);self.assertEqual(calc['combined'],'7986.23')
        response=self.save(q);ident=response.location.split('/')[-2]
        html=self.client.get('/quotes/'+ident+'/print').data.decode()
        banned=('Yearly recurring total','Contract recurring total','Contract tax','Contract total incl.','30% discount','VAT / tax conditions','The due VAT','Prices provided exclude VAT','Monthly discount','Discounted monthly total')
        for text in banned:self.assertNotIn(text,html)
        self.assertIn('Total monthly fee',html);self.assertIn('670.00',html);self.assertIn('80.00',html)
        w=load_workbook(export_excel(q),data_only=True)
        text=' '.join(str(c.value) for sheet in w for row in sheet for c in row)
        for phrase in banned:self.assertNotIn(phrase,text)
        for url in ('/quotes/new','/quotes/new?blank=1'):
            content=self.client.get(url).data.decode();raw=content.split('id="initial-quotation">')[1].split('</script>')[0];doc=json.loads(raw)['document']
            self.assertFalse(doc['discount']['enabled']);self.assertEqual(doc['discount']['percent'],'0')
        with store.connect(self.root) as db:self.assertEqual(calculate(store.records(db)[0]['data']['document'])['combined'],'7986.23')

    def test_v4_migration_case_collisions_preserved_and_backup_restores_ledger(self):
        old=Path(self.temp.name)/'legacy';store.migrate(old)
        with store.connect(old) as db:
            for i,ref in enumerate(('CIR26-149-1','cir26-149-1')):
                db.execute('INSERT INTO records (id,kind,data,created,updated) VALUES (?,?,?,?,?)',(str(i),'quote',json.dumps(quote(ref)),'2026-10-01T00:00:00+00:00','2026-10-01T00:00:00+00:00'))
            db.execute('DROP TABLE reference_assignments');db.execute('DROP TABLE reference_registry');db.execute('DROP TABLE reference_conflicts');db.execute('PRAGMA user_version=4')
        store.migrate(old)
        with store.connect(old) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reference_registry').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reference_conflicts').fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],18)
            from workspace_app.model import FIELDS
            project={k:'' for k,_,_ in FIELDS['project']};project.update(name='Unaffected project',customer='Synthetic customer',status='Active')
            store.save(db,'project',project) # Legacy duplicate quotes must not block unrelated work.
        archive=Path(self.temp.name)/'backup.zip';backup(old,archive);restored=Path(self.temp.name)/'restored';restore(archive,restored)
        with store.connect(restored) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM reference_conflicts').fetchone()[0],1)


if __name__=='__main__':unittest.main()
