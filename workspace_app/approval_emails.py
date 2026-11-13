"""Two email milestones per saved approval round; public metadata only.

Portal notifications keep their existing behavior. Durable batches and per-address
uniqueness are committed with the approval transaction; SMTP stays in the worker.
"""
import hashlib
import json
import sqlite3
from datetime import datetime
from urllib.parse import quote, urlsplit
from flask import current_app
from .references import stamp

STAGES=('submission','complete')


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS approval_email_batches(
        round_id TEXT NOT NULL REFERENCES approval_rounds(id),stage TEXT NOT NULL,
        data TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(round_id,stage),
        CHECK(stage IN ('submission','complete')))''')
    db.execute('''CREATE TABLE IF NOT EXISTS approval_email_recipients(
        notification_id INTEGER PRIMARY KEY REFERENCES notification_emails(notification_id),
        round_id TEXT NOT NULL,stage TEXT NOT NULL,address_key TEXT NOT NULL,
        FOREIGN KEY(round_id,stage) REFERENCES approval_email_batches(round_id,stage),
        UNIQUE(round_id,stage,address_key))''')
    db.execute('''CREATE TRIGGER IF NOT EXISTS approval_email_batch_immutable
        BEFORE UPDATE ON approval_email_batches BEGIN
        SELECT RAISE(ABORT,'Approval email snapshots are immutable'); END''')
    # Retain delivery history, but never replay old discussion/decision emails.
    db.execute("""UPDATE notification_emails SET status='cancelled',
        error='Previous email policy retired; intermediate updates remain in the portal.'
        WHERE status IN ('pending','failed','running') AND NOT EXISTS
        (SELECT 1 FROM approval_email_recipients r WHERE r.notification_id=notification_emails.notification_id)""")


def payload_for_round(db,round_id,stage):
    from . import approvals as flow
    round_=db.execute('SELECT * FROM approval_rounds WHERE id=?',(round_id,)).fetchone()
    saved=db.execute('SELECT data FROM approval_versions WHERE quote_id=? AND version=?',
                     (round_['quote_id'],round_['version'])).fetchone()
    q=json.loads(saved['data']);reviews=flow.decisions(db,round_id)
    submitter=db.execute('SELECT username FROM users WHERE id=?',(round_['submitter'],)).fetchone()
    people=[]
    for r in reviews:
        state=r['decision'] if r['decision']!='Pending' else 'Pending' if flow.actionable(round_,r) else 'Waiting'
        people.append(dict(name=r['username'],responsibility=flow.PHASES[r['phase']],status=state,decided_at=r['decided_at']))
    # Deliberately omit quotation rows, costs, margins, notes and reviewer comments.
    payload=dict(quote_id=round_['quote_id'],round_id=round_id,stage=stage,
        client=q.get('customer',''),reference=q.get('number',''),title=q.get('title',''),
        revision=q.get('revision',''),version=round_['version'],submitter=submitter[0] if submitter else 'Former account',
        submitted_at=round_['at'],completed_at=round_['completed_at'],status=round_['status'],approvers=people)
    return payload


def queue(db,round_id,stage,event_key):
    from . import notifications
    if stage not in STAGES:raise ValueError('Unknown approval email milestone.')
    round_=db.execute('SELECT * FROM approval_rounds WHERE id=?',(round_id,)).fetchone()
    from . import approvals as flow
    reviews=flow.decisions(db,round_id);payload=payload_for_round(db,round_id,stage)
    inserted=db.execute('INSERT OR IGNORE INTO approval_email_batches VALUES (?,?,?,?)',
                        (round_id,stage,json.dumps(payload,ensure_ascii=False),stamp()))
    if not inserted.rowcount:return
    if not notifications.config(db)['enabled']:return
    recipients=[r['user_id'] for r in reviews]
    if stage=='complete':recipients.append(round_['submitter'])
    for user_id in dict.fromkeys(recipients):
        address=db.execute('''SELECT e.email FROM account_emails e JOIN users u ON u.id=e.user_id
            WHERE e.user_id=? AND e.enabled=1 AND u.active=1''',(user_id,)).fetchone()
        if not address or not notifications.valid_email(address[0]):continue
        normalized=address[0].strip().casefold()
        if db.execute('SELECT 1 FROM approval_email_recipients WHERE round_id=? AND stage=? AND address_key=?',
                      (round_id,stage,normalized)).fetchone():continue
        notification=db.execute('SELECT id FROM portal_notifications WHERE user_id=? AND event_key=?',
                                (user_id,event_key)).fetchone()
        if not notification:continue
        db.execute("INSERT INTO notification_emails(notification_id,address,status) VALUES (?,?,'pending')",
                   (notification[0],address[0].strip()))
        db.execute('INSERT INTO approval_email_recipients VALUES (?,?,?,?)',
                   (notification[0],round_id,stage,normalized))


def claim(db,job,record,user,pref):
    """Revalidate live access and cancel superseded/outdated requests before SMTP."""
    from . import approvals as flow,notifications,security
    metadata=db.execute('''SELECT r.*,b.data FROM approval_email_recipients r
        JOIN approval_email_batches b ON b.round_id=r.round_id AND b.stage=r.stage
        WHERE r.notification_id=?''',(job['notification_id'],)).fetchone()
    def cancel(reason):
        db.execute("UPDATE notification_emails SET status='cancelled',error=? WHERE notification_id=?",
                   (reason,job['notification_id']))
        return None
    if not metadata:return cancel('Intermediate or legacy email suppressed; updates remain in the portal.')
    if not user or not pref or not notifications.valid_email(pref['email']) or not security.can_read(db,record,user=dict(user)):
        return cancel('Recipient is disabled, lacks a valid email address or is no longer authorized.')
    round_=db.execute('SELECT * FROM approval_rounds WHERE id=? AND quote_id=?',(metadata['round_id'],record['id'])).fetchone()
    version=db.execute('SELECT hash FROM approval_versions WHERE quote_id=? AND version=?',(record['id'],round_['version'])).fetchone() if round_ else None
    if not round_ or not version or round_['hash']!=version['hash']:
        return cancel('The saved approval round is unavailable.')
    reviews=flow.decisions(db,round_['id'])
    if metadata['stage']=='submission':
        current=flow.current_round(db,record['id']);latest=flow.current_version(db,record['id'])
        if not current or current['id']!=round_['id'] or not latest or latest['hash']!=round_['hash']:
            return cancel('This submission was superseded; review the current quotation in the portal.')
        mine=next((r for r in reviews if r['user_id']==job['user_id']),None)
        if round_['status'] not in flow.ACTIVE or not mine or mine['decision']!='Pending':
            return cancel('This submission no longer requires this recipient to review it.')
    # Completion belongs to the immutable approved version, even if a later edit
    # already started another round. The email and link identify that saved round.
    elif round_['status'] not in ('Approved by all','Sent to client') or not all(r['decision']=='Approved' for r in reviews):
        return cancel('This round is no longer fully approved.')
    # Keep existing administrator address corrections usable for failed deliveries,
    # while atomically preventing two accounts from converging on one recipient.
    address=pref['email'].strip();key=address.casefold()
    try:db.execute('UPDATE approval_email_recipients SET address_key=? WHERE notification_id=?',(key,job['notification_id']))
    except sqlite3.IntegrityError:return cancel('Duplicate recipient address for this approval round.')
    job['address']=address
    db.execute("UPDATE notification_emails SET address=?,status='running',attempts=attempts+1,at=? WHERE notification_id=?",
               (address,stamp(),job['notification_id']))
    return json.loads(metadata['data'])


def format_time(value):
    if not value:return 'Not yet recorded'
    from .statistics import zone
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        from datetime import timezone
        parsed=parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone()).strftime('%d %b %Y, %H:%M %Z')


def render(payload,cfg,address):
    base=cfg['base_url'].rstrip('/');parsed=urlsplit(base)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise ValueError('Configure an explicit portal origin for email links.')
    link=base+'/quotes/'+quote(payload['quote_id'],safe='')+'/approval#approval-round-'+quote(payload['round_id'],safe='')
    sent=payload['stage']=='sent';complete=payload['stage']=='complete';heading='Quotation Fully Approved' if complete else 'Submission of New Quotation'
    if sent:heading='Quotation Sent to Client'
    if payload['stage']=='reminder':heading='Pending Approval Reminder'
    client=payload['client'] or 'Client not specified';reference=payload['reference'] or 'Reference not specified'
    subject=('Sent to Client' if sent else 'Fully Approved' if complete else 'Review Required')+' | '+client+' | '+reference
    subject=' '.join(subject.split())[:250]
    context=dict(email=payload,heading=heading,color='#187546' if complete else '#16395c',
                 approval_url=link,format_time=format_time,complete=complete,sent=sent)
    html=current_app.jinja_env.get_template('email/quotation_approval.html').render(**context)
    text='\n'.join(['Cirrus Workplace',heading,'',
        'Client: '+client,'Quotation reference: '+reference,'Quotation title: '+payload['title'],
        'Submitted by: '+payload['submitter'],'Submitted: '+format_time(payload['submitted_at']),
        *([payload['sent_by']+' marked this quotation as sent to the client. Delivery is not verified.', 'Marked sent: '+format_time(payload['sent_at']),'Recipient: '+payload['recipient_name']+' '+payload['recipient_email'],'Method: '+payload['method']] if sent else []),
        'Revision: '+str(payload['revision'])+' · Saved version '+str(payload['version']),
        ('Approval status: ' if complete or sent else 'Approval status at submission: ')+payload['status'],
        *(['Fully approved: '+format_time(payload['completed_at'])] if complete else []),'','Selected approvers:',
        *[r['name']+' | '+r['responsibility']+' | '+r['status']+' | '+format_time(r['decided_at']) for r in payload['approvers']],
        '','Review Quotation: '+link,'',
        'Sign in with your normal Cirrus Workplace account. Internal network or VPN access may be required.',
        *(['Approval applies only to the saved version shown above; later edits require a new review.'] if complete else []),
        'This notification does not send the quotation to the customer.'])
    identity=hashlib.sha256((payload['round_id']+':'+payload['stage']+':'+address.casefold()).encode()).hexdigest()
    return dict(subject=subject,text=text,html=html,message_id='<'+identity+'@notifications.cirrus-workplace.local>')
