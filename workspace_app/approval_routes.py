"""Quotation approval/discussion screens and scoped JSON polling."""
import hashlib
import io
import json
import re
import tempfile
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file
from . import approvals as flow, security, store
from .commercial import fingerprint
from .documents import filename
from .model import ValidationError
from .references import actor, stamp

bp = Blueprint('approvals', __name__)



def fetch(db, ident, write=False):
    row = db.execute("SELECT id,kind,data,created,updated FROM records WHERE id=? AND kind='quote'", (ident,)).fetchone()
    if not row:
        abort(404)
    record = dict(row, data=json.loads(row['data']))
    security.require_record(db, record, write)
    return record


def settings_for(db, record):
    current=flow.selection(db,record['id']) if record else dict(data=flow.defaults(db),version=0)
    users = [dict(r) for r in db.execute("SELECT id,username FROM users WHERE active=1 AND role IN ('Editor','Administrator') ORDER BY username")]
    return dict(approver_choices=users,selected_approvers=current['data'],approvers_version=current['version'])


def discussion(db, record):
    people = flow.participants(db, record['id'])
    users = {r['id']: r['username'] for r in db.execute('SELECT id,username FROM users')}
    messages = [dict(r, username=users.get(r['author'], 'Former account')) for r in db.execute('SELECT * FROM approval_messages WHERE quote_id=? ORDER BY id', (record['id'],))]
    parents = {r['id']: r for r in messages}
    for message in messages:
        parent = parents.get(message['parent_id'])
        message['reply_to'] = parent['username'] + ': ' + parent['body'][:140] if parent else ''
    events = [dict(r, username=users.get(r['actor'], 'System'), details=json.loads(r['details'])) for r in db.execute('SELECT * FROM approval_events WHERE quote_id=? ORDER BY id', (record['id'],))]
    read = db.execute('SELECT last_id FROM approval_reads WHERE quote_id=? AND user_id=?', (record['id'], actor())).fetchone()
    unread = sum(m['id'] > (read[0] if read else 0) and m['author'] != actor() for m in messages)
    can_post = security.can_read(db, record, write=True)
    if not can_post:
        messages=[];unread=0
    return dict(messages=messages, events=events, unread=unread, last_id=max(parents, default=0), people=people, can_post=can_post)


@bp.route('/quotes/<ident>/approval', methods=['GET', 'POST'])
def page(ident):
    error = None
    with store.connect(current_app.config['DATA_DIR']) as db:
        if request.method == 'POST':
            db.execute('BEGIN IMMEDIATE')
        record = fetch(db, ident)
        if request.method == 'POST':
            try:
                security.require_record(db, record, True)
                action = request.form.get('action')
                version = request.form.get('version', ''); digest = request.form.get('hash', '')
                if action == 'submit':
                    # Re-save the exact, version-checked saved content in the same
                    # transaction as submission. Editor has its own Save & submit.
                    flow.require_current(db, ident, version, digest)
                    store.save(db, 'quote', record['data'], ident)
                    selected=flow.selection_from_form(request.form,flow.selection(db,ident)['data'])
                    if 'approvers' in request.form and 'approvers_version' not in request.form:raise ValidationError('Reload the approver selection before submitting.')
                    flow.submit(db, record, selected, version, digest,request.form.get('approvers_version'))
                elif action == 'reassign':
                    if not flow.private_access(db,record):abort(403)
                    saved=flow.require_current(db,ident,version,digest)
                    reason=request.form.get('reason','').strip()
                    if not reason or len(reason)>2000:raise ValidationError('Explain the approver change in 1–2,000 characters.')
                    selected=flow.selection_from_form(request.form,flow.selection(db,ident)['data'])
                    if 'approvers' in request.form and 'approvers_version' not in request.form:raise ValidationError('Reload the approver selection before saving.')
                    flow.save_selection(db,record,selected,request.form.get('approvers_version'),reason)
                elif action == 'revoke':
                    if not flow.private_access(db,record):abort(403)
                    target=request.form.get('user_id','');current=flow.current_round(db,ident)
                    if target==flow.owner_id(db,ident) or current and (target==current['submitter'] or any(r['user_id']==target for r in flow.decisions(db,current['id']))):
                        raise ValidationError('Reassign the current round before removing a current participant.')
                    db.execute('DELETE FROM approval_grants WHERE quote_id=? AND user_id=?',(ident,target))
                    flow.event(db,ident,flow.current_version(db,ident)['version'],'access','Removed a previous workflow participant grant.')
                elif action == 'decision':
                    flow.decide(db, record, request.form.get('round_id'), version, digest, request.form.get('decision'), request.form.get('comment', ''))
                elif action == 'sent':
                    flow.mark_sent(db, record, request.form.get('round_id'), version, digest,request.form)
                elif action == 'retry_pdf':
                    row = db.execute('''SELECT a.round_id FROM approval_artifacts a JOIN approval_rounds r ON r.id=a.round_id
                        WHERE r.quote_id=? AND a.round_id=? AND a.pdf IS NULL''', (ident, request.form.get('round_id'))).fetchone()
                    if not row:
                        raise ValidationError('This approval PDF is already retained or unavailable.')
                    db.execute("UPDATE approval_artifacts SET status='pending',error='' WHERE round_id=?", (row[0],))
                else:
                    raise ValidationError('Choose a valid approval action.')
                flash('Approval workflow updated.'); return redirect(request.path+('?embedded=yes' if request.args.get('embedded')=='yes' else ''))
            except ValidationError as exc:
                db.rollback(); error = str(exc)
        state = flow.overview(db, record); chat = discussion(db, record)
        setup = settings_for(db, record) if state['can_manage'] else {}
        if error and state['can_manage'] and request.form.get('approvers'):
            try:setup['selected_approvers']=flow.selection_from_form(request.form,[])
            except ValidationError:pass
    from .sent_tracking import history
    with store.connect(current_app.config['DATA_DIR']) as db:sent_history=history(db,ident)
    return render_template('approval.html', sent_history=sent_history,record=record, approval=state, chat=chat, error=error, **setup), (409 if error and 'changed while' in error else 200)


