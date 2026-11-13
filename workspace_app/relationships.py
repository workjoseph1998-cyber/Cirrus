"""Version 8 customer pricing, immutable contract versions and monthly snapshots.

All child access is checked against the parent record. No inferred customer links,
no automatic approvals, repricing or document extraction.
"""
import calendar
import copy
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request
from werkzeug.utils import secure_filename
from . import security, store
from .model import ValidationError, decimal, money
from .statistics import today_local

bp = Blueprint('relationships', __name__)


def schema(db):
    for sql in (
        '''CREATE TABLE IF NOT EXISTS agreed_prices (id TEXT PRIMARY KEY, scope_id TEXT NOT NULL REFERENCES records(id),
           item_key TEXT NOT NULL, billing TEXT NOT NULL, currency TEXT NOT NULL, start TEXT NOT NULL,
           finish TEXT NOT NULL, price TEXT NOT NULL, notes TEXT NOT NULL, active INTEGER NOT NULL,
           version INTEGER NOT NULL, updated TEXT NOT NULL, updated_by TEXT)''',
        'CREATE INDEX IF NOT EXISTS agreed_scope ON agreed_prices(scope_id,item_key,billing,currency)',
        '''CREATE TABLE IF NOT EXISTS price_history (id INTEGER PRIMARY KEY, price_id TEXT NOT NULL, scope_id TEXT NOT NULL,
           at TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL, before_data TEXT, after_data TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS contracts (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES records(id),
           version INTEGER NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL, at TEXT NOT NULL,
           actor TEXT NOT NULL, UNIQUE(project_id,version))''',
        '''CREATE TABLE IF NOT EXISTS contract_documents (contract_id TEXT NOT NULL REFERENCES contracts(id),
           attachment_id TEXT NOT NULL REFERENCES attachments(id), label TEXT NOT NULL,
           PRIMARY KEY(contract_id,attachment_id))''',
        '''CREATE TABLE IF NOT EXISTS consumption (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES records(id),
           month TEXT NOT NULL, contract_id TEXT NOT NULL REFERENCES contracts(id), data TEXT NOT NULL,
           version INTEGER NOT NULL, at TEXT NOT NULL, actor TEXT NOT NULL, UNIQUE(project_id,month))''',
        '''CREATE TABLE IF NOT EXISTS consumption_history (id INTEGER PRIMARY KEY, consumption_id TEXT NOT NULL,
           at TEXT NOT NULL, actor TEXT NOT NULL, data TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS quotation_archives (reference_key TEXT PRIMARY KEY COLLATE NOCASE,
           archived INTEGER NOT NULL, at TEXT NOT NULL, actor TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS archive_history (id INTEGER PRIMARY KEY, reference_key TEXT NOT NULL,
           archived INTEGER NOT NULL, at TEXT NOT NULL, actor TEXT NOT NULL)''',
    ):
        db.execute(sql)


def connect():
    return store.connect(current_app.config['DATA_DIR'])


def stamp():
    return datetime.now(timezone.utc).isoformat()


def actor():
    return (security.current_user() or {}).get('username', 'Local administrator')


def text(value, label, limit=10000):
    if not isinstance(value, str) or len(value) > limit:
        raise ValidationError(label + ': invalid text.')
    return value.strip()


def iso(value, label, optional=True):
    value = text(value, label, 10)
    if not value and optional:
        return ''
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise ValidationError(label + ': use a valid date.') from None
    return value


def currency(value):
    value = text(value, 'Currency', 3).upper()
    if not re.fullmatch('[A-Z]{3}', value):
        raise ValidationError('Currency must be a three-letter code.')
    return value


def payload(field):
    try:
        value = json.loads(request.form.get(field, '{}'))
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, TypeError, RecursionError):
        raise ValidationError('Invalid ' + field + ' data.') from None


def record(db, ident, kind=None, write=False):
    row=db.execute('SELECT id,kind,data,created,updated FROM records WHERE id=?',(ident,)).fetchone()
    r={**dict(row),'data':json.loads(row['data'])} if row else None
    if not r or (kind and r['kind'] != kind):
        abort(404)
    security.require_record(db, r, write)
    return r


