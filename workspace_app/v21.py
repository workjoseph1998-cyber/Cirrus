"""Small workflow conveniences using existing authorization, history and email workers."""
import json
import time
from datetime import date
from uuid import uuid4
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request
from . import security, store, statistics
from .references import actor, stamp
from .model import ValidationError

bp = Blueprint('v21', __name__)


def schema(db):
    for sql in [
        'CREATE TABLE IF NOT EXISTS user_favorites(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE, PRIMARY KEY(user_id,record_id))',
        'CREATE TABLE IF NOT EXISTS user_recent(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE, viewed REAL NOT NULL, PRIMARY KEY(user_id,record_id))',
        'CREATE INDEX IF NOT EXISTS recent_user_time ON user_recent(user_id,viewed DESC)',
        'CREATE TABLE IF NOT EXISTS quotation_internal_notes(id TEXT PRIMARY KEY, quote_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE, author TEXT REFERENCES users(id) ON DELETE SET NULL, at TEXT NOT NULL, body TEXT NOT NULL)',
        'CREATE INDEX IF NOT EXISTS internal_notes_quote ON quotation_internal_notes(quote_id,at)',
        'CREATE TABLE IF NOT EXISTS approval_reminders(round_id TEXT PRIMARY KEY REFERENCES approval_rounds(id) ON DELETE CASCADE, at REAL NOT NULL)',
        'CREATE TABLE IF NOT EXISTS reminder_email_recipients(notification_id INTEGER PRIMARY KEY REFERENCES notification_emails(notification_id) ON DELETE CASCADE, round_id TEXT NOT NULL, payload TEXT NOT NULL)'
    ]:db.execute(sql)


def validity(record, today=None):
    try:days = (date.fromisoformat(record['data'].get('valid_until', '')) - (today or statistics.today_local())).days
    except (TypeError, ValueError):return dict(status='No validity date', days=None, tone='neutral')
    return dict(status='Expired' if days < 0 else 'Expiring Soon' if days <= 7 else 'Valid',
                days=days, tone='expired' if days < 0 else 'soon' if days <= 7 else 'valid')


def accessible(db, ident, kind=None, write=False):
    row = db.execute('SELECT id,kind,data,created,updated FROM records WHERE id=?', (ident,)).fetchone()
    if not row or (kind and row['kind'] != kind):abort(404)
    r = dict(row, data=json.loads(row['data']))
    security.require_record(db, r, write)
    return r


def personal_records(db, table, limit=None):
    uid = actor()
    if not uid:return []
    # Filter with the live ACL before applying the visible-history limit.
    ids = [r[0] for r in db.execute('SELECT record_id FROM ' + table + ' WHERE user_id=?' + (' ORDER BY viewed DESC' if table == 'user_recent' else ''), (uid,))]
    records = {r['id']: r for r in store.records(db) if r['kind'] in ('quote', 'customer')}
    result = [records[i] for i in ids if i in records]
    return result[:limit] if limit else result


@bp.post('/v21/favorites/<ident>')
def favorite(ident):
    if not actor():abort(403)
    with store.connect(current_app.config['DATA_DIR']) as db:
        r = accessible(db, ident)
        if r['kind'] not in ('quote', 'customer'):abort(404)
        if request.form.get('action') == 'remove':
            db.execute('DELETE FROM user_favorites WHERE user_id=? AND record_id=?', (actor(), ident))
            flash('Favorite removed.')
        else:
            db.execute('INSERT OR IGNORE INTO user_favorites VALUES (?,?)', (actor(), ident))
            flash('Favorite saved.')
    return redirect('/v21/shortcuts')


@bp.get('/v21/shortcuts')
def shortcuts():
    with store.connect(current_app.config['DATA_DIR']) as db:
        favorites = personal_records(db, 'user_favorites')
        recent = personal_records(db, 'user_recent', 10)
    return render_template('v21_shortcuts.html', favorites=favorites, recent=recent)


