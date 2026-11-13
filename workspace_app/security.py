"""Identity and record authorization. No authorization decisions trust client roles."""
import time
from contextlib import contextmanager
from contextvars import ContextVar

_RECORD_BATCH = ContextVar("record_batch", default=None)
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4
from flask import abort, current_app, g, has_request_context, redirect, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from .model import ValidationError

ROLES=('Administrator','Editor','Viewer')


def current_user():
    return getattr(g,'user',None) if has_request_context() else None


def enabled():return has_request_context() and not current_app.config.get('AUTH_TEST_BYPASS',False)


def admin():return bool(current_user() and current_user()['role']=='Administrator')


def require_admin():
    if enabled() and not admin():abort(403)


def can_read(db,record,user=None,write=False,seen=None,include_workflow=True):
    if not enabled() and user is None:return True
    user=user or current_user()
    if not user:return False
    if write and user['role']=='Viewer':return False
    if record['kind'] in ('catalog','category'):return user['role']=='Administrator' if write else True
    batch=_RECORD_BATCH.get()
    batch=batch if batch and batch['db'] is db and batch['uid']==user['id'] else None
    meta=batch['meta'].get(record['id']) if batch else db.execute('SELECT owner_id,personal FROM records WHERE id=?',(record['id'],)).fetchone()
    if not meta:return False
    if meta['personal'] or personal_flag(db,record['kind'],record['data']):return meta['owner_id']==user['id']
    if meta['owner_id']==user['id'] or user['role']=='Administrator':return True
    acl=batch['acl'].get(record['id']) if batch else db.execute('SELECT permission FROM record_acl WHERE record_id=? AND user_id=?',(record['id'],user['id'])).fetchone()
    if acl and (not write or acl['permission']=='edit'):return True
    if include_workflow and record['kind']=='quote' and (batch['version'] if batch else db.execute('PRAGMA user_version').fetchone()[0])>=11:
        if (record['id'] in batch['grants'] if batch else db.execute('SELECT 1 FROM approval_grants WHERE quote_id=? AND user_id=?',(record['id'],user['id'])).fetchone()):return True
    project=record['data'].get('project_id')
    if project and record['kind'] in ('note','quote','document'):
        import json
        row=db.execute('SELECT id,kind,data FROM records WHERE id=? AND kind=?',(project,'project')).fetchone()
        if row:return can_read(db,{'id':row['id'],'kind':row['kind'],'data':json.loads(row['data'])},user,write,include_workflow=include_workflow)
    return False


@contextmanager
def record_batch(db, records):
    """One immutable ACL snapshot per record-list evaluation, never across requests.

    Only used while filtering/redacting fetched records; mutation authorization
    outside this scope continues to read the current transaction directly.
    """
    user=current_user()
    if not enabled() or not user:
        yield
        return
    existing=_RECORD_BATCH.get()
    if existing and existing['db'] is db and existing['uid']==user['id']:
        yield
        return
    version=db.execute('PRAGMA user_version').fetchone()[0]
    batch=dict(db=db,uid=user['id'],version=version,
        meta={r['id']:r for r in db.execute('SELECT id,owner_id,personal FROM records')},
        acl={r['record_id']:r for r in db.execute('SELECT record_id,permission FROM record_acl WHERE user_id=?',(user['id'],))},
        grants={r[0] for r in db.execute('SELECT quote_id FROM approval_grants WHERE user_id=?',(user['id'],))} if version>=11 else set())
    token=_RECORD_BATCH.set(batch)
    try:yield
    finally:_RECORD_BATCH.reset(token)


def visible(db,records):
    with record_batch(db,records):return [r for r in records if can_read(db,r)]


def require_record(db,record,write=False,include_workflow=True):
    if enabled() and not can_read(db,record,write=write,include_workflow=include_workflow):abort(404)