def guard_delete(db, r):
    if r['kind'] in ('customer', 'project'):
        if db.execute('SELECT 1 FROM customer_preferences WHERE scope_id=?',(r['id'],)).fetchone():raise ValidationError('This workspace has customer defaults/history and must be retained.')
        if db.execute('SELECT 1 FROM agreed_prices WHERE scope_id=?', (r['id'],)).fetchone() or db.execute('SELECT 1 FROM contracts WHERE project_id=?', (r['id'],)).fetchone():
            raise ValidationError('This record has price or contract history. Retain it to preserve commercial records.')
    if r['kind'] == 'quote':
        from .approvals import protect_delete
        protect_delete(db,r['id'])
        for row in db.execute('SELECT data FROM contracts'):
            data = json.loads(row['data'])
            if r['id'] in (data.get('initial_quote_id'), data.get('accepted_quote_id')):
                raise ValidationError('This revision is linked to a contract version and must be retained.')


def price_rows(db, scope_id):
    return [dict(r) for r in db.execute('SELECT * FROM agreed_prices WHERE scope_id=? ORDER BY item_key,start DESC', (scope_id,))]


def item_options(db,customer_id=''):
    from .hosting import entries
    result = []
    for r in store.records(db):
        if r['kind'] == 'catalog':
            d = r['data']
            result.append(dict(key='catalog:' + r['id'], label=d['code'] + ' · ' + d['name'] + ' / ' + d['description']))
    vm_rows=entries(db)
    if customer_id:
        from .tenant import entries as customer_entries
        vm_rows=customer_entries(db,customer_id) or vm_rows
    for r in vm_rows:
        for os, label in [('a', 'Linux'), ('b', 'Microsoft Windows')]:
            result.append(dict(key='vm:' + r['id'] + ':' + os, label=r['data']['name'] + ' · ' + label))
    return result


def save_price(db, scope_id, values, ident=None):
    scope = record(db, scope_id, write=True)
    if scope['kind'] not in ('customer', 'project'):
        abort(404)
    previous = db.execute('SELECT * FROM agreed_prices WHERE id=? AND scope_id=?', (ident, scope_id)).fetchone() if ident else None
    if ident and not previous:
        abort(404)
    if previous and str(previous['version']) != str(values.get('version')):
        raise ValidationError('Price changed since you opened it. Reload before saving.')
    key = text(values.get('item_key', ''), 'Service / VM', 150)
    # Previously saved identifiers can be retained when a catalog entry is retired.
    if key not in {i['key'] for i in item_options(db)} and (not previous or key != previous['item_key']):
        raise ValidationError('Choose an existing service or VM configuration.')
    billing = values.get('billing', '')
    if billing not in ('monthly', 'one_time'):
        raise ValidationError('Choose monthly or one-time billing.')
    cur = currency(values.get('currency', 'USD'))
    start = iso(values.get('start', ''), 'Effective from')
    finish = iso(values.get('finish', ''), 'Effective until')
    if start and finish and start > finish:
        raise ValidationError('Effective until must follow effective from.')
    price = str(money(decimal(values.get('price'), 'Agreed unit price')))
    notes = text(values.get('notes', ''), 'Notes')
    reason = text(values.get('reason', ''), 'Change reason')
    if not reason:
        raise ValidationError('A price-change reason is required.')
    active = values.get('active', 'yes') in (True, 'yes', 'on', '1')
    if active:
        for other in price_rows(db, scope_id):
            if other['id'] == ident or not other['active'] or (other['item_key'], other['billing'], other['currency']) != (key, billing, cur):
                continue
            if (not finish or not other['start'] or other['start'] <= finish) and (not other['finish'] or not start or start <= other['finish']):
                raise ValidationError('An active agreed price already covers these dates. Edit it or end its effective period first.')
    ident = ident or str(uuid4())
    now = stamp(); version = previous['version'] + 1 if previous else 1
    after = dict(id=ident, scope_id=scope_id, item_key=key, billing=billing, currency=cur, start=start, finish=finish, price=price, notes=notes, active=int(active), version=version, updated=now, updated_by=actor())
    db.execute('''INSERT INTO agreed_prices VALUES (:id,:scope_id,:item_key,:billing,:currency,:start,:finish,:price,:notes,:active,:version,:updated,:updated_by)
       ON CONFLICT(id) DO UPDATE SET item_key=excluded.item_key,billing=excluded.billing,currency=excluded.currency,
       start=excluded.start,finish=excluded.finish,price=excluded.price,notes=excluded.notes,active=excluded.active,
       version=excluded.version,updated=excluded.updated,updated_by=excluded.updated_by''', after)
    db.execute('INSERT INTO price_history(price_id,scope_id,at,actor,reason,before_data,after_data) VALUES (?,?,?,?,?,?,?)', (ident, scope_id, now, actor(), reason, json.dumps(dict(previous)) if previous else None, json.dumps(after)))
    return ident


