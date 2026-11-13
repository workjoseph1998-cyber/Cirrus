"""Saved-content approval rounds, independent decisions and immutable evidence.

All mutations are called inside the application's SQLite write transaction.
Business outcomes and approval state deliberately use different tables.
"""
import copy
import json
from uuid import uuid4

from flask import abort
from . import security
from .commercial import fingerprint
from .model import ValidationError
from .references import actor, stamp

SLOTS = {'operations_1': 'Operations · technical review 1',
         'operations_2': 'Operations · technical review 2',
         'commercial': 'Commercial · terms and presentation'}
ACTIVE = ('Awaiting operations approval', 'Awaiting commercial approval')
PHASES = {'operations': 'Operations · technical scope', 'commercial': 'Commercial · terms and presentation'}


def normalize_selection(value):
    """Accept V12 slot mappings on old callers; persist an ordered V13 list."""
    if isinstance(value, dict):
        if set(value)-set(SLOTS):raise ValidationError('Unknown approver assignment fields.')
        value=[dict(user_id=value[slot],phase='commercial' if slot=='commercial' else 'operations')
               for slot in SLOTS if value.get(slot)]
    if not isinstance(value,list) or len(value)>100:
        raise ValidationError('Select up to 100 distinct approvers.')
    result=[];seen=set()
    for item in value:
        if isinstance(item,str):item=dict(user_id=item,phase='operations')
        if not isinstance(item,dict) or set(item)-{'user_id','phase'}:
            raise ValidationError('Invalid approver selection.')
        ident=item.get('user_id','');phase=item.get('phase','operations')
        if not isinstance(ident,str) or not ident or len(ident)>100 or phase not in PHASES:
            raise ValidationError('Choose an approver for every row, or remove the empty row.')
        if ident in seen:raise ValidationError('An approver can only be selected once per quotation.')
        seen.add(ident);result.append(dict(user_id=ident,phase=phase))
    return result


def defaults(db):
    row=db.execute("SELECT value FROM settings WHERE key='approval_defaults'").fetchone()
    return normalize_selection(json.loads(row[0])) if row else []


def variable_schema(db):
    columns={r[1] for r in db.execute('PRAGMA table_info(approval_reviews)')}
    if 'phase' not in columns:
        db.execute("ALTER TABLE approval_reviews ADD COLUMN phase TEXT NOT NULL DEFAULT 'operations'")
        db.execute("ALTER TABLE approval_reviews ADD COLUMN position INTEGER NOT NULL DEFAULT 0")
        db.execute("UPDATE approval_reviews SET phase=CASE WHEN slot='commercial' THEN 'commercial' ELSE 'operations' END,position=CASE slot WHEN 'operations_1' THEN 0 WHEN 'operations_2' THEN 1 ELSE 2 END")
    db.execute('''CREATE TABLE IF NOT EXISTS quotation_approvers(quote_id TEXT PRIMARY KEY,
        version INTEGER NOT NULL,data TEXT NOT NULL,at TEXT NOT NULL,actor TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS approval_preparations(id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,customer_id TEXT NOT NULL,reference TEXT NOT NULL,data TEXT NOT NULL,at TEXT NOT NULL)''')
    for row in db.execute("SELECT id FROM records WHERE kind='quote'").fetchall():
        initialize_selection(db,row['id'])


def initialize_selection(db,ident,source=None):
    if db.execute('SELECT 1 FROM quotation_approvers WHERE quote_id=?',(ident,)).fetchone():return
    last=last_round(db,ident)
    inherited=db.execute('SELECT data FROM quotation_approvers WHERE quote_id=?',(source,)).fetchone() if source else None
    selected=[dict(user_id=r['user_id'],phase=r['phase']) for r in decisions(db,last['id'])] if last else json.loads(inherited[0]) if inherited else defaults(db)
    db.execute('INSERT INTO quotation_approvers VALUES (?,1,?,?,?)',(ident,json.dumps(selected),stamp(),actor()))


