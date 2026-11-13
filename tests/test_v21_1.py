"""V21.1 uses synthetic data only; exercises real authorization and routes."""
import hashlib
import json
from pathlib import Path
import unittest
import test_v21


class UX21_1(unittest.TestCase):
    setUp = test_v21.Version21.setUp
    tearDown = test_v21.Version21.tearDown
    login = test_v21.Version21.login
    post = test_v21.Version21.post
    # Use shared synthetic setup, without rerunning the inherited suite here.
    def test_secondary_actions_move_to_manage(self):
        listing=self.client.get('/list/quote').get_data(as_text=True)
        self.assertNotIn('data-copy-quote',listing)
        self.assertNotIn('>Internal notes</a>',listing)
        manage=self.client.get('/documents/'+self.quote+'/manage').get_data(as_text=True)
        for label in ['Copy link','Internal notes','Pre-send check','Remind Pending Approvers','History · Activity history']:
            self.assertIn(label,manage)
        self.assertEqual(manage.count('>Internal notes</a>'),1)
        self.assertEqual(manage.count('>Pre-send check</a>'),1)

    def test_editor_assets_are_excluded(self):
        editor=self.client.get('/quotes/'+self.quote+'/edit').get_data(as_text=True)
        self.assertNotIn('/static/ux21',editor)
        self.assertNotIn('ux-breadcrumbs',editor)
        self.assertNotIn('nav-group',editor)
        self.assertIn('/static/quotation_editor.js',editor)

    def test_viewer_manage_does_not_expose_write_workflow(self):
        from workspace_app import store
        with store.connect(self.root) as db:
            db.execute('INSERT INTO record_acl VALUES (?,?,?)',(self.quote,self.viewer,'view'))
        self.login('viewer')
        page=self.client.get('/documents/'+self.quote+'/manage').get_data(as_text=True)
        self.assertNotIn('>Internal notes</a>',page)
        self.assertNotIn('>Pre-send check</a>',page)
        self.assertNotIn('Remind Pending Approvers',page)
        self.assertNotIn('+ <span>New</span>',page)
        self.assertEqual(self.client.get('/quotes/'+self.quote+'/internal-notes').status_code,404)

    def test_favorite_state_and_remove(self):
        self.post('/v21/favorites/'+self.quote)
        page=self.client.get('/documents/'+self.quote+'/manage').data
        self.assertIn('★ Remove favorite'.encode(),page)
        self.post('/v21/favorites/'+self.quote,action='remove')
        self.assertIn('☆ Favorite'.encode(),self.client.get('/documents/'+self.quote+'/manage').data)

    def test_grouped_search_keeps_access_rules(self):
        page=self.client.get('/v21/search?q=V21').get_data(as_text=True)
        self.assertIn('ux-search-result',page)
        self.assertIn('V21 customer',page)
        self.login('viewer')
        self.assertNotIn('ux-search-result',self.client.get('/v21/search?q=V21').get_data(as_text=True))

    def test_protected_source_matches_uploaded_manifest(self):
        root=Path(__file__).resolve().parents[1]
        manifest=json.loads((root/'tests/v21_1_protected.json').read_text())
        for name,digest in manifest.items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest,name)
        original_filter=(root/'tests/v21_1_filters.html').read_text()
        current=(root/'workspace_app/templates/documents.html').read_text()
        self.assertEqual(current[current.index('<form method="get"'):current.index('</form>')+7],original_filter)