def resolve(db, item_key, billing, cur, day, project_id='', customer_id='', source_quote=''):
    """An explicitly linked project's customer wins over a free-text quote name."""
    day = iso(day, 'Pricing date', False); cur = currency(cur)
    scopes = []
    if project_id:
        p = record(db, project_id, 'project')
        scopes.append(('Project agreed price', p['id']))
        customer_id = p['data'].get('customer_id', '')
        if customer_id:
            # A readable project grants its agreed selling prices through the picker,
            # not general access to customer documents or other projects.
            scopes.append(('Customer agreed price', customer_id))
    elif customer_id:
        record(db, customer_id, 'customer')
        scopes.append(('Customer agreed price', customer_id))
    for label, scope in scopes:
        matches = [dict(r) for r in db.execute("SELECT * FROM agreed_prices WHERE scope_id=? AND item_key=? AND billing=? AND currency=? AND active=1 AND (start='' OR start<=?) AND (finish='' OR finish>=?)",(scope,item_key,billing,cur,day,day))]
        if len(matches) > 1:
            raise ValidationError('Conflicting agreed prices need administrator review.')
        if matches:
            r = matches[0]
            return dict(price=r['price'], source=label, price_id=r['id'], price_version=r['version'], currency=cur, verified=True)
    if item_key.startswith('catalog:'):
        r = record(db, item_key[8:], 'catalog'); d = r['data']
        if d['currency'] == cur and d['billing'] == billing:
            return dict(price=d['fixed_fee'] if d['method'] == 'fixed' else d['price'], source='Standard catalog', currency=cur, verified=True)
    elif item_key.startswith('vm:'):
        from .hosting import entries
        parts = item_key.split(':')
        if len(parts) != 3 or parts[2] not in ('a', 'b'):
            raise ValidationError('Invalid VM selection.')
        row=db.execute('SELECT data FROM customer_vm_catalog WHERE customer_id=? AND entry_id=?',(customer_id,parts[1])).fetchone() if customer_id else None
        if not row:row=db.execute('SELECT data FROM hosting_vms WHERE id=?',(parts[1],)).fetchone()
        vm=json.loads(row['data']) if row else None
        if not vm:
            abort(404)
        if cur == 'USD' and billing == 'monthly':
            return dict(price=vm['cost_' + parts[2]] if vm['price_status'] == 'Confirmed' else '', source='Standard VM library' if vm['price_status'] == 'Confirmed' else 'Standard VM library · unconfirmed', currency=cur, verified=vm['price_status'] == 'Confirmed')
    return dict(price='', source='No applicable price · enter manually', currency=cur, verified=False)