@bp.route('/quotes/<ident>/internal-notes', methods=['GET', 'POST'])
def notes(ident):
    with store.connect(current_app.config['DATA_DIR']) as db:
        r = accessible(db, ident, 'quote', write=True)
        # Internal notes are staff-only, just like the private pricing worksheet.
        from .approvals import private_access
        if not private_access(db, r):abort(403)
        if request.method == 'POST':
            body = request.form.get('body', '').strip()
            if not body or len(body) > 4000:raise ValidationError('Enter an internal note of 1–4,000 characters.')
            db.execute('INSERT INTO quotation_internal_notes VALUES (?,?,?,?,?)', (uuid4().hex, ident, actor(), stamp(), body))
            from .documents import event
            event(db, ident, 'Internal note added')
            flash('Internal note added.')
            return redirect(request.path)
        rows = [dict(x) for x in db.execute('SELECT n.*,u.username FROM quotation_internal_notes n LEFT JOIN users u ON u.id=n.author WHERE quote_id=? ORDER BY at DESC,id DESC', (ident,))]
    return render_template('v21_notes.html', r=r, notes=rows)


def pre_send(db, r):
    from . import approvals as flow
    from .quotation import validate_document, calculate
    # A stable customer ID may be inherited through an existing project.
    customer_id = r['data'].get('customer_id')
    if not customer_id and r['data'].get('project_id'):
        project = db.execute("SELECT data FROM records WHERE id=? AND kind='project'", (r['data']['project_id'],)).fetchone()
        if project:customer_id = json.loads(project[0]).get('customer_id')
    selected = bool(customer_id and db.execute("SELECT 1 FROM records WHERE id=? AND kind='customer'", (customer_id,)).fetchone())
    valid = validity(r)['days'] is not None
    try:
        doc = validate_document(r['data']['document'], enforce_minimum=True)
        calculation = calculate(doc)
        priced = calculation.get('combined') is not None
    except (ValidationError, KeyError, TypeError):priced = False
    round_ = flow.current_round(db, r['id'])
    latest = flow.current_version(db, r['id'])
    reviews = flow.decisions(db, round_['id']) if round_ else []
    approved = bool(round_ and latest and round_['hash'] == latest['hash'] and round_['status'] in ('Approved by all', 'Sent to client') and reviews and all(x['decision'] == 'Approved' for x in reviews))
    artifact = db.execute('SELECT pdf FROM approval_artifacts WHERE round_id=?', (round_['id'],)).fetchone() if round_ else None
    return [('Customer selected', selected), ('Quotation validity entered', valid), ('Required pricing complete', priced), ('All required approvers approved', approved), ('Approved PDF available', bool(artifact and artifact[0]))]


@bp.get('/quotes/<ident>/pre-send')
def verification(ident):
    with store.connect(current_app.config['DATA_DIR']) as db:
        r = accessible(db, ident, 'quote', write=True)
        from .approvals import private_access
        if not private_access(db, r):abort(403)
        checks = pre_send(db, r)
    return render_template('v21_verification.html', r=r, checks=checks, ready=all(x[1] for x in checks))


