"""Family-level workflow and immutable accepted-value snapshots with staff audit history."""
import json
from datetime import date,datetime
from flask import Blueprint,abort,current_app,flash,g,redirect,render_template,request
from . import store,security
from .model import ValidationError
from .references import key,stamp,actor
from .commercial import amount

bp=Blueprint('outcomes',__name__)
STATUSES=('Draft','Internal Review','Approved','Under review','Sent','On hold','Won','Lost','Cancelled')
REASONS=('Price','Technical solution','Customer relationship','Delivery timeline','Competition','Budget unavailable','Project cancelled','Project postponed','Other')
LEGACY={'Accepted':'Won','Rejected':'Lost','Canceled':'Cancelled'}


def event(db,reference_key,quote_id,action,before,after):
    db.execute('INSERT INTO quotation_activity (reference_key,quote_id,actor_id,at,action,before_data,after_data) VALUES (?,?,?,?,?,?,?)',(reference_key,quote_id,actor(),stamp(),action,json.dumps(before),json.dumps(after)))


def schema(db):
    for sql in (
      'CREATE TABLE IF NOT EXISTS quote_costing (quote_id TEXT PRIMARY KEY, version INTEGER NOT NULL, data TEXT NOT NULL, updated TEXT NOT NULL, updated_by TEXT)',
      '''CREATE TABLE IF NOT EXISTS quotation_outcomes (reference_key TEXT PRIMARY KEY COLLATE NOCASE,
      status TEXT NOT NULL,reason TEXT NOT NULL,notes TEXT NOT NULL,outcome_date TEXT,recorded_by TEXT,
      accepted_quote_id TEXT,accepted_value TEXT,accepted_currency TEXT,accepted_snapshot TEXT,
      updated TEXT NOT NULL,version INTEGER NOT NULL)''',
      '''CREATE TABLE IF NOT EXISTS quotation_activity (id INTEGER PRIMARY KEY AUTOINCREMENT,
      reference_key TEXT NOT NULL,quote_id TEXT,actor_id TEXT,at TEXT NOT NULL,action TEXT NOT NULL,
      before_data TEXT NOT NULL,after_data TEXT NOT NULL)''',
      '''CREATE TABLE IF NOT EXISTS reference_usage (reference_key TEXT PRIMARY KEY COLLATE NOCASE,
      draft_only INTEGER NOT NULL DEFAULT 0,ever_sent INTEGER NOT NULL DEFAULT 0,provenance TEXT NOT NULL)'''):
        db.execute(sql)
    # V5 kept reservation provenance after it was consumed by a quotation.
    db.execute("UPDATE reference_registry SET source='quotation' WHERE kind='quotation' AND source='manual' AND key IN (SELECT reference_key FROM reference_assignments)")
    families={}
    for r in store.records(db,unrestricted=True):
        if r['kind']=='quote':families.setdefault(key(r['data']['number']),[]).append(r)
    for k,family in families.items():
        latest=max(family,key=lambda r:(r['data']['revision'],r['updated'],r['id']))
        d=latest['data'];status=LEGACY.get(d['status'],d['status']);status=status if status in STATUSES else 'Draft'
        candidates=[r for r in family if r['data']['status'] in ('Accepted','Won')]
        accepted=max(candidates,key=lambda r:(r['data']['revision'],r['updated'],r['id'])) if candidates and status!='Lost' else None
        if accepted:status='Won'
        value=None
        if accepted:
            try:value=amount(accepted['data'])
            except (ValueError,ArithmeticError,KeyError,TypeError):pass
        snapshot=json.dumps(accepted['data']) if accepted else None
        db.execute('INSERT OR IGNORE INTO quotation_outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(k,status,'Other' if status in ('Won','Lost') else '', 'Migrated legacy status; outcome date/user were not recorded.' if status in ('Won','Lost') else '',None,None,accepted['id'] if accepted else None,None if value is None else str(value),accepted['data']['currency'] if accepted else None,snapshot,latest['updated'],1))
        sent=any(r['data']['status']!='Draft' for r in family)
        db.execute('INSERT OR IGNORE INTO reference_usage VALUES (?,?,?,?)',(k,0,int(sent),'legacy-unverified'))


def get(db,k):
    row=db.execute('SELECT * FROM quotation_outcomes WHERE reference_key=?',(k,)).fetchone()
    return dict(row) if row else None


def visible(db,records):
    keys={key(r['data']['number']) for r in records if r['kind']=='quote'};ids={r['id'] for r in records}
    result={}
    for row in db.execute('SELECT * FROM quotation_outcomes'):
        if row['reference_key'] not in keys:continue
        item=dict(row);item.pop('accepted_snapshot',None)
        if item['accepted_quote_id'] and item['accepted_quote_id'] not in ids:
            item['accepted_value']=None;item['accepted_currency']=None;item['accepted_quote_id']=None
        result[row['reference_key']]=item
    return result


def on_save(db,d,ident,previous=None,revision_of=None,imported=False):
    k=key(d['number']);old=get(db,k)
    status=d['status'];newstatus=LEGACY.get(status,status)
    if newstatus in ('Won','Lost') and not imported and security.enabled():
        if (not old or old['status']!=newstatus) and (not previous or status!=previous['data']['status']):
            raise ValidationError('Use Outcome / workflow to mark Won or Lost and select a reason and accepted revision.')
    if not old:
        terminal_import=imported and newstatus in ('Won','Lost')
        if terminal_import:newstatus='Under review'
        if newstatus not in STATUSES:newstatus='Draft'
        accepted=newstatus=='Won'
        value=amount(d) if accepted else None
        data=(k,newstatus,'Other' if newstatus in ('Won','Lost') else '', 'Imported terminal status has no workflow history. Review and record an outcome with its reason, date and accepted revision.' if terminal_import else 'Imported legacy status; outcome date/user require review.' if newstatus in ('Won','Lost') else '',None,actor(),ident if accepted else None,None if value is None else str(value),d['currency'] if accepted else None,json.dumps(d) if accepted else None,stamp(),1)
        db.execute('INSERT INTO quotation_outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',data)
        event(db,k,ident,'Workflow created',None,dict(status=newstatus))
    elif previous and status!=previous['data']['status'] and not revision_of and newstatus!=old['status']:
        if old['status'] in ('Won','Lost'):raise ValidationError('Use Outcome / workflow to reopen or change a completed opportunity.')
        if newstatus in ('Won','Lost'):raise ValidationError('Use Outcome / workflow to record the reason and accepted revision.')
        db.execute('UPDATE quotation_outcomes SET status=?,updated=?,version=version+1 WHERE reference_key=?',(newstatus,stamp(),k))
        event(db,k,ident,'Workflow changed',dict(status=old['status']),dict(status=newstatus))
    usage=db.execute('SELECT * FROM reference_usage WHERE reference_key=?',(k,)).fetchone()
    officially_used=status in ('Sent','Won','Lost','Accepted','Rejected','Cancelled','Canceled')
    if not usage:db.execute('INSERT INTO reference_usage VALUES (?,?,?,?)',(k,int(not officially_used and not imported),int(officially_used),'imported' if imported else 'tracked'))
    elif officially_used:db.execute('UPDATE reference_usage SET draft_only=0,ever_sent=1 WHERE reference_key=?',(k,))
    if revision_of:
        source=db.execute('SELECT * FROM quote_costing WHERE quote_id=?',(revision_of,)).fetchone()
        if source:db.execute('INSERT OR IGNORE INTO quote_costing VALUES (?,?,?,?,?)',(ident,1,source['data'],stamp(),actor()))


def save_outcome(db,record,fields):
    from .statistics import today_local
    k=key(record['data']['number']);old=get(db,k)
    if not old:raise ValidationError('Workflow missing; reload this quotation.')
    try:version=int(fields.get('version',''))
    except ValueError:raise ValidationError('Invalid workflow version.') from None
    if version!=old['version']:raise ValidationError('Workflow changed in another session. Reload before saving.')
    status=fields.get('status','');reason=fields.get('reason','');notes=fields.get('notes','').strip();when=fields.get('outcome_date','');accepted=None;value=None;currency=None;snapshot=None
    if status not in STATUSES:raise ValidationError('Invalid outcome status.')
    if len(notes)>100000:raise ValidationError('Outcome notes exceed 100,000 characters.')
    if status in ('Won','Lost'):
        if reason not in REASONS:raise ValidationError('Select an outcome reason for Won or Lost.')
        try:day=date.fromisoformat(when)
        except ValueError:raise ValidationError('Enter a valid outcome date.') from None
        if day>today_local():raise ValidationError('Outcome date cannot be in the future.')
    else:reason='';when=None
    if status=='Won':
        ident=fields.get('accepted_quote_id','');security.require_id(db,ident)
        accepted=next((r for r in store.records(db) if r['id']==ident and r['kind']=='quote'),None)
        if not accepted or key(accepted['data']['number'])!=k:raise ValidationError('Select an accepted revision of this quotation family.')
        if old['status']=='Won' and old['accepted_quote_id']==ident and fields.get('resnapshot')!='yes':
            # Changing reason/date does not silently revalue an already accepted revision.
            value=old['accepted_value'];currency=old['accepted_currency'];snapshot=old['accepted_snapshot']
        else:
            value=amount(accepted['data'])
            if value is None:raise ValidationError('Accepted revision must be fully priced; zero is allowed.')
            value=str(value);currency=accepted['data']['currency'];snapshot=json.dumps(accepted['data'])
    after=dict(status=status,reason=reason,notes=notes,outcome_date=when,recorded_by=actor(),accepted_quote_id=accepted['id'] if accepted else None,accepted_value=value,accepted_currency=currency)
    db.execute('UPDATE quotation_outcomes SET status=?,reason=?,notes=?,outcome_date=?,recorded_by=?,accepted_quote_id=?,accepted_value=?,accepted_currency=?,accepted_snapshot=?,updated=?,version=version+1 WHERE reference_key=?',(status,reason,notes,when,actor(),after['accepted_quote_id'],value,currency,snapshot,stamp(),k))
    event(db,k,record['id'],'Outcome recorded',{x:old[x] for x in after},after)
    if status in ('Sent','Won','Lost','Cancelled'):db.execute('UPDATE reference_usage SET draft_only=0,ever_sent=1 WHERE reference_key=?',(k,))
    return after


def require_not_accepted(db,ident):
    if db.execute("SELECT 1 FROM quotation_outcomes WHERE status='Won' AND accepted_quote_id=?",(ident,)).fetchone():raise ValidationError('This is the accepted Won revision. Reopen/change the outcome before deleting it; its accepted value is protected.')


@bp.route('/quotes/<ident>/outcome',methods=['GET','POST'])
def page(ident):
    from .quote_routes import get_quote
    from .statistics import today_local,zone
    record=get_quote(ident);k=key(record['data']['number'])
    with store.connect(current_app.config['DATA_DIR']) as db:
        writable=security.can_read(db,record,write=True)
        if request.method=='POST':
            security.require_record(db,record,True);db.execute('BEGIN IMMEDIATE');save_outcome(db,record,request.form)
            flash('Outcome recorded. Accepted value is a saved snapshot, not invoiced revenue.');return redirect('/quotes/'+ident+'/outcome')
        state=get(db,k);family=[r for r in store.records(db) if r['kind']=='quote' and key(r['data']['number'])==k]
        history=[];allowed={r['id'] for r in family}
        for row in db.execute('SELECT a.*,u.username FROM quotation_activity a LEFT JOIN users u ON u.id=a.actor_id WHERE reference_key=? ORDER BY a.id DESC',(k,)):
            r=dict(row);r['display_at']=datetime.fromisoformat(r['at']).astimezone(zone()).strftime('%Y-%m-%d %H:%M:%S %z');before=json.loads(r['before_data']);after=json.loads(r['after_data'])
            # No costing details, document snapshots or hidden accepted values in history.
            def public_event(data):
                if not isinstance(data,dict):return data
                clean={x:data[x] for x in ('status','reason','notes','outcome_date') if x in data}
                if data.get('accepted_quote_id') in allowed:clean.update(accepted_revision=data.get('accepted_quote_id'),accepted_value=data.get('accepted_value'),currency=data.get('accepted_currency'))
                return clean
            r['before']=public_event(before);r['after']=public_event(after);history.append(r)
        safe=dict(state);safe.pop('accepted_snapshot',None)
        if safe.get('accepted_quote_id') not in allowed:safe.update(accepted_quote_id=None,accepted_value=None,accepted_currency=None)
    return render_template('outcome.html',record=record,state=safe,family=sorted(family,key=lambda r:r['data']['revision'],reverse=True),history=history,statuses=STATUSES,reasons=REASONS,writable=writable,today=today_local())


@bp.get('/quotes/<ident>/accepted')
def accepted_snapshot(ident):
    from .quote_routes import get_quote,render_customer
    record=get_quote(ident)
    with store.connect(current_app.config['DATA_DIR']) as db:
        state=get(db,key(record['data']['number']))
        if not state or state['status']!='Won' or not state['accepted_snapshot']:abort(404)
        security.require_id(db,state['accepted_quote_id'])
    return render_customer(json.loads(state['accepted_snapshot']))


def guard_quote_edit(db,existing,clean):
    state=db.execute("SELECT 1 FROM quotation_outcomes WHERE status='Won' AND accepted_quote_id=?",(existing['id'],)).fetchone()
    if state and (key(existing['data']['number'])!=key(clean['number']) or existing['data']['revision']!=clean['revision']):raise ValidationError('The accepted Won revision must keep its reference and revision number. Create a new revision or reopen the outcome first.')
