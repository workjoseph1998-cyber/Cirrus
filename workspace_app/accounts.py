"""Login and administrator account management. Initial admin is created at the console."""
import secrets,time
from flask import Blueprint,abort,current_app,flash,g,redirect,render_template,request,session
from werkzeug.security import generate_password_hash
from . import store,security
from .model import ValidationError

bp=Blueprint('accounts',__name__)
def db():return store.connect(current_app.config['DATA_DIR'])


def schema(conn):
    # Retain the identity row: existing foreign keys and historical name joins
    # must continue to resolve after the login account is deleted.
    conn.execute('''CREATE TABLE IF NOT EXISTS account_deletions(
        user_id TEXT PRIMARY KEY REFERENCES users(id),deleted_at TEXT NOT NULL,
        deleted_by TEXT NOT NULL REFERENCES users(id))''')


def deletion_block(conn,user):
    if security.current_user() and user['id']==security.current_user()['id']:
        return 'You cannot delete the currently signed-in account.'
    if user['active'] and user['role']=='Administrator' and conn.execute(
        "SELECT count(*) FROM users WHERE active=1 AND role='Administrator'").fetchone()[0]<=1:
        return 'You cannot delete the last active administrator.'
    return ''


@bp.route('/accounts/<ident>/delete',methods=['GET','POST'])
def delete_account(ident):
    security.require_admin();error=None
    with db() as conn:
        if request.method=='POST':conn.execute('BEGIN IMMEDIATE')
        user=conn.execute('''SELECT * FROM users WHERE id=? AND NOT EXISTS
            (SELECT 1 FROM account_deletions WHERE user_id=users.id)''',(ident,)).fetchone()
        if not user:abort(404)
        blocked=deletion_block(conn,user)
        if request.method=='POST':
            if blocked:error=blocked
            elif request.form.get('confirm')!='yes' or request.form.get('account_name')!=user['username']:
                error='Confirm the named account before deleting it.'
            else:
                from .references import stamp,actor
                conn.execute('INSERT INTO account_deletions VALUES (?,?,?)',(ident,stamp(),actor()))
                # A deleted account cannot be re-enabled/reset. Keep its stable
                # ID/name for ownership, messages, decisions and audit history.
                conn.execute('UPDATE users SET active=0,password_hash=?,session_version=session_version+1 WHERE id=?',
                             (generate_password_hash(secrets.token_hex(64)),ident))
                conn.execute('UPDATE account_emails SET enabled=0 WHERE user_id=?',(ident,))
                conn.execute("""UPDATE notification_emails SET status='cancelled',error='Account deleted.'
                    WHERE status IN ('pending','failed') AND notification_id IN
                    (SELECT id FROM portal_notifications WHERE user_id=?)""",(ident,))
                flash('Account '+user['username']+' deleted. Linked records and historical attribution are retained.')
                return redirect('/accounts')
    return render_template('account_delete.html',account=user,blocked=blocked,error=error),(400 if error else 200)

@bp.route('/login',methods=['GET','POST'])
def login():
    error=None
    if request.method=='POST':
        try:
            with db() as conn:user=security.login(conn,request.form.get('username',''),request.form.get('password',''),request.remote_addr or 'unknown')
            if user:
                session.clear();session.update(uid=user['id'],version=user['session_version'],issued=time.time(),seen=time.time(),csrf=secrets.token_hex(32))
                return redirect('/')
            error='Invalid username/password or disabled account.'
        except ValidationError as exc:error=str(exc)
    with db() as conn:has_users=bool(conn.execute('SELECT 1 FROM users LIMIT 1').fetchone())
    return render_template('login.html',error=error,has_users=has_users), (400 if error else 200)

@bp.post('/logout')
def logout():
    session.clear();return redirect('/login')