@bp.post('/quotes/<ident>/remind')
def remind(ident):
    from . import approvals as flow, notifications, approval_emails
    with store.connect(current_app.config['DATA_DIR']) as db:
        db.execute('BEGIN IMMEDIATE')
        r = accessible(db, ident, 'quote', write=True)
        if not flow.private_access(db, r):abort(403)
        round_ = flow.current_round(db, ident)
        if not round_ or round_['status'] not in flow.ACTIVE:raise ValidationError('No pending approval round.')
        old = db.execute('SELECT at FROM approval_reminders WHERE round_id=?', (round_['id'],)).fetchone()
        if old and time.time() - old[0] < 3600:raise ValidationError('A reminder was already requested within the last hour.')
        pending = [d['user_id'] for d in flow.decisions(db, round_['id']) if d['decision'] == 'Pending']
        if not pending:raise ValidationError('No pending approvers.')
        eid = flow.event(db, ident, round_['version'], 'reminder', 'Reminder requested for pending approvers only.', round_['id'])
        event_key = 'reminder:' + str(eid)
        flow.notify(db, ident, pending, 'Approval reminder', 'Please review the pending quotation.', event_key)
        payload = approval_emails.payload_for_round(db, round_['id'], 'reminder')
        queued = 0;seen=set()
        if notifications.config(db)['enabled']:
            for uid in pending:
                user=db.execute('SELECT * FROM users WHERE id=? AND active=1', (uid,)).fetchone()
                email=db.execute('SELECT email FROM account_emails WHERE user_id=? AND enabled=1', (uid,)).fetchone()
                if not user or not email or not notifications.valid_email(email[0]) or email[0].casefold() in seen or not security.can_read(db,r,user=dict(user)):continue
                seen.add(email[0].casefold())
                n=db.execute('SELECT id FROM portal_notifications WHERE user_id=? AND event_key=?', (uid,event_key)).fetchone()
                if not n:continue
                db.execute("INSERT INTO notification_emails(notification_id,address,status) VALUES (?,?,'pending')", (n[0],email[0]))
                db.execute('INSERT INTO reminder_email_recipients VALUES (?,?,?)', (n[0],round_['id'],json.dumps(payload)))
                queued+=1
        db.execute('INSERT INTO approval_reminders VALUES (?,?) ON CONFLICT(round_id) DO UPDATE SET at=excluded.at', (round_['id'],time.time()))
        message=f'Reminder recorded for {len(pending)} pending approver(s); {queued} emails queued.'
        if not current_app.config.get('V21_LIVE'):message+=' Email delivery is disabled in the test profile.'
        flash(message)
    return redirect('/quotes/' + ident + '/approval')


def claim_reminder(db, job, record, user, pref):
    from . import approvals as flow, notifications
    meta=db.execute('SELECT * FROM reminder_email_recipients WHERE notification_id=?',(job['notification_id'],)).fetchone()
    round_=flow.current_round(db,record['id'])
    mine=next((x for x in flow.decisions(db,round_['id']) if x['user_id']==job['user_id']),None) if round_ else None
    if not user or not pref or not notifications.valid_email(pref['email']) or not security.can_read(db,record,user=dict(user)) or not round_ or round_['id']!=meta['round_id'] or round_['status'] not in flow.ACTIVE or not mine or mine['decision']!='Pending':
        db.execute("UPDATE notification_emails SET status='cancelled',error='Reminder superseded, decided or recipient unavailable.' WHERE notification_id=?",(job['notification_id'],))
        return None
    job['address']=pref['email']
    db.execute("UPDATE notification_emails SET address=?,status='running',attempts=attempts+1,at=? WHERE notification_id=?",(job['address'],stamp(),job['notification_id']))
    return json.loads(meta['payload'])


@bp.get('/customers/<ident>/activity')
def activity(ident):
    with store.connect(current_app.config['DATA_DIR']) as db:
        c=accessible(db,ident,'customer')
        rows=store.records(db)
        projects={r['id'] for r in rows if r['kind']=='project' and r['data'].get('customer_id')==ident}
        related={r['id']:r for r in rows if r['data'].get('customer_id')==ident or r['data'].get('project_id') in projects}
        events=[]
        for r in related.values():
            if r['kind'] in ('quote','document'):events.append(dict(at=r['created'],action='Created · revision '+str(r['data'].get('revision',1)),record=r))
        # Reuse stored events; do not copy customer history into another table.
        for table, col in [('document_activity','record_id'),('approval_events','quote_id')]:
            for e in db.execute('SELECT * FROM '+table):
                if e[col] in related:events.append(dict(at=e['at'],action=e['kind'] if table=='approval_events' else e['action'],record=related[e[col]]))
        for e in db.execute('SELECT at,action FROM customer_document_audit WHERE customer_id=?',(ident,)):
            events.append(dict(at=e['at'],action='Customer documents · '+e['action'],record=c))
        events.sort(key=lambda e:e['at'],reverse=True)
    return render_template('v21_activity.html', customer=c, events=events[:250])


@bp.get('/v21/whats-new')
def whats_new():
    return render_template('v21_whats_new.html')


@bp.get('/v21/version')
def version_info():
    return dict(version=21,build=current_app.config['V21_BUILD'],mode='live' if current_app.config['V21_LIVE'] else 'test',features=['copy_links','validity','favorites','recently_viewed','approval_reminders','internal_notes','pre_send','customer_timeline','dashboard_attention','global_search','unsaved_changes'])