def selection(db,ident):
    saved=db.execute('SELECT * FROM quotation_approvers WHERE quote_id=?',(ident,)).fetchone()
    return dict(saved,data=json.loads(saved['data'])) if saved else dict(version=0,data=defaults(db))


def selection_from_form(form,fallback):
    if 'approvers' in form:
        try:return normalize_selection(json.loads(form['approvers']))
        except (ValueError,TypeError) as exc:raise ValidationError('Invalid approvers: '+str(exc)) from exc
    if any(slot in form for slot in SLOTS):return normalize_selection({slot:form.get(slot,'') for slot in SLOTS})
    return normalize_selection(fallback)


def save_selection(db,record,selected,expected=None,reason='Approvers changed'):
    if not private_access(db,record):abort(403)
    current=selection(db,record['id']);selected=normalize_selection(selected)
    if expected is not None and str(expected)!=str(current['version']):
        raise ValidationError('Approvers changed in another session. Reload and review the current selection before saving.')
    if current['data']==selected:return False
    reviewers_valid(db,selected,allow_empty=True)
    old_round=current_round(db,record['id']);old_people=participants(db,record['id']) if old_round else {}
    db.execute('''INSERT INTO quotation_approvers VALUES (?,?,?,?,?) ON CONFLICT(quote_id)
        DO UPDATE SET version=excluded.version,data=excluded.data,at=excluded.at,actor=excluded.actor''',
        (record['id'],current['version']+1,json.dumps(selected),stamp(),actor()))
    if old_round:db.execute('UPDATE approval_rounds SET superseded=1 WHERE id=?',(old_round['id'],))
    version=current_version(db,record['id'])
    eid=event(db,record['id'],version['version'],'approvers',reason+('; resubmission required.' if last_round(db,record['id']) else '.'),
        details=[dict(field='approvers',before=current['data'],after=selected)])
    if old_round:
        notify(db,record['id'],old_people,'Resubmission required','Approvers changed. Previous decisions are retained; the quotation must be resubmitted.','approvers:'+str(eid))
    return True


