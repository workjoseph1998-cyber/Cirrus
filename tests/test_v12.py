"""Synthetic workflow, version, privacy, notification and retirement checks."""
import copy
import io
import json
import re
import sqlite3
import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from workspace_app import create_app, store, security, approvals as flow, notifications
from workspace_app.approval_routes import capture_pdf
from workspace_app.backup import online_safety_backup, restore
from workspace_app.commercial import fingerprint
from test_v5 import quote

PASSWORD='Workflow-test-credentials-only-2026!'


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'data';self.app=create_app(self.root,True)
        with store.connect(self.root) as db:
            self.ids={name:security.create_user(db,name,PASSWORD,'Administrator' if name=='admin' else 'Viewer' if name=='viewer' else 'Editor',name=='admin')
                      for name in ['admin','author','ops1','ops2','commercial','outsider','viewer']}
            self.customer=store.save(db,'customer',dict(name='Private customer',contact='',notes='Private customer notes'))
            self.project=store.save(db,'project',dict(name='Private project',customer='Private customer',customer_id=self.customer,status='Active'))
            for ident in [self.customer,self.project]:db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.ids['author'],ident))
        self.clients={name:self.login(name) for name in self.ids};self.c=self.clients['author']
        q=quote('APPROVAL-TEST',status='Draft');q.update(valid_until='2026-12-31',customer_id=self.customer,project_id=self.project,internal_notes='PRIVATE-NOTES-MARKER')
        q['document']['sections'][0]['rows'][0]['cost']='731.29'
        result=self.post('/quotes/new',quotation=json.dumps(q));self.assertEqual(result.status_code,302,result.data[:300]);self.ident=result.location.split('/')[-2]
        self.url='/quotes/'+self.ident
        self.mapping={s:self.ids[name] for s,name in [('operations_1','ops1'),('operations_2','ops2'),('commercial','commercial')]}

    def tearDown(self):self.temp.cleanup()
    def login(self,name):
        client=self.app.test_client();client.get('/login')
        with client.session_transaction() as s:token=s['csrf']
        self.assertEqual(client.post('/login',data=dict(csrf=token,username=name,password=PASSWORD)).status_code,302)
        return client

    def post(self,path,client=None,**values):
        client=client or self.c
        with client.session_transaction() as s:token=s['csrf']
        return client.post(path,data=dict(csrf=token,**values))

    def state(self):
        with store.connect(self.root) as db:return flow.current_version(db,self.ident),flow.current_round(db,self.ident)

    def raw(self):
        with store.connect(self.root) as db:return json.loads(db.execute('SELECT data FROM records WHERE id=?',(self.ident,)).fetchone()[0])

    def submit(self):
        version,_=self.state()
        result=self.post(self.url+'/approval',action='submit',version=str(version['version']),hash=version['hash'],**self.mapping)
        self.assertEqual(result.status_code,302,result.data[:1000]);return self.state()

    def decision(self,name,decision='Approved',comment='',tokens=None):
        version,round_=tokens or self.state()
        return self.post(self.url+'/approval',client=self.clients[name],action='decision',version=str(version['version']),hash=version['hash'],round_id=round_['id'],decision=decision,comment=comment)

    def edit(self,change=None,client=None,base_hash=None):
        client=client or self.c;html=client.get(self.url+'/edit').data
        current=json.loads(re.search(rb'id="initial-quotation">(.*?)</script>',html,re.S)[1]);token=re.search(rb'name="base_hash" value="([^"]+)"',html)[1].decode()
        if change:change(current)
        return self.post(self.url+'/edit',client=client,base_hash=base_hash or token,quotation=json.dumps(current))

    def approve_all(self):
        self.submit()
        for who in ['ops1','ops2','commercial']:self.assertEqual(self.decision(who).status_code,302)

    @staticmethod
    def renderer(app,data,path):
        Path(path).write_bytes(b'%PDF-1.4\n'+json.dumps(flow.content(data)).encode()+b'\n'+b'x'*200)

    def test_parallel_operations_then_commercial_and_sent_snapshot(self):
        self.submit();self.assertEqual(self.decision('commercial').status_code,200)
        self.assertEqual(self.state()[1]['status'],flow.ACTIVE[0])
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(self.decision,['ops1','ops2']))
        self.assertEqual([r.status_code for r in results],[302,302]);self.assertEqual(self.state()[1]['status'],flow.ACTIVE[1])
        self.assertEqual(self.decision('commercial',comment='Presentation checked').status_code,302)
        version,round_=self.state();self.assertEqual(round_['status'],'Approved by all')
        self.assertTrue(capture_pdf(self.app,self.renderer))
        pdf=self.c.get(self.url+'/approval/'+round_['id']+'/pdf');self.assertTrue(pdf.data.startswith(b'%PDF-'))
        self.assertNotIn(b'PRIVATE-NOTES-MARKER',pdf.data);self.assertNotIn(b'731.29',pdf.data)
        self.assertEqual(self.post(self.url+'/approval',action='sent',version=version['version'],hash=version['hash'],round_id=round_['id'],recipient_name='Customer contact',recipient_email='customer@example.test',method='Email').status_code,302)
        self.assertEqual(self.state()[1]['status'],'Sent to client')
        self.assertEqual(self.raw()['status'],'Draft')
        with store.connect(self.root) as db:
            self.assertEqual(db.execute('SELECT ever_sent FROM reference_usage').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM portal_notifications WHERE kind=?',('Approved by all',)).fetchone()[0],4)

    def test_changes_decline_and_explicit_resubmission_history(self):
        self.submit();self.assertEqual(self.decision('ops1','Changes requested').status_code,200)
        self.assertEqual(self.state()[1]['status'],flow.ACTIVE[0])
        self.assertEqual(self.decision('ops1','Changes requested','Clarify scope').status_code,302)
        self.assertEqual(self.state()[1]['status'],'Changes requested');self.assertEqual(self.decision('ops2').status_code,200)
        self.assertEqual(self.edit(lambda q:q.update(scope='Clarified scope')).status_code,302)
        self.assertIsNone(self.state()[1]);self.submit()
        self.assertEqual(self.decision('ops2','Declined','Not deliverable').status_code,302)
        self.submit();self.assertEqual(self.state()[1]['status'],flow.ACTIVE[0])
        with store.connect(self.root) as db:
            history=flow.overview(db,dict(id=self.ident,kind='quote',data=self.raw()))['history']
            self.assertEqual(len(history),3);self.assertTrue(history[-1]['superseded']);self.assertEqual(history[-1]['reviews'][0]['comment'],'Clarify scope')

    def test_edit_invalidates_approval_preserves_evidence_and_unchanged_is_noop(self):
        self.approve_all();capture_pdf(self.app,self.renderer);version,round_=self.state()
        original=self.c.get(self.url+'/approval/'+round_['id']+'/pdf').data
        self.assertEqual(self.edit().status_code,302);self.assertEqual(self.state()[0]['version'],version['version']);self.assertEqual(self.state()[1]['status'],'Approved by all')
        def modify(q):q['document']['sections'][0]['rows'][0]['quantity']='3';q['document']['terms'][0]['text']='New payment terms';q['document']['show_12_month']=not q['document']['show_12_month']
        self.assertEqual(self.edit(modify).status_code,302)
        changed,newround=self.state();self.assertEqual(changed['version'],version['version']+1);self.assertEqual(newround['status'],flow.ACTIVE[0]);self.assertTrue(newround['reapproval'])
        self.assertEqual(self.c.get(self.url+'/approval/'+round_['id']+'/pdf').data,original)
        with store.connect(self.root) as db:
            self.assertEqual(sum(r['decision']=='Approved' for r in flow.decisions(db,newround['id'])),0)
            self.assertIn('quantity',changed['changes']);self.assertTrue(db.execute("SELECT 1 FROM portal_notifications WHERE kind='Reapproval required'").fetchone())
            with self.assertRaises(sqlite3.IntegrityError):db.execute('UPDATE approval_artifacts SET pdf=? WHERE round_id=?',(b'changed',round_['id']))

    def test_stale_approvals_and_stale_editor_never_overwrite(self):
        tokens=self.submit();saved=self.raw();old=fingerprint(saved)
        self.assertEqual(self.edit(lambda q:q.update(scope='Another author change')).status_code,302)
        result=self.decision('ops1',tokens=tokens);self.assertEqual(result.status_code,409);self.assertIn(b'Review the updated',result.data)
        response=self.post(self.url+'/edit',base_hash=old,quotation=json.dumps(dict(saved,scope='Stale overwrite')))
        self.assertEqual(response.status_code,200);self.assertIn(b'entered values are retained',response.data);self.assertEqual(self.raw()['scope'],'Another author change')

    def test_save_and_submit_is_atomic_and_uses_edited_version(self):
        html=self.c.get(self.url+'/edit').data;token=re.search(rb'name="base_hash" value="([^"]+)"',html)[1].decode();q=self.raw();q['scope']='Submit exact edits'
        bad=self.post(self.url+'/edit',base_hash=token,quotation=json.dumps(q),intent='submit_review',**dict(self.mapping,commercial=self.mapping['operations_1']))
        self.assertEqual(bad.status_code,200);self.assertNotEqual(self.raw()['scope'],'Submit exact edits');self.assertIsNone(self.state()[1])
        good=self.post(self.url+'/edit',base_hash=token,quotation=json.dumps(q),intent='submit_review',**self.mapping);self.assertEqual(good.status_code,302)
        version,round_=self.state();self.assertEqual(json.loads(version['data'])['scope'],'Submit exact edits');self.assertEqual(version['hash'],round_['hash'])

    def test_reviewer_scoped_edit_private_margin_and_saved_private_fields(self):
        self.submit();client=self.clients['ops1']
        for path in ['/customers/'+self.customer,'/record/'+self.project]:self.assertEqual(client.get(path).status_code,404)
        for suffix in ['/pricing-margin','/costing','/costing/apply']:
            self.assertEqual(client.get(self.url+suffix).status_code,404)
        html=client.get(self.url+'/edit').data;self.assertNotIn(b'PRIVATE-NOTES-MARKER',html);self.assertNotIn(b'731.29',html)
        exported=client.get('/export');self.assertNotIn(b'PRIVATE-NOTES-MARKER',exported.data);self.assertNotIn(b'731.29',exported.data)
        self.assertEqual(self.edit(lambda q:q.update(scope='Reviewer changed scope',internal_notes='FORGED'),client=client).status_code,302)
        self.assertEqual(self.raw()['internal_notes'],'PRIVATE-NOTES-MARKER');self.assertEqual(self.raw()['document']['sections'][0]['rows'][0]['cost'],'731.29')
        self.assertEqual(self.clients['outsider'].get(self.url+'/approval').status_code,404)
        self.assertEqual(self.clients['ops1'].get('/accounts').status_code,403)

    def test_discussion_replies_mentions_unread_no_invalidation_and_xss(self):
        self.submit();before=self.state()
        response=self.post(self.url+'/discussion',body='@ops1 Please check <script>alert(1)</script>');self.assertEqual(response.status_code,200);mid=response.json['id']
        poll=self.clients['ops1'].get(self.url+'/approval/poll').json;self.assertEqual(poll['unread'],1);self.assertEqual(poll['messages'][0]['body'],'@ops1 Please check <script>alert(1)</script>')
        self.assertEqual(self.post(self.url+'/discussion',client=self.clients['ops2'],parent_id=str(mid),body='I checked the scope.').status_code,200)
        self.assertEqual(self.post(self.url+'/discussion',body='@outsider should not be mentioned').status_code,400)
        self.assertEqual(self.post(self.url+'/discussion/read',client=self.clients['ops1'],last_id='99999').status_code,200)
        self.assertEqual(self.clients['ops1'].get(self.url+'/approval/poll').json['unread'],0)
        self.assertEqual(self.state()[0]['hash'],before[0]['hash']);self.assertEqual(self.state()[1]['id'],before[1]['id'])
        with store.connect(self.root) as db:self.assertEqual(db.execute("SELECT count(*) FROM portal_notifications WHERE user_id=? AND kind='Mention'",(self.ids['ops1'],)).fetchone()[0],1)

    def test_notifications_counts_read_ownership_and_permission_recheck(self):
        self.submit();c=self.clients['ops1'];data=c.get('/notifications/poll').json;self.assertEqual(data['pending'],1);self.assertGreater(data['unread'],0)
        first=data['recent'][0]['id'];self.assertEqual(self.post('/notifications/read',client=self.clients['outsider'],id=str(first)).status_code,302)
        self.assertEqual(c.get('/notifications/poll').json['unread'],data['unread'])
        self.assertEqual(self.post('/notifications/read',client=c,all='yes').status_code,302);self.assertEqual(c.get('/notifications/poll').json['unread'],0)
        with store.connect(self.root) as db:db.execute('DELETE FROM approval_grants WHERE quote_id=? AND user_id=?',(self.ident,self.ids['ops1']))
        self.assertEqual(c.get('/notifications/'+str(first)+'/open').status_code,404);self.assertEqual(c.get('/notifications/poll').json['unread'],0)

    def test_dashboard_actionable_vs_waiting_and_duplicate_decisions(self):
        self.submit();ops=self.clients['ops1'];commercial=self.clients['commercial']
        self.assertEqual(ops.get('/notifications/poll').json['pending'],1);self.assertEqual(commercial.get('/notifications/poll').json['pending'],0)
        self.assertIn(b'My pending approvals',ops.get('/').data);self.assertIn(b'1 actionable',ops.get('/approvals').data)
        self.assertEqual(self.decision('ops1').status_code,302)
        with store.connect(self.root) as db:count=db.execute('SELECT count(*) FROM portal_notifications').fetchone()[0]
        self.assertEqual(self.decision('ops1').status_code,200)
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM portal_notifications').fetchone()[0],count)
        self.decision('ops2');self.assertEqual(commercial.get('/notifications/poll').json['pending'],1)
        self.assertIn(b'Pending:',self.c.get('/approvals?filter=mine').data)

    def configure_email(self):
        admin=self.clients['admin'];cfg=dict(action='smtp',enabled='yes',host='smtp.example.test',port='587',security='starttls',username='workplace',sender='workplace@example.test',password_env='CIRRUS_SMTP_PASSWORD',base_url='https://workplace.example.test')
        self.assertEqual(self.post('/administration/workflow',client=admin,**cfg).status_code,302)
        for name in ['author','ops1','ops2','commercial']:
            self.assertEqual(self.post('/administration/workflow',client=admin,action='recipient',user_id=self.ids[name],email=name+'@example.test',recipient_enabled='yes').status_code,302)

    def test_optional_email_disabled_failure_retry_and_no_real_smtp_in_tests(self):
        self.submit()
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM notification_emails').fetchone()[0],0)
        self.configure_email();self.edit(lambda q:q.update(scope='Changed quotation before deliberate resubmission'))
        self.decision('ops1','Changes requested','Please resubmit')
        self.submit();self.post(self.url+'/discussion',body='Email notification test')
        with patch('smtplib.SMTP',side_effect=AssertionError('Real SMTP must never be contacted')):
            self.assertTrue(notifications.process_email(self.app))
        with store.connect(self.root) as db:
            failed=dict(db.execute("SELECT * FROM notification_emails WHERE status='failed'").fetchone());self.assertEqual(db.execute('SELECT count(*) FROM approval_messages').fetchone()[0],1)
        self.assertIn(b'SMTP delivery failed',self.clients['admin'].get('/administration/workflow').data)
        self.assertEqual(self.post('/administration/workflow',client=self.clients['admin'],action='retry',notification_id=failed['notification_id']).status_code,302)
        sent=[]
        while notifications.process_email(self.app,lambda cfg,to,subject,body,**message:sent.append((to,body))):pass
        self.assertTrue(sent);self.assertIn('https://workplace.example.test/quotes/',sent[0][1]);self.assertIn('Sign in',sent[0][1])
        self.assertNotIn(b'workflow_smtp',self.clients['admin'].get('/export').data)

    def test_approved_pdf_fail_retry_and_backup_restore(self):
        self.approve_all();version,round_=self.state()
        def broken(app,data,path):raise OSError('PDF renderer unavailable')
        capture_pdf(self.app,broken)
        self.assertEqual(self.post(self.url+'/approval',action='sent',version=version['version'],hash=version['hash'],round_id=round_['id'],recipient_name='Customer contact',recipient_email='customer@example.test',method='Email').status_code,200)
        self.assertEqual(self.post(self.url+'/approval',action='retry_pdf',round_id=round_['id']).status_code,302)
        capture_pdf(self.app,self.renderer);before=self.c.get(self.url+'/approval/'+round_['id']+'/pdf').data
        path=Path(self.temp.name)/'full.zip';online_safety_backup(self.root,path);target=Path(self.temp.name)/'restored';restore(path,target)
        with store.connect(target) as db:
            self.assertEqual(db.execute('SELECT pdf FROM approval_artifacts').fetchone()[0],before)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],18)
            self.assertEqual(flow.selection(db,self.ident)['data'],flow.normalize_selection(self.mapping))
        self.assertEqual(self.post('/record/'+self.ident+'/delete').status_code,400)

    def test_retired_consumption_routes_handover_and_data_retained(self):
        with store.connect(self.root) as db:
            db.execute('INSERT INTO monthly_snapshots VALUES (?,?,?,?,?,?)',(self.customer,'2026-11',1,json.dumps([dict(VM='Retained-VM',Date='February',Qty='x')]),'2026-11-02',self.ids['author']))
        for url in ['/customers/'+self.customer+'/consumption','/customers/'+self.customer+'/consumption/import','/projects/'+self.project+'/consumption','/customers/'+self.customer+'?tab=consumption']:
            self.assertEqual(self.c.get(url).status_code,410);self.assertEqual(self.post(url).status_code,410)
        for url in ['/','/customers','/customers/'+self.customer]:
            html=self.c.get(url).data;self.assertNotIn(b'Retained-VM',html);self.assertNotIn(b'>Consumption<',html);self.assertNotIn(b'consumption charges',html)
        self.assertEqual(self.post('/administration/consumption-handover').status_code,403)
        result=self.post('/administration/consumption-handover',client=self.clients['admin']);self.assertEqual(result.status_code,200)
        with zipfile.ZipFile(io.BytesIO(result.data)) as z:self.assertIn(b'Retained-VM',z.read('tables/monthly_snapshots.json'))
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM monthly_snapshots').fetchone()[0],1)

    def test_theme_per_user_and_professional_customer_documents(self):
        self.assertEqual(self.post('/preferences',theme='dark',collapsed='yes').status_code,200)
        self.assertIn(b'data-theme="dark"',self.c.get('/').data);self.assertIn(b'nav-collapsed',self.c.get('/').data)
        self.assertIn(b'data-theme="system"',self.clients['ops1'].get('/').data)
        public=self.c.get(self.url+'/print').data;self.assertNotIn(b'portal.css',public);self.assertNotIn(b'data-theme="dark"',public)
        for path in ['/reports','/notifications','/approvals','/hosting-vms','/customers/'+self.customer+'/tenant-pricing']:
            self.assertEqual(self.c.get(path).status_code,200)

    def test_reassign_and_revoke_previous_reviewer(self):
        self.submit();self.decision('ops1');version,round_=self.state()
        mapping=dict(self.mapping,operations_1=self.ids['outsider'])
        result=self.post(self.url+'/approval',action='reassign',version=version['version'],hash=version['hash'],reason='Different technical reviewer',**mapping);self.assertEqual(result.status_code,302)
        self.assertIsNone(self.state()[1])
        self.assertEqual(self.post(self.url+'/approval',action='submit',version=version['version'],hash=version['hash'],**mapping).status_code,302)
        self.assertNotEqual(self.state()[1]['id'],round_['id'])
        self.assertEqual(self.post(self.url+'/approval',action='revoke',user_id=self.ids['ops1']).status_code,302)
        self.assertEqual(self.clients['ops1'].get(self.url+'/approval').status_code,404)
        self.assertEqual(self.clients['outsider'].get(self.url+'/approval').status_code,200)

    def test_message_request_is_idempotent_and_disabled_reviewer_has_no_actions(self):
        self.submit()
        first=self.post(self.url+'/discussion',body='One message only',request_id='stable-request-123')
        second=self.post(self.url+'/discussion',body='One message only',request_id='stable-request-123')
        self.assertEqual(first.json['id'],second.json['id'])
        with store.connect(self.root) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM approval_messages').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM portal_notifications WHERE event_key=?",('message:'+str(first.json['id']),)).fetchone()[0],3)
            db.execute("UPDATE users SET role='Viewer',session_version=session_version+1 WHERE id=?",(self.ids['ops1'],))
            old_message_notification=db.execute("SELECT id FROM portal_notifications WHERE user_id=? AND kind='Discussion'",(self.ids['ops1'],)).fetchone()[0]
        viewer=self.login('ops1');state=viewer.get('/notifications/poll').json;self.assertEqual(state['pending'],0)
        self.assertFalse(any(n['kind']=='Discussion' for n in state['recent']))
        self.assertEqual(viewer.get('/notifications/'+str(old_message_notification)+'/open').status_code,404)

    def test_approved_customer_folder_copy_cannot_be_overwritten_by_later_edits(self):
        from workspace_app import automation,export_folders
        folder=Path(self.temp.name)/'customer-pdfs';folder.mkdir();mapped=folder/'Bank';mapped.mkdir()
        admin=self.clients['admin']
        self.assertEqual(self.post('/automation/settings',client=admin,pdf_enabled='yes',pdf_folder=str(folder),backup_folder='',daily_retention='14',weekly_retention='8').status_code,302)
        with store.connect(self.root) as db:
            customer=dict(db.execute('SELECT id,kind,data FROM records WHERE id=?',(self.customer,)).fetchone());customer['data']=json.loads(customer['data']);context=export_folders.context(db,customer)
        self.assertEqual(self.post('/customers/'+self.customer+'/quotation-folder',client=admin,quotation_folder=str(mapped),version='0',root_hash=context['folder_root_hash'],mapping_hash=context['folder_mapping_hash']).status_code,302)
        self.edit();automation.process_pdf(self.app,self.renderer)
        with store.connect(self.root) as db:path=Path(db.execute('SELECT destination FROM pdf_exports WHERE record_id=?',(self.ident,)).fetchone()[0])
        original=path.read_bytes();self.approve_all();capture_pdf(self.app,self.renderer)
        self.assertEqual(self.edit(lambda q:q.update(scope='Changed after approval')).status_code,302)
        automation.process_pdf(self.app,self.renderer);self.assertEqual(path.read_bytes(),original)
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT status FROM pdf_exports WHERE record_id=?',(self.ident,)).fetchone()[0],'failed')
        self.assertEqual(self.edit(lambda q:q.update(title='Synthetic quotation - new content version')).status_code,302)
        automation.process_pdf(self.app,self.renderer);self.assertEqual(path.read_bytes(),original)
        self.assertTrue((mapped/'Synthetic quotation - new content version.pdf').exists())

    def test_private_cost_and_business_status_changes_do_not_invalidate_customer_approval(self):
        self.approve_all();version,round_=self.state()
        def change(q):
            q['internal_notes']='Updated private note';q['status']='Under review';q['document']['sections'][0]['rows'][0]['cost']='900'
        self.assertEqual(self.edit(change).status_code,302)
        self.assertEqual(self.state()[0]['hash'],version['hash']);self.assertEqual(self.state()[1]['id'],round_['id']);self.assertEqual(self.state()[1]['status'],'Approved by all')

    def test_raw_private_attachments_and_readonly_discussion_stay_separate(self):
        result=self.post('/record/'+self.ident+'/attachment',file=(io.BytesIO(b'PRIVATE BUY PRICES'),'supplier.txt'));self.assertEqual(result.status_code,302)
        self.submit()
        with store.connect(self.root) as db:attachment=db.execute('SELECT id FROM attachments WHERE record_id=?',(self.ident,)).fetchone()[0]
        self.assertEqual(self.clients['ops1'].get('/attachment/'+attachment).status_code,404)
        self.assertEqual(self.post('/attachment/'+attachment+'/delete',client=self.clients['ops1']).status_code,404)
        self.post(self.url+'/discussion',body='Internal workflow discussion')
        self.post('/record/'+self.ident+'/access',**{self.ids['viewer']:'read'})
        self.assertEqual(self.clients['viewer'].get(self.url+'/approval/poll').json['messages'],[])
        self.assertEqual(self.clients['viewer'].get(self.url+'/print').status_code,200)
        copied=self.post('/record/'+self.ident+'/copy/revision',client=self.clients['ops1']);self.assertEqual(copied.status_code,302)
        self.assertEqual(self.clients['ops1'].get(copied.location).status_code,302)
        target=copied.location.rsplit('/',1)[-1]
        html=self.clients['ops1'].get('/quotes/'+target+'/edit').data
        self.assertNotIn(b'PRIVATE-NOTES-MARKER',html);self.assertEqual(self.clients['ops1'].get('/quotes/'+target+'/pricing-margin').status_code,404)


if __name__=='__main__':unittest.main()