def require_id(db,ident,write=False,include_workflow=True):
    import json
    row=db.execute('SELECT id,kind,data FROM records WHERE id=?',(ident,)).fetchone()
    if not row:abort(404)
    require_record(db,{'id':row['id'],'kind':row['kind'],'data':json.loads(row['data'])},write,include_workflow)


def authorize_save(db,kind,data,existing,inherited=None):
    if not enabled():return
    user=current_user()
    if not user or user['role']=='Viewer':abort(403)
    if kind in ('catalog','category'):require_admin()
    if existing:require_record(db,existing,True)
    if data.get('customer_id') and (not existing or data['customer_id']!=existing['data'].get('customer_id')) and not (inherited and data['customer_id']==inherited['data'].get('customer_id') and data.get('project_id')==inherited['data'].get('project_id')):
        import json
        project=db.execute("SELECT id,kind,data FROM records WHERE id=? AND kind='project'",(data.get('project_id'),)).fetchone()
        inherited_customer=project and json.loads(project['data']).get('customer_id')==data['customer_id']
        if not inherited_customer:require_id(db,data['customer_id'])
        else:require_id(db,project['id'])
    if data.get('project_id') and not (inherited and data.get('project_id')==inherited['data'].get('project_id')):
        if not existing or data.get('project_id')!=existing['data'].get('project_id'):
            if existing and user['role']!='Administrator':
                owner=db.execute('SELECT owner_id FROM records WHERE id=?',(existing['id'],)).fetchone()[0]
                if owner!=user['id']:abort(403)
            require_id(db,data['project_id'],True)


def personal_flag(db,kind,data):
    if kind!='note':return 0
    import json
    ident=data.get('subcategory') or data.get('category')
    for _ in range(3):
        row=db.execute('SELECT data FROM records WHERE id=? AND kind=?',(ident,'category')).fetchone()
        if not row:break
        cat=json.loads(row['data'])
        if cat.get('name','').strip().casefold() in ('personal','gym'):return 1
        ident=cat.get('parent')
    return int(data.get('visibility')=='Personal')


def create_user(db,username,password,role='Editor',initial=False):
    username=username.strip().casefold()
    if not username or len(username)>80 or not all(c.isalnum() or c in '._-@' for c in username):raise ValidationError('Username must be 1–80 letters, numbers, . _ - @.')
    if len(password)<12 or len(password)>256:raise ValidationError('Use a password of 12–256 characters.')
    if role not in ROLES:raise ValidationError('Invalid role.')
    if db.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone():raise ValidationError('Username already exists.')
    ident=str(uuid4());db.execute('INSERT INTO users VALUES (?,?,?,?,?,?)',(ident,username,generate_password_hash(password),role,1,1))
    if initial:
        from . import store
        db.execute("UPDATE reference_registry SET owner_id=? WHERE owner_id IS NULL AND source='legacy'",(ident,))
        for r in store.records(db,unrestricted=True):
            db.execute('UPDATE records SET owner_id=?,personal=? WHERE id=? AND owner_id IS NULL',(ident,personal_flag(db,r['kind'],r['data']),r['id']))
    return ident


def login(db,username,password,address):
    now=time.time();username=username.strip().casefold()[:80];key=username+'|'+address
    db.execute('DELETE FROM login_attempts WHERE at<?',(now-900,))
    if db.execute('SELECT COUNT(*) FROM login_attempts WHERE key=? OR address=?',(key,address)).fetchone()[0]>=8:
        raise ValidationError('Too many login attempts. Try again in 15 minutes.')
    user=db.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
    # A dummy hash makes nonexistent-user verification comparable to a real login.
    hashed=user['password_hash'] if user else current_app.config['DUMMY_PASSWORD_HASH']
    valid=check_password_hash(hashed,password[:257]) and len(password)<=256
    if not user or not user['active'] or not valid:
        db.execute('INSERT INTO login_attempts VALUES (?,?,?)',(key,address,now));return None
    db.execute('DELETE FROM login_attempts WHERE key=?',(key,))
    return dict(user)