def schema(db):
    statements = [
        '''CREATE TABLE IF NOT EXISTS approval_versions(
        quote_id TEXT NOT NULL, version INTEGER NOT NULL, hash TEXT NOT NULL,
        data TEXT NOT NULL, actor TEXT, at TEXT NOT NULL, changes TEXT NOT NULL,
        PRIMARY KEY(quote_id,version))''',
        '''CREATE TABLE IF NOT EXISTS approval_rounds(
        id TEXT PRIMARY KEY, quote_id TEXT NOT NULL, version INTEGER NOT NULL,
        hash TEXT NOT NULL, status TEXT NOT NULL, submitter TEXT NOT NULL,
        at TEXT NOT NULL, superseded INTEGER NOT NULL DEFAULT 0,
        reapproval INTEGER NOT NULL DEFAULT 0, completed_at TEXT, sent_at TEXT, sent_by TEXT)''',
        '''CREATE UNIQUE INDEX IF NOT EXISTS current_approval_round
        ON approval_rounds(quote_id) WHERE superseded=0''',
        '''CREATE TABLE IF NOT EXISTS approval_reviews(
        round_id TEXT NOT NULL REFERENCES approval_rounds(id), slot TEXT NOT NULL,
        user_id TEXT NOT NULL REFERENCES users(id), decision TEXT NOT NULL DEFAULT 'Pending',
        comment TEXT NOT NULL DEFAULT '', decided_at TEXT,
        PRIMARY KEY(round_id,slot), UNIQUE(round_id,user_id))''',
        '''CREATE TABLE IF NOT EXISTS approval_grants(
        quote_id TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id),
        PRIMARY KEY(quote_id,user_id))''',
        '''CREATE TABLE IF NOT EXISTS approval_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, quote_id TEXT NOT NULL, round_id TEXT,
        version INTEGER NOT NULL, actor TEXT, at TEXT NOT NULL, kind TEXT NOT NULL,
        body TEXT NOT NULL, details TEXT NOT NULL DEFAULT '[]')''',
        '''CREATE TABLE IF NOT EXISTS approval_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT, quote_id TEXT NOT NULL, parent_id INTEGER,
        author TEXT NOT NULL, at TEXT NOT NULL, body TEXT NOT NULL)''',
        '''CREATE INDEX IF NOT EXISTS approval_message_quote ON approval_messages(quote_id,id)''',
        '''CREATE TABLE IF NOT EXISTS approval_reads(
        quote_id TEXT NOT NULL,user_id TEXT NOT NULL,last_id INTEGER NOT NULL,
        PRIMARY KEY(quote_id,user_id))''',
        '''CREATE TABLE IF NOT EXISTS approval_artifacts(
        round_id TEXT PRIMARY KEY REFERENCES approval_rounds(id), data TEXT NOT NULL,
        pdf BLOB,pdf_hash TEXT,status TEXT NOT NULL,error TEXT NOT NULL DEFAULT '',
        created TEXT NOT NULL, completed TEXT)''',
        '''CREATE TABLE IF NOT EXISTS user_preferences(
        user_id TEXT PRIMARY KEY,theme TEXT NOT NULL DEFAULT 'system',collapsed INTEGER NOT NULL DEFAULT 0)''',
        '''CREATE TABLE IF NOT EXISTS portal_notifications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL,quote_id TEXT NOT NULL,
        event_key TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,at TEXT NOT NULL,
        read_at TEXT,message_id INTEGER,UNIQUE(user_id,event_key))''',
        '''CREATE INDEX IF NOT EXISTS notification_user ON portal_notifications(user_id,id)''',
        '''CREATE TABLE IF NOT EXISTS notification_emails(
        notification_id INTEGER PRIMARY KEY REFERENCES portal_notifications(id),
        address TEXT NOT NULL,status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
        error TEXT NOT NULL DEFAULT '',at TEXT)''',
        '''CREATE TABLE IF NOT EXISTS account_emails(
        user_id TEXT PRIMARY KEY REFERENCES users(id),email TEXT NOT NULL,enabled INTEGER NOT NULL)'''
    ]
    for sql in statements:
        db.execute(sql)
    if 'request_key' not in {r[1] for r in db.execute('PRAGMA table_info(approval_messages)')}:
        db.execute("ALTER TABLE approval_messages ADD COLUMN request_key TEXT NOT NULL DEFAULT ''")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS approval_message_request ON approval_messages(quote_id,author,request_key) WHERE request_key<>''")
    if 'approved_hash' not in {r[1] for r in db.execute('PRAGMA table_info(pdf_file_owners)')}:
        db.execute("ALTER TABLE pdf_file_owners ADD COLUMN approved_hash TEXT NOT NULL DEFAULT ''")
    if 'published_hash' not in {r[1] for r in db.execute('PRAGMA table_info(pdf_exports)')}:
        db.execute("ALTER TABLE pdf_exports ADD COLUMN published_hash TEXT NOT NULL DEFAULT ''")
    for sql in [
        "CREATE TRIGGER IF NOT EXISTS approval_version_immutable BEFORE UPDATE ON approval_versions BEGIN SELECT RAISE(ABORT,'Saved approval versions are immutable'); END",
        "CREATE TRIGGER IF NOT EXISTS approval_snapshot_immutable BEFORE UPDATE OF data ON approval_artifacts BEGIN SELECT RAISE(ABORT,'Approved snapshots are immutable'); END",
        "CREATE TRIGGER IF NOT EXISTS approval_pdf_immutable BEFORE UPDATE OF pdf,pdf_hash ON approval_artifacts WHEN OLD.pdf IS NOT NULL BEGIN SELECT RAISE(ABORT,'Approved PDFs are immutable'); END",
        "CREATE TRIGGER IF NOT EXISTS approval_decision_immutable BEFORE UPDATE OF decision,comment,decided_at ON approval_reviews WHEN OLD.decision<>'Pending' BEGIN SELECT RAISE(ABORT,'Review decisions are immutable'); END"
    ]:
        db.execute(sql)
    for row in db.execute("SELECT id,data FROM records WHERE kind='quote'").fetchall():
        data = json.loads(row['data'])
        ensure_version(db, row['id'], data, imported=True)