@bp.get('/pricing/options')
def pricing_options():
    with connect() as db:
        project = request.args.get('project_id', ''); customer = request.args.get('customer_id', '')
        day = request.args.get('date') or today_local().isoformat(); cur = request.args.get('currency', 'USD')
        # Quote-only edit assignments retain the standard pickers. Project and
        # customer agreed prices still require their normal scope permission.
        limited=False
        scope_id=project or customer
        if scope_id:
            scope_row=db.execute('SELECT id,kind,data FROM records WHERE id=?',(scope_id,)).fetchone()
            readable=scope_row and security.can_read(db,dict(scope_row,data=json.loads(scope_row['data'])))
            if not readable:
                source=record(db,request.args.get('source_quote',''),'quote',True)
                if (project and source['data'].get('project_id')!=project) or (not project and source['data'].get('customer_id')!=customer):abort(404)
                project=customer='';limited=True
            elif project:record(db,project,'project')
            else:record(db,customer,'customer')
        values = {}
        pricing_customer=record(db,project,'project')['data'].get('customer_id','') if project else customer
        for item in item_options(db,pricing_customer):
            billing = 'monthly'
            if item['key'].startswith('catalog:'):
                billing = record(db, item['key'][8:], 'catalog')['data']['billing']
            values[item['key']] = resolve(db, item['key'], billing, cur, day, project, customer)
        if limited:
            for price in values.values():price['source']+=' · agreed pricing requires project/customer access'
        return dict(prices=values)


@bp.route('/prices/<scope_id>', methods=['GET', 'POST'])
def prices(scope_id):
    with connect() as db:
        scope = record(db, scope_id)
        if scope['kind'] not in ('customer', 'project'): abort(404)
        if request.method == 'POST':
            db.execute('BEGIN IMMEDIATE')
            save_price(db, scope_id, request.form, request.form.get('id') or None)
            flash('Agreed price saved with an audit entry. Saved quotations and consumption are unchanged.')
            return redirect('/prices/' + scope_id)
        rows = price_rows(db, scope_id)
        history = [dict(r) for r in db.execute('SELECT * FROM price_history WHERE scope_id=? ORDER BY id DESC', (scope_id,))]
        for h in history:
            h['before'] = json.loads(h['before_data']) if h['before_data'] else None; h['after'] = json.loads(h['after_data'])
        options = item_options(db); labels = {i['key']: i['label'] for i in options}
    return render_template('agreed_prices.html', scope=scope, rows=rows, history=history, options=options, labels=labels)


def contract_rows(db, project_id):
    return [{**dict(r), 'data': json.loads(r['data'])} for r in db.execute('SELECT * FROM contracts WHERE project_id=? ORDER BY version DESC', (project_id,))]


def latest_contract(db, project_id, approved=False):
    return next((c for c in contract_rows(db, project_id) if not approved or c['status'] == 'Approved'), None)


def clean_services(raw):
    if not isinstance(raw, list) or len(raw) > 2000:
        raise ValidationError('Use at most 2,000 agreed services.')
    rows = []; seen = set()
    for row in raw:
        if not isinstance(row, dict): raise ValidationError('Invalid agreed service.')
        rid = text(row.get('id') or uuid4().hex, 'Service ID', 80)
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',rid):raise ValidationError('Invalid agreed service ID.')
        if rid in seen: raise ValidationError('Duplicate agreed service ID.')
        seen.add(rid)
        service = text(row.get('service', ''), 'Service')
        if not service: raise ValidationError('Service is required.')
        billing = row.get('billing', 'monthly'); basis = row.get('basis', 'fixed')
        if billing not in ('monthly', 'one_time') or basis not in ('fixed', 'actual'):
            raise ValidationError('Choose monthly/one-time and fixed/actual billing.')
        method = row.get('method', 'unit')
        if method not in ('unit', 'fixed'): raise ValidationError('Unsupported agreed pricing method.')
        rows.append(dict(id=rid, item_key=text(row.get('item_key', ''), 'Item key', 150), service=service,
             quantity=str(decimal(row.get('quantity'), 'Contracted quantity', maximum=Decimal('1000000'))),
             unit_price=str(money(decimal(row.get('unit_price'), 'Agreed price'))),
             discount=str(decimal(row.get('discount', '0'), 'Discount', maximum=Decimal(100))),
             billing=billing, basis=basis, method=method, notes=text(row.get('notes', ''), 'Service notes')))
    return rows


