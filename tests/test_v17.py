"""V17 permanent deletion, sent milestones, monthly reports and file permissions."""
import copy,io,json,re,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from werkzeug.datastructures import MultiDict
from workspace_app import store,approvals as flow,notifications,reporting,archives,quotation_deletion as deletion
from workspace_app.commercial import fingerprint
from workspace_app.approval_routes import capture_pdf
from workspace_app.automation import process_pdf
from test_v5 import quote
import test_v12 as old


class Version17(unittest.TestCase):
    setUp=old.WorkflowTests.setUp
    tearDown=old.WorkflowTests.tearDown
    login=old.WorkflowTests.login
    post=old.WorkflowTests.post
    state=old.WorkflowTests.state
    raw=old.WorkflowTests.raw
    submit=old.WorkflowTests.submit
    edit=old.WorkflowTests.edit
    decision=old.WorkflowTests.decision
    approve_all=old.WorkflowTests.approve_all
    configure_email=old.WorkflowTests.configure_email
    renderer=staticmethod(old.WorkflowTests.renderer)

    def sent(self,**values):
        version,round_=self.state();return self.post(self.url+'/approval',action='sent',version=version['version'],hash=version['hash'],round_id=round_['id'],recipient_name='Client Contact',recipient_email='client@example.test',method='Email',**values)

    def drain(self):
        sent=[]
        while notifications.process_email(self.app,lambda cfg,to,subject,text,**kw:sent.append(dict(to=to,subject=subject,text=text,**kw))):pass
        return sent

    def delete_family(self,confirm=True):
        reference=self.raw()['number']
        with store.connect(self.root) as db:db.execute('INSERT OR REPLACE INTO quotation_archives VALUES (?,1,?,?)',(reference.casefold(),'2026-11-05',self.ids['author']))
        r=self.post('/quotes/bulk',action='delete',references=[reference],archive_view='archived')
        if not confirm:return r
        self.assertEqual(r.status_code,200,r.data[:400]);digest=re.search(rb'name="selection_hash" value="([^"]+)"',r.data)[1].decode()
        return self.post('/quotes/bulk',action='delete',references=[reference],archive_view='archived',confirm='yes',selection_hash=digest,delete_phrase='DELETE')

    def test_sent_history_exact_pdf_and_deduplicated_creator_email(self):
        self.configure_email();self.approve_all();self.drain();capture_pdf(self.app,self.renderer)
        self.assertEqual(self.sent().status_code,302);self.assertEqual(self.sent().status_code,302)
        messages=self.drain();self.assertEqual(len(messages),4);self.assertEqual({m['to'] for m in messages},{n+'@example.test' for n in ('author','ops1','ops2','commercial')})
        for m in messages:
            self.assertTrue(m['subject'].startswith('Sent to Client | '));self.assertIn('Quotation Sent to Client',m['html']);self.assertIn('author marked this quotation',m['text']);self.assertIn('Delivery is not verified',m['text']);self.assertNotIn('PRIVATE-NOTES-MARKER',m['text']+m['html']);self.assertNotEqual(m['to'],'client@example.test')
        with store.connect(self.root) as db:
            e=dict(db.execute('SELECT * FROM quotation_sent_events').fetchone());self.assertTrue(e['pdf_hash']);self.assertEqual(e['recipient_email'],'client@example.test');self.assertEqual(db.execute('SELECT count(*) FROM quotation_sent_events').fetchone()[0],1)
        page=self.c.get(self.url+'/approval');self.assertIn(b'Sent to client history',page.data);self.assertIn(b'Client Contact',page.data)
        self.assertIn(b'Sent date',self.c.get('/list/quote?basis=sent').data);self.assertEqual(self.drain(),[])
        with self.app.test_request_context('/'):
            from flask import g
            from workspace_app.documents import workspace
            with store.connect(self.root) as db:
                g.user=dict(db.execute('SELECT * FROM users WHERE id=?',(self.ids['author'],)).fetchone());self.assertEqual(workspace(db,dict(basis='sent'))[2]['sent'],1)

    def test_sent_requires_fields_pdf_and_permissions_and_legacy_migration(self):
        self.approve_all();v,r=self.state()
        self.assertIn(b'PDF',self.sent().data);capture_pdf(self.app,self.renderer)
        bad=self.post(self.url+'/approval',action='sent',version=v['version'],hash=v['hash'],round_id=r['id']);self.assertEqual(bad.status_code,200)
        response=self.post(self.url+'/approval',client=self.clients['ops1'],action='sent',version=v['version'],hash=v['hash'],round_id=r['id'],recipient_name='Contact',method='WhatsApp');self.assertEqual(response.status_code,403)
        self.assertEqual(self.sent().status_code,302)
        with store.connect(self.root) as db:db.execute('DELETE FROM quotation_sent_events');db.execute('PRAGMA user_version=15')
        store.migrate(self.root);store.migrate(self.root)
        with store.connect(self.root) as db:
            legacy=dict(db.execute('SELECT * FROM quotation_sent_events').fetchone());self.assertEqual(legacy['legacy'],1);self.assertEqual(legacy['method'],'');self.assertEqual(legacy['recipient_email'],'')
        self.assertEqual(self.drain(),[])

    def test_deletes_approved_sent_discussion_all_children_and_owned_files(self):
        self.configure_email();self.approve_all();capture_pdf(self.app,self.renderer);self.sent();self.post(self.url+'/discussion',body='Delete discussion');self.assertEqual(self.post('/record/'+self.ident+'/copy/revision').status_code,302)
        external=Path(self.temp.name)/'exports';external.mkdir();owned=external/'quote.pdf';owned.write_bytes(b'%PDF-owned');other=external/'unrelated.pdf';other.write_bytes(b'%PDF-unrelated')
        attachment=self.root/'attachments'/'owned.bin';attachment.write_bytes(b'attachment')
        with store.connect(self.root) as db:
            db.execute('INSERT INTO attachments VALUES (?,?,?,?,?)',('file',self.ident,'owned.bin','owned.bin','application/octet-stream'))
            db.execute('INSERT INTO pdf_file_owners(path_key,record_id,path,revision) VALUES (?,?,?,1)',('owned-key',self.ident,str(owned)))
        result=self.delete_family();self.assertEqual(result.status_code,302);self.assertEqual(result.location,'/quotation-deletions');self.assertFalse(owned.exists());self.assertTrue(other.exists());self.assertTrue(external.exists());self.assertFalse(attachment.exists())
        with store.connect(self.root) as db:
            for table in ('approval_rounds','approval_versions','approval_messages','approval_reviews','approval_artifacts','portal_notifications','notification_emails','sent_email_recipients','approval_email_batches','approval_email_recipients','quotation_sent_events','quote_costing'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)
            self.assertEqual(db.execute('SELECT status FROM quotation_deletions').fetchone()[0],'Complete');self.assertEqual(db.execute('SELECT revisions FROM quotation_deletions').fetchone()[0],2)
            self.assertTrue(db.execute('SELECT 1 FROM reference_registry WHERE key=?',('approval-test',)).fetchone())
            self.assertTrue(db.execute('SELECT 1 FROM deleted_quotation_ids WHERE record_id=?',(self.ident,)).fetchone())
        self.assertEqual(self.drain(),[])

    def test_external_cleanup_failure_retry_and_permissions(self):
        folder=Path(self.temp.name)/'exports';folder.mkdir();p=folder/'q.pdf';p.write_bytes(b'%PDF-q')
        with store.connect(self.root) as db:db.execute('INSERT INTO pdf_file_owners(path_key,record_id,path,revision) VALUES (?,?,?,1)',('key',self.ident,str(p)))
        real=Path.unlink
        def blocked(path,*a,**kw):
            if path==p:raise PermissionError('File locked on Windows')
            return real(path,*a,**kw)
        with patch.object(Path,'unlink',blocked):self.assertEqual(self.delete_family().status_code,302)
        with store.connect(self.root) as db:
            job=dict(db.execute('SELECT * FROM quotation_deletions').fetchone());self.assertEqual(job['status'],'Cleanup pending');self.assertFalse(db.execute('SELECT 1 FROM records WHERE id=?',(self.ident,)).fetchone())
        self.assertIn(b'File locked on Windows',self.c.get('/quotation-deletions').data)
        self.assertEqual(self.post('/quotation-deletions',client=self.clients['outsider'],id=job['id']).status_code,404)
        self.assertEqual(self.post('/quotation-deletions',id=job['id']).status_code,302);self.assertFalse(p.exists())
        self.assertIn(b'Complete',self.c.get('/quotation-deletions').data)

    def test_running_export_cannot_recreate_deleted_quotation(self):
        folder=Path(self.temp.name)/'pdfs';folder.mkdir();customer_folder=folder/'Customer';customer_folder.mkdir()
        with store.connect(self.root) as db:
            db.execute("INSERT INTO settings VALUES ('automation',?)",(json.dumps(dict(pdf_enabled=True,pdf_folder=str(folder))),))
            db.execute('INSERT INTO customer_export_folders VALUES (?,?,?,?,?,?)',(self.customer,str(customer_folder),'native:'+str(customer_folder),1,'2026-11-05',self.ids['admin']))
            from workspace_app.automation import enqueue
            enqueue(db,self.ident,self.raw())
        def renderer(app,data,destination):
            self.assertEqual(self.delete_family().status_code,302);Path(destination).write_bytes(b'%PDF-'+b'x'*200)
        self.assertTrue(process_pdf(self.app,renderer));self.assertFalse(list(customer_folder.glob('*.pdf')))
        with store.connect(self.root) as db:self.assertFalse(db.execute('SELECT 1 FROM pdf_exports WHERE record_id=?',(self.ident,)).fetchone())

    def test_monthly_report_totals_no_term_multiplication_and_revision_dedup(self):
        with store.connect(self.root) as db:
            q=self.raw();q['revision']=2;q['document']['contract_months']=36;latest=store.save(db,'quote',q,inherit_from=self.ident)
            db.execute('UPDATE records SET owner_id=?,created=? WHERE id=?',(self.ids['author'],'2026-11-05T10:00:00+00:00',latest));db.execute('UPDATE records SET created=? WHERE id=?',('2026-11-01T10:00:00+00:00',self.ident))
        for period in ('month','quarter','year'):
            with self.app.test_request_context('/'):
                from flask import g
                with store.connect(self.root) as db:
                    g.user=dict(db.execute('SELECT * FROM users WHERE id=?',(self.ids['author'],)).fetchone());report=reporting.build(db,dict(report='register',period=period,year='2026',month='11',quarter='4'))
            self.assertEqual(len(report['rows']),1);self.assertEqual(report['rows'][0]['revision'],2);self.assertEqual(report['summary']['monthly'],'100.00');self.assertEqual(report['summary']['one_time'],'50.00')
        self.assertIn(b'USD/month',self.c.get('/reports?period=all').data)

    def test_missing_zero_foreign_currency_and_scope_reports(self):
        self.edit(lambda q:q['document']['sections'][0]['rows'][0].update(unit_price=''))
        page=self.c.get('/reports?report=register&period=all');self.assertIn(b'Unpriced',page.data)
        self.assertNotIn(b'APPROVAL-TEST',self.clients['outsider'].get('/reports?period=all').data)
        self.assertNotIn(b'PRIVATE-NOTES-MARKER',page.data)
        self.assertEqual(self.c.get('/reports?period=custom&start=2026-11-30&end=2026-11-01').status_code,400)

    def test_pending_family_once_sent_exact_snapshot_and_date_filters(self):
        self.submit();self.decision('ops1');page=self.c.get('/reports?report=pending&period=all');self.assertIn(b'ops2',page.data);self.assertIn(b'commercial',page.data)
        self.decision('ops2');self.decision('commercial');capture_pdf(self.app,self.renderer);self.sent()
        original=self.raw()['title'];self.edit(lambda q:q.update(title='New revision wording'))
        with self.app.test_request_context('/'):
            from flask import g
            with store.connect(self.root) as db:
                g.user=dict(db.execute('SELECT * FROM users WHERE id=?',(self.ids['author'],)).fetchone());r=reporting.build(db,dict(report='sent',period='all'))
                self.assertEqual(r['sent_events'],1);self.assertEqual(r['sent_count'],1);self.assertEqual(r['rows'][0]['revision'],1);self.assertEqual(r['summary']['monthly'],'100.00')

    def test_reports_folder_pdf_unique_download_and_revoked_access(self):
        folder=Path(self.temp.name)/'reports';folder.mkdir()
        self.assertEqual(self.post('/reports/settings',client=self.clients['outsider'],reports_folder=str(folder),action='save').status_code,403)
        self.assertEqual(self.post('/reports/settings',client=self.clients['admin'],reports_folder=str(folder),action='save').status_code,302)
        def fake(app,html,path):self.assertIn('USD/month',html);self.assertNotIn('PRIVATE-NOTES-MARKER',html);Path(path).write_bytes(b'%PDF-'+html.encode())
        with patch('workspace_app.automation.print_html_pdf',fake):
            one=self.post('/reports',report='register',period='all');two=self.post('/reports',report='register',period='all')
        self.assertEqual(one.status_code,302);self.assertNotEqual(one.location,two.location);self.assertEqual(len(list(folder.glob('*.pdf'))),2)
        from urllib.parse import parse_qs,urlsplit
        download='/reports/files/'+parse_qs(urlsplit(one.location).query)['generated'][0]
        response=self.c.get(download);self.assertEqual(response.status_code,200);response.close()
        self.assertEqual(self.clients['outsider'].get(download).status_code,403)
        with store.connect(self.root) as db:db.execute('UPDATE records SET owner_id=?',(self.ids['outsider'],))
        self.assertEqual(self.c.get(download).status_code,403)
        with patch('workspace_app.automation.print_html_pdf',side_effect=OSError('Disk full')):self.assertEqual(self.post('/reports',report='register',period='all').status_code,400)
        self.assertEqual(len(list(folder.glob('*.pdf'))),2)

    def test_report_optional_services_zero_and_non_usd_prices(self):
        from test_v15 import optional_quote
        q=optional_quote();q['number']='OPTIONAL-REPORT';q['document']['optional_monitoring']=True
        with store.connect(self.root) as db:
            ident=store.save(db,'quote',q);db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.ids['author'],ident))
            zero=quote('ZERO-REPORT',price='0');zero['document']['sections'][0]['rows'][1]['fixed_fee']='0';zid=store.save(db,'quote',zero);db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.ids['author'],zid))
            fx=quote('FOREIGN-REPORT');fx['currency']='EUR';fid=store.save(db,'quote',fx);db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.ids['author'],fid))
        with self.app.test_request_context('/'):
            from flask import g
            with store.connect(self.root) as db:
                g.user=dict(db.execute('SELECT * FROM users WHERE id=?',(self.ids['author'],)).fetchone());r=reporting.build(db,dict(report='register',period='all'))
        row=next(x for x in r['rows'] if x['reference']=='OPTIONAL-REPORT');self.assertEqual(row['monthly'],'1150.00');self.assertEqual(row['one_time'],'296.00')
        self.assertEqual(r['summary']['non_usd'],1);self.assertGreaterEqual(r['summary']['zero'],1)

    def test_viewer_report_reads_do_not_expose_other_customer_records(self):
        with store.connect(self.root) as db:db.execute('INSERT INTO record_acl VALUES (?,?,?)',(self.ident,self.ids['viewer'],'read'))
        page=self.clients['viewer'].get('/reports?report=register&period=all');self.assertEqual(page.status_code,200);self.assertIn(b'APPROVAL-TEST',page.data);self.assertNotIn(b'PRIVATE-NOTES-MARKER',page.data)
        self.assertEqual(self.clients['viewer'].get('/reports/settings').status_code,403)

    def test_customer_owner_and_quarter_filters_and_report_pdf_errors(self):
        other=quote('OTHER-CUSTOMER');other.update(customer='Different Bank',project_id='',customer_id='')
        with store.connect(self.root) as db:
            ident=store.save(db,'quote',other);db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.ids['author'],ident))
        page=self.c.get('/reports?report=register&period=all&customer_id='+self.customer+'&owner='+self.ids['author']);self.assertIn(b'APPROVAL-TEST',page.data);self.assertNotIn(b'OTHER-CUSTOMER',page.data)
        self.assertEqual(self.c.get('/reports?period=quarter&quarter=5').status_code,400)
        response=self.post('/reports',report='register',period='all');self.assertEqual(response.status_code,400);self.assertIn(b'folder is not configured',response.data)

    def test_new_sent_email_uses_creator_not_different_submitter(self):
        self.configure_email();v,_=self.state()
        self.post(self.url+'/approval',client=self.clients['admin'],action='submit',version=v['version'],hash=v['hash'],**self.mapping)
        for n in ('ops1','ops2','commercial'):self.decision(n)
        self.drain();capture_pdf(self.app,self.renderer);self.assertEqual(self.sent().status_code,302)
        sent=self.drain();self.assertEqual({m['to'] for m in sent},{n+'@example.test' for n in ('author','ops1','ops2','commercial')})

    def test_bulk_deletion_reports_each_family_and_retries_only_failed_file(self):
        other=quote('BULK-SECOND');other.update(customer_id=self.customer,project_id=self.project)
        exports=Path(self.temp.name)/'bulk-exports';exports.mkdir();locked=exports/'locked.pdf';locked.write_bytes(b'%PDF-locked');clean=exports/'clean.pdf';clean.write_bytes(b'%PDF-clean')
        with store.connect(self.root) as db:
            second=store.save(db,'quote',other);db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.ids['author'],second))
            for rid,ref,path in [(self.ident,'approval-test',locked),(second,'bulk-second',clean)]:
                db.execute('INSERT INTO quotation_archives VALUES (?,1,?,?)',(ref,'2026-11-05',self.ids['author']));db.execute('INSERT INTO pdf_file_owners(path_key,record_id,path,revision) VALUES (?,?,?,1)',(str(path),rid,str(path)))
        references=['APPROVAL-TEST','BULK-SECOND'];review=self.post('/quotes/bulk',action='delete',references=references,archive_view='archived');digest=re.search(rb'name="selection_hash" value="([^"]+)"',review.data)[1].decode();real=Path.unlink
        def blocked(path,*a,**kw):
            if path==locked:raise PermissionError('Synthetic locked file')
            return real(path,*a,**kw)
        with patch.object(Path,'unlink',blocked):result=self.post('/quotes/bulk',action='delete',references=references,archive_view='archived',confirm='yes',selection_hash=digest,delete_phrase='DELETE')
        self.assertEqual(result.status_code,302);self.assertTrue(locked.exists());self.assertFalse(clean.exists())
        with store.connect(self.root) as db:
            rows={r['reference'].casefold():dict(r) for r in db.execute('SELECT * FROM quotation_deletions')};self.assertEqual(rows['approval-test']['status'],'Cleanup pending');self.assertEqual(rows['bulk-second']['status'],'Complete');self.assertFalse(db.execute("SELECT 1 FROM records WHERE kind='quote'").fetchone())
        self.assertEqual(self.post('/quotation-deletions',id=rows['approval-test']['id']).status_code,302);self.assertFalse(locked.exists())
        with store.connect(self.root) as db:self.assertEqual(db.execute("SELECT count(*) FROM quotation_deletions WHERE status='Complete'").fetchone()[0],2)

    def test_sent_report_uses_historical_customer_after_reassignment(self):
        self.approve_all();capture_pdf(self.app,self.renderer);self.sent()
        with store.connect(self.root) as db:
            new_customer=store.save(db,'customer',dict(name='New Bank',contact='',notes=''));db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.ids['author'],new_customer))
        self.edit(lambda q:q.update(customer='New Bank',customer_id=new_customer,project_id=''))
        with self.app.test_request_context('/'):
            from flask import g
            with store.connect(self.root) as db:
                g.user=dict(db.execute('SELECT * FROM users WHERE id=?',(self.ids['author'],)).fetchone());r=reporting.build(db,dict(report='sent',period='all',customer_id=self.customer))
        self.assertEqual(len(r['rows']),1);self.assertNotEqual(r['rows'][0]['client'],'New Bank');self.assertEqual(r['summary']['monthly'],'100.00')

    def test_sent_shared_email_addresses_and_failed_delivery_retry(self):
        self.configure_email();self.approve_all();self.drain();capture_pdf(self.app,self.renderer)
        with store.connect(self.root) as db:
            db.execute('UPDATE account_emails SET email=? WHERE user_id=?',('OPS1@example.test',self.ids['author']))
        self.assertEqual(self.sent().status_code,302);self.assertEqual(self.sent().status_code,302)
        def fail(*a,**kw):raise OSError('Synthetic unavailable SMTP')
        self.assertTrue(notifications.process_email(self.app,fail))
        messages=self.drain();self.assertEqual(len(messages),2)
        with store.connect(self.root) as db:
            failed=db.execute("SELECT notification_id FROM notification_emails WHERE status='failed'").fetchone()[0];self.assertEqual(db.execute('SELECT count(*) FROM quotation_sent_events').fetchone()[0],1)
        self.assertEqual(self.post('/administration/workflow',client=self.clients['admin'],action='retry',notification_id=str(failed)).status_code,302)
        messages+=self.drain();self.assertEqual(len(messages),3);self.assertEqual(len({m['to'].casefold() for m in messages}),3)
        self.assertEqual(self.sent().status_code,302);self.assertEqual(self.drain(),[])

    def test_report_preview_styles_comply_with_existing_security_policy(self):
        page=self.c.get('/reports/preview?report=register&period=all');self.assertEqual(page.status_code,200)
        self.assertIn(b'/static/report_document.css',page.data);self.assertNotIn(b'<style>',page.data)
        self.assertIn("style-src 'self'",page.headers['Content-Security-Policy'])
        with self.app.test_request_context('/'):
            from flask import g
            with store.connect(self.root) as db:
                g.user=dict(db.execute('SELECT * FROM users WHERE id=?',(self.ids['author'],)).fetchone());data=reporting.build(db,dict(report='register',period='all'))
            self.assertIn('<style>',reporting.document_html(data,inline=True))


    def test_report_filename_collision_preserves_previously_saved_report(self):
        from datetime import datetime,timezone
        from types import SimpleNamespace
        folder=Path(self.temp.name)/'reports';folder.mkdir()
        self.assertEqual(self.post('/reports/settings',client=self.clients['admin'],reports_folder=str(folder),action='save').status_code,302)
        def fake(app,html,path):Path(path).write_bytes(b'%PDF-existing-report')
        fixed=SimpleNamespace(now=lambda tz:datetime(2026,11,5,12,0,tzinfo=timezone.utc))
        with patch('workspace_app.reporting.uuid4',return_value=SimpleNamespace(hex='a'*32)),patch('workspace_app.reporting.datetime',fixed),patch('workspace_app.automation.print_html_pdf',fake):
            self.assertEqual(self.post('/reports',report='register',period='all').status_code,302)
            response=self.post('/reports',report='register',period='all');self.assertEqual(response.status_code,400);self.assertIn(b'collision',response.data)
        paths=list(folder.glob('*.pdf'));self.assertEqual(len(paths),1);self.assertEqual(paths[0].read_bytes(),b'%PDF-existing-report');self.assertFalse(list(folder.glob('.cirrus-report-*.tmp')))