def private_access(db, record, user=None):
    """Original staff/edit permissions; a reviewer grant never grants margin access."""
    user = user or security.current_user()
    return (not security.enabled() and user is None) or bool(
        user and user['role'] in ('Administrator', 'Editor') and
        security.can_read(db, record, user=user, write=True, include_workflow=False))


def redact(data):
    data = copy.deepcopy(data)
    data['internal_notes'] = ''
    for row in data.get('lines', []):
        row['cost'] = ''
    for section in data.get('document', {}).get('sections', []):
        for row in section['rows']:
            row['cost'] = ''
    return data


def content(data):
    result = redact(data)
    # Merely loading/saving an older quotation with default V14 headings must
    # not turn an unchanged saved version into a different approval fingerprint.
    from .quotation_presentation import FEE_HEADINGS
    if result.get('document',{}).get('fee_headings')==FEE_HEADINGS:
        result['document'].pop('fee_headings',None)
    if 'document' in result and not result['document'].get('optional_monitoring',False):
        result['document'].pop('optional_monitoring',None);result['document'].pop('monitoring_ids',None)
    result.pop('status', None)  # Won/Lost/archiving is not approval content.
    # Legacy duplicate line projections are not the structured document's content.
    if 'document' in result:
        result.pop('lines', None)
    return result


def current_version(db, ident):
    row = db.execute('SELECT * FROM approval_versions WHERE quote_id=? ORDER BY version DESC LIMIT 1', (ident,)).fetchone()
    return dict(row) if row else None


def current_round(db, ident):
    row = db.execute('SELECT * FROM approval_rounds WHERE quote_id=? AND superseded=0', (ident,)).fetchone()
    return dict(row) if row else None


def last_round(db, ident):
    row = db.execute('SELECT * FROM approval_rounds WHERE quote_id=? ORDER BY rowid DESC LIMIT 1', (ident,)).fetchone()
    return dict(row) if row else None


def decisions(db, round_id):
    return [dict(r) for r in db.execute('''SELECT r.*,u.username,u.active,u.role FROM approval_reviews r
        JOIN users u ON u.id=r.user_id WHERE round_id=? ORDER BY position,slot''', (round_id,))]


def event(db, ident, version, kind, body, round_id=None, details=None):
    cursor = db.execute('''INSERT INTO approval_events(quote_id,round_id,version,actor,at,kind,body,details)
        VALUES (?,?,?,?,?,?,?,?)''', (ident, round_id, version, actor(), stamp(), kind, body, json.dumps(details or [])))
    return cursor.lastrowid


