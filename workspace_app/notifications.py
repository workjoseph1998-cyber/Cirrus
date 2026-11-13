"""Per-account portal notifications and optional durable SMTP outbox.

Passwords live in the service environment, never settings, source or backups.
The production SMTP sender refuses to run in tests. Test senders are injected.
"""
import json
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlsplit
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request
from . import security, store
from .model import ValidationError
from .references import actor, stamp

bp = Blueprint('notifications', __name__)
DEFAULTS = dict(enabled=False, host='', port=587, security='starttls', username='',
                sender='', base_url='', password_env='CIRRUS_SMTP_PASSWORD')


def config(db):
    value = db.execute("SELECT value FROM settings WHERE key='workflow_smtp'").fetchone()
    return dict(DEFAULTS, **(json.loads(value[0]) if value else {}))


def valid_email(value):
    return len(value) <= 254 and bool(re.fullmatch(r'[^\s<>@,;:]+@[^\s<>@,;:]+\.[^\s<>@,;:]+', value))


def create(db, user_id, quote_id, event_key, kind, body, message_id=None):
    user = db.execute('SELECT active FROM users WHERE id=?', (user_id,)).fetchone()
    if not user or not user['active']:
        return
    cursor = db.execute('''INSERT OR IGNORE INTO portal_notifications(user_id,quote_id,event_key,kind,body,at,message_id)
        VALUES (?,?,?,?,?,?,?)''', (user_id, quote_id, event_key, kind, body[:20000], stamp(), message_id))
    if not cursor.rowcount:
        return


def visible(db, user_id,records=None):
    # Check current access on every poll/list/open, rather than trusting historical assignments.
    saved=db.execute('SELECT * FROM portal_notifications WHERE user_id=? ORDER BY id DESC',(user_id,)).fetchall()
    if not saved:return []
    records = {r['id']: r for r in (store.records(db) if records is None else records)}
    return [dict(n, title=records[n['quote_id']]['data']['title'],
                 customer=records[n['quote_id']]['data'].get('customer', ''),
                 reference=records[n['quote_id']]['data'].get('number', ''))
            for n in saved
            if n['quote_id'] in records and (n['kind'] not in ('Mention','Discussion') or security.can_read(db,records[n['quote_id']],write=True))]


@bp.get('/notifications')
def page():
    with store.connect(current_app.config['DATA_DIR']) as db:
        rows = visible(db, actor())
    if request.args.get('unread') == 'yes':
        rows = [n for n in rows if not n['read_at']]
    return render_template('notifications.html', notifications=rows)


@bp.get('/notifications/poll')
def poll():
    from .approvals import my_work
    with store.connect(current_app.config['DATA_DIR']) as db:
        rows = visible(db, actor()); work = my_work(db, actor())
    return dict(unread=sum(not n['read_at'] for n in rows), pending=len(work['pending']), recent=rows[:10])


@bp.post('/notifications/read')
def read():
    with store.connect(current_app.config['DATA_DIR']) as db:
        rows = visible(db, actor()); ids = {str(n['id']) for n in rows}
        chosen = ids if request.form.get('all') == 'yes' else {request.form.get('id', '')} & ids
        for ident in chosen:
            db.execute('UPDATE portal_notifications SET read_at=COALESCE(read_at,?) WHERE id=? AND user_id=?', (stamp(), ident, actor()))
    if request.headers.get('X-Requested-With') == 'fetch':
        return dict(ok=True)
    return redirect('/notifications')


@bp.get('/notifications/<int:ident>/open')
def open_notification(ident):
    with store.connect(current_app.config['DATA_DIR']) as db:
        row = db.execute('SELECT * FROM portal_notifications WHERE id=? AND user_id=?', (ident, actor())).fetchone()
        if not row:
            abort(404)
        security.require_id(db, row['quote_id'],write=row['kind'] in ('Mention','Discussion'))
        target = '/quotes/' + row['quote_id'] + '/approval'
        if row['message_id']:
            target += '#message-' + str(row['message_id'])
    return redirect(target)


