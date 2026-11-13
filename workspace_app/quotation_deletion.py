"""Family deletion with durable, permission-checked external cleanup and retries."""
import hashlib,json,os
from pathlib import Path
from uuid import uuid4
from flask import Blueprint,abort,current_app,render_template,request,redirect
from . import store,security,document_storage as fs
from .references import actor,stamp,key
from .model import ValidationError
bp=Blueprint('quotation_deletion',__name__)


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS quotation_deletions(id TEXT PRIMARY KEY,reference TEXT NOT NULL,
        actor TEXT,at TEXT NOT NULL,revisions INTEGER NOT NULL,details TEXT NOT NULL,files TEXT NOT NULL,status TEXT NOT NULL)''')
    db.execute('CREATE TABLE IF NOT EXISTS deleted_quotation_ids(record_id TEXT PRIMARY KEY,deletion_id TEXT NOT NULL REFERENCES quotation_deletions(id))')


def purge(db,family,root):
    ident=uuid4().hex;files=[];details=[]
    for record_id in family['ids']:
        row=db.execute('SELECT data FROM records WHERE id=?',(record_id,)).fetchone()
        if not row:raise ValidationError('A selected quotation changed. Review deletion again.')
        q=json.loads(row['data']);details.append(dict(id=record_id,title=q['title'],revision=q['revision']))
        for r in db.execute('SELECT stored FROM attachments WHERE record_id=?',(record_id,)):
            if Path(r[0]).name!=r[0] or '\\' in r[0]:raise ValidationError('Unsafe attachment metadata; no deletion performed.')
            files.append(dict(path=str(Path(root)/'attachments'/r[0]),record_id=record_id,external=False,done=False,error=''))
        legacy=db.execute('SELECT destination FROM pdf_exports WHERE record_id=?',(record_id,)).fetchone()
        if legacy and legacy[0]:
            import ntpath
            path_key=ntpath.normcase(legacy[0].replace('/','\\')).casefold()
            db.execute('INSERT OR IGNORE INTO pdf_file_owners(path_key,record_id,path,revision) VALUES (?,?,?,?)',(path_key,record_id,legacy[0],q['revision']))
        for r in db.execute('SELECT path,path_key FROM pdf_file_owners WHERE record_id=?',(record_id,)):
            files.append(dict(path=r['path'],path_key=r['path_key'],record_id=record_id,external=True,done=False,error=''))
    db.execute('INSERT INTO quotation_deletions VALUES (?,?,?,?,?,?,?,?)',(ident,family['reference'],actor(),stamp(),len(details),json.dumps(details),json.dumps(files),'Cleanup pending'))
    for r in details:
        rid=r['id'];db.execute('INSERT INTO deleted_quotation_ids VALUES (?,?)',(rid,ident))
        # Remove workflow children before their foreign-key parents. Audit tables
        # without foreign keys deliberately retain the deletion record/reference.
        nids=[x[0] for x in db.execute('SELECT id FROM portal_notifications WHERE quote_id=?',(rid,))]
        for nid in nids:
            db.execute('DELETE FROM sent_email_recipients WHERE notification_id=?',(nid,))
            db.execute('DELETE FROM approval_email_recipients WHERE notification_id=?',(nid,))
            db.execute('DELETE FROM notification_emails WHERE notification_id=?',(nid,))
        db.execute('DELETE FROM portal_notifications WHERE quote_id=?',(rid,))
        for round_ in db.execute('SELECT id FROM approval_rounds WHERE quote_id=?',(rid,)).fetchall():
            db.execute('DELETE FROM approval_email_batches WHERE round_id=?',(round_[0],))
            db.execute('DELETE FROM approval_reviews WHERE round_id=?',(round_[0],))
            db.execute('DELETE FROM approval_artifacts WHERE round_id=?',(round_[0],))
        for table,col in [('quotation_sent_events','quote_id'),('approval_rounds','quote_id'),('approval_messages','quote_id'),('approval_reads','quote_id'),('approval_events','quote_id'),('approval_grants','quote_id'),('quotation_approvers','quote_id'),('approval_versions','quote_id'),('attachments','record_id'),('record_acl','record_id'),('reference_conflicts','record_id'),('quote_costing','quote_id'),('support_migrations','quote_id'),('support_migration_issues','quote_id')]:
            db.execute('DELETE FROM '+table+' WHERE '+col+'=?',(rid,))
        from .documents import event
        event(db,rid,'Permanently deleted',q['title'] if len(details)==1 else family['reference'])
        db.execute('DELETE FROM records WHERE id=?',(rid,))
    # Keep the registry/reservations and sent/issued usage protected. A family
    # deletion never silently allocates its old reference to a different document.
    db.execute("UPDATE reference_registry SET state='issued',expires=NULL WHERE key=?",(family['key'],))
    db.execute('UPDATE reference_usage SET draft_only=0 WHERE reference_key=?',(family['key'],))
    db.execute('DELETE FROM quotation_outcomes WHERE reference_key=?',(family['key'],))
    db.execute('DELETE FROM support_migration_issues WHERE quote_id=?',('accepted:'+family['key'],))
    db.execute('DELETE FROM quotation_archives WHERE reference_key=?',(family['key'],))
    from .outcomes import event
    event(db,family['key'],None,'Archived quotation family permanently deleted',details,dict(deletion_id=ident))
    return ident


def cleanup(root,ident):
    with store.connect(root) as db,fs.LOCK:
        row=db.execute('SELECT * FROM quotation_deletions WHERE id=?',(ident,)).fetchone()
        if not row:return
        files=json.loads(row['files'])
        for f in files:
            if f['done']:continue
            try:
                p=Path(f['path'])
                if f['external']:
                    from .isolation import require_path
                    require_path(p,'exports')
                    owner=db.execute('SELECT record_id FROM pdf_file_owners WHERE path_key=?',(f['path_key'],)).fetchone()
                    if not owner or owner[0]!=f['record_id']:raise ValidationError('Ownership changed; unrelated file preserved.')
                else:
                    if p.parent!=Path(root)/'attachments':raise ValidationError('Unsafe attachment path.')
                fs.check_components(p.parent)
                if p.exists() or p.is_symlink():
                    fs.file_info(p);p.unlink()
                f['done']=True;f['error']=''
                if f['external']:db.execute('DELETE FROM pdf_file_owners WHERE path_key=? AND record_id=?',(f['path_key'],f['record_id']))
            except (OSError,ValidationError,RuntimeError) as exc:f['error']=str(exc)[:500]
            db.execute('UPDATE quotation_deletions SET files=?,status=? WHERE id=?',(json.dumps(files),'Complete' if all(x['done'] for x in files) else 'Cleanup pending',ident));db.commit()
        status='Complete' if all(f['done'] for f in files) else 'Cleanup pending'
        db.execute('UPDATE quotation_deletions SET files=?,status=? WHERE id=?',(json.dumps(files),status,ident))


def authorized(row):
    user=security.current_user()
    return security.admin() or user and user['role']!='Viewer' and row['actor']==user['id'] or not security.enabled()


@bp.route('/quotation-deletions',methods=['GET','POST'])
def page():
    root=current_app.config['DATA_DIR']
    if request.method=='POST':
        with store.connect(root) as db:r=db.execute('SELECT * FROM quotation_deletions WHERE id=?',(request.form.get('id'),)).fetchone()
        if not r or not authorized(r):abort(404)
        cleanup(root,r['id']);return redirect('/quotation-deletions')
    with store.connect(root) as db:rows=[dict(r,files=json.loads(r['files']),details=json.loads(r['details'])) for r in db.execute('SELECT * FROM quotation_deletions ORDER BY at DESC') if authorized(r)]
    return render_template('quotation_deletions.html',rows=rows)


@bp.get('/quotes/<ident>/delete-review')
def review_one(ident):
    from .archives import archived_keys,selection
    from .commercial import fingerprint
    from werkzeug.datastructures import MultiDict
    with store.connect(current_app.config['DATA_DIR']) as db:
        security.require_id(db,ident,True)
        r=db.execute('SELECT data FROM records WHERE id=?',(ident,)).fetchone()
        if not r:abort(404)
        reference=json.loads(r[0])['number']
    # The ordinary archived-list single-row POST is the canonical confirmation.
    return render_template('delete_review_start.html',reference=reference)