def clean_contract(db, project, raw):
    values = {k: text(raw.get(k, ''), k) for k in ('reference', 'notes', 'initial_quote_id', 'accepted_quote_id')}
    values['currency'] = currency(raw.get('currency', 'USD'))
    for k in ('start', 'end', 'renewal'):
        values[k] = iso(raw.get(k, ''), k)
    if values['start'] and values['end'] and values['start'] > values['end']:
        raise ValidationError('Contract end must follow start.')
    for k in ('initial_quote_id', 'accepted_quote_id'):
        if values[k]:
            q = record(db, values[k], 'quote')
            if q['data'].get('project_id') != project['id']:
                raise ValidationError('Linked quotations must belong to this project.')
            if k == 'accepted_quote_id':
                from .outcomes import get
                from .references import key
                state = get(db, key(q['data']['number']))
                if not state or state['status'] != 'Won' or state['accepted_quote_id'] != q['id']:
                    raise ValidationError('Choose the accepted revision of a Won quotation.')
    values['services'] = clean_services(raw.get('services', []))
    return values


def save_contract(db, project, raw, previous_version, status='Proposed'):
    latest = latest_contract(db, project['id'])
    if str(previous_version) != str(latest['version'] if latest else 0):
        raise ValidationError('A newer contract version exists. Reload before saving.')
    if status not in ('Proposed', 'Approved'): raise ValidationError('Invalid contract status.')
    data = clean_contract(db, project, raw)
    if status == 'Approved' and (not data['reference'] or not data['services']):
        raise ValidationError('Approval requires a contract reference and agreed services.')
    ident = str(uuid4()); version = latest['version'] + 1 if latest else 1
    db.execute('INSERT INTO contracts VALUES (?,?,?,?,?,?,?)', (ident, project['id'], version, status, json.dumps(data), stamp(), actor()))
    # Each new version retains links to documents of its predecessor. New uploads
    # attach explicitly to a selected version and never change its approval state.
    if latest:
        db.execute('INSERT INTO contract_documents SELECT ?,attachment_id,label FROM contract_documents WHERE contract_id=?', (ident, latest['id']))
    return ident


def accepted_services(db, quote_id, project):
    from .outcomes import get
    from .references import key
    from .quotation import calculate, validate_document
    q = record(db, quote_id, 'quote')
    if q['data'].get('project_id') != project['id']:
        raise ValidationError('Quotation belongs to another project.')
    state = get(db, key(q['data']['number']))
    if not state or state['status'] != 'Won' or state['accepted_quote_id'] != quote_id or not state['accepted_snapshot']:
        raise ValidationError('Only an explicitly accepted Won revision can supply contract prices.')
    snap = json.loads(state['accepted_snapshot']) if isinstance(state['accepted_snapshot'], str) else state['accepted_snapshot']
    doc = validate_document(snap['document']); calc = calculate(doc)
    # Summary discounts have a time/eligibility policy, not one permanent unit
    # price. Copy row terms into a proposed version with an explicit review note.
    warning=''
    if doc['discount']['enabled'] and (Decimal(calc['discount'] or 0) or Decimal(calc['one_time_discount'] or 0)):
        warning='REVIEW REQUIRED: Copied row prices and line discounts only. The accepted quotation also contains a summary/promotion discount; agree its contract service rates explicitly before approval. See the linked accepted revision for the original terms.'
    rows = []
    for s in doc['sections']:
        for r in s['rows']:
            if r['state'] == 'excluded' or s['excluded'] or any(x['id'] == s['parent'] and x['excluded'] for x in doc['sections']): continue
            value = calc['rows'][r['id']]
            if value is None: raise ValidationError('Accepted quotation contains unpriced services.')
            price = r['unit_price'] if r['method'] == 'unit' else r['fixed_fee'] if r['method'] == 'fixed' else value
            rows.append(dict(id=r['id'], item_key=r.get('item_key', ''), service=r['service'] + (' / ' + r['sub_service'] if r['sub_service'] else ''), quantity=r['quantity'], unit_price='0' if r['state'] == 'included' else price, discount='0' if r['method'] == 'percent' else r['discount'], billing=r['billing'], basis='fixed', method='unit' if r['method'] == 'unit' else 'fixed', notes=r['comments']))
    return clean_services(rows), snap['currency'], warning