def send_smtp(cfg, address, subject, text, html=None, message_id=None):
    # Never send real messages from a development/test run, even if its temporary
    # database was configured with enabled SMTP. Tests inject a memory sender.
    if current_app.testing or os.environ.get('CIRRUS_DISABLE_EMAIL') == '1':
        raise RuntimeError('Email delivery is disabled in this environment.')
    message = EmailMessage()
    message['From'] = cfg['sender']; message['To'] = address
    message['Subject'] = subject
    if message_id:message['Message-ID'] = message_id
    message.set_content(text)
    if html:message.add_alternative(html, subtype='html')
    context = ssl.create_default_context() if cfg['security']!='none' else None
    smtp_class = smtplib.SMTP_SSL if cfg['security'] == 'ssl' else smtplib.SMTP
    kwargs = dict(host=cfg['host'], port=cfg['port'], timeout=15)
    if cfg['security'] == 'ssl':
        kwargs['context'] = context
    with smtp_class(**kwargs) as smtp:
        if cfg['security'] == 'starttls':
            smtp.starttls(context=context)
        if cfg['username']:
            password = os.environ.get(cfg['password_env'], '')
            if not password:
                raise RuntimeError('SMTP password environment variable is not configured for the Workplace service.')
            smtp.login(cfg['username'], password)
        smtp.send_message(message)


def process_email(app, sender=None):
    from . import approval_emails
    sender = sender or send_smtp
    with store.connect(app.config['DATA_DIR']) as db:
        db.execute('BEGIN IMMEDIATE'); cfg = config(db)
        if not cfg['enabled']:return False
        job = db.execute("""SELECT e.*,n.quote_id,n.user_id,n.kind,r.data
            FROM notification_emails e JOIN portal_notifications n ON n.id=e.notification_id
            LEFT JOIN records r ON r.id=n.quote_id
            WHERE e.status='pending' ORDER BY n.id LIMIT 1""").fetchone()
        if not job:return False
        job = dict(job)
        if job['data'] is None:
            db.execute("UPDATE notification_emails SET status='cancelled',error='Quotation no longer exists.' WHERE notification_id=?",(job['notification_id'],))
            return True
        user = db.execute('SELECT * FROM users WHERE id=? AND active=1', (job['user_id'],)).fetchone()
        pref = db.execute('SELECT * FROM account_emails WHERE user_id=? AND enabled=1', (job['user_id'],)).fetchone()
        record = dict(id=job['quote_id'], kind='quote', data=json.loads(job['data']))
        sent=db.execute('SELECT * FROM sent_email_recipients WHERE notification_id=?',(job['notification_id'],)).fetchone()
        if sent:
            import sqlite3
            payload=None
            if user and pref and security.can_read(db,record,user=dict(user)) and valid_email(pref['email']):
                try:
                    db.execute('UPDATE sent_email_recipients SET address_key=? WHERE notification_id=?',(pref['email'].casefold(),job['notification_id']))
                    job['address']=pref['email'];payload=json.loads(sent['payload'])
                    db.execute("UPDATE notification_emails SET address=?,status='running',attempts=attempts+1,at=? WHERE notification_id=?",(job['address'],stamp(),job['notification_id']))
                except sqlite3.IntegrityError:payload=None
            if payload is None:db.execute("UPDATE notification_emails SET status='cancelled',error='Recipient unavailable, unauthorized or duplicate.' WHERE notification_id=?",(job['notification_id'],))
        elif db.execute('SELECT 1 FROM reminder_email_recipients WHERE notification_id=?',(job['notification_id'],)).fetchone():
            from .v21 import claim_reminder
            payload=claim_reminder(db,job,record,user,pref)
        else:payload=approval_emails.claim(db,job,record,user,pref)
        if payload is None:return True
    try:
        with app.app_context():
            message=approval_emails.render(payload,cfg,job['address'])
            sender(cfg,job['address'],message['subject'],message['text'],html=message['html'],message_id=message['message_id'])
        status, error = 'sent', ''
    except Exception:
        # SMTP server errors may echo authentication strings; do not persist them.
        status, error = 'failed', 'SMTP delivery failed. Check service SMTP configuration, credentials and connectivity, then Retry. Delivery may be uncertain if the server disconnected.'
    with store.connect(app.config['DATA_DIR']) as db:
        db.execute("UPDATE notification_emails SET status=?,error=?,at=? WHERE notification_id=? AND status='running'", (status, error, stamp(), job['notification_id']))
    return True


