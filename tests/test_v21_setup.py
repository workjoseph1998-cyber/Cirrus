"""Simple setup/start installation without manual profile configuration."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts import bootstrap_v21 as bootstrap
from workspace_app import isolation, store


class SimpleSetup21(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.environment=patch.dict(os.environ,{'LOCALAPPDATA':str(self.base/'Local'),'PROGRAMDATA':str(self.base/'Program')},clear=True)
        self.environment.start();self.previous=isolation.PROFILE;isolation.PROFILE=None
    def tearDown(self):
        isolation.PROFILE=self.previous;self.environment.stop();self.temp.cleanup()

    @patch('scripts.live_copy_v21.prepare_live', side_effect=lambda profile:bootstrap.prepare())
    def test_setup_creates_profile_database_and_login_then_repeats_safely(self, mocked_prepare):
        with patch('builtins.input',return_value='setup-admin'),patch('getpass.getpass',return_value='Synthetic-setup-password-21!'):
            bootstrap.setup()
        root=isolation.PROFILE['roots']['data'];profile=bootstrap.default_profile_path()
        self.assertTrue(profile.is_file())
        self.assertEqual(root,self.base/'Local'/'CirrusWorkplaceV21Live'/'Data')
        with store.connect(root) as db:
            user=db.execute('SELECT username,role FROM users').fetchone()
            self.assertEqual(tuple(user),('setup-admin','Administrator'))
        before=profile.read_bytes();database=(root/'workspace.sqlite').read_bytes()
        with patch('builtins.input',side_effect=AssertionError('Must not prompt again')):
            bootstrap.setup()
        self.assertEqual(profile.read_bytes(),before)
        self.assertEqual((root/'workspace.sqlite').read_bytes(),database)
        env=dict(os.environ);env.pop('CIRRUS_V21_PROFILE',None)
        result=subprocess.run([sys.executable,'scripts/v21.py','check'],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_existing_iis_settings_read_only_no_production_data_copied(self):
        old=self.base/'Program'/'CirrusWorkplace'/'deployment.json';old.parent.mkdir(parents=True)
        production=self.base/'V20-production';production.mkdir();sentinel=production/'workspace.sqlite';sentinel.write_bytes(b'production-sentinel')
        old.write_text(json.dumps(dict(CIRRUS_ALLOWED_HOSTS='localhost,127.0.0.1,existing.internal',CIRRUS_HTTPS='1',CIRRUS_INTERNAL_ACCESS='1',CIRRUS_TRUSTED_PROXY='127.0.0.1',CIRRUS_DATA_DIR=str(production))))
        before=old.read_bytes();root=bootstrap.prepare()
        self.assertEqual(os.environ['CIRRUS_ALLOWED_HOSTS'],'localhost,127.0.0.1,existing.internal')
        self.assertEqual(os.environ['CIRRUS_HTTPS'],'1')
        self.assertEqual(old.read_bytes(),before);self.assertEqual(sentinel.read_bytes(),b'production-sentinel')
        self.assertNotEqual(root,production)
        with store.connect(root) as db:self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],0)

    def test_existing_unrecognized_data_is_not_adopted_or_overwritten(self):
        root=self.base/'Local'/'CirrusWorkplaceV21Live'/'Data';root.mkdir(parents=True)
        sentinel=root/'workspace.sqlite';sentinel.write_bytes(b'do-not-overwrite')
        with self.assertRaisesRegex(RuntimeError,'nothing overwritten'):bootstrap.prepare()
        self.assertEqual(sentinel.read_bytes(),b'do-not-overwrite')
        self.assertFalse(bootstrap.default_profile_path().exists())

    def test_setup_does_not_silently_migrate_an_existing_database(self):
        root=bootstrap.prepare()
        with store.connect(root) as db:db.execute('PRAGMA user_version=17')
        before=(root/'workspace.sqlite').read_bytes()
        with self.assertRaisesRegex(RuntimeError,'never migrates'):bootstrap.prepare()
        self.assertEqual((root/'workspace.sqlite').read_bytes(),before)