def change_list(before, after, path=''):
    """Field-level evidence, including before/after values; no private cost fields."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        return [c for key in sorted(before.keys() | after.keys())
                for c in change_list(before.get(key), after.get(key), (path + '.' + key).strip('.'))]
    if isinstance(before, list) and isinstance(after, list) and all(isinstance(x, dict) and 'id' in x for x in before + after):
        old = {x['id']: x for x in before}; new = {x['id']: x for x in after}
        changes = change_list(old, new, path)
        if list(old) != list(new):
            changes.append(dict(field=path + '.order', before=list(old), after=list(new)))
        return changes
    return [dict(field=path, before=before, after=after)]


def ensure_version(db, ident, data, imported=False):
    previous = current_version(db, ident)
    digest = fingerprint(content(data))
    if previous and previous['hash'] == digest:
        return previous, False
    version = previous['version'] + 1 if previous else 1
    changes = change_list(content(json.loads(previous['data'])), content(data)) if previous else []
    db.execute('INSERT INTO approval_versions VALUES (?,?,?,?,?,?,?)',
               (ident, version, digest, json.dumps(redact(data)), None if imported else actor(), stamp(), json.dumps(changes)))
    return current_version(db, ident), True


def owner_id(db, ident):
    row = db.execute('SELECT owner_id FROM records WHERE id=?', (ident,)).fetchone()
    return row[0] if row else None


def participants(db, ident):
    ids = {r[0] for r in db.execute('SELECT user_id FROM approval_grants WHERE quote_id=?', (ident,))}
    ids.add(owner_id(db, ident))
    ids.update(r[0] for r in db.execute('SELECT submitter FROM approval_rounds WHERE quote_id=?', (ident,)))
    creator = db.execute('SELECT created_by FROM document_management WHERE record_id=?', (ident,)).fetchone()
    if creator:
        ids.add(creator[0])
    saved=db.execute("SELECT id,kind,data FROM records WHERE id=? AND kind='quote'",(ident,)).fetchone()
    record=dict(saved,data=json.loads(saved['data'])) if saved else None
    return {r['id']: r['username'] for r in db.execute("SELECT * FROM users WHERE active=1 AND role<>'Viewer'")
            if r['id'] in ids and record and security.can_read(db,record,user=dict(r))}


def notify(db, ident, recipients, kind, body, event_key, message_id=None):
    from .notifications import create
    for user in set(recipients) - {None, ''}:
        create(db, user, ident, event_key, kind, body, message_id)


def workflow_people(db,ident):
    current=current_round(db,ident);ids={owner_id(db,ident)}
    creator=db.execute('SELECT created_by FROM document_management WHERE record_id=?',(ident,)).fetchone()
    if creator:ids.add(creator[0])
    if current:
        ids.add(current['submitter']);ids.update(r['user_id'] for r in decisions(db,current['id']))
    return {user:name for user,name in participants(db,ident).items() if user in ids}


def reviewers_valid(db, mapping,allow_empty=False):
    selected=normalize_selection(mapping)
    if not selected and not allow_empty:raise ValidationError('Select at least one approver before submitting for approval.')
    for item in selected:
        ident=item['user_id']
        if not db.execute("SELECT 1 FROM users WHERE id=? AND active=1 AND role IN ('Editor','Administrator')", (ident,)).fetchone():
            raise ValidationError('Each approver must be an existing active staff account. Update inactive assignments before submitting.')
    return selected


def start_round(db, ident, version, mapping, reapproval=False, submitter=None):
    selected=reviewers_valid(db, mapping)
    db.execute('UPDATE approval_rounds SET superseded=1 WHERE quote_id=? AND superseded=0', (ident,))
    rid = uuid4().hex
    db.execute('''INSERT INTO approval_rounds(id,quote_id,version,hash,status,submitter,at,reapproval)
        VALUES (?,?,?,?,?,?,?,?)''', (rid, ident, version['version'], version['hash'], ACTIVE[0] if any(x['phase']=='operations' for x in selected) else ACTIVE[1], submitter or actor(), stamp(), int(reapproval)))
    for position,item in enumerate(selected):
        slot='approver_'+str(position);user=item['user_id'];phase=item['phase']
        db.execute('INSERT INTO approval_reviews(round_id,slot,user_id,phase,position) VALUES (?,?,?,?,?)', (rid, slot, user,phase,position))
        db.execute('INSERT OR IGNORE INTO approval_grants VALUES (?,?)', (ident, user))
        notify(db, ident, [user], 'Review assignment', PHASES[phase] + ' approver assigned for saved version ' + str(version['version']) + '.', rid + ':assign:' + slot)
        if phase=='operations' or not any(x['phase']=='operations' for x in selected):
            notify(db, ident, [user], 'Action required', PHASES[phase]+' approval is ready for saved version ' + str(version['version']) + '.', rid + ':action:' + slot)
    return current_round(db, ident)


def on_save(db, ident, data, previous, defer_restart=False):
    version, changed = ensure_version(db, ident, data)
    if not changed:
        return
    round_ = current_round(db, ident)
    detail = json.loads(version['changes'])
    text = 'Saved content version ' + str(version['version']) + ('; reapproval is required.' if round_ else '.')
    eid = event(db, ident, version['version'], 'content', text, details=detail)
    if round_:
        db.execute('UPDATE approval_rounds SET superseded=1 WHERE id=?', (round_['id'],))
        mapping = [dict(user_id=r['user_id'],phase=r['phase']) for r in decisions(db, round_['id'])]
        # Failed/changes-requested rounds need deliberate resubmission. Active or
        # approved content edits restart the sequence immediately when staff remain valid.
        if not defer_restart and round_['status'] in (*ACTIVE, 'Approved by all', 'Sent to client'):
            try:
                reviewers_valid(db, mapping)
            except ValidationError:
                event(db, ident, version['version'], 'attention', 'Reapproval required; update inactive approvers and resubmit.')
            else:
                start_round(db, ident, version, mapping, True, round_['submitter'])
        notify(db, ident, workflow_people(db, ident), 'Reapproval required', text, 'edit:' + str(eid))


def require_current(db, ident, version, digest):
    saved = current_version(db, ident)
    if not saved or str(saved['version']) != str(version) or saved['hash'] != digest:
        raise ValidationError('This quotation changed while you were reviewing it. Review the updated saved version before taking action.')
    return saved


def submit(db, record, mapping, version, digest,selection_version=None):
    if not private_access(db, record):
        abort(403)
    saved = require_current(db, record['id'], version, digest)
    reviewers_valid(db,mapping)
    save_selection(db,record,mapping,expected=selection_version)
    current = current_round(db, record['id'])
    if current and current['status'] in (*ACTIVE, 'Approved by all', 'Sent to client'):
        raise ValidationError('This saved version already has an active or completed review. Edit its content to start reapproval.')
    round_ = start_round(db, record['id'], saved, mapping, bool(last_round(db, record['id'])))
    eid = event(db, record['id'], saved['version'], 'submitted', 'Submitted the quotation for review.', round_['id'])
    notify(db, record['id'], workflow_people(db, record['id']), 'Submitted for review', 'Saved version ' + str(saved['version']) + ' submitted to '+str(len(normalize_selection(mapping)))+' selected approvers.', 'submit:' + str(eid))
    from .approval_emails import queue
    queue(db,round_['id'],'submission','submit:'+str(eid))
    return round_


def decide(db, record, round_id, version, digest, decision, comment):
    saved = require_current(db, record['id'], version, digest)
    round_ = current_round(db, record['id'])
    if not round_ or round_['id'] != round_id or round_['hash'] != saved['hash'] or round_['status'] not in ACTIVE:
        raise ValidationError('This review round is no longer actionable. Review the latest version and stage.')
    reviews = decisions(db, round_id)
    mine = next((r for r in reviews if r['user_id'] == actor()), None)
    if not mine:
        abort(403)
    if mine['decision'] != 'Pending':
        raise ValidationError('Your decision is already recorded for this round.')
    if mine['phase'] == 'commercial' and round_['status'] != ACTIVE[1]:
        raise ValidationError('Commercial approval starts after all selected operations approvers approve this saved version.')
    if decision not in ('Approved', 'Changes requested', 'Declined'):
        raise ValidationError('Choose Approve, Request changes or Decline.')
    comment = comment.strip()
    if len(comment) > 10000 or (decision != 'Approved' and not comment):
        raise ValidationError('Changes or decline require an explanation; comments are limited to 10,000 characters.')
    db.execute('UPDATE approval_reviews SET decision=?,comment=?,decided_at=? WHERE round_id=? AND slot=?', (decision, comment, stamp(), round_id, mine['slot']))
    status = round_['status']
    if decision != 'Approved':
        status = decision
    elif all(r['decision']=='Approved' for r in decisions(db,round_id)):
        status = 'Approved by all'
        db.execute("INSERT INTO approval_artifacts(round_id,data,status,created) VALUES (?,?,'pending',?)", (round_id, saved['data'], stamp()))
        db.execute('UPDATE approval_rounds SET completed_at=? WHERE id=?', (stamp(), round_id))
        # Freeze an already published, up-to-date customer-folder copy too. Future
        # changed content must use another filename; old external files stay put.
        db.execute("""UPDATE pdf_file_owners SET approved_hash=? WHERE record_id=? AND approved_hash=''
            AND path=(SELECT destination FROM pdf_exports WHERE record_id=? AND
              (published_hash=? OR (status='success' AND snapshot=?)))""",
            (saved['hash'],record['id'],record['id'],saved['hash'],fingerprint(record['data'])))
    elif round_['status']==ACTIVE[0] and all(r['decision'] == 'Approved' for r in decisions(db, round_id) if r['phase'] == 'operations'):
        status = ACTIVE[1]
        for commercial in reviews:
            if commercial['phase']=='commercial' and commercial['decision']=='Pending':
                notify(db, record['id'], [commercial['user_id']], 'Action required', 'All selected operations approvers approved; commercial approval is ready.', round_id + ':commercial-ready:'+commercial['user_id'])
    db.execute('UPDATE approval_rounds SET status=? WHERE id=?', (status, round_id))
    eid = event(db, record['id'], saved['version'], 'decision', decision + ' version ' + str(saved['version']) + (' — ' + comment if comment else '.'), round_id)
    notify(db, record['id'], workflow_people(db, record['id']), decision, PHASES[mine['phase']] + ': ' + decision + ('. ' + comment if comment else ''), 'decision:' + str(eid))
    if status == 'Approved by all':
        eid = event(db, record['id'], saved['version'], 'complete', 'All selected approvers approved version ' + str(saved['version']) + '.', round_id)
        notify(db, record['id'], workflow_people(db, record['id']), 'Approved by all', 'All '+str(len(reviews))+' selected approvers approved saved version ' + str(saved['version']) + '. Ready to send after its immutable PDF is captured.', 'complete:' + str(eid))
        from .approval_emails import queue
        queue(db,round_id,'complete','complete:'+str(eid))


def mark_sent(db, record, round_id, version, digest, values=None):
    from .sent_tracking import record as sent_record
    return sent_record(db,record,round_id,version,digest,values or {})


def actionable(round_, review):
    return bool(review['active'] and review['role'] in ('Editor','Administrator')) and not round_['superseded'] and review['decision'] == 'Pending' and (
        round_['status'] == ACTIVE[0] and review['phase'] == 'operations' or
        round_['status'] == ACTIVE[1] and review['phase'] == 'commercial')


def progress(db,record):
    """One current-version projection used by every portal approval indicator."""
    selected=selection(db,record['id'])['data'];version=current_version(db,record['id'])
    round_=current_round(db,record['id']);last=last_round(db,record['id'])
    reviews=decisions(db,round_['id']) if round_ else []
    valid=bool(round_ and version and round_['hash']==version['hash'] and
               selected==[dict(user_id=r['user_id'],phase=r['phase']) for r in reviews])
    users={r['id']:r['username'] for r in db.execute('SELECT id,username FROM users')}
    by_id={r['user_id']:r for r in reviews} if valid else {}
    dots=[]
    for item in selected:
        review=by_id.get(item['user_id']);state=review['decision'] if review else 'Pending'
        date=review['decided_at'] if review else None
        if review and state=='Pending':state='Pending' if actionable(round_,review) else 'Waiting'
        name=users.get(item['user_id'],'Former account')
        dots.append(dict(user_id=item['user_id'],name=name,status=state,approved=bool(review and review['decision']=='Approved'),date=date,
            tooltip=name+' · '+state+(' · '+date if date else '')))
    return dict(quote_id=record['id'],dots=dots,total=len(dots),approved=sum(d['approved'] for d in dots),
                submitted=valid,status=round_['status'] if valid else 'Draft',
                label=('Not submitted' if not last else 'Resubmission required') if not valid else '',
                reapproval=bool((round_ and round_['reapproval'] and round_['status'] not in ('Approved by all','Sent to client')) or (last and not valid)),
                selection_version=selection(db,record['id'])['version'])


def overview(db, record):
    version = current_version(db, record['id'])
    round_ = current_round(db, record['id'])
    last = last_round(db, record['id'])
    reviews = decisions(db, round_['id']) if round_ else []
    history = [dict(r) for r in db.execute('SELECT * FROM approval_rounds WHERE quote_id=? ORDER BY rowid DESC', (record['id'],))]
    for h in history:
        h['reviews'] = decisions(db, h['id'])
        artifact = db.execute('SELECT status,error,completed,pdf_hash FROM approval_artifacts WHERE round_id=?', (h['id'],)).fetchone()
        h['artifact'] = dict(artifact) if artifact else None
    for r in reviews:
        r['responsibility'] = PHASES[r['phase']]
        r['actionable'] = actionable(round_, r)
        r['display_state'] = r['decision'] if r['decision'] != 'Pending' else ('Reapproval required' if round_['reapproval'] and r['actionable'] else 'Pending' if r['actionable'] else 'Waiting')
    current_progress=progress(db,record)
    return dict(version=version, current=round_, history=history, reviews=reviews,progress=current_progress,total=current_progress['total'],
                status=round_['status'] if round_ else 'Draft', reapproval=current_progress['reapproval'],
                approved=current_progress['approved'],
                can_manage=private_access(db, record), participants=participants(db, record['id']))


def my_work(db, user_id,records=None):
    from . import store
    pending = []; waiting = []; submitted = []
    for record in (store.records(db) if records is None else records):
        if record['kind'] != 'quote':
            continue
        round_ = current_round(db, record['id'])
        if not round_:
            previous=last_round(db,record['id'])
            if previous and (owner_id(db,record['id'])==user_id or previous['submitter']==user_id):
                submitted.append(dict(record=record,round=dict(previous,status='Reapproval required · resubmit'),approved=0,progress=progress(db,record),
                    pending=', '.join(r['name'] for r in progress(db,record)['dots']),submitted_by='See round history'))
            continue
        reviews = decisions(db, round_['id'])
        item = dict(record=record, round=round_, approved=sum(r['decision'] == 'Approved' for r in reviews),progress=progress(db,record),
                    pending=', '.join(r['username'] for r in reviews if r['decision'] == 'Pending'),
                    submitted_by=(db.execute('SELECT username FROM users WHERE id=?', (round_['submitter'],)).fetchone() or ['Unknown'])[0])
        for review in reviews:
            if review['user_id'] == user_id and review['decision'] == 'Pending' and round_['status'] in ACTIVE:
                (pending if actionable(round_, review) else waiting).append(dict(item, responsibility=PHASES[review['phase']]))
        if owner_id(db, record['id']) == user_id or round_['submitter'] == user_id:
            submitted.append(item)
    return dict(pending=pending, waiting=waiting, submitted=submitted)


def protect_delete(db, ident):
    if db.execute('SELECT 1 FROM approval_rounds WHERE quote_id=?', (ident,)).fetchone() or db.execute('SELECT 1 FROM approval_messages WHERE quote_id=?', (ident,)).fetchone():
        raise ValidationError('This quotation has approval/discussion history. Archive it to preserve approved and sent evidence.')