@bp.route('/administration/workflow', methods=['GET', 'POST'])
def settings():
    from .approvals import reviewers_valid,defaults as load_defaults,selection_from_form
    security.require_admin(); error = None
    with store.connect(current_app.config['DATA_DIR']) as db:
        cfg = config(db)
        defaults = load_defaults(db)
        if request.method == 'POST':
            try:
                db.execute('BEGIN IMMEDIATE')
                action = request.form.get('action', '')
                if action == 'defaults':
                    defaults = selection_from_form(request.form,defaults)
                    reviewers_valid(db, defaults,allow_empty=True)
                    db.execute("INSERT INTO settings VALUES ('approval_defaults',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(defaults),))
                elif action == 'smtp':
                    cfg = {k: request.form.get(k, '').strip() for k in DEFAULTS if k not in ('enabled', 'port')}
                    cfg.update(enabled=request.form.get('enabled') == 'yes', port=int(request.form.get('port', '587')))
                    if not 1 <= cfg['port'] <= 65535 or cfg['security'] not in ('starttls', 'ssl', 'none'):
                        raise ValidationError('Use a valid SMTP port and security mode.')
                    if any('\r' in v or '\n' in v or len(v) > 500 for v in cfg.values() if isinstance(v, str)):
                        raise ValidationError('SMTP settings contain invalid text.')
                    if not re.fullmatch('[A-Z][A-Z0-9_]{0,79}', cfg['password_env']):
                        raise ValidationError('Use an uppercase password environment variable name.')
                    if cfg['enabled']:
                        parsed = urlsplit(cfg['base_url'])
                        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
                            raise ValidationError('Set the explicit portal origin, such as https://workplace.cirrus.local, without credentials, query or a path.')
                        if not cfg['host'] or not valid_email(cfg['sender']):
                            raise ValidationError('Set the SMTP host and a valid From email address.')
                    db.execute("INSERT INTO settings VALUES ('workflow_smtp',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(cfg),))
                elif action == 'recipient':
                    user = request.form.get('user_id', ''); address = request.form.get('email', '').strip()
                    if not db.execute('SELECT 1 FROM users WHERE id=? AND NOT EXISTS (SELECT 1 FROM account_deletions WHERE user_id=users.id)', (user,)).fetchone() or address and not valid_email(address):
                        raise ValidationError('Select an existing account and enter a valid email address.')
                    db.execute('INSERT INTO account_emails VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET email=excluded.email,enabled=excluded.enabled', (user, address, int(bool(address) and request.form.get('recipient_enabled') == 'yes')))
                elif action == 'retry':
                    db.execute("UPDATE notification_emails SET status='pending',error='' WHERE notification_id=? AND status='failed'", (request.form.get('notification_id'),))
                else:
                    raise ValidationError('Choose a valid settings action.')
                flash('Workflow settings updated. Portal notifications remain independent of email.'); return redirect(request.path)
            except (ValueError, ValidationError) as exc:
                db.rollback(); error = str(exc)
        users = [dict(r) for r in db.execute('SELECT id,username,role,active FROM users WHERE NOT EXISTS (SELECT 1 FROM account_deletions WHERE user_id=users.id) ORDER BY username')]
        recipients = {r['user_id']: dict(r) for r in db.execute('SELECT * FROM account_emails')}
        failures = [dict(r) for r in db.execute("SELECT e.*,n.kind,u.username FROM notification_emails e JOIN portal_notifications n ON n.id=e.notification_id JOIN users u ON u.id=n.user_id WHERE e.status='failed' ORDER BY e.at DESC LIMIT 100")]
    return render_template('workflow_settings.html', smtp=cfg, defaults=defaults, users=users, recipients=recipients, failures=failures, approver_choices=[u for u in users if u['active'] and u['role']!='Viewer'],selected_approvers=defaults,approvers_version=0,error=error)


@bp.post('/preferences')
def preferences():
    theme = request.form.get('theme', 'system'); collapsed = int(request.form.get('collapsed') == 'yes')
    if theme not in ('light', 'dark', 'system'):
        raise ValidationError('Choose Light, Dark or System.')
    with store.connect(current_app.config['DATA_DIR']) as db:
        db.execute('INSERT INTO user_preferences VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET theme=excluded.theme,collapsed=excluded.collapsed', (actor(), theme, collapsed))
    return dict(ok=True)
