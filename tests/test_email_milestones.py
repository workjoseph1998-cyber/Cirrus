"""Approval-only email delivery, MIME/privacy, idempotency and safe migration."""
import copy,json,re,unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from workspace_app import store,notifications,approvals as flow,approval_emails
from workspace_app.commercial import fingerprint
from test_v5 import quote
import test_v12 as workflow


class MilestoneEmails(unittest.TestCase):
    setUp=workflow.WorkflowTests.setUp
    tearDown=workflow.WorkflowTests.tearDown
    login=workflow.WorkflowTests.login
    post=workflow.WorkflowTests.post
    state=workflow.WorkflowTests.state
    raw=workflow.WorkflowTests.raw
    submit=workflow.WorkflowTests.submit
    edit=workflow.WorkflowTests.edit
    decision=workflow.WorkflowTests.decision
    configure_email=workflow.WorkflowTests.configure_email

    def jobs(self):
        with store.connect(self.root) as db:return [dict(r) for r in db.execute('SELECT * FROM notification_emails')]

    def drain(self):
        sent=[]
        def sender(cfg,to,subject,text,**message):sent.append(dict(to=to,subject=subject,text=text,**message))
        while notifications.process_email(self.app,sender):pass
        return sent

    def test_submission_once_per_selected_approver_html_plain_and_public_metadata(self):
        self.configure_email();version,round_=self.submit();sent=self.drain()
        self.assertEqual({m['to'] for m in sent},{n+'@example.test' for n in ('ops1','ops2','commercial')});self.assertEqual(len(sent),3)
        for m in sent:
            self.assertEqual(m['subject'],'Review Required | '+self.raw()['customer']+' | APPROVAL-TEST')
            for label in ('Submission of New Quotation','CIRRUS WORKPLACE','Review Quotation','author','ops1','ops2','commercial','Revision','Submission date/time','#16395c'):
                self.assertIn(label,m['html'])
            self.assertIn('Sign in',m['text']);self.assertIn('VPN',m['text']);self.assertIn('approval#approval-round-'+round_['id'],m['text']);self.assertIn('[if mso]',m['html'])
            self.assertNotIn('PRIVATE-NOTES-MARKER',m['html']+m['text']);self.assertNotIn('731.29',m['html']+m['text']);self.assertNotIn('Unit cost',m['html'])
        with store.connect(self.root) as db:
            data=db.execute('SELECT data FROM approval_email_batches').fetchone()[0]
            self.assertNotIn('PRIVATE-NOTES-MARKER',data);self.assertNotIn('731.29',data)
            self.assertEqual(db.execute('SELECT count(*) FROM approval_email_batches').fetchone()[0],1)
        self.assertEqual(self.drain(),[])

    def test_intermediate_events_stay_in_portal_final_only_after_last_approval(self):
        self.configure_email();self.submit();self.drain()
        for name in ('ops1','ops2'):
            self.assertEqual(self.decision(name,comment='Internal cost note 731.29').status_code,302);self.assertEqual(self.drain(),[])
        self.assertEqual(self.post(self.url+'/discussion',body='@ops1 Please review private margin 731.29').status_code,200)
        self.c.get(self.url+'/approval/poll');self.c.get('/notifications/poll');self.post('/notifications/read',all='yes')
        self.assertEqual(self.drain(),[])
        with store.connect(self.root) as db:
            self.assertTrue(db.execute("SELECT 1 FROM portal_notifications WHERE kind='Mention'").fetchone())
            self.assertTrue(db.execute("SELECT 1 FROM portal_notifications WHERE kind='Action required'").fetchone())
        self.assertEqual(self.decision('commercial').status_code,302);sent=self.drain();self.assertEqual(len(sent),4)
        self.assertEqual({m['to'] for m in sent},{n+'@example.test' for n in ('author','ops1','ops2','commercial')})
        for m in sent:
            self.assertEqual(m['subject'],'Fully Approved | '+self.raw()['customer']+' | APPROVAL-TEST')
            self.assertIn('Quotation Fully Approved',m['html']);self.assertIn('#187546',m['html']);self.assertNotIn('Internal cost note',m['html']);self.assertNotIn('731.29',m['html'])
        with store.connect(self.root) as db:
            payload=json.loads(db.execute("SELECT data FROM approval_email_batches WHERE stage='complete'").fetchone()[0])
            self.assertTrue(payload['completed_at']);self.assertTrue(all(r['status']=='Approved' and r['decided_at'] for r in payload['approvers']))
        self.assertEqual(self.drain(),[])

    def test_parallel_repeat_submissions_and_final_decisions_do_not_duplicate(self):
        self.configure_email();version,_=self.state()
        with self.c.session_transaction() as s:auth=dict(s)
        def submit_once(_):
            c=self.app.test_client()
            with c.session_transaction() as s:s.update(auth)
            return self.post(self.url+'/approval',client=c,action='submit',version=version['version'],hash=version['hash'],**self.mapping).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(submit_once,range(2)))
        self.assertEqual(sorted(codes),[200,302]);self.assertEqual(len(self.drain()),3)
        self.decision('ops1');self.decision('ops2');tokens=self.state()
        with self.clients['commercial'].session_transaction() as s:auth=dict(s)
        def approve_once(_):
            c=self.app.test_client()
            with c.session_transaction() as s:s.update(auth)
            return self.post(self.url+'/approval',client=c,action='decision',version=tokens[0]['version'],hash=tokens[0]['hash'],round_id=tokens[1]['id'],decision='Approved',comment='').status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(approve_once,range(2)))
        self.assertEqual(sorted(codes),[200,302]);self.assertEqual(len(self.drain()),4)
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM approval_email_batches').fetchone()[0],2)

    def test_changes_decline_and_deliberate_resubmission_make_new_batches_only(self):
        self.configure_email();_,first=self.submit();self.drain();self.decision('ops1','Changes requested','Scope needs revision')
        self.assertEqual(self.drain(),[]);self.edit(lambda q:q.update(scope='Revised scope'));_,second=self.submit();self.assertNotEqual(first['id'],second['id']);self.assertEqual(len(self.drain()),3)
        self.decision('ops2','Declined','Revise terms');self.assertEqual(self.drain(),[]);_,third=self.submit();self.assertNotEqual(second['id'],third['id']);self.assertEqual(len(self.drain()),3)
        with store.connect(self.root) as db:self.assertEqual(db.execute("SELECT count(*) FROM approval_email_batches WHERE stage='complete'").fetchone()[0],0)

    def test_ordinary_edits_reapproval_has_no_submission_mail_and_cancels_stale_jobs(self):
        self.configure_email();_,old=self.submit();self.edit(lambda q:q.update(scope='New saved scope'))
        _,current=self.state();self.assertNotEqual(old['id'],current['id']);self.assertEqual(self.drain(),[])
        self.assertTrue(all(r['status']=='cancelled' for r in self.jobs()))
        self.edit();self.c.get(self.url+'/edit');self.assertEqual(self.drain(),[])
        for name in ('ops1','ops2','commercial'):self.assertEqual(self.decision(name).status_code,302)
        self.assertEqual(len(self.drain()),4)
        with store.connect(self.root) as db:
            stages=[tuple(r) for r in db.execute('SELECT round_id,stage FROM approval_email_batches')]
            self.assertEqual(set(stages),{(old['id'],'submission'),(current['id'],'complete')})

    def test_duplicate_addresses_and_submitter_as_approver_are_deduplicated(self):
        self.configure_email()
        with store.connect(self.root) as db:
            db.execute('UPDATE account_emails SET email=? WHERE user_id IN (?,?)',('SHARED@example.test',self.ids['author'],self.ids['ops1']))
            db.execute('UPDATE account_emails SET email=? WHERE user_id=?',('shared@example.test',self.ids['ops2']))
        self.submit();self.assertEqual(len(self.drain()),2)
        for name in ('ops1','ops2','commercial'):self.decision(name)
        sent=self.drain();self.assertEqual(len(sent),2);self.assertEqual({m['to'].casefold() for m in sent},{'shared@example.test','commercial@example.test'})

    def test_changed_addresses_do_not_cause_duplicate_final_deliveries(self):
        self.configure_email();self.submit();self.drain()
        for name in ('ops1','ops2','commercial'):self.decision(name)
        with store.connect(self.root) as db:db.execute('UPDATE account_emails SET email=?',('shared@example.test',))
        sent=self.drain();self.assertEqual(len(sent),1)
        self.assertEqual(sum(r['status']=='cancelled' for r in self.jobs()),3)

    def test_disabled_or_unconfigured_email_remains_portal_only(self):
        self.submit();self.assertEqual(self.jobs(),[]);self.configure_email()
        self.post(self.url+'/discussion',body='No retroactive email or intermediate messages')
        self.assertEqual(self.drain(),[])
        self.decision('ops1');self.decision('ops2');self.assertEqual(self.drain(),[])
        self.decision('commercial');self.assertEqual(len(self.drain()),4)

    def test_html_is_escaped_and_multipart_smtp_supports_outlook_and_plain_fallback(self):
        self.configure_email();self.edit(lambda q:q.update(title='Title <script>alert(1)</script> & safe'))
        self.submit()
        with store.connect(self.root) as db:payload=json.loads(db.execute('SELECT data FROM approval_email_batches').fetchone()[0]);cfg=notifications.config(db)
        with self.app.app_context():
            message=approval_emails.render(payload,cfg,'ops1@example.test');self.assertNotIn('<script>',message['html']);self.assertIn('&lt;script&gt;',message['html'])
            cfg.update(security='none',username='')
            with patch.dict('os.environ',{'CIRRUS_DISABLE_EMAIL':'0'}),patch.dict(self.app.config,{'TESTING':False}),patch('smtplib.SMTP') as smtp:
                notifications.send_smtp(cfg,'ops1@example.test',message['subject'],message['text'],html=message['html'],message_id=message['message_id'])
                smtp.return_value.__enter__.return_value.starttls.assert_not_called()
                mime=smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
                self.assertEqual(mime.get_content_type(),'multipart/alternative');self.assertEqual([p.get_content_type() for p in mime.iter_parts()],['text/plain','text/html'])
                self.assertEqual(mime['Message-ID'],message['message_id']);self.assertNotIn('PRIVATE-NOTES-MARKER',str(mime))

    def test_draft_dialog_markup_and_save_do_not_start_email(self):
        self.configure_email();html=self.c.get(self.url+'/edit').data.decode();self.assertIn('id="open-approvers-submission"',html)
        self.assertNotIn('class="editor-approval-setup"',html);self.assertEqual(html.count('id="optional-monitoring"'),1);self.assertEqual(html.count('id="show-12-month"'),1)
        self.assertIn('id="quotation-options"',html);self.assertIn('id="approvers-submission-dialog"',html)
        self.assertEqual(self.edit().status_code,302);self.assertEqual(self.jobs(),[])
        q=quote('NEW-EMAIL-DRAFT',status='Draft');response=self.post('/quotes/new',quotation=json.dumps(q),approvers=json.dumps([dict(user_id=self.ids['ops1'],phase='operations')]),approvers_version='0',intent='submit_review')
        self.assertEqual(response.status_code,302);ident=response.location.split('/')[-2]
        with store.connect(self.root) as db:
            self.assertTrue(db.execute('SELECT 1 FROM records WHERE id=?',(ident,)).fetchone());self.assertTrue(flow.current_round(db,ident))
        self.assertEqual(len(self.drain()),1)

    def test_migration_preserves_business_rows_and_suppresses_legacy_outbox(self):
        self.configure_email();self.submit();self.drain()
        with store.connect(self.root) as db:
            original=[tuple(r) for r in db.execute('SELECT * FROM records ORDER BY id')]
            accounts=[tuple(r) for r in db.execute('SELECT * FROM users ORDER BY id')]
            smtp=db.execute("SELECT value FROM settings WHERE key='workflow_smtp'").fetchone()[0]
            # A legacy intermediate event is retained, but never sent after upgrade.
            notifications.create(db,self.ids['ops1'],self.ident,'legacy-comment','Discussion','Private costs must stay in portal')
            nid=db.execute("SELECT id FROM portal_notifications WHERE event_key='legacy-comment'").fetchone()[0]
            db.execute("INSERT INTO notification_emails(notification_id,address,status) VALUES (?,?,'pending')",(nid,'ops1@example.test'))
            db.execute('PRAGMA user_version=14')
        store.migrate(self.root);store.migrate(self.root)
        with store.connect(self.root) as db:
            self.assertEqual(original,[tuple(r) for r in db.execute('SELECT * FROM records ORDER BY id')]);self.assertEqual(accounts,[tuple(r) for r in db.execute('SELECT * FROM users ORDER BY id')])
            self.assertEqual(smtp,db.execute("SELECT value FROM settings WHERE key='workflow_smtp'").fetchone()[0]);self.assertEqual(db.execute('SELECT status FROM notification_emails WHERE notification_id=?',(nid,)).fetchone()[0],'cancelled')
        self.assertEqual(self.drain(),[])

    def test_delivery_access_and_email_failures_do_not_undo_submission(self):
        self.configure_email();self.submit()
        with store.connect(self.root) as db:db.execute('UPDATE users SET active=0 WHERE id=?',(self.ids['ops1'],))
        with patch('smtplib.SMTP',side_effect=AssertionError('Do not send real emails')):
            while notifications.process_email(self.app):pass
        self.assertEqual(self.state()[1]['status'],flow.ACTIVE[0]);self.assertTrue(any(r['status']=='cancelled' for r in self.jobs()));self.assertTrue(any(r['status']=='failed' for r in self.jobs()))
        with store.connect(self.root) as db:
            failed=db.execute("SELECT notification_id FROM notification_emails WHERE status='failed' LIMIT 1").fetchone()[0]
        self.assertEqual(self.post('/administration/workflow',client=self.clients['admin'],action='retry',notification_id=str(failed)).status_code,302)
        self.assertEqual(len(self.drain()),1)

    def test_submitter_selected_as_approver_receives_one_final_email(self):
        self.configure_email();version,_=self.state()
        selected=[dict(user_id=self.ids['author'],phase='operations'),dict(user_id=self.ids['ops1'],phase='commercial')]
        with store.connect(self.root) as db:selection=flow.selection(db,self.ident)
        result=self.post(self.url+'/approval',action='submit',version=version['version'],hash=version['hash'],approvers=json.dumps(selected),approvers_version=selection['version'])
        self.assertEqual(result.status_code,302);self.assertEqual(len(self.drain()),2)
        self.assertEqual(self.decision('author').status_code,302);self.assertEqual(self.drain(),[])
        self.assertEqual(self.decision('ops1').status_code,302);sent=self.drain()
        self.assertEqual(len(sent),2);self.assertEqual({m['to'] for m in sent},{'author@example.test','ops1@example.test'})

    def test_actual_submitter_receives_final_email_instead_of_unselected_owner(self):
        self.configure_email()
        self.assertEqual(self.post('/administration/workflow',client=self.clients['admin'],action='recipient',user_id=self.ids['admin'],email='admin@example.test',recipient_enabled='yes').status_code,302)
        version,_=self.state()
        result=self.post(self.url+'/approval',client=self.clients['admin'],action='submit',version=version['version'],hash=version['hash'],**self.mapping)
        self.assertEqual(result.status_code,302);self.assertEqual(self.state()[1]['submitter'],self.ids['admin'])
        for mail in self.drain():self.assertIn('Submitted by: admin',mail['text'])
        for name in ('ops1','ops2','commercial'):self.decision(name)
        self.assertEqual({m['to'] for m in self.drain()},{n+'@example.test' for n in ('admin','ops1','ops2','commercial')})

    def test_completed_round_email_keeps_its_frozen_version_after_later_edits(self):
        self.configure_email();_,approved_round=self.submit();self.drain();original_title=self.raw()['title']
        for name in ('ops1','ops2','commercial'):self.decision(name)
        self.assertEqual(self.edit(lambda q:q.update(title='Later edited quotation')).status_code,302)
        self.assertNotEqual(self.state()[1]['id'],approved_round['id'])
        sent=self.drain();self.assertEqual(len(sent),4)
        for mail in sent:
            self.assertIn(original_title,mail['text']);self.assertNotIn('Later edited quotation',mail['text'])
            self.assertIn('approval-round-'+approved_round['id'],mail['text']);self.assertIn('later edits require a new review',mail['text'])
        self.assertEqual(self.drain(),[])
