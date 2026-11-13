"""One customer workspace over preserved customer/project identities and ACLs."""
import calendar,copy,json
from collections import Counter,defaultdict
from datetime import date
from decimal import Decimal
from flask import Blueprint,abort,current_app,flash,redirect,render_template,request
from . import security,statistics,store
from .commercial import fingerprint
from .model import FIELDS,ValidationError,decimal
from .relationships import (actor,connect,contract_rows,currency,iso,item_options,latest_contract,
    price_rows,record,resolve,save_price,stamp,text)
from .references import key
from .support import defaults,apply_defaults,standalone

bp=Blueprint('customers',__name__)


def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS customer_preferences(scope_id TEXT PRIMARY KEY REFERENCES records(id),version INTEGER NOT NULL,data TEXT NOT NULL,at TEXT NOT NULL,actor TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS customer_policy_history(id INTEGER PRIMARY KEY,scope_id TEXT NOT NULL,at TEXT NOT NULL,actor TEXT NOT NULL,before_data TEXT,after_data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS support_migrations(quote_id TEXT PRIMARY KEY,at TEXT NOT NULL,before_data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS support_migration_issues(quote_id TEXT PRIMARY KEY,error TEXT NOT NULL)')
    for row in db.execute("SELECT id,data FROM records WHERE kind='quote'").fetchall():
        data=json.loads(row['data'])
        if 'document' not in data:continue
        try:converted,changed=standalone(data['document'])
        except (ValidationError,KeyError,TypeError) as exc:
            db.execute('INSERT OR REPLACE INTO support_migration_issues VALUES (?,?)',(row['id'],str(exc)));continue
        if changed:
            db.execute('INSERT OR IGNORE INTO support_migrations VALUES (?,?,?)',(row['id'],stamp(),json.dumps(data)))
            data['document']=converted;db.execute('UPDATE records SET data=? WHERE id=?',(json.dumps(data),row['id']))
    for row in db.execute('SELECT reference_key,accepted_snapshot FROM quotation_outcomes WHERE accepted_snapshot IS NOT NULL').fetchall():
        data=json.loads(row['accepted_snapshot'])
        if 'document' in data:
            try:converted,changed=standalone(data['document'])
            except (ValidationError,KeyError,TypeError) as exc:
                db.execute('INSERT OR REPLACE INTO support_migration_issues VALUES (?,?)',('accepted:'+row['reference_key'],str(exc)));continue
            if changed:
                data['document']=converted;db.execute('UPDATE quotation_outcomes SET accepted_snapshot=? WHERE reference_key=?',(json.dumps(data),row['reference_key']))


def scope(db,ident,write=False):
    r=record(db,ident,write=write)
    if r['kind'] not in ('customer','project'):abort(404)
    return r


def members(db,customer,records=None):
    if customer['kind']=='project':return [customer]
    return [r for r in (records if records is not None else store.records(db)) if r['kind']=='project' and r['data'].get('customer_id')==customer['id']]


def quote_rows(db,customer,projects,records=None):
    ids={p['id'] for p in projects};all_quotes=[r for r in (records if records is not None else store.records(db)) if r['kind']=='quote'];families=defaultdict(list)
    for r in all_quotes:families[key(r['data']['number'])].append(r)
    result=[]
    for rows in families.values():
        latest=max(rows,key=lambda r:(r['data']['revision'],r['updated'],r['id']));d=latest['data']
        if d.get('project_id') in ids or (not d.get('project_id') and customer['kind']=='customer' and d.get('customer_id')==customer['id']):result.extend(rows)
    return result


def indicators(db,customer,projects,args,records=None):
    from .outcomes import visible
    rows=quote_rows(db,customer,projects,records);qstats=statistics.quotations(rows,args,outcomes=visible(db,rows))
    window=qstats['window'];totals=defaultdict(Decimal);monthly=defaultdict(Decimal);variance=0;months=[];renewals=[]
    # "Monthly charges" is the selected period's final calendar month; period
    # charges sum monthly snapshots whose billing month overlaps the date range.
    anchor=window['end'] or statistics.today_local();anchor=anchor.strftime('%Y-%m')
    for p in projects:
        c=latest_contract(db,p['id'],True)
        if c:
            for label,field in [('Contract expiry','end'),('Renewal','renewal')]:
                if c['data'].get(field):
                    days=(date.fromisoformat(c['data'][field])-statistics.today_local()).days
                    if days<=90:renewals.append(dict(project=p,contract=c,label=label,days=days,date=c['data'][field]))
    suppliers=[]
    # Private supplier information follows costing's staff-and-edit rule.
    latest_quotes={}
    for q in rows:
        k=key(q['data']['number'])
        if k not in latest_quotes or q['data']['revision']>latest_quotes[k]['data']['revision']:latest_quotes[k]=q
    for q in latest_quotes.values():
        from .approvals import private_access
        if not private_access(db,q):continue
        row=db.execute('SELECT data FROM quote_costing WHERE quote_id=?',(q['id'],)).fetchone()
        if row:
            for item in json.loads(row['data'])['rows']:
                if item.get('valid_until'):
                    days=(date.fromisoformat(item['valid_until'])-statistics.today_local()).days
                    if days<=90:suppliers.append(dict(quote=q,description=item['description'],date=item['valid_until'],days=days))
    return dict(qstats=qstats,monthly=monthly,period_charges=totals,variance=variance,months=months,renewals=renewals,suppliers=suppliers,anchor=anchor)


def workspaces(db,records=None):
    visible=records if records is not None else store.records(db)
    return [r for r in visible if r['kind']=='customer' or (r['kind']=='project' and not r['data'].get('customer_id'))]


@bp.get('/customers')
def listing():
    with connect() as db:
        visible_records=store.records(db);rows=workspaces(db,visible_records);archived={r[0] for r in db.execute('SELECT customer_id FROM customer_archives WHERE archived=1')};rows=[r for r in rows if request.args.get('archived')=='yes' or r['id'] not in archived];counts=Counter(r['data']['name'].strip().casefold() for r in rows)
        items=[]
        for r in rows:
            if request.args.get('q','').casefold() not in (r['data']['name']+' '+r['data'].get('customer','')).casefold():continue
            ps=members(db,r,visible_records);stats=indicators(db,r,ps,{'period':'month'},visible_records)
            renew=min((c['data']['renewal'] for p in ps if (c:=latest_contract(db,p['id'],True)) and c['data'].get('renewal')),default='')
            # Sorting is explicitly USD only; native-currency figures remain visible.
            items.append(dict(record=r,stats=stats,renewal=renew,usd=stats['monthly'].get('USD',Decimal(0)),duplicate=counts[r['data']['name'].strip().casefold()]>1))
        order=request.args.get('sort','name')
        if order not in ('name','charges','renewal','quotes','value'):raise ValidationError('Invalid customer sort.')
        items.sort(key=(lambda x:(-x['stats']['qstats']['total'],x['record']['data']['name'].casefold())) if order=='quotes' else (lambda x:(-Decimal(x['stats']['qstats']['value'].replace(',','')),x['record']['data']['name'].casefold())) if order=='value' else (lambda x:(-x['usd'],x['record']['data']['name'].casefold())) if order=='charges' else (lambda x:(x['renewal'] or '9999',x['record']['data']['name'].casefold())) if order=='renewal' else lambda x:x['record']['data']['name'].casefold())
        from .listing_ui import paginate
        items,pagination=paginate(items)
    return render_template('customers.html',items=items,pagination=pagination)


@bp.get('/customers/<ident>')
def overview(ident):
    tab=request.args.get('tab','overview')
    if tab=='documents':return redirect('/customers/'+ident+'/documents')
    if tab not in ('overview','quotations','prices','contract','projects','contacts'):raise ValidationError('Invalid customer tab.')
    with connect() as db:
        customer=scope(db,ident);projects=members(db,customer);stats=indicators(db,customer,projects,dict(request.args,period=request.args.get('period','month')))
        contracts=[dict(project=p,versions=contract_rows(db,p['id'])) for p in projects]
        table=pricing_table(db,customer) if tab=='prices' else []
        prefs=defaults(db,ident);saved=db.execute('SELECT version FROM customer_preferences WHERE scope_id=?',(ident,)).fetchone()
        policy_version=saved['version'] if saved else 0
        prices_hash=table_hash(db,ident) if tab=='prices' else ''
        options=item_options(db) if tab=='prices' else [];bases=[dict(key='category:'+s,label=s) for s in ('Production','Disaster Recovery','Monitoring — 24×7 NOC Services','Cyber Security Services','Connectivity Services')]+[i for i in options if not i['key'].startswith('catalog:') or record(db,i['key'][8:],'catalog')['data']['billing']=='monthly']
        history=[dict(r) for r in db.execute('SELECT * FROM customer_policy_history WHERE scope_id=? ORDER BY id DESC LIMIT 50',(ident,))]
        from .export_folders import context as export_context
        folder_context=export_context(db,customer) if security.admin() and customer['kind']=='customer' else {}
        duplicates=[r for r in workspaces(db) if r['id']!=ident and r['data']['name'].strip().casefold()==customer['data']['name'].strip().casefold()]
    from .workspace11 import customer_context
    with connect() as db:extra=customer_context(db,customer)
    pagination=None
    if tab=='quotations':
        order=request.args.get('sort','updated')
        if order not in ('updated','title','reference'):raise ValidationError('Invalid quotation sort.')
        stats['qstats']['rows'].sort(key=lambda r:r['updated'] if order=='updated' else r['data']['title'].casefold() if order=='title' else r['data']['number'].casefold(),reverse=order=='updated')
        from .listing_ui import paginate
        stats['qstats']['rows'],pagination=paginate(stats['qstats']['rows'])
    return render_template('customer_workspace.html',pagination=pagination,**extra,customer=customer,workspaces=projects,stats=stats,tab=tab,contracts=contracts,price_table=table,preferences=prefs,policy_version=policy_version,prices_hash=prices_hash,bases=bases,policy_history=history,duplicates=duplicates,**folder_context)


def table_hash(db,ident):
    return fingerprint(price_rows(db,ident))


def pricing_table(db,customer):
    options=item_options(db);today=statistics.today_local().isoformat();rows=[];scoped=price_rows(db,customer['id'])
    for item in options:
        if item['key'].startswith('catalog:'):
            data=record(db,item['key'][8:],'catalog')['data'];billing=data['billing'];cur=data['currency']
        else:billing='monthly';cur='USD'
        standard=resolve(db,item['key'],billing,cur,today)
        overrides=[r for r in scoped if r['item_key']==item['key'] and r['billing']==billing and r['currency']==cur and r['active'] and (not r['start'] or r['start']<=today) and (not r['finish'] or r['finish']>=today)]
        price=overrides[0] if overrides else None
        rows.append(dict(item=item,billing=billing,currency=cur,standard=standard['price'],price=price,field=item['key']+'|'+billing+'|'+cur))
    return rows


@bp.post('/customers/<ident>/prices')
def save_prices(ident):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');customer=scope(db,ident,True)
        if request.form.get('prices_hash')!=table_hash(db,ident):raise ValidationError('Customer prices changed. Reload before saving.')
        try:posted=json.loads(request.form.get('prices','{}'))
        except ValueError:raise ValidationError('Invalid pricing table.') from None
        table=pricing_table(db,customer)
        if not isinstance(posted,dict) or set(posted)!={r['field'] for r in table}:raise ValidationError('The price library changed. Reload the table.')
        reason=text(request.form.get('reason',''),'Change reason')
        if not reason:raise ValidationError('Enter a reason for the price changes.')
        for row in table:
            value=posted[row['field']]
            if not isinstance(value,str):raise ValidationError('Customer prices must be numeric text or blank.')
            value=value.strip()
            decimal(value,'Customer price',optional=True)
            old=row['price']
            if value=='':
                if old:
                    values=dict(old,active='no',reason=reason);save_price(db,ident,values,old['id'])
            elif old and Decimal(value)==Decimal(old['price']):continue
            else:
                values=dict(item_key=row['item']['key'],billing=row['billing'],currency=row['currency'],price=value,reason=reason,notes=old['notes'] if old else '',start=old['start'] if old else statistics.today_local().isoformat(),finish=old['finish'] if old else '',active='yes')
                if old:values['version']=old['version']
                save_price(db,ident,values,old['id'] if old else None)
        flash('Customer prices saved. Blank inherits Cirrus defaults; explicit zero remains zero. Saved quotation prices are unchanged.')
    return redirect('/customers/'+ident+'?tab=prices')


@bp.post('/customers/<ident>/policy')
def save_policy(ident):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE');scope(db,ident,True)
        previous=db.execute('SELECT * FROM customer_preferences WHERE scope_id=?',(ident,)).fetchone()
        version=previous['version'] if previous else 0
        if request.form.get('version')!=str(version):raise ValidationError('Customer defaults changed. Reload before saving.')
        pct=request.form.get('support_percent','');decimal(pct,'Support percentage',optional=True,maximum=Decimal(100))
        base=request.form.getlist('support_base')
        if any(k.startswith('catalog:') and (r:=db.execute("SELECT data FROM records WHERE id=? AND kind='catalog'",(k[8:],)).fetchone()) and json.loads(r['data']).get('type','').casefold()=='support' for k in base):raise ValidationError('Support cannot include itself in its calculation base.')
        if len(base)>2000 or any(len(x)>150 for x in base):raise ValidationError('Invalid support base selection.')
        rule=dict(enabled=request.form.get('discount_enabled')=='yes',kind=request.form.get('discount_kind','percent'),percent=request.form.get('discount_percent','0'),amount=request.form.get('discount_amount','0'),billing=request.form.get('discount_billing','monthly'),duration=request.form.get('discount_duration','full'),months=0,wording=text(request.form.get('discount_wording',''),'Discount description'))
        try:rule['months']=int(request.form.get('discount_months','0'))
        except ValueError:raise ValidationError('Invalid promotional months.') from None
        from .quotation import default_document,validate_document
        prefs=dict(support_percent=pct,support_base=base,discount=rule)
        validate_document(apply_defaults(default_document(),prefs))
        # Validate inactive rules too, so enabling later is predictable.
        if rule['kind'] not in ('percent','fixed') or rule['billing'] not in ('monthly','one_time','both') or rule['duration'] not in ('full','temporary') or not 0<=rule['months']<=1200:raise ValidationError('Invalid discount defaults.')
        decimal(rule['percent'],'Discount percentage',maximum=Decimal(100));decimal(rule['amount'],'Fixed discount')
        db.execute('INSERT INTO customer_preferences VALUES (?,?,?,?,?) ON CONFLICT(scope_id) DO UPDATE SET version=excluded.version,data=excluded.data,at=excluded.at,actor=excluded.actor',(ident,version+1,json.dumps(prefs),stamp(),actor()))
        db.execute('INSERT INTO customer_policy_history(scope_id,at,actor,before_data,after_data) VALUES (?,?,?,?,?)',(ident,stamp(),actor(),previous['data'] if previous else None,json.dumps(prefs)))
    flash('Defaults saved for new quotations only. Existing quotations retain their saved policy.')
    return redirect('/customers/'+ident+'?tab=prices')


@bp.route('/customers/<ident>/new-quotation',methods=['GET','POST'])
def new_quote(ident):
    with connect() as db:
        customer=scope(db,ident);projects=members(db,customer)
        requested=request.values.get('workspace_id')
        if requested:
            project=next((p for p in projects if p['id']==requested),None)
            if not project:abort(404)
            security.require_record(db,project,True)
        else:
            editable=[p for p in projects if security.can_read(db,p,write=True)]
            if len(editable)>1:raise ValidationError('Choose the agreement/environment for this customer before creating a quotation.')
            project=editable[0] if editable else None
        if not project and request.method!='POST':
            flash('Use Create quotation to create this customer’s agreement workspace.')
            return redirect('/customers/'+ident)
        if not project:
            security.require_record(db,customer,True)
            db.execute('BEGIN IMMEDIATE')
            d={k:'' for k,_,_ in FIELDS['project']};d.update(name=customer['data']['name'],customer=customer['data']['name'],customer_id=customer['id'],status='Active')
            project=dict(id=store.save(db,'project',d))
    return redirect('/quotes/new?project_id='+project['id'])


@bp.route('/customers/<ident>/link',methods=['GET','POST'])
def link_workspace(ident):
    """Explicit duplicate review links a legacy workspace; never merges/deletes records."""
    with connect() as db:
        source=scope(db,ident,request.method=='POST')
        if source['kind']!='project':raise ValidationError('Existing customer records remain distinct. Review their names and project links explicitly; no automatic merge is performed.')
        if request.method=='POST':
            db.execute('BEGIN IMMEDIATE');source=scope(db,ident,True);target=record(db,request.form.get('customer_id',''),'customer',True)
            if request.form.get('confirm')!='yes':raise ValidationError('Confirm the customer link after reviewing the existing workspace.')
            before=copy.deepcopy(source['data']);values=dict(before,customer_id=target['id']);store.save(db,'project',values,ident)
            db.execute('INSERT INTO customer_policy_history(scope_id,at,actor,before_data,after_data) VALUES (?,?,?,?,?)',(target['id'],stamp(),actor(),json.dumps(dict(project_id=ident,customer_id=before.get('customer_id',''))),json.dumps(dict(project_id=ident,customer_id=target['id']))))
            flash('Existing agreement linked. Records, quotation text, prices and permissions retained; project-specific prices still take priority.')
            return redirect('/customers/'+target['id'])
        candidates=[r for r in store.records(db) if r['kind']=='customer' and security.can_read(db,r,write=True)]
    return render_template('customer_link.html',source=source,candidates=candidates)


@bp.get('/support-migration-review')
def migration_review():
    security.require_admin()
    with connect() as db:
        issues=[dict(r) for r in db.execute('SELECT * FROM support_migration_issues')]
    return render_template('support_migration_review.html',issues=issues)
