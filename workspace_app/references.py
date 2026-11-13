"""Shared reference ledger. Call mutations within BEGIN IMMEDIATE transactions."""
import csv,io,json,re,time,unicodedata,sqlite3
from datetime import datetime,timezone
from flask import Blueprint,abort,current_app,flash,g,redirect,render_template,request
from . import store,security
from .model import ValidationError

bp=Blueprint('references',__name__)
LEASE_SECONDS=1800
KINDS=('quotation','proposal','document')


def key(value):
    if not isinstance(value,str) or not value.strip() or len(value)>80 or not value.isprintable():raise ValidationError('Reference must be 1–80 printable characters.')
    return unicodedata.normalize('NFKC',value.strip()).casefold()


def stamp():return datetime.now(timezone.utc).isoformat()


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS reference_registry (
      key TEXT PRIMARY KEY COLLATE NOCASE, reference TEXT NOT NULL UNIQUE COLLATE NOCASE, kind TEXT NOT NULL,
      state TEXT NOT NULL CHECK(state IN ('reserved','issued')), owner_id TEXT,
      expires REAL, created TEXT NOT NULL, issued TEXT, source TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS reference_assignments (record_id TEXT PRIMARY KEY,
      reference_key TEXT NOT NULL COLLATE NOCASE REFERENCES reference_registry(key), revision INTEGER NOT NULL,
      UNIQUE(reference_key,revision))''')
    db.execute('''CREATE TABLE IF NOT EXISTS reference_conflicts (record_id TEXT PRIMARY KEY,
      reference_key TEXT NOT NULL, revision INTEGER NOT NULL)''')
    # Preserve every legacy record, including formerly allowed case collisions.
    for r in db.execute("SELECT id,data,owner_id,created FROM records WHERE kind='quote' ORDER BY created,id").fetchall():
        d=json.loads(r['data']);k=key(d['number'])
        db.execute("INSERT OR IGNORE INTO reference_registry VALUES (?,?,?,'issued',?,NULL,?,?,?)",(k,d['number'].strip(),'quotation',r['owner_id'],r['created'],r['created'],'legacy'))
        try:db.execute('INSERT INTO reference_assignments VALUES (?,?,?) ON CONFLICT(record_id) DO NOTHING',(r['id'],k,d['revision']))
        except sqlite3.IntegrityError:db.execute('INSERT OR IGNORE INTO reference_conflicts VALUES (?,?,?)',(r['id'],k,d['revision']))


def actor():return (security.current_user() or {}).get('id')


def reserve(db,reference,kind='quotation',now=None):
    if kind not in KINDS:raise ValidationError('Invalid reference type.')
    now=time.time() if now is None else now;k=key(reference);existing=db.execute('SELECT * FROM reference_registry WHERE key=?',(k,)).fetchone()
    if existing and existing['state']=='issued':raise ValidationError('Reference already issued/assigned; it cannot be reused. Use New revision for an existing quotation.')
    if existing and existing['expires']>now and existing['owner_id']!=actor():raise ValidationError('Reference is already reserved by another user.')
    if existing and existing['expires']>now and existing['kind']!=kind:raise ValidationError('This reference is reserved for another document type.')
    db.execute("INSERT INTO reference_registry VALUES (?,?,?,'reserved',?,?,?,NULL,'manual') ON CONFLICT(key) DO UPDATE SET reference=excluded.reference,kind=excluded.kind,owner_id=excluded.owner_id,expires=excluded.expires,created=excluded.created",(k,reference.strip(),kind,actor(),now+LEASE_SECONDS,stamp()))
    return k


def renew(db,k,now=None):
    now=time.time() if now is None else now
    changed=db.execute("UPDATE reference_registry SET expires=? WHERE key=? AND state='reserved' AND owner_id=? AND expires>?",(now+LEASE_SECONDS,k,actor(),now)).rowcount
    if not changed:raise ValidationError('Reservation expired or is not yours. Reserve the reference again; it may have been claimed by a colleague.')


def issue(db,k):
    changed=db.execute("UPDATE reference_registry SET state='issued',issued=?,expires=NULL WHERE key=? AND state='reserved' AND owner_id=? AND expires>?",(stamp(),k,actor(),time.time())).rowcount
    if not changed:raise ValidationError('An active reservation owned by you is required. Expired reservations cannot be issued.')


def register_quote(db,d,ident,previous=None,revision_of=None,import_family=False):
    registry_kind='quotation' if 'document' in d or 'lines' in d else 'proposal' if d.get('type')=='Proposal' else 'document'
    k=key(d['number']);oldkey=key(previous['data']['number']) if previous else None
    existing=db.execute('SELECT * FROM reference_registry WHERE key=?',(k,)).fetchone()
    binding=db.execute('SELECT * FROM reference_assignments WHERE record_id=?',(ident,)).fetchone()
    conflict=db.execute('SELECT 1 FROM reference_conflicts WHERE record_id=?',(ident,)).fetchone()
    same=bool((binding and binding['reference_key']==k) or (conflict and oldkey==k))
    revision_source=False
    if revision_of:
        source=db.execute('SELECT data FROM records WHERE id=?',(revision_of,)).fetchone()
        revision_source=bool(source and key(json.loads(source['data'])['number'])==k)
        if not revision_source:raise ValidationError('A revision must retain the source reference. Use Duplicate for a separate quotation.')
    if import_family and existing and existing['kind']==registry_kind:
        for source in db.execute('SELECT r.id,r.kind,r.data FROM records r JOIN reference_assignments a ON a.record_id=r.id WHERE a.reference_key=?',(k,)):
            r=dict(source);r['data']=json.loads(r['data'])
            if security.can_read(db,r,write=True):revision_source=True;break
    if existing:
        if existing['state']=='issued' and not (same or revision_source):
            raise ValidationError('Reference already issued/assigned. Choose another reference or use New revision; issued references remain protected after deletion.')
        if existing['state']=='reserved':
            if existing['expires']<=time.time():raise ValidationError('Reservation expired. Reserve this reference again before saving.')
            if existing['owner_id']!=actor():raise ValidationError('Reference is reserved by another user.')
            if existing['kind']!=registry_kind:raise ValidationError('Reference is reserved for a proposal/document, not a quotation.')
            issue(db,k)
            db.execute('UPDATE reference_registry SET source=? WHERE key=?',(registry_kind,k))
    else:
        db.execute("INSERT INTO reference_registry VALUES (?,?,?,'issued',?,NULL,?,?,?)",(k,d['number'].strip(),registry_kind,actor(),stamp(),stamp(),registry_kind))
    if conflict and oldkey==k and db.execute('SELECT 1 FROM reference_assignments WHERE reference_key=? AND revision=? AND record_id<>?',(k,d['revision'],ident)).fetchone():
        raise ValidationError('Legacy duplicate reference/revision: choose an unused reference or a distinct revision to resolve it.')
    try:
        db.execute('INSERT INTO reference_assignments VALUES (?,?,?) ON CONFLICT(record_id) DO UPDATE SET reference_key=excluded.reference_key,revision=excluded.revision',(ident,k,d['revision']))
    except sqlite3.IntegrityError:raise ValidationError('Reference and revision already assigned. Reload and create a new revision.') from None
    db.execute('DELETE FROM reference_conflicts WHERE record_id=?',(ident,))


def overview(db,today):
    pattern=re.compile(r'^cir'+str(today.year)[-2:]+r'-(\d+)-(\d+)$',re.I)
    issued=[];occupied=[]
    for r in db.execute('SELECT * FROM reference_registry'):
        m=pattern.fullmatch(r['reference'])
        if not m:continue
        entry=(int(m[1]),int(m[2]),r['reference'])
        if r['state']=='issued':issued.append(entry)
        if r['state']=='issued' or r['expires']>time.time():occupied.append(entry)
    last=max(issued)[2] if issued else 'None issued this year'
    sequence=max((x[0] for x in occupied),default=0)+1
    return dict(last=last,next=f'CIR{str(today.year)[-2:]}-{sequence}-1',year=today.year)


def connect():return store.connect(current_app.config['DATA_DIR'])


@bp.route('/references',methods=['GET','POST'])
def registry():
    from .statistics import today_local
    error=None
    if request.method=='POST':
        try:
            with connect() as db:
                db.execute('BEGIN IMMEDIATE');action=request.form.get('action')
                if action=='reserve':reserve(db,request.form.get('reference',''),request.form.get('kind','quotation'))
                elif action=='next':reserve(db,overview(db,today_local())['next'],request.form.get('kind','quotation'))
                elif action=='renew':renew(db,request.form.get('key',''))
                elif action=='issue':issue(db,request.form.get('key',''))
                elif action=='release_reservation':
                    k=key(request.form.get('key',''))
                    changed=db.execute("UPDATE reference_registry SET expires=0 WHERE key=? AND state='reserved' AND owner_id=?",(k,actor())).rowcount
                    if not changed:raise ValidationError('Only your own unused reservation can be released.')
                    from .outcomes import event
                    event(db,k,None,'Unused reservation released',None,None)
                elif action=='release':
                    security.require_admin()
                    if key(request.form.get('confirm_reference',''))!=key(request.form.get('key','')):raise ValidationError('Type the exact reference to confirm the unused-draft review.')
                    release_unused(db,request.form.get('key',''),request.form.get('never_sent')=='yes')
                else:raise ValidationError('Invalid reference action.')
            flash('Reference updated. Reservations last 30 minutes; issued references never expire.')
            return redirect('/references')
        except ValidationError as exc:error=str(exc)
    with connect() as db:
        info=overview(db,today_local());entries=[]
        for r in db.execute('SELECT x.*,u.username FROM reference_registry x LEFT JOIN users u ON u.id=x.owner_id ORDER BY x.created DESC,x.key'):
            r=dict(r);r['expired']=r['state']=='reserved' and r['expires']<=time.time()
            r['remaining']=max(0,int(((r['expires'] or 0)-time.time())/60))
            if request.args.get('q','').casefold() not in r['reference'].casefold():continue
            r['links']=[]
            for row in db.execute('SELECT r.id,r.kind,r.data FROM records r JOIN reference_assignments a ON a.record_id=r.id WHERE a.reference_key=? ORDER BY a.revision DESC',(r['key'],)):
                record=dict(row);record['data']=json.loads(record['data'])
                if security.can_read(db,record):r['links'].append((record['id'],record['data']['revision']))
            usage=db.execute('SELECT * FROM reference_usage WHERE reference_key=?',(r['key'],)).fetchone()
            live=db.execute('SELECT COUNT(*) FROM records r JOIN reference_assignments a ON a.record_id=r.id WHERE a.reference_key=?',(r['key'],)).fetchone()[0]
            r['draft_only']=bool(usage and usage['draft_only'] and not usage['ever_sent'])
            r['deleted']=r['state']=='issued' and r['kind']=='quotation' and not live
            r['releasable']=r['deleted'] and r['source']=='quotation' and not (usage and (usage['ever_sent'] or usage['provenance']=='imported'))
            entries.append(r)
        conflicts=db.execute('SELECT COUNT(*) FROM reference_conflicts c JOIN records r ON r.id=c.record_id').fetchone()[0]
        conflict_records=[]
        for row in db.execute('SELECT r.id,r.kind,r.data FROM records r JOIN reference_conflicts c ON c.record_id=r.id'):
            r=dict(row);r['data']=json.loads(r['data'])
            if security.can_read(db,r):conflict_records.append(r)
    return render_template('references.html',entries=entries,info=info,error=error,conflicts=conflicts,conflict_records=conflict_records,kinds=KINDS)


@bp.post('/references/check')
def check():
    with connect() as db:
        reference=request.form.get('reference','');k=key(reference)
        if request.form.get('reserve')=='yes':
            db.execute('BEGIN IMMEDIATE');reserve(db,reference,'quotation')
        r=db.execute('SELECT * FROM reference_registry WHERE key=?',(k,)).fetchone()
        source=request.form.get('source_quote','')
        same=bool(source and db.execute('SELECT 1 FROM reference_assignments WHERE record_id=? AND reference_key=?',(source,k)).fetchone())
        if same:security.require_id(db,source,True)
        state='available' if not r else 'assigned to this quotation' if same else 'already issued' if r['state']=='issued' else 'expired — reserve again' if r['expires']<=time.time() else 'reserved by you' if r['owner_id']==actor() else 'reserved by another user'
        return {'state':state,'reference':reference,'available':not r or (r['state']=='reserved' and r['expires']<=time.time()),'expires':r['expires'] if r else None}


def parse_history(raw,filename,column=''):
    if len(raw)>1024*1024:raise ValidationError('Reference import exceeds 1 MiB.')
    if filename.lower().endswith('.csv'):
        try:
            rows=[]
            for row in csv.reader(io.StringIO(raw.decode('utf-8-sig'))):
                if len(rows)>=5001:raise ValidationError('Maximum 5,000 references plus a header.')
                rows.append(row)
        except (UnicodeError,csv.Error):raise ValidationError('Use a UTF-8 CSV file.') from None
    elif filename.lower().endswith('.xlsx'):
        from .excel_import import load
        book,_=load(raw)
        if len(book.worksheets)!=1:raise ValidationError('Export the reference sheet to a single-sheet XLSX or CSV.')
        rows=[[c.value for c in row] for row in book.worksheets[0].iter_rows()]
    else:raise ValidationError('Use CSV or XLSX.')
    if not rows or len(rows)>5001:raise ValidationError('Use a header plus at most 5,000 references.')
    headers=[str(x or '').strip() for x in rows[0]]
    if not column:column=next((x for x in headers if x.casefold() in ('reference','ref','reference number','cir reference')),'')
    if column not in headers:raise ValidationError('Reference column not found. Enter its exact header name.')
    if headers.count(column)!=1:raise ValidationError('The selected column header must be unique.')
    index=headers.index(column);result=[];seen=set()
    for row in rows[1:]:
        value=str(row[index] or '').strip() if index<len(row) else ''
        if not value:continue
        if value.startswith('='):raise ValidationError('Reference formulas are not evaluated. Export the reference column as literal values.')
        k=key(value)
        if k in seen:continue
        seen.add(k);result.append(value)
    if not result:raise ValidationError('No references found.')
    return result


@bp.route('/references/import',methods=['GET','POST'])
def import_history():
    if not g.user or g.user['role']=='Viewer':abort(403)
    preview=None
    if request.method=='POST':
        if request.form.get('action')=='confirm':
            try:preview=json.loads(request.form.get('references',''))
            except (ValueError,RecursionError):raise ValidationError('Invalid historical reference list.') from None
            if not isinstance(preview,list) or len(preview)>5000:raise ValidationError('Maximum 5,000 references per import.')
            added=0;skipped=0
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                for value in preview:
                    k=key(value);r=db.execute('SELECT * FROM reference_registry WHERE key=?',(k,)).fetchone()
                    if r and r['state']=='issued':skipped+=1;continue
                    if r and r['expires']>time.time():raise ValidationError('Historical import conflicts with active reservation: '+value)
                    db.execute("INSERT INTO reference_registry VALUES (?,?,?,'issued',?,NULL,?,?,?) ON CONFLICT(key) DO UPDATE SET reference=excluded.reference,kind=excluded.kind,state='issued',owner_id=excluded.owner_id,expires=NULL,issued=excluded.issued,source=excluded.source",(k,value.strip(),'document',actor(),stamp(),stamp(),'historical'))
                    added+=1
            flash(f'Historical import: {added} issued references protected; {skipped} already issued references skipped. No quotations were created.')
            return redirect('/references')
        f=request.files.get('file')
        if not f:raise ValidationError('Choose a reference file.')
        preview=parse_history(f.read(1024*1024+1),f.filename,request.form.get('column',''))
    return render_template('reference_import.html',preview=preview)


def release_unused(db,k,attest=False):
    """Release only deleted, never-issued draft identity. Keep an audit tombstone."""
    k=key(k);row=db.execute('SELECT * FROM reference_registry WHERE key=?',(k,)).fetchone()
    if not row or row['kind']!='quotation' or row['source']!='quotation':raise ValidationError('Historical/imported/document references cannot be released.')
    if db.execute('SELECT 1 FROM records r JOIN reference_assignments a ON a.record_id=r.id WHERE a.reference_key=?',(k,)).fetchone():raise ValidationError('Delete all draft revisions before releasing their reference.')
    for r in store.records(db,unrestricted=True):
        if r['kind']=='quote' and key(r['data']['number'])==k:raise ValidationError('This reference still has saved quotations.')
    usage=db.execute('SELECT * FROM reference_usage WHERE reference_key=?',(k,)).fetchone()
    outcome=db.execute('SELECT status FROM quotation_outcomes WHERE reference_key=?',(k,)).fetchone()
    if (usage and (usage['ever_sent'] or usage['provenance']=='imported')) or (outcome and outcome['status']!='Draft'):raise ValidationError('A sent or completed reference stays protected and cannot be recycled.')
    verified=usage and usage['draft_only']
    if not verified:
        security.require_admin()
        if not attest:raise ValidationError('An administrator must verify that this older deleted draft was never sent or externally issued.')
    from .outcomes import event
    event(db,k,None,'Unused deleted draft reference released',dict(reference=row['reference'],verification='tracked draft' if verified else 'administrator attestation'),None)
    db.execute('DELETE FROM reference_assignments WHERE reference_key=?',(k,));db.execute('DELETE FROM reference_conflicts WHERE reference_key=?',(k,))
    db.execute('DELETE FROM quotation_outcomes WHERE reference_key=?',(k,));db.execute('DELETE FROM reference_usage WHERE reference_key=?',(k,))
    db.execute('DELETE FROM reference_registry WHERE key=?',(k,))
    return True


def after_delete(db,k):
    usage=db.execute('SELECT * FROM reference_usage WHERE reference_key=?',(k,)).fetchone()
    if not usage or not usage['draft_only'] or usage['ever_sent']:return False
    if db.execute('SELECT 1 FROM records r JOIN reference_assignments a ON a.record_id=r.id WHERE a.reference_key=?',(k,)).fetchone():return False
    outcome=db.execute('SELECT status FROM quotation_outcomes WHERE reference_key=?',(k,)).fetchone()
    if outcome and outcome['status']!='Draft':return False
    return release_unused(db,k)