@bp.route('/projects/<project_id>/commercial', methods=['GET', 'POST'])
def project_commercial(project_id):
    with connect() as db:
        project = record(db, project_id, 'project', request.method == 'POST')
        if request.method == 'POST':
            db.execute('BEGIN IMMEDIATE')
            project=record(db,project_id,'project',True)
            action = request.form.get('action', 'save')
            raw = payload('contract')
            if action == 'copy':
                if request.form.get('confirm') != 'yes': raise ValidationError('Confirm copying the accepted quotation into a new proposed contract version.')
                raw['services'], raw['currency'],warning = accepted_services(db, raw.get('accepted_quote_id', ''), project)
                if warning:
                    raw['notes']=(raw.get('notes','')+'\n'+warning).strip()
                    flash(warning)
            if action not in ('save', 'copy', 'approve'): raise ValidationError('Unknown contract action.')
            if action == 'approve' and request.form.get('confirm') != 'yes': raise ValidationError('Confirm explicit approval of the entered contract terms.')
            ident = save_contract(db, project, raw, request.form.get('version', '0'), 'Approved' if action == 'approve' else 'Proposed')
            flash('Contract version saved as ' + ('Approved.' if action == 'approve' else 'Proposed. No approval was inferred.'))
            return redirect('/projects/' + project_id + '/commercial?version=' + ident)
        versions = contract_rows(db, project_id)
        selected = next((c for c in versions if c['id'] == request.args.get('version')), versions[0] if versions else None)
        current = versions[0] if versions else None
        draft = selected['data'] if selected else dict(reference='', currency='USD', start='', end='', renewal='', notes='', initial_quote_id='', accepted_quote_id='', services=[])
        files = [dict(f) for f in db.execute('SELECT a.*,d.label FROM attachments a JOIN contract_documents d ON a.id=d.attachment_id WHERE d.contract_id=?', (selected['id'] if selected else '',))]
        quotes = [r for r in store.records(db) if r['kind'] == 'quote' and r['data'].get('project_id') == project_id]
    return render_template('project_commercial.html', project=project, versions=versions, selected=selected, current=current, draft=draft, files=files, quotes=quotes)


@bp.post('/contracts/<contract_id>/documents')
def upload_contract(contract_id):
    root = Path(current_app.config['DATA_DIR']); path = None
    try:
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            c = db.execute('SELECT * FROM contracts WHERE id=?', (contract_id,)).fetchone()
            if not c: abort(404)
            project = record(db, c['project_id'], 'project', True)
            f = request.files.get('file'); name = secure_filename(f.filename or '') if f else ''
            ext = Path(name).suffix.lower()
            mime = {'.pdf':'application/pdf', '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.txt':'text/plain', '.md':'text/markdown'}.get(ext)
            if not mime: raise ValidationError('Upload PDF, PNG, JPEG, TXT or MD, up to 10 MiB.')
            content = f.read(10*1024*1024+1)
            if not content or len(content) > 10*1024*1024: raise ValidationError('Upload a nonempty file up to 10 MiB.')
            signatures = {'.pdf': b'%PDF-', '.png': b'\x89PNG\r\n\x1a\n', '.jpg': b'\xff\xd8\xff', '.jpeg': b'\xff\xd8\xff'}
            if ext in signatures and not content.startswith(signatures[ext]): raise ValidationError('File signature does not match extension.')
            if ext in ('.txt', '.md'):
                try: content.decode('utf-8')
                except UnicodeError: raise ValidationError('Text documents must use UTF-8.') from None
            ident = str(uuid4()); stored = ident + ext
            path = root/'attachments'/stored; path.write_bytes(content)
            db.execute('INSERT INTO attachments VALUES (?,?,?,?,?)', (ident, project['id'], name, stored, mime))
            db.execute('INSERT INTO contract_documents VALUES (?,?,?)', (contract_id, ident, text(request.form.get('label','Supporting document'), 'Document label', 200)))
        flash('Document linked to this contract version. Uploading does not approve or extract prices.')
        return redirect('/projects/' + project['id'] + '/commercial?version=' + contract_id)
    except Exception:
        if path: path.unlink(missing_ok=True)
        raise


