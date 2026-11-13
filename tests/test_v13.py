"""V13 variable approvers, current-version dots, filters, SMTP and startup."""
import copy
import html
import json
import os
import re
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock,patch
from urllib.parse import parse_qs,urlsplit,urlencode

from workspace_app import approvals as flow,store,notifications,network,create_app
from workspace_app import deployment_settings as deployment
from workspace_app.commercial import fingerprint
from workspace_app.model import ValidationError
import test_v12 as v12
from test_v5 import quote


class VariableApprovers(unittest.TestCase):
    setUp=v12.WorkflowTests.setUp
    tearDown=v12.WorkflowTests.tearDown
    login=v12.WorkflowTests.login
    post=v12.WorkflowTests.post
    state=v12.WorkflowTests.state
    raw=v12.WorkflowTests.raw
    edit=v12.WorkflowTests.edit
    decision=v12.WorkflowTests.decision

    def chosen(self,*names):
        return [dict(user_id=self.ids[name],phase='commercial' if name=='commercial' else 'operations') for name in names]

    def selection(self):
        with store.connect(self.root) as db:return flow.selection(db,self.ident)

    def save(self,selected,version=None):
        current=self.c.get(self.url+'/edit').data;token=re.search(rb'name="base_hash" value="([^"]+)"',current)[1].decode()
        return self.post(self.url+'/edit',base_hash=token,quotation=json.dumps(self.raw()),approvers=json.dumps(selected),approvers_version=str(self.selection()['version'] if version is None else version))

    def submit_selected(self,selected=None):
        version,_=self.state();selection=self.selection()
        return self.post(self.url+'/approval',action='submit',version=str(version['version']),hash=version['hash'],approvers=json.dumps(selection['data'] if selected is None else selected),approvers_version=str(selection['version']))

    def progress(self):
        return self.c.get(self.url+'/approval/poll').json['progress']

    def assert_dots(self,response,green,white):
        markup=response.data.decode();matches=re.findall(r'<a class="approval-progress-summary" data-approval-progress="'+re.escape(self.ident)+'".*?</a>',markup,re.S)
        self.assertTrue(matches,'Missing shared approval summary')
        for value in matches:
            self.assertEqual(value.count('class="approval-dot is-approved"'),green)
            self.assertEqual(len(re.findall(r'class="approval-dot\s*"',value)),white)
            self.assertIn(str(green)+' out of '+str(green+white)+' approved',value)
            self.assertEqual(value.count('tabindex="0"'),green+white)

    def test_draft_selection_one_approver_and_no_notifications_until_submission(self):
        selected=self.chosen('ops1');self.assertEqual(self.save(selected).status_code,302)
        self.assertEqual(self.selection()['data'],selected);self.assertIsNone(self.state()[1]);self.assertEqual(self.progress()['label'],'Not submitted')
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM portal_notifications').fetchone()[0],0)
        self.assert_dots(self.c.get('/list/quote'),0,1)
        self.assertEqual(self.submit_selected().status_code,302);self.assertEqual(self.decision('ops1').status_code,302)
        self.assertEqual(self.state()[1]['status'],'Approved by all');self.assertEqual(self.progress()['total'],1)
        self.assert_dots(self.c.get(self.url+'/approval'),1,0)

    def test_two_green_one_white_same_projection_everywhere(self):
        self.assertEqual(self.submit_selected(self.chosen('ops1','ops2','commercial')).status_code,302)
        self.decision('ops1');self.decision('ops2')
        for url in ['/list/quote','/', '/customers/'+self.customer+'?tab=quotations&period=all','/approvals?filter=mine',self.url+'/approval']:
            self.assert_dots(self.c.get(url),2,1)
        self.assert_dots(self.clients['commercial'].get('/'),2,1)
        progress=self.progress();self.assertEqual([d['name'] for d in progress['dots']],['ops1','ops2','commercial'])
        self.assertTrue(progress['dots'][0]['date']);self.assertIsNone(progress['dots'][2]['date'])
        self.assertIn('Approved',progress['dots'][0]['tooltip']);self.assertIn('Pending',progress['dots'][2]['tooltip'])
        self.assertEqual(self.decision('commercial').status_code,302);self.assert_dots(self.c.get('/list/quote'),3,0)

    def test_four_approvers_multiple_commercial_all_required_and_recipients(self):
        selected=self.chosen('ops1','ops2','commercial','outsider');selected[-1]['phase']='commercial'
        self.assertEqual(self.submit_selected(selected).status_code,302)
        self.assertEqual(self.decision('outsider').status_code,200)
        self.decision('ops1');self.decision('ops2');self.assertEqual(self.state()[1]['status'],flow.ACTIVE[1])
        self.assertEqual(self.decision('commercial').status_code,302);self.assertEqual(self.state()[1]['status'],flow.ACTIVE[1]);self.assertEqual(self.progress()['approved'],3)
        self.assertEqual(self.decision('outsider').status_code,302);self.assertEqual(self.state()[1]['status'],'Approved by all')
        with store.connect(self.root) as db:
            assigned={r[0] for r in db.execute("SELECT user_id FROM portal_notifications WHERE kind='Review assignment'")}
            completed={r[0] for r in db.execute("SELECT user_id FROM portal_notifications WHERE kind='Approved by all'")}
            self.assertEqual(assigned,{r['user_id'] for r in selected});self.assertEqual(completed,assigned|{self.ids['author']})
            self.assertEqual(db.execute('SELECT count(*) FROM approval_artifacts').fetchone()[0],1)

    def test_commercial_only_and_all_parallel_operations(self):
        self.assertEqual(self.submit_selected(self.chosen('commercial')).status_code,302)
        self.assertEqual(self.state()[1]['status'],flow.ACTIVE[1]);self.decision('commercial')
        self.assertEqual(self.state()[1]['status'],'Approved by all')
        self.assertEqual(self.save(self.chosen('ops1','ops2','outsider')).status_code,302);self.assertIsNone(self.state()[1])
        self.assertEqual(self.submit_selected().status_code,302)
        self.decision('outsider');self.decision('ops2');self.assertNotEqual(self.state()[1]['status'],'Approved by all')
        self.decision('ops1');self.assertEqual(self.progress()['approved'],3);self.assertEqual(self.state()[1]['status'],'Approved by all');self.assertFalse(self.progress()['reapproval'])

    def test_approver_changes_record_history_white_dots_and_explicit_resubmission(self):
        self.submit_selected(self.chosen('ops1','ops2','commercial'));self.decision('ops1');version,old=self.state()
        selected=self.chosen('commercial','outsider','ops1');self.assertEqual(self.save(selected).status_code,302)
        self.assertIsNone(self.state()[1]);self.assertEqual(self.state()[0]['hash'],version['hash'])
        self.assertEqual(self.progress()['label'],'Resubmission required');self.assert_dots(self.c.get('/list/quote'),0,3)
        with store.connect(self.root) as db:
            self.assertTrue(db.execute('SELECT superseded FROM approval_rounds WHERE id=?',(old['id'],)).fetchone()[0])
            self.assertEqual(flow.decisions(db,old['id'])[0]['decision'],'Approved')
            self.assertFalse(db.execute("SELECT 1 FROM portal_notifications WHERE user_id=? AND kind='Review assignment'",(self.ids['outsider'],)).fetchone())
        self.assertEqual(self.decision('ops1',tokens=(version,old)).status_code,200)
        self.assertEqual(self.submit_selected().status_code,302);self.assertNotEqual(self.state()[1]['id'],old['id'])
        self.assertEqual([d['name'] for d in self.progress()['dots']],['commercial','outsider','ops1']);self.assertEqual(self.progress()['approved'],0)
        self.decision('ops1');self.decision('outsider');self.decision('commercial')
        with store.connect(self.root) as db:
            new=self.state()[1]['id'];self.assertFalse(db.execute("SELECT 1 FROM portal_notifications WHERE user_id=? AND event_key=?",(self.ids['ops2'],new+':assign:approver_0')).fetchone())
            complete=list(db.execute("SELECT user_id FROM portal_notifications WHERE kind='Approved by all'"));self.assertNotIn(self.ids['ops2'],{r[0] for r in complete})

    def test_variable_declines_changes_and_resubmission_require_everyone_again(self):
        selected=self.chosen('ops1','ops2');self.submit_selected(selected);self.decision('ops1')
        self.assertEqual(self.decision('ops2',decision='Changes requested',comment='Clarify the scope').status_code,302)
        self.assertEqual(self.state()[1]['status'],'Changes requested');self.assert_dots(self.c.get('/list/quote'),1,1)
        self.submit_selected();self.assert_dots(self.c.get('/list/quote'),0,2)
        self.assertEqual(self.decision('ops2',decision='Declined',comment='Scope still incorrect').status_code,302)
        self.assertEqual(self.state()[1]['status'],'Declined');self.assertEqual(self.decision('ops1').status_code,200)
        self.submit_selected();self.decision('ops2');self.assertEqual(self.progress()['approved'],1)
        self.decision('ops1');self.assertEqual(self.state()[1]['status'],'Approved by all');self.assertFalse(self.progress()['reapproval'])
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM approval_rounds').fetchone()[0],3)

    def test_duplicates_empty_inactive_and_selection_stale_checks(self):
        selected=self.chosen('ops1','ops1');self.assertEqual(self.save(selected).status_code,200);self.assertEqual(self.selection()['data'],[])
        self.assertEqual(self.save([]).status_code,302);self.assertEqual(self.submit_selected().status_code,200);self.assertIsNone(self.state()[1])
        self.assertEqual(self.save(self.chosen('viewer')).status_code,200)
        with store.connect(self.root) as db:db.execute('UPDATE users SET active=0 WHERE id=?',(self.ids['outsider'],))
        self.assertEqual(self.save(self.chosen('outsider')).status_code,200)
        old_version=self.selection()['version'];self.save(self.chosen('ops1','ops2'))
        result=self.save(self.chosen('commercial'),version=old_version);self.assertIn(b'Approvers changed in another session',result.data)
        self.assertEqual(self.selection()['data'],self.chosen('ops1','ops2'))

    def test_content_changes_reset_every_dot_for_variable_count(self):
        self.submit_selected(self.chosen('ops1','ops2','outsider'));self.decision('ops1');self.decision('ops2');self.decision('outsider')
        _,old=self.state();self.assert_dots(self.c.get('/list/quote'),3,0)
        self.assertEqual(self.edit(lambda q:q.update(scope='Changed scope')).status_code,302)
        self.assertNotEqual(self.state()[1]['id'],old['id']);self.assertEqual(self.progress()['approved'],0);self.assert_dots(self.c.get('/list/quote'),0,3)

    def test_new_document_approvers_survive_continue_creation_and_draft_edit(self):
        selected=self.chosen('ops2','commercial')
        response=self.post('/documents/new',type='Quotation',subject='Selected approvers',customer_id=self.customer,approvers=json.dumps(selected))
        self.assertEqual(response.status_code,302);params=parse_qs(urlsplit(response.location).query)
        page=self.c.get(response.location);self.assertEqual(page.status_code,200)
        encoded=re.search(rb'name="approvers" value="([^"]*)"',page.data)[1].decode();self.assertEqual(json.loads(html.unescape(encoded)),selected)
        q=quote(params['reference'][0],status='Draft');q.update(customer_id=self.customer,customer='Private customer',title='Draft with approvers')
        result=self.post(response.location,quotation=json.dumps(q),approvers=json.dumps(selected),approvers_version='0')
        self.assertEqual(result.status_code,302,result.data[:1000]);ident=result.location.split('/')[-2]
        with store.connect(self.root) as db:
            self.assertEqual(flow.selection(db,ident)['data'],selected);self.assertIsNone(flow.current_round(db,ident))
            self.assertEqual(db.execute('SELECT count(*) FROM portal_notifications').fetchone()[0],0)
            self.assertFalse(db.execute('SELECT 1 FROM approval_preparations WHERE id=?',(params['preparation'][0],)).fetchone())
        saved_page=self.c.get(result.location);self.assertIn(b'Approvers & submission',saved_page.data)

    def test_concurrent_submissions_and_commercial_decisions(self):
        selected=self.chosen('commercial','outsider');selected[-1]['phase']='commercial';self.save(selected)
        with self.c.session_transaction() as session:session_data=dict(session)
        version,_=self.state();sv=self.selection()['version']
        def submit(_):
            client=self.app.test_client()
            with client.session_transaction() as s:s.update(session_data)
            return self.post(self.url+'/approval',client=client,action='submit',version=str(version['version']),hash=version['hash'],approvers=json.dumps(selected),approvers_version=str(sv)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(submit,range(2)))
        self.assertEqual(sorted(codes),[200,302])
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(lambda n:self.decision(n).status_code,['commercial','outsider']))
        self.assertEqual(codes,[302,302]);self.assertEqual(self.state()[1]['status'],'Approved by all')
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM approval_artifacts').fetchone()[0],1)

    def test_combined_customer_filter_pagination_and_bulk_selection(self):
        with store.connect(self.root) as db:
            other=store.save(db,'customer',dict(name='Second customer',contact='',notes=''));db.execute('UPDATE records SET owner_id=? WHERE id=?',(self.ids['author'],other))
        for index in range(28):
            q=quote('FILTER-'+str(index),status='Draft');q.update(title='Filter quote '+str(index),customer_id=self.customer if index<26 else other,customer='Private customer' if index<26 else 'Second customer',date='2026-11-03')
            self.assertEqual(self.post('/quotes/new',quotation=json.dumps(q)).status_code,302)
        filters=dict(q='Filter',customer_id=self.customer,type='Quotation',status='Draft',owner=self.ids['author'],basis='date',filter_year='2026',filter_month='11',per_page='25')
        first=self.c.get('/list/quote?'+urlencode(filters));self.assertEqual(first.data.count(b'data-family-select'),25);self.assertIn(b'Approvals</th>',first.data)
        self.assertIn(('customer_id='+self.customer).encode(),first.data);self.assertIn(b'All customers',first.data)
        second=self.c.get('/list/quote?'+urlencode(dict(filters,page='2')));self.assertEqual(second.data.count(b'data-family-select'),1)
        preview=self.post('/quotes/bulk',action='archive',selection_mode='matching',filters=json.dumps(filters))
        self.assertEqual(preview.status_code,200);self.assertIn(b'26 families',preview.data)
        token=re.search(rb'name="selection_hash" value="([^"]+)"',preview.data)[1].decode()
        result=self.post('/quotes/bulk',action='archive',selection_mode='matching',filters=json.dumps(filters),confirm='yes',selection_hash=token)
        self.assertEqual(result.status_code,302)
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT count(*) FROM quotation_archives WHERE archived=1').fetchone()[0],26)
        self.assertEqual(self.c.get('/list/quote?'+urlencode(dict(filters,customer_id=other))).data.count(b'data-family-select'),2)

    def test_customers_separate_count_and_usd_value(self):
        self.edit(lambda q:q.update(date='2026-11-03'))
        for number,currency,price in [('COUNT-EUR','EUR','100'),('COUNT-UNPRICED','USD','')]:
            q=quote(number,status='Draft');q.update(customer_id=self.customer,date='2026-11-03',currency=currency);q['document']['sections'][0]['rows'][0]['unit_price']=price
            self.assertEqual(self.post('/quotes/new',quotation=json.dumps(q)).status_code,302)
        with patch('workspace_app.statistics.today_local',return_value=__import__('datetime').date(2026,11,3)):
            page=self.c.get('/customers').data
        self.assertIn(b'<th scope="col">Quotation count</th><th scope="col">Quotation value (USD)</th>',page)
        row=re.search(rb'<tr><td><a href="/customers/'+self.customer.encode()+rb'".*?</tr>',page,re.S)[0]
        self.assertIn(b'<td>3</td><td>1,375.00</td>',row)

    def test_variable_defaults_copy_to_new_drafts_without_changing_existing_selection(self):
        selected=self.chosen('ops1','ops2','commercial','outsider')
        result=self.post('/administration/workflow',client=self.clients['admin'],action='defaults',approvers=json.dumps(selected))
        self.assertEqual(result.status_code,302);self.assertEqual(self.selection()['data'],[])
        page=self.c.get('/documents/new').data
        encoded=re.search(rb'name="approvers" value="([^"]*)"',page)[1].decode();self.assertEqual(json.loads(html.unescape(encoded)),selected)
        q=quote('DEFAULTS-VARIABLE',status='Draft');created=self.post('/quotes/new',quotation=json.dumps(q));self.assertEqual(created.status_code,302)
        ident=created.location.split('/')[-2]
        with store.connect(self.root) as db:
            self.assertEqual(flow.selection(db,ident)['data'],selected)
            self.assertEqual(db.execute('SELECT count(*) FROM portal_notifications').fetchone()[0],0)


