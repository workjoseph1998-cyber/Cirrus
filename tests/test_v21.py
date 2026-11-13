"""Synthetic V21 regression tests: real roles, isolation and no production writes."""
import copy
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from workspace_app import create_app, store, security, isolation
from workspace_app.v21 import validity, pre_send
from quotation_fixture import fixture


class Version21(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)/'data'
        self.app=create_app(self.root,testing=True)
        with store.connect(self.root) as db:
            self.admin=security.create_user(db,'admin','Synthetic-password-21!','Administrator',True)
            self.editor=security.create_user(db,'editor','Synthetic-password-21!','Editor')
            self.viewer=security.create_user(db,'viewer','Synthetic-password-21!','Viewer')
            self.customer=store.save(db,'customer',dict(name='V21 customer',contact='',notes=''))
            q=fixture();q.update(number='V21-SYNTH',customer_id=self.customer,valid_until=(date.today()+timedelta(days=4)).isoformat())
            self.quote=store.save(db,'quote',q)
            db.execute('UPDATE records SET owner_id=?',(self.admin,))
        self.client=self.app.test_client();self.login('admin')

    def tearDown(self):self.temp.cleanup()

    def login(self,name):
        self.client.get('/login')
        with self.client.session_transaction() as s:token=s['csrf']
        self.client.post('/login',data=dict(csrf=token,username=name,password='Synthetic-password-21!'))
        with self.client.session_transaction() as s:self.token=s['csrf']

    def post(self,url,**values):return self.client.post(url,data=dict(csrf=self.token,**values))

    def test_validity_boundaries(self):
        today=date(2026,11,13)
        for delta,status in [(-1,'Expired'),(0,'Expiring Soon'),(7,'Expiring Soon'),(8,'Valid')]:
            self.assertEqual(validity(dict(data=dict(valid_until=(today+timedelta(days=delta)).isoformat())),today)['status'],status)
        self.assertIsNone(validity(dict(data={}))['days'])
        self.assertIsNone(validity(dict(data=dict(valid_until='invalid')))['days'])

    def test_favorites_are_private_and_revocation_is_live(self):
        self.assertEqual(self.post('/v21/favorites/'+self.quote).status_code,302)
        self.assertIn(b'Synthetic cloud quotation',self.client.get('/v21/shortcuts').data)
        self.login('editor')
        self.assertNotIn(b'Synthetic cloud quotation',self.client.get('/v21/shortcuts').data)
        self.assertEqual(self.post('/v21/favorites/'+self.quote).status_code,404)
        with store.connect(self.root) as db:db.execute('INSERT INTO record_acl VALUES (?,?,?)',(self.quote,self.editor,'view'))
        self.assertEqual(self.post('/v21/favorites/'+self.quote).status_code,302)
        with store.connect(self.root) as db:db.execute('DELETE FROM record_acl WHERE user_id=?',(self.editor,))
        self.assertNotIn(b'Synthetic cloud quotation',self.client.get('/v21/shortcuts').data)

    def test_viewer_can_favorite_but_cannot_write_internal_notes(self):
        with store.connect(self.root) as db:db.execute('INSERT INTO record_acl VALUES (?,?,?)',(self.quote,self.viewer,'view'))
        self.login('viewer')
        self.assertEqual(self.post('/v21/favorites/'+self.quote).status_code,302)
        self.assertEqual(self.post('/quotes/'+self.quote+'/internal-notes',body='forbidden').status_code,403)

    def test_recent_history_and_notes_not_in_exports(self):
        self.assertEqual(self.client.get('/quotes/'+self.quote+'/approval').status_code,200)
        self.assertEqual(self.post('/quotes/'+self.quote+'/internal-notes',body='<script>V21-PRIVATE-SENTINEL</script>').status_code,302)
        page=self.client.get('/quotes/'+self.quote+'/internal-notes')
        self.assertIn(b'&lt;script&gt;V21-PRIVATE-SENTINEL',page.data)
        self.assertNotIn(b'<script>V21-PRIVATE',page.data)
        for suffix in ('print','xlsx','csv'):
            response=self.client.get('/quotes/'+self.quote+'/'+suffix)
            self.assertEqual(response.status_code,200)
            self.assertNotIn(b'V21-PRIVATE-SENTINEL',response.data)
        self.assertIn(b'Synthetic cloud quotation',self.client.get('/v21/shortcuts').data)
        with store.connect(self.root) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM user_recent WHERE user_id=?',(self.admin,)).fetchone()[0],1)

    def test_pre_send_validates_pricing_customer_and_approval(self):
        with self.app.test_request_context():
            from flask import g
            with store.connect(self.root) as db:
                g.user=dict(db.execute('SELECT * FROM users WHERE id=?',(self.admin,)).fetchone())
                r=next(r for r in store.records(db) if r['id']==self.quote)
                checks=dict(pre_send(db,r))
                self.assertTrue(checks['Customer selected']); self.assertTrue(checks['Quotation validity entered'])
                self.assertTrue(checks['Required pricing complete']);self.assertFalse(checks['All required approvers approved'])
                r=copy.deepcopy(r);r['data']['customer_id']='';self.assertFalse(dict(pre_send(db,r))['Customer selected'])
        self.assertEqual(self.client.get('/quotes/'+self.quote+'/pre-send').status_code,200)

    def test_search_and_timeline_respect_access(self):
        self.assertIn(b'Synthetic cloud quotation',self.client.get('/list/search?q=Synthetic').data)
        self.assertIn(b'Synthetic cloud quotation',self.client.get('/v21/search?q=Synthetic').data)
        with store.connect(self.root) as db:
            db.execute("INSERT INTO customer_document_nodes(id,customer_id,parent_id,kind,name,name_key,size,sha256,created,uploaded,uploader,version) VALUES (?,?,NULL,'file',?,?,0,'',?,?,?,1)",('v21-search-file',self.customer,'Private-file-V21.pdf','private-file-v21.pdf','2026-11-13T12:00:00+00:00','2026-11-13T12:00:00+00:00',self.admin))
        self.assertIn(b'Private-file-V21.pdf',self.client.get('/v21/search?q=Private-file').data)
        self.assertIn(b'Created',self.client.get('/customers/'+self.customer+'/activity').data)
        self.login('editor')
        self.assertNotIn(b'Synthetic cloud quotation',self.client.get('/list/search?q=Synthetic').data)
        self.assertNotIn(b'Private-file-V21.pdf',self.client.get('/v21/search?q=Private-file').data)
        self.assertEqual(self.client.get('/customers/'+self.customer+'/activity').status_code,404)

    def test_csrf_enforced(self):
        self.assertEqual(self.client.post('/v21/favorites/'+self.quote,data={}).status_code,400)
        self.assertEqual(self.client.post('/quotes/'+self.quote+'/remind',data={}).status_code,400)

    def test_recent_limit_ten(self):
        with store.connect(self.root) as db:
            ids=[]
            for i in range(12):
                ident=store.save(db,'customer',dict(name='Recent customer '+str(i),contact='',notes=''));ids.append(ident)
                db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.admin,ident))
        for ident in ids:self.assertEqual(self.client.get('/customers/'+ident).status_code,200)
        with store.connect(self.root) as db:
            rows=db.execute('SELECT record_id FROM user_recent WHERE user_id=? ORDER BY viewed DESC',(self.admin,)).fetchall()
            self.assertEqual([r[0] for r in rows],list(reversed(ids[-10:])))