@bp.get('/quotes/<ident>/approval/poll')
def poll(ident):
    with store.connect(current_app.config['DATA_DIR']) as db:
        record = fetch(db, ident); state = flow.overview(db, record); chat = discussion(db, record)
        # Do not serialize version snapshots/internal costing or other customers.
        return dict(status=state['status'], version=state['version']['version'], hash=state['version']['hash'],
                    round_id=(state['current'] or {}).get('id'), approved=state['approved'],total=state['total'],progress=state['progress'],
                    reapproval=state['reapproval'], reviews=state['reviews'], artifacts=[dict(id=h['id'],status=h['artifact']['status']) for h in state['history'] if h['artifact']], messages=chat['messages'],
                    events=chat['events'], unread=chat['unread'], last_id=chat['last_id'])


@bp.post('/quotes/<ident>/discussion')
def message(ident):
    with store.connect(current_app.config['DATA_DIR']) as db:
        db.execute('BEGIN IMMEDIATE'); record = fetch(db, ident, True)
        body = request.form.get('body', '').strip()
        if not body or len(body) > 10000:
            raise ValidationError('Write a message of 1–10,000 characters.')
        parent = request.form.get('parent_id', '')
        if parent and not db.execute('SELECT 1 FROM approval_messages WHERE id=? AND quote_id=?', (parent, ident)).fetchone():
            raise ValidationError('Reply target is not part of this quotation.')
        token=request.form.get('request_id','')
        if token and not re.fullmatch('[a-zA-Z0-9_-]{1,80}',token):raise ValidationError('Invalid message request identity.')
        if token:
            existing=db.execute('SELECT id,body,parent_id FROM approval_messages WHERE quote_id=? AND author=? AND request_key=?',(ident,actor(),token)).fetchone()
            if existing:
                if body!=existing['body'] or str(existing['parent_id'] or '')!=parent:raise ValidationError('This message request was already used. Reload the discussion before sending another message.')
                return dict(ok=True,id=existing['id'])
        # Explicit quote editors participating in discussion are added to this
        # quotation's participants only, never a project/customer grant.
        db.execute('INSERT OR IGNORE INTO approval_grants VALUES (?,?)', (ident, actor()))
        people = flow.participants(db, ident)
        mentions = {m.casefold() for m in re.findall(r'(?<!\S)@([\w.@-]+)', body)}
        names = {name.casefold(): user for user, name in people.items()}
        mentions={m if m in names else m.rstrip('.') for m in mentions}
        if mentions - set(names):
            raise ValidationError('@mentions must name authorized active participants shown in this quotation.')
        cursor = db.execute('INSERT INTO approval_messages(quote_id,parent_id,author,at,body,request_key) VALUES (?,?,?,?,?,?)', (ident, parent or None, actor(), stamp(), body,token))
        mid = cursor.lastrowid
        for user in people:
            if user == actor():
                continue
            mentioned = user in {names[n] for n in mentions}
            flow.notify(db, ident, [user], 'Mention' if mentioned else 'Discussion', ('You were mentioned. ' if mentioned else '') + body, 'message:' + str(mid), mid)
    return dict(ok=True, id=mid)