@bp.route('/accounts',methods=['GET','POST'])
def accounts():
    security.require_admin();error=None
    if request.method=='POST':
        try:
            with db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                action=request.form.get('action')
                if action=='create':security.create_user(conn,request.form.get('username',''),request.form.get('password',''),request.form.get('role',''))
                else:
                    user=conn.execute('''SELECT * FROM users WHERE id=? AND NOT EXISTS
                        (SELECT 1 FROM account_deletions WHERE user_id=users.id)''',(request.form.get('id'),)).fetchone()
                    if not user:abort(404)
                    if action=='reset':
                        password=request.form.get('password','')
                        if not 12<=len(password)<=256:raise ValidationError('Use a password of 12–256 characters.')
                        conn.execute('UPDATE users SET password_hash=?,session_version=session_version+1 WHERE id=?',(generate_password_hash(password),user['id']))
                    elif action=='access':
                        role=request.form.get('role');active=int(request.form.get('active')=='yes')
                        if role not in security.ROLES:raise ValidationError('Invalid role.')
                        if user['id']==g.user['id'] and (not active or role!='Administrator'):raise ValidationError('You cannot disable or demote your own administrator account.')
                        if user['active'] and user['role']=='Administrator' and (not active or role!='Administrator') and conn.execute("SELECT count(*) FROM users WHERE active=1 AND role='Administrator'").fetchone()[0]<=1:
                            raise ValidationError('You cannot disable or demote the last active administrator.')
                        conn.execute('UPDATE users SET active=?,role=?,session_version=session_version+1 WHERE id=?',(active,role,user['id']))
                    else:raise ValidationError('Invalid action.')
            flash('Account updated. Existing sessions are revoked after password/access changes.')
            return redirect('/accounts')
        except ValidationError as exc:error=str(exc)
    with db() as conn:users=conn.execute('''SELECT id,username,role,active FROM users WHERE NOT EXISTS
        (SELECT 1 FROM account_deletions WHERE user_id=users.id) ORDER BY username''').fetchall()
    with db() as conn:
        records=store.records(conn)
        reservations=conn.execute("SELECT COUNT(*) FROM reference_registry WHERE state='reserved' AND expires>?",(time.time(),)).fetchone()[0]
    kpis=[('Users',len(users)),('Enabled users',sum(u['active'] for u in users)),('Enabled administrators',sum(u['active'] and u['role']=='Administrator' for u in users)),('Active reference reservations',reservations),('Accessible work records',sum(r['kind'] in ('project','quote') for r in records))]
    return render_template('accounts.html',users=users,error=error,roles=security.ROLES,kpis=kpis)

@bp.route('/record/<ident>/access',methods=['GET','POST'])
def access(ident):
    with db() as conn:
        security.require_id(conn,ident)
        meta=conn.execute('SELECT * FROM records WHERE id=?',(ident,)).fetchone()
        if meta['kind'] in ('catalog','category') or meta['personal'] or (meta['owner_id']!=g.user['id'] and not security.admin()):abort(403)
        if g.user['role']=='Viewer':abort(403)
        if request.method=='POST':
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM record_acl WHERE record_id=?',(ident,))
            for user in conn.execute('SELECT id FROM users WHERE active=1 AND (? IS NULL OR id<>?)',(meta['owner_id'],meta['owner_id'])):
                value=request.form.get(user['id'],'')
                if value not in ('','read','edit'):raise ValidationError('Invalid permission.')
                if value:conn.execute('INSERT INTO record_acl VALUES (?,?,?)',(ident,user['id'],value))
            if security.admin() and request.form.get('owner'):
                owner=conn.execute('SELECT id FROM users WHERE id=? AND active=1',(request.form['owner'],)).fetchone()
                if not owner:raise ValidationError('Invalid owner.')
                conn.execute('UPDATE records SET owner_id=? WHERE id=?',(owner['id'],ident))
            return redirect('/record/'+ident)
        users=conn.execute('SELECT id,username,role FROM users WHERE active=1').fetchall()
        shares={r['user_id']:r['permission'] for r in conn.execute('SELECT * FROM record_acl WHERE record_id=?',(ident,))}
        original=conn.execute('SELECT username FROM users WHERE id=?',(meta['owner_id'],)).fetchone()
    return render_template('access.html',ident=ident,users=users,shares=shares,owner=meta['owner_id'],owner_name=original['username'] if original else 'Unassigned')