class PersistentSettings(unittest.TestCase):
    def test_external_file_default_and_environment_precedence_across_upgrades(self):
        with tempfile.TemporaryDirectory() as temporary:
            env={'PROGRAMDATA':temporary};path=deployment.load(environ=env,windows=True)
            self.assertEqual(path,Path(temporary)/'CirrusWorkplace/deployment.json');self.assertEqual(env['CIRRUS_ALLOWED_HOSTS'],deployment.DEFAULT_HOSTS)
            path.write_text(json.dumps(dict(CIRRUS_ALLOWED_HOSTS='localhost,override.internal',CIRRUS_PORT='8011',CIRRUS_DATA_DIR=str(Path(temporary)/'old-data'))))
            before=path.read_bytes();first={'CIRRUS_ALLOWED_HOSTS':'administrator.internal','CIRRUS_PORT':'8123'}
            deployment.load(environ=first,path=path);self.assertEqual(first['CIRRUS_ALLOWED_HOSTS'],'administrator.internal');self.assertEqual(first['CIRRUS_PORT'],'8123')
            second={};deployment.load(environ=second,path=path);self.assertEqual(second['CIRRUS_PORT'],'8011');self.assertEqual(path.read_bytes(),before)
            self.assertEqual(first['CIRRUS_DATA_DIR'],second['CIRRUS_DATA_DIR'])

    def test_invalid_settings_do_not_overwrite_or_execute_and_source_path_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'deployment.json';path.write_text('{invalid')
            with self.assertRaises(RuntimeError):deployment.load(environ={},path=path)
            self.assertEqual(path.read_text(),'{invalid')
            path.write_text(json.dumps({'CIRRUS_SMTP_PASSWORD':'must-not-be-stored'}))
            with self.assertRaisesRegex(RuntimeError,'supported deployment'):deployment.load(environ={},path=path)
        with self.assertRaisesRegex(RuntimeError,'outside'):deployment.load(environ={},path=Path(__file__).resolve().parents[1]/'forbidden.json')

    def test_default_hosts_keep_bindings_and_reject_unlisted_host(self):
        with patch.dict(os.environ,{},clear=True),tempfile.TemporaryDirectory() as temporary:
            cfg=network.configuration();self.assertEqual(cfg['bind'],'127.0.0.1');self.assertEqual(cfg['port'],8000);self.assertIn('172.18.69.10',cfg['hosts'])
            app=create_app(Path(temporary)/'data',True);app.config['AUTH_TEST_BYPASS']=True;c=app.test_client()
            self.assertEqual(c.get('/',headers={'Host':'172.18.69.10'}).status_code,200)
            self.assertEqual(c.get('/',headers={'Host':'172.18.69.11'}).status_code,400)

    def test_start_launcher_loads_before_running_server(self):
        import runpy
        original=runpy.run_path;order=[];source=Path(__file__).resolve().parents[1]
        with patch('workspace_app.deployment_settings.load',side_effect=lambda:order.append('load')),patch('runpy.run_path',side_effect=lambda *a,**k:order.append('run')):
            original(str(source/'scripts/start_workplace.py'),run_name='__main__')
        self.assertEqual(order,['load','run']);self.assertIn('start-v21.bat',(source/'start.bat').read_text());self.assertIn('control-v21.ps1',(source/'start-v21.bat').read_text())