def month_value(raw):
    if not isinstance(raw, str) or not re.fullmatch(r'\d{4}-\d{2}', raw): raise ValidationError('Use a valid YYYY-MM month.')
    try:
        parsed=date.fromisoformat(raw + '-01')
        if parsed.year<1900:raise ValueError
    except ValueError: raise ValidationError('Use a valid YYYY-MM month.') from None
    return raw


def monthly_charge(row):
    contracted = decimal(row['quantity'], 'Contracted quantity', maximum=Decimal(1000000))
    actual = decimal(row.get('actual', '0'), 'Actual quantity', maximum=Decimal(1000000))
    qty = contracted if row['basis'] == 'fixed' else actual
    if row['method'] == 'fixed': qty = Decimal(1) if qty else Decimal(0)
    return money(qty * decimal(row['unit_price'], 'Agreed unit price') * (1-decimal(row['discount'], 'Discount', maximum=Decimal(100))/100))


def consumption_data(db, project_id, month, copy_previous=False):
    existing = db.execute('SELECT * FROM consumption WHERE project_id=? AND month=?', (project_id, month)).fetchone()
    first = date.fromisoformat(month+'-01'); last = first.replace(day=calendar.monthrange(first.year,first.month)[1])
    if existing:
        sheet={**dict(existing),'data':json.loads(existing['data'])}
        if copy_previous:
            prev=db.execute('SELECT data FROM consumption WHERE project_id=? AND month=?',(project_id,date.fromordinal(first.toordinal()-1).strftime('%Y-%m'))).fetchone()
            if prev:
                actuals={r['id']:r['actual'] for r in json.loads(prev['data'])['rows']}
                for r in sheet['data']['rows']:r['actual']=actuals.get(r['id'],'0')
        return sheet
    contract = next((c for c in contract_rows(db,project_id) if c['status']=='Approved' and (not c['data']['start'] or c['data']['start']<=last.isoformat()) and (not c['data']['end'] or c['data']['end']>=first.isoformat())),None)
    if not contract: return None
    d = contract['data']
    if (d['start'] and d['start'] > last.isoformat()) or (d['end'] and d['end'] < first.isoformat()):
        raise ValidationError('The approved contract does not cover this month.')
    rows = [dict(r, actual='0') for r in d['services'] if r['billing'] == 'monthly']
    if copy_previous:
        previous_month = (first.replace(day=1).toordinal()-1)
        prev = db.execute('SELECT data FROM consumption WHERE project_id=? AND month=?', (project_id, date.fromordinal(previous_month).strftime('%Y-%m'))).fetchone()
        if prev:
            actuals = {r['id']:r['actual'] for r in json.loads(prev['data'])['rows']}
            for r in rows: r['actual'] = actuals.get(r['id'], '0')
    return dict(id='', project_id=project_id, month=month, contract_id=contract['id'], version=0, data=dict(currency=d['currency'], contract_version=contract['version'], rows=rows, notes=''))