@bp.get('/v21/search')
def search():
    term=request.args.get('q','').strip()[:200]
    matches=[]
    if term:
        with store.connect(current_app.config['DATA_DIR']) as db:
            records=store.records(db)
            allowed={r['id']:r for r in records if r['kind'] in ('customer','project')}
            needle=term.casefold()
            for r in records:
                if r['kind'] not in ('quote','customer','project','document'):continue
                if any(needle in str(r['data'].get(k,'')).casefold() for k in ('title','name','number','customer','contact')):
                    matches.append(dict(title=r['data'].get('title') or r['data'].get('name','Untitled'),kind=r['kind'],url='/record/'+r['id']))
            for node in db.execute("SELECT id,customer_id,parent_id,name FROM customer_document_nodes WHERE kind='file' ORDER BY name_key"):
                if node['customer_id'] in allowed and needle in node['name'].casefold():
                    # Link to the existing folder view; its download route rechecks permissions.
                    from urllib.parse import urlencode
                    suffix='?'+urlencode(dict(folder=node['parent_id'])) if node['parent_id'] else ''
                    matches.append(dict(title=node['name'],kind='Customer document',url='/customers/'+node['customer_id']+'/documents'+suffix))
    return render_template('v21_search.html',term=term,matches=matches[:100],truncated=len(matches)>100)


@bp.get('/v21/attention')
def attention():
    from .documents import latest
    with store.connect(current_app.config['DATA_DIR']) as db:
        rows=[r for r in latest(store.records(db)) if r['kind']=='quote']
    mode=request.args.get('filter','expiring')
    if mode not in ('expiring','active','sent'):raise ValidationError('Unknown attention filter.')
    if mode=='expiring':rows=[r for r in rows if validity(r)['status']=='Expiring Soon']
    elif mode=='sent':
        with store.connect(current_app.config['DATA_DIR']) as db:
            month=statistics.today_local().isoformat()[:7]
            ids={r['quote_id'] for r in db.execute('SELECT quote_id,at FROM quotation_sent_events') if statistics.local_date(r['at']).isoformat().startswith(month)}
        rows=[r for r in rows if r['id'] in ids]
    else:rows=[r for r in rows if r['data'].get('status') not in ('Cancelled','Lost','Won')]
    return render_template('v21_attention.html', rows=rows, mode=mode)


def install(app):
    @app.after_request
    def recently_viewed(response):
        if request.method=='GET' and response.status_code==200 and getattr(g,'user',None):
            # Only successful, authorized record pages count; exports and polling do not.
            parts=request.path.strip('/').split('/')
            ident=parts[1] if len(parts)>=2 and parts[0] in ('record','customers','quotes') else None
            page=(len(parts)==2 and parts[0] in ('record','customers')) or (len(parts)==3 and parts[0]=='quotes' and parts[2] in ('edit','approval','internal-notes','pre-send'))
            if ident and page:
                with store.connect(app.config['DATA_DIR']) as db:
                    row=db.execute("SELECT id,kind,data FROM records WHERE id=? AND kind IN ('quote','customer')",(ident,)).fetchone()
                    if row and security.can_read(db,dict(row,data=json.loads(row['data']))):
                        db.execute('INSERT INTO user_recent VALUES (?,?,?) ON CONFLICT(user_id,record_id) DO UPDATE SET viewed=excluded.viewed',(actor(),ident,time.time()))
                        db.execute('DELETE FROM user_recent WHERE user_id=? AND record_id NOT IN (SELECT record_id FROM user_recent WHERE user_id=? ORDER BY viewed DESC LIMIT 10)',(actor(),actor()))
        return response
    @app.context_processor
    def conveniences():
        favorites = set()
        if actor():
            with store.connect(current_app.config['DATA_DIR']) as db:
                favorites = {row[0] for row in db.execute('SELECT record_id FROM user_favorites WHERE user_id=?', (actor(),))}
        return dict(v21_favorites=favorites,v21_validity=validity,v21_live=current_app.config.get('V21_LIVE',False),v21_build=current_app.config.get('V21_BUILD','source'))