@bp.post('/quotes/<ident>/discussion/read')
def read_discussion(ident):
    with store.connect(current_app.config['DATA_DIR']) as db:
        record = fetch(db, ident)
        maximum = db.execute('SELECT COALESCE(MAX(id),0) FROM approval_messages WHERE quote_id=?', (ident,)).fetchone()[0]
        try:
            last = min(maximum, max(0, int(request.form.get('last_id', '0'))))
        except ValueError:
            raise ValidationError('Invalid discussion cursor.') from None
        db.execute('INSERT INTO approval_reads VALUES (?,?,?) ON CONFLICT(quote_id,user_id) DO UPDATE SET last_id=MAX(last_id,excluded.last_id)', (ident, actor(), last))
        db.execute("UPDATE portal_notifications SET read_at=COALESCE(read_at,?) WHERE user_id=? AND quote_id=? AND message_id<=?", (stamp(), actor(), ident, last))
    return dict(ok=True)


@bp.get('/quotes/<ident>/approval/<round_id>/<kind>')
def artifact(ident, round_id, kind):
    with store.connect(current_app.config['DATA_DIR']) as db:
        record = fetch(db, ident)
        row = db.execute('SELECT a.* FROM approval_artifacts a JOIN approval_rounds r ON r.id=a.round_id WHERE r.quote_id=? AND a.round_id=?', (ident, round_id)).fetchone()
        if not row:
            abort(404)
        data = json.loads(row['data'])
    if kind == 'snapshot':
        return send_file(io.BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode()), mimetype='application/json', as_attachment=True, download_name=filename(data['title'], 'json'))
    if kind == 'pdf':
        if not row['pdf']:
            raise ValidationError('The immutable approved PDF is pending or failed. Retry generation in the approval panel.')
        return send_file(io.BytesIO(row['pdf']), mimetype='application/pdf', as_attachment=True, download_name=filename(data['title'], 'pdf'))
    abort(404)


def capture_pdf(app, renderer=None):
    """Background job; renders the frozen snapshot, never current mutable content."""
    from .automation import render_pdf
    renderer = renderer or render_pdf
    with store.connect(app.config['DATA_DIR']) as db:
        db.execute('BEGIN IMMEDIATE')
        job = db.execute("SELECT * FROM approval_artifacts WHERE status='pending' AND pdf IS NULL ORDER BY created LIMIT 1").fetchone()
        if not job:
            return False
        job = dict(job)
        db.execute("UPDATE approval_artifacts SET status='running' WHERE round_id=?", (job['round_id'],))
    try:
        with tempfile.TemporaryDirectory(prefix='cirrus-approved-') as directory:
            path = Path(directory) / 'approved.pdf'
            with app.app_context():
                renderer(app, json.loads(job['data']), path)
            pdf = path.read_bytes()
            if not pdf.startswith(b'%PDF-') or len(pdf) < 100:
                raise RuntimeError('Renderer returned an invalid PDF.')
        with store.connect(app.config['DATA_DIR']) as db:
            db.execute("UPDATE approval_artifacts SET pdf=?,pdf_hash=?,status='success',completed=?,error='' WHERE round_id=? AND pdf IS NULL", (pdf, hashlib.sha256(pdf).hexdigest(), stamp(), job['round_id']))
    except Exception as exc:
        with store.connect(app.config['DATA_DIR']) as db:
            db.execute("UPDATE approval_artifacts SET status='failed',error=? WHERE round_id=? AND pdf IS NULL", (str(exc)[:1000], job['round_id']))
    return True


@bp.get('/approvals')
def listing():
    filter_ = request.args.get('filter', 'pending')
    if filter_ not in ('pending', 'waiting', 'approved', 'changes', 'declined', 'mine', 'all'):
        raise ValidationError('Choose a valid approval filter.')
    with store.connect(current_app.config['DATA_DIR']) as db:
        work = flow.my_work(db, actor()); rows = []
        if filter_ in ('pending', 'waiting', 'mine'):
            rows = work[{'pending': 'pending', 'waiting': 'waiting', 'mine': 'submitted'}[filter_]]
        else:
            for record in store.records(db):
                if record['kind'] != 'quote':
                    continue
                round_ = flow.current_round(db, record['id'])
                if not round_:
                    continue
                if filter_ != 'all' and round_['status'] not in {'approved': ('Approved by all', 'Sent to client'), 'changes': ('Changes requested',), 'declined': ('Declined',)}[filter_]:
                    continue
                reviews = flow.decisions(db, round_['id'])
                rows.append(dict(record=record, round=round_, approved=sum(r['decision'] == 'Approved' for r in reviews),progress=flow.progress(db,record), pending=', '.join(r['username'] for r in reviews if r['decision'] == 'Pending')))
    term = request.args.get('q', '').casefold()
    rows = [r for r in rows if not term or any(term in r['record']['data'].get(k, '').casefold() for k in ('title', 'number', 'customer'))]
    rows.sort(key=lambda r:r['round']['at'],reverse=True)
    from .listing_ui import paginate
    rows,pagination=paginate(rows)
    return render_template('approvals.html',pagination=pagination,rows=rows, work=work, filter=filter_)