@bp.route('/projects/<project_id>/consumption', methods=['GET', 'POST'])
def consumption(project_id):
    month = month_value(request.values.get('month') or today_local().strftime('%Y-%m'))
    with connect() as db:
        project = record(db, project_id, 'project', request.method == 'POST')
        if request.method == 'POST':
            db.execute('BEGIN IMMEDIATE')
            project=record(db,project_id,'project',True)
        sheet = consumption_data(db, project_id, month, request.values.get('copy_previous') == 'yes')
        if request.method == 'POST':
            if not sheet: raise ValidationError('Approve a contract with monthly services first.')
            if str(sheet['version']) != request.form.get('version', ''): raise ValidationError('Monthly consumption changed. Reload before saving.')
            if request.form.get('contract_id') != sheet['contract_id']: raise ValidationError('The approved contract changed. Reload before saving the monthly snapshot.')
            raw = payload('consumption'); actuals = raw.get('actuals', {})
            if not isinstance(actuals, dict) or set(actuals) != {r['id'] for r in sheet['data']['rows']}:
                raise ValidationError('Consumption rows changed. Reload the sheet.')
            for r in sheet['data']['rows']:
                r['actual'] = str(decimal(actuals[r['id']], 'Actual quantity', maximum=Decimal(1000000)))
                r['charge'] = str(monthly_charge(r))
            sheet['data']['notes'] = text(raw.get('notes',''), 'Monthly notes')
            sheet['data']['total'] = str(sum((Decimal(r['charge']) for r in sheet['data']['rows']), Decimal('0.00')))
            ident = sheet['id'] or str(uuid4()); now = stamp()
            db.execute('''INSERT INTO consumption VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(project_id,month)
                DO UPDATE SET data=excluded.data,version=excluded.version,at=excluded.at,actor=excluded.actor''', (ident, project_id, month, sheet['contract_id'], json.dumps(sheet['data']), sheet['version']+1, now, actor()))
            db.execute('INSERT INTO consumption_history(consumption_id,at,actor,data) VALUES (?,?,?,?)', (ident, now, actor(), json.dumps(sheet['data'])))
            flash('Monthly snapshot saved. Later price and contract changes will not reprice it.')
            return redirect('/projects/' + project_id + '/consumption?month=' + month)
        if sheet:
            for r in sheet['data']['rows']:
                r['charge'] = str(monthly_charge(r)); r['over'] = Decimal(r['actual']) > Decimal(r['quantity'])
            sheet['data']['total'] = str(sum((Decimal(r['charge']) for r in sheet['data']['rows']), Decimal('0.00')))
        months = [dict(r) for r in db.execute('SELECT month,version,at,actor FROM consumption WHERE project_id=? ORDER BY month DESC',(project_id,))]
        history = [dict(r) for r in db.execute('SELECT * FROM consumption_history WHERE consumption_id=? ORDER BY id DESC',(sheet['id'] if sheet else '',))]
    return render_template('consumption.html', project=project, month=month, sheet=sheet, months=months, history=history)


@bp.get('/legacy-customers/<customer_id>')
def customer_overview(customer_id):
    with connect() as db:
        customer = record(db, customer_id, 'customer')
        projects = [r for r in store.records(db) if r['kind']=='project' and r['data'].get('customer_id')==customer_id]
        month = today_local().strftime('%Y-%m'); totals = defaultdict(Decimal); variance = 0; renewal = []; project_rows = []
        for p in projects:
            c = latest_contract(db,p['id'],True); latest = latest_contract(db,p['id'])
            sheet = db.execute('SELECT data FROM consumption WHERE project_id=? AND month=?',(p['id'],month)).fetchone()
            if sheet:
                d = json.loads(sheet['data']); totals[d['currency']] += Decimal(d['total']); variance += sum(Decimal(r['actual'])>Decimal(r['quantity']) for r in d['rows'])
            if c and c['data']['renewal']:
                days = (date.fromisoformat(c['data']['renewal'])-today_local()).days
                if 0<=days<=90: renewal.append(dict(project=p,contract=c,days=days,window=30 if days<=30 else 60 if days<=60 else 90))
            project_rows.append(dict(project=p,contract=c,latest=latest,saved_month=bool(sheet)))
        current = [r for r in price_rows(db, customer_id) if r['active'] and (not r['start'] or r['start']<=today_local().isoformat()) and (not r['finish'] or r['finish']>=today_local().isoformat())]
        labels = {i['key']:i['label'] for i in item_options(db)}
    return render_template('customer_overview.html', customer=customer, project_rows=project_rows, prices=current, labels=labels, month=month, totals=totals, variance=variance, renewal=renewal)