class Isolation21(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.profile=self.base/'profile.json'
        self.values=dict(version=21,**{key:str(self.base/key) for key in ('data','documents','exports','backups')},v20_protected_paths=[str(self.base/'v20-app'),str(self.base/'v20-data')],network={})
        self.profile.write_text(json.dumps(self.values))
        self.env=dict(os.environ,CIRRUS_V21_PROFILE=str(self.profile))

    def tearDown(self):self.temp.cleanup()

    def command(self,action):
        return subprocess.run([sys.executable,'scripts/v21.py',action],env=self.env,text=True,capture_output=True)

    def test_fresh_init_and_no_startup_migration(self):
        self.assertEqual(self.command('init').returncode,0)
        db=Path(self.values['data'])/'workspace.sqlite'
        before=db.read_bytes()
        self.assertEqual(self.command('check').returncode,0)
        self.assertEqual(db.read_bytes(),before)
        self.assertNotEqual(self.command('init').returncode,0)
        with sqlite3.connect(db) as conn:conn.execute('PRAGMA user_version=17')
        before=db.read_bytes()
        self.assertNotEqual(self.command('check').returncode,0)
        self.assertEqual(db.read_bytes(),before)
        self.assertEqual(self.command('migrate').returncode,0)
        self.assertEqual(self.command('check').returncode,0)

    def test_production_overlap_and_existing_db_refused(self):
        self.values['data']=self.values['v20_protected_paths'][1];self.profile.write_text(json.dumps(self.values))
        self.assertNotEqual(self.command('init').returncode,0)
        self.assertFalse(Path(self.values['data']).exists())
        self.values['data']=str(self.base/'data');self.profile.write_text(json.dumps(self.values))
        root=Path(self.values['data']);root.mkdir();db=root/'workspace.sqlite';db.write_bytes(b'production sentinel')
        self.assertNotEqual(self.command('init').returncode,0)
        self.assertEqual(db.read_bytes(),b'production sentinel')

    def test_port_occupied_refuses_before_database_creation(self):
        with socket.socket() as listener:
            if os.name!='nt':listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:listener.bind(('127.0.0.1',8000))
            except OSError:self.skipTest('Port 8000 already occupied in test environment')
            listener.listen()
            response=self.command('start')
            self.assertNotEqual(response.returncode,0);self.assertIn('Port 8000 is occupied',response.stderr)
            self.assertFalse(Path(self.values['data']).exists())

    def test_inherited_v20_configuration_ignored(self):
        with patch.dict(os.environ,dict(self.env,CIRRUS_DATA_DIR=str(self.base/'v20-data'),JOSEPH_DATA_DIR=str(self.base/'v20-data'),CIRRUS_PORT='9000',CIRRUS_DISABLE_EMAIL='0',CIRRUS_DEPLOYMENT_FILE=str(self.base/'v20.json')),clear=True):
            old=isolation.PROFILE
            try:
                root=isolation.activate();self.assertEqual(root,Path(self.values['data']))
                self.assertEqual(os.environ['CIRRUS_PORT'],'8000');self.assertEqual(os.environ['CIRRUS_DISABLE_EMAIL'],'1')
                with self.assertRaises(RuntimeError):isolation.require_path(self.base/'v20-docs','documents')
            finally:isolation.PROFILE=old
        self.assertFalse((self.base/'v20.json').exists())

    def test_waitress_runs_on_reserved_socket_and_second_start_refused(self):
        import time
        import urllib.request
        self.assertEqual(self.command('init').returncode,0)
        with tempfile.TemporaryFile(mode='w+') as output:
            process=subprocess.Popen([sys.executable,'scripts/v21.py','start'],env=self.env,stdout=output,stderr=output,text=True)
            try:
                for _ in range(80):
                    if process.poll() is not None:
                        output.seek(0);self.fail(output.read())
                    try:
                        with urllib.request.urlopen('http://127.0.0.1:8000/login',timeout=1) as response:
                            self.assertEqual(response.status,200)
                            self.assertIn('cirrus_workplace_v21',response.headers['Set-Cookie'])
                            break
                    except OSError:time.sleep(.1)
                else:self.fail('V21 did not start within eight seconds')
                self.assertNotEqual(self.command('start').returncode,0)
                self.assertFalse((self.base/'v20-data').exists())
            finally:
                process.terminate();process.wait(timeout=10)

    def test_complete_backup_includes_external_documents_and_exports(self):
        import hashlib
        import zipfile
        self.assertEqual(self.command('init').returncode,0)
        (Path(self.values['documents'])/'synthetic.txt').write_bytes(b'synthetic customer document')
        (Path(self.values['exports'])/'synthetic.pdf').write_bytes(b'%PDF synthetic export')
        result=subprocess.run([sys.executable,'scripts/full_backup_v21.py'],env=self.env,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        with zipfile.ZipFile(result.stdout.strip()) as archive:
            manifest=json.loads(archive.read('manifest-v21.json'))
            self.assertIn('documents/synthetic.txt',manifest['files'])
            self.assertIn('exports/synthetic.pdf',manifest['files'])
            self.assertIn('data/.cirrus-v21.json',manifest['files'])
            for name,digest in manifest['files'].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),digest)

    def test_old_export_cleanup_metadata_cannot_touch_production(self):
        from workspace_app import quotation_deletion
        self.assertEqual(self.command('init').returncode,0)
        root=Path(self.values['data']);victim=self.base/'v20-export.pdf';victim.write_bytes(b'production PDF sentinel')
        files=[dict(path=str(victim),external=True,done=False,error='',path_key='v20-path',record_id='legacy-record')]
        with store.connect(root) as db:
            db.execute('INSERT INTO quotation_deletions VALUES (?,?,?,?,?,?,?,?)',('v21-test-deletion','TEST','tester','2026-11-13',1,'[]',json.dumps(files),'Cleanup pending'))
        self.assertNotEqual(self.command('check').returncode,0)
        old=isolation.PROFILE
        try:
            with patch.dict(os.environ,self.env):isolation.activate()
            quotation_deletion.cleanup(root,'v21-test-deletion')
        finally:isolation.PROFILE=old
        self.assertEqual(victim.read_bytes(),b'production PDF sentinel')
        with store.connect(root) as db:
            saved=json.loads(db.execute('SELECT files FROM quotation_deletions').fetchone()[0])
            self.assertFalse(saved[0]['done']);self.assertIn('outside',saved[0]['error'])

    def test_linked_storage_refused(self):
        (self.base/'v20-data').mkdir();(self.base/'data').symlink_to(self.base/'v20-data',target_is_directory=True)
        self.assertNotEqual(self.command('init').returncode,0)
        self.assertFalse((self.base/'v20-data'/'workspace.sqlite').exists())