class SmtpModes(unittest.TestCase):
    def test_portal_saves_none_and_preserves_custom_host_port(self):
        with tempfile.TemporaryDirectory() as temporary:
            app=create_app(Path(temporary)/'data',True);app.config['AUTH_TEST_BYPASS']=True;client=app.test_client();client.get('/administration/workflow')
            with client.session_transaction() as s:csrf=s['csrf']
            fields=dict(csrf=csrf,action='smtp',enabled='yes',host='relay.custom.example',port='2526',security='none',username='',sender='workplace@example.test',password_env='CIRRUS_SMTP_PASSWORD',base_url='https://workplace.example.test')
            self.assertEqual(client.post('/administration/workflow',data=fields).status_code,302)
            with store.connect(Path(temporary)/'data') as db:
                cfg=notifications.config(db);self.assertEqual((cfg['security'],cfg['host'],cfg['port'],cfg['username']),('none','relay.custom.example',2526,''))
            self.assertIn(b'None (no TLS)',client.get('/administration/workflow').data)

    def test_all_modes_use_configured_hostname_port_and_blank_relay_username(self):
        with tempfile.TemporaryDirectory() as temporary:
            app=create_app(Path(temporary)/'data',True)
            # Production sender is isolated behind mocks; no socket/email delivery.
            app.testing=False
            with app.app_context(),patch.dict(os.environ,{'CIRRUS_DISABLE_EMAIL':'0'}):
                for mode,host,port in [('none','192.0.2.31',1026),('starttls','smtp.dynamic.example',2525),('ssl','192.0.2.44',2465)]:
                    with self.subTest(mode=mode),patch('smtplib.SMTP') as plain,patch('smtplib.SMTP_SSL') as tls,patch('ssl.create_default_context') as context:
                        cfg=dict(notifications.DEFAULTS,security=mode,host=host,port=port,sender='workplace@example.test')
                        notifications.send_smtp(cfg,'staff@example.test','Test','Test body')
                        chosen=tls if mode=='ssl' else plain;self.assertEqual(chosen.call_args.kwargs['host'],host);self.assertEqual(chosen.call_args.kwargs['port'],port)
                        server=chosen.return_value.__enter__.return_value;server.login.assert_not_called();server.send_message.assert_called_once()
                        if mode=='starttls':server.starttls.assert_called_once()
                        else:server.starttls.assert_not_called()
                        if mode=='none':tls.assert_not_called();context.assert_not_called()
            self.assertEqual(notifications.DEFAULTS['security'],'starttls')


if __name__=='__main__':unittest.main()
