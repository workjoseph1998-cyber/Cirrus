"""SQLite repository and versioned migrations. Values are always parameters."""
import json
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4
from .model import validate, ValidationError


@contextmanager
def connect(root):
    db = sqlite3.connect(Path(root) / 'workspace.sqlite', timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def migrate(root):
    Path(root).mkdir(parents=True, exist_ok=True)
    with connect(root) as db:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > 18:
            raise RuntimeError('Database is newer than this application; do not downgrade.')
        if version == 0:
            db.executescript('''BEGIN;
            CREATE TABLE records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL,
              created TEXT NOT NULL, updated TEXT NOT NULL);
            CREATE TABLE attachments (id TEXT PRIMARY KEY, record_id TEXT NOT NULL,
              name TEXT NOT NULL, stored TEXT NOT NULL UNIQUE, mime TEXT NOT NULL);
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            PRAGMA user_version=1;
            COMMIT;''')
        if version < 2:
            from .quotation import legacy_document
            db.execute('BEGIN IMMEDIATE')
            company = settings(db)['company']
            for r in records(db):
                if r['kind'] == 'quote' and 'document' not in r['data']:
                    r['data']['document'] = legacy_document(r['data'], company)
                    r['data']['document']['project_name'] = next((x['data']['name'] for x in records(db) if x['kind']=='project' and x['id']==r['data'].get('project_id')), '')
                    db.execute('UPDATE records SET data=? WHERE id=?', (json.dumps(r['data']), r['id']))
            db.execute('PRAGMA user_version=2')
        if version < 3:
            from .hosting import seeds, validate_vm
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS hosting_vms (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            for item in seeds():
                db.execute('INSERT OR IGNORE INTO hosting_vms VALUES (?,?)',(item['id'],json.dumps(validate_vm(item['data']))))
            for r in records(db):
                if r['kind']=='catalog':
                    r['data']=upgrade_catalog(r['data'])
                    db.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(r['data']),r['id']))
            db.execute('PRAGMA user_version=3')
        if version < 4:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            columns={r[1] for r in db.execute('PRAGMA table_info(records)')}
            if 'owner_id' not in columns:db.execute('ALTER TABLE records ADD COLUMN owner_id TEXT')
            if 'personal' not in columns:db.execute('ALTER TABLE records ADD COLUMN personal INTEGER NOT NULL DEFAULT 0')
            for statement in [
                'CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER NOT NULL, session_version INTEGER NOT NULL)',
                'CREATE TABLE IF NOT EXISTS record_acl (record_id TEXT NOT NULL, user_id TEXT NOT NULL, permission TEXT NOT NULL, PRIMARY KEY(record_id,user_id))',
                'CREATE TABLE IF NOT EXISTS login_attempts (key TEXT, address TEXT, at REAL)',
                'CREATE TABLE IF NOT EXISTS company_template (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS upgrade_operations (name TEXT PRIMARY KEY, at TEXT, details TEXT)',
                'CREATE TABLE IF NOT EXISTS import_jobs (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, created REAL, fingerprint TEXT, data TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS excel_imports (fingerprint TEXT, user_id TEXT, record_id TEXT, PRIMARY KEY(fingerprint,user_id,record_id))']:
                db.execute(statement)
            # Existing VM costs remain available for internal review. Unconfirmed
            # costs are never copied into new selling prices by the picker.
            db.execute("UPDATE settings SET value='CIRRUS SAL' WHERE key='company' AND value='Joseph Workspace'")
            db.execute('PRAGMA user_version=4')
        if version < 5:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .references import schema
            schema(db)
            db.execute('PRAGMA user_version=5')
        if version < 6:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .outcomes import schema
            schema(db)
            db.execute('PRAGMA user_version=6')
        if version < 7:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .relationships import schema
            schema(db)
            db.execute('PRAGMA user_version=7')
        if version < 8:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .customers import schema
            schema(db)
            db.execute('PRAGMA user_version=8')
        if version < 9:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .documents import schema
            schema(db)
            db.execute('PRAGMA user_version=9')
        if version < 10:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .monthly import schema
            schema(db)
            db.execute('PRAGMA user_version=10')
        if version < 11:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .approvals import schema
            schema(db)
            db.execute('PRAGMA user_version=11')
        if version < 12:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .approvals import variable_schema
            variable_schema(db)
            db.execute('PRAGMA user_version=12')
        if version < 13:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .accounts import schema
            schema(db)
            db.execute('PRAGMA user_version=13')
        if version < 14:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .customer_documents import schema
            schema(db)
            db.execute('CREATE INDEX IF NOT EXISTS approval_quote_history ON approval_rounds(quote_id)')
            db.execute('PRAGMA user_version=14')
        if version < 15:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .approval_emails import schema
            schema(db)
            db.execute('PRAGMA user_version=15')
        if version < 16:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .sent_tracking import schema as sent_schema
            from .quotation_deletion import schema as deletion_schema
            from .reporting import schema as report_schema
            sent_schema(db);deletion_schema(db);report_schema(db)
            db.execute('PRAGMA user_version=16')
        if version < 17:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS standard_catalog_bindings (code TEXT PRIMARY KEY, record_id TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS quotation_default_setup (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            db.execute('PRAGMA user_version=17')
        if version < 18:
            if not db.in_transaction:db.execute('BEGIN IMMEDIATE')
            from .v21 import schema
            schema(db)
            db.execute('PRAGMA user_version=18')
    (Path(root) / 'attachments').mkdir(exist_ok=True)


def records(db,unrestricted=False):
    result=[{**dict(r), 'data':json.loads(r['data'])} for r in db.execute('SELECT id,kind,data,created,updated FROM records ORDER BY updated DESC')]
    if unrestricted:return result
    from . import security
    with security.record_batch(db,result):
        result=security.visible(db,result)
        if db.execute('PRAGMA user_version').fetchone()[0]>=11 and security.enabled():
            from .approvals import private_access,redact
            result=[dict(r,data=redact(r['data'])) if r['kind']=='quote' and not private_access(db,r) else r for r in result]
    return result


def save(db, kind, data, ident=None, inherit_from=None, reference_import=False, review_submission=False):
    if ident and db.execute('SELECT 1 FROM deleted_quotation_ids WHERE record_id=?',(ident,)).fetchone():raise ValidationError('This record was permanently deleted; create a new record instead.')
    all_records = records(db,unrestricted=True)
    ident = ident or str(uuid4())
    existing = next((r for r in all_records if r['id'] == ident), None)
    if existing and existing['kind'] != kind:
        raise ValidationError('Record type cannot change.')
    from . import security
    inherited=next((r for r in all_records if r['id']==inherit_from),None) if inherit_from else None
    if inherit_from:
        if not inherited or inherited['kind'] not in ('quote','document') or kind!=inherited['kind']:raise ValidationError('Invalid revision source.')
        security.require_record(db,inherited,True)
    security.authorize_save(db,kind,data,existing,inherited)
    if (existing or inherited) and kind=='quote':
        from .approvals import private_access
        private_source=existing or inherited
        if not private_access(db,private_source):
            # Workflow editing does not grant purchase-cost or private-note access.
            # Preserve these server-side, ignoring forged/replayed private fields.
            import copy
            data=copy.deepcopy(data);data['internal_notes']=private_source['data'].get('internal_notes','')
            original={r['id']:r for s in private_source['data'].get('document',{}).get('sections',[]) for r in s['rows']}
            for section in data.get('document',{}).get('sections',[]):
                for row in section.get('rows',[]):row['cost']=original.get(row['id'],{}).get('cost','')
    validation_records=security.visible(db,all_records)
    source=existing or inherited
    if source and data.get('project_id')==source['data'].get('project_id'):
        for parent in all_records:
            if parent['id']==data.get('project_id') and parent not in validation_records:validation_records.append(parent)
    customer_id=data.get('customer_id')
    if customer_id:
        project=next((r for r in validation_records if r['kind']=='project' and r['id']==data.get('project_id')),None)
        if (source and customer_id==source['data'].get('customer_id')) or (project and customer_id==project['data'].get('customer_id')):
            for customer in all_records:
                if customer['id']==customer_id and customer not in validation_records:validation_records.append(customer)
    if kind=='quote' and 'document' in data:
        from .support import standalone
        data=dict(data,document=standalone(data['document'])[0])
    retain_customer=bool(source and data.get('customer_id')==source['data'].get('customer_id') and data.get('project_id')==source['data'].get('project_id'))
    clean = validate(kind, data, validation_records, ident,preserve_customer=retain_customer)
    proposed = [r for r in all_records if r['id'] != ident] + [{'id':ident, 'kind':kind, 'data':clean}]
    # Category edits must not break an existing subcategory or note relationship.
    if kind=='category':
        for r in proposed:
            if r['kind'] in ('category','note'):validate(r['kind'],r['data'],proposed,r['id'])
    if kind in ('quote','document'):
        if existing:
            from .outcomes import guard_quote_edit
            guard_quote_edit(db,existing,clean)
            from .archives import archived_keys
            from .references import key
            if key(existing['data']['number']) in archived_keys(db) and key(existing['data']['number'])!=key(clean['number']):raise ValidationError('Restore the archived family before changing its reference.')
        from .references import register_quote
        register_quote(db,clean,ident,existing,inherit_from)
    now = datetime.now(timezone.utc).isoformat()
    db.execute('INSERT INTO records (id,kind,data,created,updated) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated=excluded.updated',
               (ident, kind, json.dumps(clean), existing['created'] if existing else now, now))
    actor=security.current_user()
    if actor:
        db.execute('UPDATE records SET owner_id=COALESCE(owner_id,?), personal=MAX(personal,?) WHERE id=?',(actor['id'],security.personal_flag(db,kind,clean),ident))
    if inherited:
        owner=db.execute('SELECT owner_id FROM records WHERE id=?',(inherited['id'],)).fetchone()[0]
        db.execute('UPDATE records SET owner_id=? WHERE id=?',(owner,ident))
        for acl in db.execute('SELECT user_id,permission FROM record_acl WHERE record_id=?',(inherited['id'],)).fetchall():db.execute('INSERT INTO record_acl VALUES (?,?,?)',(ident,acl['user_id'],acl['permission']))
        if kind=='quote' and actor and not security.can_read(db,dict(id=ident,kind=kind,data=clean),user=actor,write=True,include_workflow=False):
            db.execute('INSERT OR IGNORE INTO approval_grants VALUES (?,?)',(ident,actor['id']))
    if kind=='category':
        for item in records(db,unrestricted=True):
            if security.personal_flag(db,item['kind'],item['data']):db.execute('UPDATE records SET personal=1 WHERE id=?',(item['id'],))
    if kind=='quote':
        db.execute('DELETE FROM support_migration_issues WHERE quote_id=?',(ident,))
        from .outcomes import on_save
        on_save(db,clean,ident,existing,inherit_from,reference_import)
    if kind in ('quote','document'):
        from .documents import saved
        saved(db,ident,existing,inherited)
    if kind=='customer' and not existing:
        from .monthly import initialize_catalog
        initialize_catalog(db,ident)
    if kind=='quote':
        from .approvals import on_save,initialize_selection
        initialize_selection(db,ident,inherit_from)
        on_save(db,ident,clean,existing,defer_restart=review_submission)
    return ident


def upgrade_catalog(data):
    data=dict(data)
    for k,v in {'type':'','comments':'','pricing_model':'','billing':'monthly','method':'unit','fixed_fee':'','quantity':'1','discount':'0'}.items():data.setdefault(k,v)
    return data


def settings(db):
    from .hosting import CONFIG
    result = {'company': 'CIRRUS SAL', 'payment_terms': '', 'delivery_terms': ''}
    result.update(CONFIG)
    result.update({r['key']:r['value'] for r in db.execute('SELECT * FROM settings')})
    return result


def export_data(db):
    from .hosting import entries
    from . import security
    shared_admin=not security.enabled() or security.admin()
    return {'format': 'joseph-workspace', 'version': 3, 'records': records(db), 'settings': {k:v for k,v in settings(db).items() if k in {'company','payment_terms','delivery_terms','hosting_cost_a_label','hosting_cost_b_label','hosting_default_basis'}} if shared_admin else {}, 'hosting_vms':entries(db) if shared_admin else []}


def preview_import(db, payload):
    if not isinstance(payload, dict) or set(payload) not in ({'format','version','records','settings'},{'format','version','records','settings','hosting_vms'}) or payload['format'] != 'joseph-workspace' or type(payload['version']) is not int or payload['version'] not in (1,2,3):
        raise ValidationError('Expected Cirrus Workplace JSON format version 1, 2 or 3.')
    from .hosting import import_plan
    if payload['version']==3 and 'hosting_vms' not in payload:raise ValidationError('Version 3 requires hosting_vms.')
    if 'hosting_vms' in payload:import_plan(db,payload['hosting_vms'])
    incoming = payload['records']
    if not isinstance(incoming, list) or len(incoming) > 10000:
        raise ValidationError('Import must contain an array of at most 10,000 records.')
    # Adapt legacy imports before comparing IDs. No source data is overwritten.
    adapted=set()
    from .quotation import legacy_document
    for r in incoming:
        if isinstance(r,dict) and r.get('kind')=='catalog' and isinstance(r.get('data'),dict):r['data']=upgrade_catalog(r['data'])
        if isinstance(r, dict) and r.get('kind') == 'quote' and isinstance(r.get('data'), dict) and 'document' not in r['data']:
            adapted.add(id(r))
            r['data']['document'] = legacy_document(r['data'], (payload.get('settings') if isinstance(payload.get('settings'),dict) else {}).get('company','CIRRUS SAL'))
    current = records(db)
    for r in incoming:
        if id(r) in adapted and isinstance(r,dict) and r.get('kind')=='quote' and isinstance(r.get('data',{}).get('document'),dict) and not r['data']['document'].get('project_name'):
            r['data']['document']['project_name']=next((x['data']['name'] for x in current+incoming if isinstance(x,dict) and x.get('kind')=='project' and isinstance(x.get('data'),dict) and x.get('id')==r['data'].get('project_id')), '')
    from . import security
    visible_ids={r['id'] for r in current}
    raw_ids={r['id'] for r in records(db,unrestricted=True)}
    if security.enabled() and any(isinstance(r,dict) and r.get('id') in raw_ids-visible_ids for r in incoming):raise ValidationError('Import contains an inaccessible record ID.')
    by_id = {r['id']:r for r in current}
    seen = set()
    new = []
    skipped = 0
    for r in incoming:
        if not isinstance(r, dict) or set(r) != {'id','kind','data','created','updated'}:
            raise ValidationError('Invalid record structure.')
        try:
            from uuid import UUID
            UUID(r['id'])
            for key in ('created','updated'):
                datetime.fromisoformat(r[key])
        except (ValueError, TypeError, AttributeError):
            raise ValidationError('Invalid record ID or timestamp.') from None
        if r['id'] in seen:
            raise ValidationError('Duplicate ID in import.')
        seen.add(r['id'])
        if r['id'] in by_id:
            if by_id[r['id']] != r:
                raise ValidationError('Conflicting existing ID. Import never overwrites records: ' + r['id'])
            skipped += 1
        else:
            new.append(r)
    combined = current + new
    for r in new:
        r['data'] = validate(r['kind'], r['data'], combined, r['id'],preserve_customer=r['kind']=='quote')
        if r['kind']=='quote' and 'document' in r['data']:
            from .support import standalone
            r['data']['document']=standalone(r['data']['document'])[0]
    cfg = payload['settings']
    if not isinstance(cfg, dict) or set(cfg) - {'company','payment_terms','delivery_terms','hosting_cost_a_label','hosting_cost_b_label','hosting_default_basis'} or any(not isinstance(v,str) or len(v)>10000 for v in cfg.values()):
        raise ValidationError('Invalid settings.')
    if cfg.get('hosting_default_basis','a') not in ('a','b'):raise ValidationError('Invalid default hosting cost basis.')
    return new, skipped


def apply_import(db, payload):
    # Call inside BEGIN IMMEDIATE to validate and insert against one stable state.
    new, skipped = preview_import(db, payload)
    from . import security
    new.sort(key=lambda r:(0 if r['kind']=='customer' else 1 if r['kind'] in ('project','category') else 2, r['data'].get('revision',0)))
    for r in new:
        security.authorize_save(db,r['kind'],r['data'],None)
        if r['kind'] in ('quote','document'):
            from .references import register_quote
            register_quote(db,r['data'],r['id'],import_family=True)
        db.execute('INSERT INTO records (id,kind,data,created,updated) VALUES (?,?,?,?,?)', (r['id'], r['kind'], json.dumps(r['data']), r['created'], r['updated']))
        actor=security.current_user()
        if actor:db.execute('UPDATE records SET owner_id=? WHERE id=?',(actor['id'],r['id']))
        if r['kind']=='customer':
            from .monthly import initialize_catalog
            initialize_catalog(db,r['id'])
        if r['kind'] in ('quote','document'):
            db.execute('INSERT OR IGNORE INTO document_management(record_id) VALUES (?)',(r['id'],))
            from .documents import event
            event(db,r['id'],'Imported','Original stored timestamps retained; original creator unknown.')
        if r['kind']=='quote':
            from .outcomes import on_save
            on_save(db,r['data'],r['id'],imported=True)
            if r['kind']=='quote':
                from .approvals import ensure_version
                ensure_version(db,r['id'],r['data'])
                from .approvals import initialize_selection
                initialize_selection(db,r['id'])
            from .automation import enqueue
            enqueue(db,r['id'],r['data'])
    for r in new:
        actor=security.current_user()
        if actor:db.execute('UPDATE records SET owner_id=?,personal=? WHERE id=?',(actor['id'],security.personal_flag(db,r['kind'],r['data']),r['id']))
    if 'hosting_vms' in payload:
        if security.enabled() and not security.admin():
            if payload['hosting_vms']:raise ValidationError('Only administrators can import the VM library.')
        from .hosting import import_plan
        for item in import_plan(db,payload['hosting_vms']):
            db.execute('INSERT INTO hosting_vms VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(item['id'],json.dumps(item['data'])))
    # Preserve local branding/terms on import; apply defaults only on empty settings.
    for k,v in payload['settings'].items():
        if security.enabled() and not security.admin():continue
        db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', (k,v))
    return len(new), skipped