# Reuse the existing workflow fixture with three real approvers.
import test_v12 as workflow
from workspace_app import approvals as flow, notifications


class Reminder21(unittest.TestCase):
    setUp=workflow.WorkflowTests.setUp
    tearDown=workflow.WorkflowTests.tearDown
    login=workflow.WorkflowTests.login
    post=workflow.WorkflowTests.post
    state=workflow.WorkflowTests.state
    raw=workflow.WorkflowTests.raw
    submit=workflow.WorkflowTests.submit
    decision=workflow.WorkflowTests.decision
    configure_email=workflow.WorkflowTests.configure_email

    def test_only_pending_cooldown_audit_and_no_decision_reset(self):
        self.configure_email();self.submit()
        self.assertEqual(self.decision('ops1').status_code,302)
        _,round_=self.state()
        with store.connect(self.root) as db:before=[dict(x) for x in flow.decisions(db,round_['id'])]
        self.assertEqual(self.post(self.url+'/remind').status_code,302)
        with store.connect(self.root) as db:
            after=[dict(x) for x in flow.decisions(db,round_['id'])]
            self.assertEqual(before,after)
            ids=[r[0] for r in db.execute("SELECT user_id FROM portal_notifications WHERE kind='Approval reminder'")]
            self.assertEqual(set(ids),{self.ids['ops2'],self.ids['commercial']})
            self.assertEqual(db.execute("SELECT count(*) FROM approval_events WHERE kind='reminder'").fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM reminder_email_recipients').fetchone()[0],2)
        self.assertEqual(self.post(self.url+'/remind').status_code,400)
        self.assertEqual(self.post(self.url+'/remind',client=self.clients['outsider']).status_code,404)
        with store.connect(self.root) as db:
            db.execute('DELETE FROM notification_emails WHERE notification_id IN (SELECT notification_id FROM reminder_email_recipients)')
            self.assertEqual(db.execute('SELECT count(*) FROM reminder_email_recipients').fetchone()[0],0)

    def test_delivery_revalidates_pending_and_uses_existing_email_style(self):
        self.configure_email();self.submit()
        # Drain existing submission emails into memory, never SMTP.
        while notifications.process_email(self.app,lambda *a,**k:None):pass
        self.assertEqual(self.post(self.url+'/remind').status_code,302)
        self.assertEqual(self.decision('ops1').status_code,302)
        delivered=[]
        while notifications.process_email(self.app,lambda cfg,to,subject,text,**kwargs:delivered.append(dict(to=to,subject=subject,text=text,**kwargs))):pass
        self.assertEqual({x['to'] for x in delivered},{'ops2@example.test','commercial@example.test'})
        for message in delivered:
            self.assertIn('Pending Approval Reminder',message['html'])
            self.assertIn('APPROVAL-TEST',message['text']);self.assertIn('author',message['text'])
            self.assertNotIn('PRIVATE-NOTES-MARKER',message['html']+message['text'])
        with store.connect(self.root) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM notification_emails e JOIN reminder_email_recipients r USING(notification_id) WHERE e.status='cancelled'").fetchone()[0],1)
