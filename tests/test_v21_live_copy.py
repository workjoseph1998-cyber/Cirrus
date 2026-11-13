"""Live copy preserves source bytes, accounts, settings and independent storage."""
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from workspace_app import create_app, isolation, security, store
from workspace_app.backup import workspace_lock
from scripts.live_copy_v21 import copy_live, prepare_live
from scripts import bootstrap_v21
from quotation_fixture import fixture

PASSWORD='Synthetic-live-copy-password-21!'


class LiveCopy21(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.source=self.base/'V20-data';self.documents=self.base/'V20-documents';self.exports=self.base/'V20-exports'
        self.documents.mkdir();self.exports.mkdir();(self.exports/'Customer').mkdir()
        (self.documents/'customer.txt').write_bytes(b'V20 document sentinel')
        (self.exports/'Customer'/'quote.pdf').write_bytes(b'%PDF V20 export sentinel')
        store.migrate(self.source)
        (self.source/'attachments'/'retained.txt').write_bytes(b'V20 attachment sentinel')
        with workspace_lock(self.source):pass
        with store.connect(self.source) as db:
            self.uid=security.create_user(db,'original-admin',PASSWORD,'Administrator',True)
            self.customer=store.save(db,'customer',dict(name='Existing customer',contact='',notes='retained customer notes'))
            q=fixture();q.update(customer_id=self.customer,number='LIVE-COPY-001',valid_until='2026-12-31')
            self.quote=store.save(db,'quote',q)
            db.execute('UPDATE records SET owner_id=?',(self.uid,))
            automation=dict(pdf_enabled=False,pdf_folder=str(self.exports),backup_enabled=False,backup_folder=str(self.base/'V20-backups'),daily_retention=14,weekly_retention=8)
            smtp=dict(enabled=True,host='smtp.example.test',sender='synthetic@example.test',base_url='http://localhost:8000',password_env='CIRRUS_SMTP_PASSWORD')
            for k,v in [('automation',automation),('customer_document_storage',str(self.documents)),('workflow_smtp',smtp)]:db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(k,json.dumps(v)))
            from workspace_app.export_folders import normalized
            db.execute('INSERT INTO customer_export_folders VALUES (?,?,?,?,?,?)',(self.customer,str(self.exports/'Customer'),normalized(str(self.exports/'Customer')),1,'2026-11-13',self.uid))
            # Reproduce the current V20 schema rather than migrating the source.
            for table in ('user_favorites','user_recent','quotation_internal_notes','approval_reminders','reminder_email_recipients'):db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=17')
        self.network=dict(CIRRUS_ALLOWED_HOSTS='localhost,127.0.0.1,existing.internal',CIRRUS_HTTPS='0',CIRRUS_INTERNAL_ACCESS='1',CIRRUS_TRUSTED_PROXY='127.0.0.1')
        self.profile=self.base/'V21-live'/'Config'/'profile.json'
        self.old_profile=isolation.PROFILE;isolation.PROFILE=None
        self.env=patch.dict(os.environ,{},clear=True);self.env.start()
        self.original=self.fingerprints()

    def tearDown(self):
        isolation.PROFILE=self.old_profile;self.env.stop();self.temp.cleanup()

    def fingerprints(self):
        return {str(p.relative_to(self.base)):hashlib.sha256(p.read_bytes()).hexdigest() for root in (self.source,self.documents,self.exports) for p in root.rglob('*') if p.is_file()}

    def copy(self):return copy_live(self.profile,self.source,self.network,[self.base/'V20-app'])

    def test_live_copy_retains_login_records_configuration_and_files(self):
        root=self.copy()
        self.assertEqual(self.fingerprints(),self.original)
        self.assertEqual(os.environ['CIRRUS_DISABLE_EMAIL'],'0')
        self.assertEqual(os.environ['CIRRUS_ALLOWED_HOSTS'],self.network['CIRRUS_ALLOWED_HOSTS'])
        with store.connect(self.source) as old,store.connect(root) as new:
            self.assertEqual(old.execute('PRAGMA user_version').fetchone()[0],17)
            self.assertEqual(new.execute('PRAGMA user_version').fetchone()[0],18)
            self.assertEqual(tuple(old.execute('SELECT * FROM users').fetchone()),tuple(new.execute('SELECT * FROM users').fetchone()))
            self.assertEqual(old.execute('SELECT data FROM records WHERE id=?',(self.quote,)).fetchone()[0],new.execute('SELECT data FROM records WHERE id=?',(self.quote,)).fetchone()[0])
            self.assertEqual(old.execute("SELECT value FROM settings WHERE key='workflow_smtp'").fetchone()[0],new.execute("SELECT value FROM settings WHERE key='workflow_smtp'").fetchone()[0])
            folder=Path(new.execute('SELECT folder FROM customer_export_folders').fetchone()[0])
            self.assertEqual((folder/'quote.pdf').read_bytes(),b'%PDF V20 export sentinel')
        self.assertEqual((root/'attachments'/'retained.txt').read_bytes(),b'V20 attachment sentinel')
        self.assertEqual((isolation.PROFILE['roots']['documents']/'customer.txt').read_bytes(),b'V20 document sentinel')
        # Exercise the real live app configuration, suppressing background workers.
        with patch('workspace_app.automation.start'):
            app=create_app(root)
        self.assertTrue(app.config['V21_LIVE'])
        client=app.test_client();client.get('/login')
        with client.session_transaction() as session:csrf=session['csrf']
        self.assertEqual(client.post('/login',data=dict(csrf=csrf,username='original-admin',password=PASSWORD)).status_code,302)
        self.assertIn(b'Synthetic cloud quotation',client.get('/list/quote').data)
        self.assertIn(b'Internal notes',client.get('/quotes/'+self.quote+'/edit').data)
        self.assertIn(b'Live',client.get('/v21/whats-new').data)
        version=client.get('/v21/version').get_json()
        self.assertEqual(version['version'],21);self.assertEqual(version['mode'],'live')
        self.assertEqual(len(version['features']),11)
        # New V21 edits must leave the fallback and document originals unchanged.
        with store.connect(root) as db:db.execute("UPDATE records SET updated='2099-01-01' WHERE id=?",(self.quote,))
        self.assertEqual(self.fingerprints(),self.original)

    def test_repeat_setup_preserves_live_changes_without_recopied_v20(self):
        root=self.copy()
        with store.connect(root) as db:db.execute("UPDATE records SET updated='2099-01-01' WHERE id=?",(self.quote,))
        before=(root/'workspace.sqlite').read_bytes()
        self.assertEqual(prepare_live(self.profile),root)
        self.assertEqual((root/'workspace.sqlite').read_bytes(),before)
        self.assertEqual(self.fingerprints(),self.original)

    def test_running_v20_refuses_copy(self):
        with socket.socket() as listener:
            if os.name!='nt':listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            listener.bind(('127.0.0.1',8000));listener.listen()
            with self.assertRaisesRegex(RuntimeError,'port 8000'):self.copy()
        self.assertFalse(self.profile.exists())
        self.assertFalse((self.profile.parent.parent/'Data').exists())
        self.assertEqual(self.fingerprints(),self.original)

    def test_failed_external_copy_rolls_back_new_profile_and_leaves_source(self):
        (self.documents/'linked').symlink_to(self.exports,target_is_directory=True)
        with self.assertRaises(ValueError):self.copy()
        self.assertFalse(self.profile.exists())
        self.assertFalse((self.profile.parent.parent/'Data').exists())
        (self.documents/'linked').unlink()
        self.assertEqual(self.fingerprints(),self.original)

    def test_default_setup_discovers_v20_and_uses_existing_accounts(self):
        os.environ.update(LOCALAPPDATA=str(self.base/'Local'),PROGRAMDATA=str(self.base/'Program'))
        config=self.base/'Program'/'CirrusWorkplace'/'deployment.json';config.parent.mkdir(parents=True)
        config.write_text(json.dumps(dict(self.network,CIRRUS_DATA_DIR=str(self.source))))
        before=config.read_bytes()
        with patch('builtins.input',side_effect=AssertionError('Existing account must not be replaced')):
            bootstrap_v21.setup()
        self.assertTrue(bootstrap_v21.default_profile_path().is_file())
        self.assertEqual(config.read_bytes(),before)
        self.assertEqual(self.fingerprints(),self.original)

    def test_old_test_profile_is_not_selected_by_live_launcher(self):
        old=self.base/'old-test-profile.json';old.write_text(json.dumps(dict(version=21,mode='test')))
        os.environ['CIRRUS_V21_PROFILE']=str(old)
        self.assertEqual(bootstrap_v21.launch_profile_path(),bootstrap_v21.default_profile_path())
        self.assertEqual(json.loads(old.read_text())['mode'],'test')

    def test_prior_email_backlog_is_not_replayed_but_policy_is_retained(self):
        from workspace_app import notifications
        with store.connect(self.source) as db:
            notifications.create(db,self.uid,self.quote,'prior-version','Action required','Existing queued message')
            nid=db.execute("SELECT id FROM portal_notifications WHERE event_key='prior-version'").fetchone()[0]
            db.execute("INSERT INTO notification_emails(notification_id,address,status) VALUES (?,?,'pending')",(nid,'synthetic@example.test'))
        self.original=self.fingerprints()
        root=self.copy()
        with store.connect(root) as new,store.connect(self.source) as old:
            self.assertEqual(new.execute('SELECT status FROM notification_emails WHERE notification_id=?',(nid,)).fetchone()[0],'cancelled')
            self.assertEqual(old.execute('SELECT status FROM notification_emails WHERE notification_id=?',(nid,)).fetchone()[0],'pending')
            self.assertTrue(notifications.config(new)['enabled'])
        self.assertEqual(self.fingerprints(),self.original)

    def test_wrong_source_schema_does_not_publish_or_modify_source(self):
        with store.connect(self.source) as db:db.execute('PRAGMA user_version=99')
        self.original=self.fingerprints()
        with self.assertRaisesRegex(RuntimeError,'not the expected V20 schema'):self.copy()
        self.assertFalse(self.profile.exists())
        self.assertFalse((self.profile.parent.parent/'Data').exists())
        self.assertEqual(self.fingerprints(),self.original)
