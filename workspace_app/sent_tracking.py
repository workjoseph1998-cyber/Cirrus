"""Immutable, revision-bound sent records and internal-only milestone email."""
import hashlib,json,re
from uuid import uuid4
from flask import abort
from . import security,approvals as flow,notifications
from .references import stamp,actor,key
from .model import ValidationError


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS quotation_sent_events(id TEXT PRIMARY KEY,quote_id TEXT NOT NULL,
        round_id TEXT NOT NULL UNIQUE,reference_key TEXT NOT NULL,revision INTEGER NOT NULL,
        actor TEXT,at TEXT NOT NULL,recipient_name TEXT NOT NULL,recipient_email TEXT NOT NULL,
        method TEXT NOT NULL,notes TEXT NOT NULL,pdf_hash TEXT NOT NULL,snapshot TEXT NOT NULL,legacy INTEGER NOT NULL DEFAULT 0)''')
    db.execute('CREATE INDEX IF NOT EXISTS quotation_sent_family ON quotation_sent_events(reference_key,at)')
    db.execute('''CREATE TABLE IF NOT EXISTS sent_email_recipients(notification_id INTEGER PRIMARY KEY REFERENCES notification_emails(notification_id),
        event_id TEXT NOT NULL REFERENCES quotation_sent_events(id),address_key TEXT NOT NULL,payload TEXT NOT NULL,
        UNIQUE(event_id,address_key))''')
    db.execute("CREATE TRIGGER IF NOT EXISTS sent_event_immutable BEFORE UPDATE ON quotation_sent_events BEGIN SELECT RAISE(ABORT,'Sent records are immutable'); END")
    for r in db.execute('''SELECT r.*,a.data,a.pdf_hash FROM approval_rounds r JOIN approval_artifacts a ON a.round_id=r.id
        WHERE r.sent_at IS NOT NULL''').fetchall():
        q=json.loads(r['data'])
        db.execute('''INSERT OR IGNORE INTO quotation_sent_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1)''',
          ('legacy-'+r['id'],r['quote_id'],r['id'],key(q['number']),q['revision'],r['sent_by'],r['sent_at'],'','','',
           'Legacy sent flag: recipient and sending method were not recorded.',r['pdf_hash'] or '',r['data']))


def creator(db,ident):
    row=db.execute('SELECT created_by FROM document_management WHERE record_id=?',(ident,)).fetchone()
    if row and row[0]:return row[0]
    row=db.execute('SELECT actor FROM approval_versions WHERE quote_id=? ORDER BY version LIMIT 1',(ident,)).fetchone()
    return row[0] if row else None


def record(db,quotation,round_id,version,digest,values):
    if not flow.private_access(db,quotation):abort(403)
    from .v21 import pre_send
    failed=[label for label, passed in pre_send(db,quotation) if not passed]
    if failed:raise ValidationError('Pre-send verification: '+', '.join(failed))
    saved=flow.require_current(db,quotation['id'],version,digest);round_=flow.current_round(db,quotation['id'])
    if not round_ or round_['id']!=round_id:raise ValidationError('Review the latest approved version before recording sending.')
    name=values.get('recipient_name','').strip();email=values.get('recipient_email','').strip();method=values.get('method','');notes=values.get('sent_notes','').strip()
    if method not in ('Email','WhatsApp','Other'):raise ValidationError('Choose Email, WhatsApp or Other.')
    if not (name or email) or len(name)>250 or len(notes)>2000 or (email and not notifications.valid_email(email)) or (method=='Email' and not email):
        raise ValidationError('Enter a recipient name/email (Email requires a valid email); notes allow 2,000 characters.')
    existing=db.execute('SELECT * FROM quotation_sent_events WHERE round_id=?',(round_id,)).fetchone()
    if existing:
        if (name,email,method,notes)!=(existing['recipient_name'],existing['recipient_email'],existing['method'],existing['notes']):
            raise ValidationError('Sending is already recorded for this approved version. Its history cannot be overwritten.')
        return dict(existing)
    if round_['status']!='Approved by all':raise ValidationError('Only the currently fully approved version can be marked as sent.')
    artifact=db.execute('SELECT * FROM approval_artifacts WHERE round_id=?',(round_id,)).fetchone()
    if not artifact or not artifact['pdf']:raise ValidationError('Wait for the approved customer PDF to be captured, or Retry its generation.')
    pdf_hash=hashlib.sha256(artifact['pdf']).hexdigest()
    if artifact['pdf_hash'] and pdf_hash!=artifact['pdf_hash']:raise ValidationError('Approved PDF integrity check failed.')
    ident=uuid4().hex;at=stamp()
    db.execute('INSERT INTO quotation_sent_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0)',
       (ident,quotation['id'],round_id,key(quotation['data']['number']),quotation['data']['revision'],actor(),at,name,email,method,notes,pdf_hash,artifact['data']))
    db.execute("UPDATE approval_rounds SET status='Sent to client',sent_by=?,sent_at=? WHERE id=?",(actor(),at,round_id))
    db.execute('UPDATE reference_usage SET draft_only=0,ever_sent=1 WHERE reference_key=?',(key(quotation['data']['number']),))
    eid=flow.event(db,quotation['id'],saved['version'],'sent','Marked this quotation as sent to the client; delivery is not verified.',round_id)
    recipients={creator(db,quotation['id']),*[r['user_id'] for r in flow.decisions(db,round_id)]}-{None,''}
    event_key='sent:'+str(eid)
    flow.notify(db,quotation['id'],recipients,'Sent to Client','A staff member marked this saved quotation as sent to the client. Delivery is not verified.',event_key)
    cfg=notifications.config(db)
    if cfg['enabled']:
        from .approval_emails import payload_for_round
        payload=payload_for_round(db,round_id,'sent')
        user=db.execute('SELECT username FROM users WHERE id=?',(actor(),)).fetchone()
        payload.update(sent_by=user[0] if user else 'Former account',sent_at=at,recipient_name=name,recipient_email=email,method=method,status='Sent to client')
        for uid in sorted(recipients):
            address=db.execute('SELECT e.email FROM account_emails e JOIN users u ON u.id=e.user_id WHERE e.user_id=? AND e.enabled=1 AND u.active=1',(uid,)).fetchone()
            if not address or not notifications.valid_email(address[0]):continue
            address_key=address[0].strip().casefold()
            if db.execute('SELECT 1 FROM sent_email_recipients WHERE event_id=? AND address_key=?',(ident,address_key)).fetchone():continue
            notification=db.execute('SELECT id FROM portal_notifications WHERE user_id=? AND event_key=?',(uid,event_key)).fetchone()
            if not notification:continue
            db.execute("INSERT INTO notification_emails(notification_id,address,status) VALUES (?,?,'pending')",(notification[0],address[0]))
            db.execute('INSERT INTO sent_email_recipients VALUES (?,?,?,?)',(notification[0],ident,address_key,json.dumps(payload)))
    return dict(db.execute('SELECT * FROM quotation_sent_events WHERE id=?',(ident,)).fetchone())


def history(db,ident):
    return [dict(r) for r in db.execute('''SELECT s.*,u.username FROM quotation_sent_events s LEFT JOIN users u ON u.id=s.actor
        WHERE quote_id=? ORDER BY at DESC,id DESC''',(ident,))]


def family_dates(db,allowed):
    values={}
    for row in db.execute('SELECT quote_id,reference_key,at FROM quotation_sent_events ORDER BY at'):
        if row['quote_id'] in allowed:values[row['reference_key']]=row['at']
    return values
