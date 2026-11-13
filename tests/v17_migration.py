"""Verify an actual supplied schema-15 source tree migrates without modifying old rows.
Usage: python tests/v17_migration.py /path/to/extracted/Version16/application
Uses only synthetic accounts/records; no SMTP or live data.
"""
import hashlib,json,sqlite3,subprocess,sys,tempfile,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import store,create_app
from workspace_app.backup import online_safety_backup,restore


def tables(root):
 with sqlite3.connect(root/'workspace.sqlite') as db:
  names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
  return {name:db.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall() for name in names}


def run(base):
 base=Path(base).resolve()
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp)/'data'
  seed=r'''
import json,shutil,sys
from pathlib import Path
sys.path.insert(0,'tests')
from test_v12 import WorkflowTests
from workspace_app import store
from workspace_app.approval_routes import capture_pdf
w=WorkflowTests();w.setUp()
try:
 w.configure_email();w.approve_all();capture_pdf(w.app,w.renderer);v,r=w.state()
 assert w.post(w.url+'/approval',action='sent',version=v['version'],hash=v['hash'],round_id=r['id']).status_code==302
 (w.root/'attachments'/'migration.txt').write_bytes(b'Synthetic original attachment')
 with store.connect(w.root) as db:
  db.execute('INSERT INTO attachments VALUES (?,?,?,?,?)',('migration-file',w.ident,'Original.txt','migration.txt','text/plain'))
  assert db.execute('PRAGMA user_version').fetchone()[0]==15
 shutil.copytree(w.root,sys.argv[1])
finally:w.tearDown()
'''
  subprocess.run([sys.executable,'-c',seed,str(root)],cwd=base,check=True,capture_output=True,text=True)
  before=tables(root);attachment=(root/'attachments'/'migration.txt').read_bytes();app=create_app(root,True);store.migrate(root);after=tables(root)
  for name,rows in before.items():assert after[name]==rows,('Existing table changed',name)
  with store.connect(root) as db:
   assert db.execute('PRAGMA user_version').fetchone()[0]==16
   sent=dict(db.execute('SELECT * FROM quotation_sent_events').fetchone());assert sent['legacy']==1 and not sent['recipient_email'] and not sent['method']
   assert db.execute('SELECT count(*) FROM sent_email_recipients').fetchone()[0]==0
   assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert not db.execute('PRAGMA foreign_key_check').fetchall()
  assert (root/'attachments'/'migration.txt').read_bytes()==attachment
  backup=Path(temp)/'v17-backup.zip';online_safety_backup(root,backup);restored=Path(temp)/'restored';restore(backup,restored)
  with zipfile.ZipFile(backup) as z:
   manifest=json.loads(z.read('manifest.json'));assert manifest['schema']==16 and manifest['application_version']=='17'
  assert tables(restored)==after;assert (restored/'attachments'/'migration.txt').read_bytes()==attachment
  rejected=subprocess.run([sys.executable,'-c','from workspace_app import store;import sys;store.migrate(sys.argv[1])',str(root)],cwd=base,capture_output=True,text=True)
  assert rejected.returncode!=0 and 'newer' in rejected.stderr.lower()
  print('PASS: supplied Version 16/schema 15 → Version 17/schema 16, all '+str(len(before))+' existing tables unchanged; accounts/settings/SMTP/approval history/PDF/attachments retained; idempotent migration, legacy sent record without replay emails, SQLite integrity/foreign keys, full backup/restore, old application safely rejects newer schema.')


if __name__=='__main__':run(sys.argv[1])
