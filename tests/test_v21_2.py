"""Premium presentation retains real data, roles, editor isolation and filter structure."""
import re
from pathlib import Path
import unittest
import test_v21

class PremiumUI(unittest.TestCase):
 setUp=test_v21.Version21.setUp
 tearDown=test_v21.Version21.tearDown
 login=test_v21.Version21.login
 post=test_v21.Version21.post
 def test_real_metrics_and_scoped_assets(self):
  text=self.client.get('/list/quote').get_data(as_text=True)
  self.assertIn('/static/premium.css',text)
  metrics=text.split('aria-label="Quotation workspace summary"',1)[1].split('</section>',1)[0]
  self.assertEqual(re.findall(r'<strong>(.*?)</strong>',metrics),['1','0','0','0'])
  self.post('/v21/favorites/'+self.quote)
  metrics=self.client.get('/list/quote').get_data(as_text=True).split('aria-label="Quotation workspace summary"',1)[1].split('</section>',1)[0]
  self.assertEqual(re.findall(r'<strong>(.*?)</strong>',metrics)[-1],'1')
 def test_editor_and_new_editor_exclude_premium(self):
  for url in ['/quotes/new','/quotes/'+self.quote+'/edit']:
   text=self.client.get(url).get_data(as_text=True)
   self.assertNotIn('/static/premium.',text)
   self.assertNotIn('premium-navigation',text)
   self.assertIn('id="quotation-form"',text)
 def test_navigation_preserves_actual_routes_and_admin_permissions(self):
  text=self.client.get('/').get_data(as_text=True)
  for route in ['/list/quote','/customers','/list/project','/list/catalog','/hosting-vms','/reports','/accounts','/references','/portability','/administration/workflow','/settings','/automation/settings','/quotation-defaults','/notifications']:
   self.assertIn('href="'+route+'"',text)
  self.login('viewer');text=self.client.get('/').get_data(as_text=True)
  nav=text.split('<nav class="premium-navigation">',1)[1].split('</nav>',1)[0]
  self.assertNotIn('/accounts',nav)
  self.assertNotIn('href="/administration/workflow"',nav)
 def test_original_filters_retained(self):
  root=Path(__file__).resolve().parents[1]
  text=(root/'workspace_app/templates/documents.html').read_text()
  self.assertEqual(text[text.index('<form method="get"'):text.index('</form>')+7],(root/'tests/v21_1_filters.html').read_text())
