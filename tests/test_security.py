from editor_requests import fields_for
import copy,io,json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.security import check_password_hash
from workspace_app import create_app,store,security
from workspace_app.model import FIELDS
from test_workspace import data
from quotation_fixture import fixture

PASSWORD='Synthetic-test-password-2026!'


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'data';self.app=create_app(self.root,True)
        with store.connect(self.root) as db:
            self.admin=security.create_user(db,'admin',PASSWORD,'Administrator',True)
            self.alice=security.create_user(db,'alice',PASSWORD,'Editor')
            self.bob=security.create_user(db,'bob',PASSWORD,'Editor')
            self.viewer=security.create_user(db,'viewer',PASSWORD,'Viewer')
            self.other_admin=security.create_user(db,'other-admin',PASSWORD,'Administrator')
            self.project=store.save(db,'project',data('project',name='Alice secret project',customer='Only Alice'))
            q=fixture();q['project_id']=self.project;q['title']='Inherited quotation'
            self.quote=store.save(db,'quote',q)
            self.private=store.save(db,'note',data('note',title='Personal Gym secret',visibility='Personal',content='Do not show admin'))
            self.note=store.save(db,'note',data('note',title='Linked work note',project_id=self.project))
            for rid in (self.project,self.quote,self.private,self.note):db.execute('UPDATE records SET owner_id=?,personal=? WHERE id=?',(self.alice,int(rid==self.private),rid))
            db.execute('INSERT INTO attachments VALUES (?,?,?,?,?)',('attachment',self.quote,'private.txt','private.txt','text/plain'))
            (self.root/'attachments/private.txt').write_text('PRIVATE-BYTES')
    def tearDown(self):self.temp.cleanup()
    def client(self,username='alice'):
        client=self.app.test_client();client.get('/login')
        with client.session_transaction() as s:csrf=s['csrf']
        result=client.post('/login',data={'csrf':csrf,'username':username,'password':PASSWORD})
        self.assertEqual(result.status_code,302,result.data)
        return client
    def token(self,c):
        with c.session_transaction() as s:return s['csrf']
    def post(self,c,path,**fields):return c.post(path,data={'csrf':self.token(c),**fields_for(c,path,fields)})

    def test_login_logout_disabled_and_expiry(self):
        c=self.client();self.assertEqual(c.get('/').status_code,200)
        self.assertEqual(self.post(c,'/logout').status_code,302)
        self.assertEqual(c.get('/').location,'/login')
        c=self.client()
        with c.session_transaction() as s:s['seen']=time.time()-1900
        self.assertEqual(c.get('/').location,'/login')
        c=self.client()
        with store.connect(self.root) as db:db.execute('UPDATE users SET active=0 WHERE id=?',(self.alice,))
        self.assertEqual(c.get('/').location,'/login')
        with store.connect(self.root) as db:
            row=db.execute('SELECT password_hash FROM users WHERE id=?',(self.admin,)).fetchone()
            self.assertTrue(check_password_hash(row[0],PASSWORD));self.assertNotEqual(row[0],PASSWORD)

    def test_throttle_csrf_and_session_revocation(self):
        c=self.app.test_client();c.get('/login')
        self.assertEqual(c.post('/login',data={'username':'alice','password':PASSWORD}).status_code,400)
        for _ in range(8):self.post(c,'/login',username='missing',password='wrong')
        result=self.post(c,'/login',username='alice',password=PASSWORD)
        self.assertIn(b'Too many login attempts',result.data)
        with store.connect(self.root) as db:db.execute('DELETE FROM login_attempts')
        owner=self.client();admin=self.client('admin')
        self.post(admin,'/accounts',action='reset',id=self.alice,password='A-new-test-password-2026!')
        self.assertEqual(owner.get('/').location,'/login')

    def test_id_guessing_search_attachments_exports_and_link_parameters(self):
        c=self.client('bob')
        for path in ['/record/'+self.project,'/quotes/'+self.quote+'/edit','/quotes/'+self.quote+'/print','/quotes/'+self.quote+'/xlsx','/quotes/'+self.quote+'/csv','/attachment/attachment','/record/'+self.project+'/markdown','/edit/project/'+self.project]:
            self.assertEqual(c.get(path).status_code,404,path)
        self.assertNotIn(b'Alice secret',c.get('/list/search?q=Alice').data)
        self.assertNotIn(b'Alice secret',c.get('/').data)
        exported=json.loads(c.get('/export').data)
        self.assertNotIn(self.project,{r['id'] for r in exported['records']})
        self.assertEqual(self.post(c,'/record/'+self.quote+'/delete').status_code,404)
        q=fixture();q['project_id']=self.project
        self.assertEqual(self.post(c,'/quotes/new',quotation=json.dumps(q)).status_code,404)
        self.assertEqual(self.post(c,'/quotes/preview',quotation=json.dumps(q)).status_code,404)
        self.assertEqual(self.post(c,'/record/'+self.quote+'/attachment',file=(io.BytesIO(b'x'),'x.txt')).status_code,404)

    def test_named_shares_project_inheritance_and_roles(self):
        owner=self.client();bob=self.client('bob');viewer=self.client('viewer')
        self.assertEqual(self.post(owner,'/record/'+self.project+'/access',**{self.bob:'edit',self.viewer:'read'}).status_code,302)
        self.assertEqual(bob.get('/record/'+self.project).status_code,200)
        self.assertEqual(bob.get('/quotes/'+self.quote+'/edit').status_code,200)
        with bob.get('/attachment/attachment') as response:self.assertEqual(response.status_code,200)
        self.assertEqual(viewer.get('/quotes/'+self.quote+'/print').status_code,200)
        self.assertEqual(viewer.get('/quotes/'+self.quote+'/edit').status_code,404)
        self.assertEqual(self.post(viewer,'/record/'+self.quote+'/delete').status_code,403)
        self.assertEqual(self.post(bob,'/accounts',action='create',username='attacker',password=PASSWORD,role='Administrator').status_code,403)
        self.assertEqual(bob.get('/new/catalog').status_code,403)
        self.assertEqual(self.post(bob,'/hosting-vms/settings').status_code,403)
        self.assertEqual(bob.get('/record/'+self.project+'/access').status_code,403)

    def test_personal_owner_only_against_admin_and_project_shares(self):
        admin=self.client('admin');other=self.client('other-admin');owner=self.client()
        for c in (admin,other):
            self.assertEqual(c.get('/record/'+self.private).status_code,404)
            self.assertNotIn(b'Personal Gym secret',c.get('/list/search?q=Gym').data)
            self.assertNotIn(self.private,{r['id'] for r in json.loads(c.get('/export').data)['records']})
        self.assertEqual(owner.get('/record/'+self.private).status_code,200)
        self.assertEqual(owner.get('/record/'+self.private+'/access').status_code,403)
        self.assertEqual(admin.get('/record/'+self.project).status_code,200)

    def test_ownership_migration_initial_owner(self):
        root=Path(self.temp.name)/'legacy';store.migrate(root)
        with store.connect(root) as db:
            category=store.save(db,'category',data('category',name='Personal'))
            note=store.save(db,'note',data('note',title='Legacy private',category=category))
            user=security.create_user(db,'initial',PASSWORD,'Administrator',True)
            row=db.execute('SELECT owner_id,personal FROM records WHERE id=?',(note,)).fetchone()
            self.assertEqual((row['owner_id'],row['personal']),(user,1))

    def test_filtered_import_assigns_owner_and_forbids_catalog_mutation(self):
        c=self.client('bob')
        payload={'format':'joseph-workspace','version':3,'records':[], 'settings':{},'hosting_vms':[]}
        from uuid import uuid4
        ident=str(uuid4());payload['records']=[dict(id=ident,kind='project',data=data('project',name='Imported',customer='New'),created='2026-10-28T00:00:00+00:00',updated='2026-10-28T00:00:00+00:00')]
        self.assertEqual(self.post(c,'/import',payload=json.dumps(payload),confirm='yes').status_code,302)
        with store.connect(self.root) as db:self.assertEqual(db.execute('SELECT owner_id FROM records WHERE id=?',(ident,)).fetchone()[0],self.bob)
        payload['records'][0].update(id=str(uuid4()),kind='catalog',data=data('catalog',code='NO',name='No',unit='VM',currency='USD',status='Active'))
        self.assertEqual(self.post(c,'/import',payload=json.dumps(payload),confirm='yes').status_code,403)

    def test_proxy_host_validation_and_https_cookie(self):
        with patch.dict(os.environ,{'CIRRUS_INTERNAL_ACCESS':'1','CIRRUS_HTTPS':'1','CIRRUS_TRUSTED_PROXY':'127.0.0.1','CIRRUS_ALLOWED_HOSTS':'workplace.test'}):
            app=create_app(self.root,True)
        c=app.test_client()
        self.assertEqual(c.get('/login',base_url='http://workplace.test',headers={'X-Forwarded-Proto':'https'},environ_overrides={'REMOTE_ADDR':'10.0.0.5'}).status_code,400)
        result=c.get('/login',base_url='http://workplace.test',headers={'X-Forwarded-Proto':'https','X-Forwarded-Host':'evil.test'},environ_overrides={'REMOTE_ADDR':'127.0.0.1'})
        self.assertEqual(result.status_code,200)
        self.assertIn('Secure',result.headers.get('Set-Cookie',''))
        self.assertEqual(c.get('/login',base_url='https://evil.test').status_code,400)
        for host in ('workplace.test:70000','user@workplace.test','workplace.test:0'):
            self.assertEqual(c.get('/login',base_url='https://workplace.test',headers={'Host':host}).status_code,400)

    def test_quote_only_edit_grant_and_revision_do_not_grant_project(self):
        owner=self.client();bob=self.client('bob')
        self.post(owner,'/record/'+self.quote+'/access',**{self.bob:'edit'})
        self.assertEqual(bob.get('/record/'+self.project).status_code,404)
        with store.connect(self.root) as db:q=next(r['data'] for r in store.records(db) if r['id']==self.quote)
        q['title']='Assigned editor update'
        self.assertEqual(self.post(bob,'/quotes/preview',quotation=json.dumps(q),source_quote=self.quote).status_code,200)
        self.assertEqual(self.post(bob,'/quotes/preview',quotation=json.dumps(q),source_quote=self.project).status_code,404)
        self.assertEqual(self.post(bob,'/quotes/preview',quotation=json.dumps(q)).status_code,404)
        self.assertEqual(self.post(bob,'/quotes/'+self.quote+'/edit',quotation=json.dumps(q)).status_code,302)
        response=self.post(bob,'/record/'+self.quote+'/copy/revision')
        self.assertEqual(response.status_code,302)
        new_id=response.location.rsplit('/',1)[-1]
        with store.connect(self.root) as db:
            self.assertEqual(db.execute('SELECT owner_id FROM records WHERE id=?',(new_id,)).fetchone()[0],self.alice)
        self.assertEqual(bob.get('/quotes/'+new_id+'/edit').status_code,200)
        self.assertEqual(bob.get('/record/'+self.project).status_code,404)
