"""Revision-specific private purchasing worksheet and explicit, stale-checked price application."""
import copy,json
from datetime import date
from decimal import Decimal
from flask import Blueprint,abort,current_app,flash,g,redirect,render_template,request
from . import store,security
from .model import ValidationError,decimal
from .quotation import validate_document,calculate
from .commercial import fingerprint,line_values,eligible_rows,rounded,amount
from .references import key,stamp,actor
from .outcomes import event

bp=Blueprint('costing',__name__)
EDITABLE=('description','quantity','supplier','supplier_reference','unit_purchase','purchase_basis','shipping','documentation','implementation','other','selling_unit','target_margin','valid_until','notes')
MONEY=('unit_purchase','shipping','documentation','implementation','other','selling_unit')


def require_staff(db,record):
    security.require_record(db,record,True)
    from .approvals import private_access
    if not private_access(db,record):abort(404)
    if security.enabled() and (not g.user or g.user['role'] not in ('Administrator','Editor')):abort(404)


def source_rows(q):return [(s,r) for s in q['document']['sections'] for r in s['rows']]


def load(db,record):
    saved=db.execute('SELECT * FROM quote_costing WHERE quote_id=?',(record['id'],)).fetchone();payload=json.loads(saved['data']) if saved else {'rows':[],'orphaned':[]}
    old={r['id']:r for r in payload['rows']};q=record['data'];result=[]
    for section,r in source_rows(q):
        existing=old.pop(r['id'],None)
        row=dict(id=r['id'],description=r['service']+' / '+r['sub_service'],quantity=r['quantity'],supplier='',supplier_reference='',unit_purchase=r.get('cost',''),purchase_basis=r['billing'],shipping='0',documentation='0',implementation='0',other='0',selling_unit=r['fixed_fee'] if r['method']=='fixed' else r['unit_price'],target_margin='',valid_until='',notes='')
        if existing:row.update({k:existing[k] for k in EDITABLE})
        row.update(method=r['method'],billing=r['billing'],quote_quantity=r['quantity'],section=section['name'])
        result.append(row)
    orphaned=payload.get('orphaned',[])+list(old.values())
    return dict(rows=result,orphaned=orphaned,version=saved['version'] if saved else 0,quote_hash=fingerprint(q))


def validate(payload,record):
    if not isinstance(payload,dict) or set(payload)!={'rows'} or not isinstance(payload['rows'],list):raise ValidationError('Invalid costing worksheet.')
    ids={r['id'] for _,r in source_rows(record['data'])}
    if any(not isinstance(r,dict) or not isinstance(r.get('id'),str) for r in payload['rows']):raise ValidationError('Invalid costing item identity.')
    if len(payload['rows'])!=len(ids) or {r.get('id') for r in payload['rows'] if isinstance(r,dict)}!=ids:raise ValidationError('Quotation rows changed; reload the worksheet.')
    result=[]
    for row in payload['rows']:
        if not isinstance(row,dict) or set(row)!={'id',*EDITABLE}:raise ValidationError('Invalid costing row fields.')
        clean=dict(row)
        for name in EDITABLE:
            if not isinstance(row[name],str) or len(row[name])>100000:raise ValidationError('Costing values must be text, at most 100,000 characters.')
            clean[name]=row[name].strip()
        decimal(clean['quantity'],'Purchase quantity',maximum=Decimal(1000000))
        for name in MONEY:decimal(clean[name],name,optional=name in ('unit_purchase','selling_unit'))
        if clean['purchase_basis'] not in ('monthly','one_time'):raise ValidationError('Choose monthly or one-time purchase cost.')
        target=decimal(clean['target_margin'],'Target margin',optional=True,maximum=Decimal(100))
        if target is not None and target>=100:raise ValidationError('Target margin must be at least 0 and below 100%. Margin is not markup.')
        if clean['valid_until']:
            try:date.fromisoformat(clean['valid_until'])
            except ValueError:raise ValidationError('Invalid supplier price validity date.') from None
        result.append(clean)
    return result


def proposed(record,rows):
    q=copy.deepcopy(record['data']);mapping={r['id']:r for r in rows}
    for _,r in source_rows(q):
        if r['method']=='percent':continue
        field='fixed_fee' if r['method']=='fixed' else 'unit_price';value=mapping[r['id']]['selling_unit']
        if r[field]!=value:r[field]=value;r['unverified_price']=False if value!='' else r.get('unverified_price',False)
    q['document']=validate_document(q['document']);return q


def _calculate_sheet(record,sheet):
    q=record['data'];candidate=proposed(record,sheet['rows']);values=line_values(candidate);months=q['document']['contract_months'];result=[];costs=[];selling=[]
    from .optional_services import row_ids
    optional=row_ids(q['document'])
    source={r['id']:r for _,r in source_rows(q)};eligible=eligible_rows(q['document'])
    sections={s['id']:s for s in q['document']['sections']};inactive={r['id'] for s,r in source_rows(q) if r['state'] in ('excluded','included') or s['excluded'] or (s['parent'] and sections[s['parent']]['excluded'])}
    for row in sheet['rows']:
        r=source[row['id']];qty=decimal(row['quantity'],'Quantity');unit=decimal(row['unit_purchase'],'Cost',optional=True)
        extras=sum((decimal(row[k],k) for k in ('shipping','documentation','implementation','other')),Decimal(0))
        cost=None if qty!=0 and unit is None else rounded(qty*(unit or 0)*(months if row['purchase_basis']=='monthly' else 1)+extras)
        sell=values[row['id']];profit=None if cost is None or sell is None else rounded(sell-cost);margin=None if profit is None or sell==0 else rounded(profit/sell*100)
        target=decimal(row['target_margin'],'Target margin',optional=True);suggested=None if cost is None or target is None else rounded(cost/(1-target/100))
        factor=Decimal(r['quantity']) if r['method']=='unit' else Decimal(1) if Decimal(r['quantity']) else Decimal(0)
        if r['id'] in inactive:factor=Decimal(0)
        factor*=1-Decimal(r['discount'])/100
        if r['billing']=='monthly':
            rule=q['document']['discount']
            duration=(months if rule.get('duration')=='full' else rule['months']) if rule['enabled'] and rule.get('billing','monthly') in ('monthly','both') and r['id'] in eligible else 0
            factor*=months-duration*Decimal(rule['percent'])/100
        elif q['document']['discount']['enabled'] and q['document']['discount'].get('billing') in ('one_time','both') and r['id'] in eligible:
            factor*=1-Decimal(q['document']['discount']['percent'])/100
        # A fixed summary budget is shared across rows. An independent unit-price
        # suggestion cannot solve that allocation safely; use explicit prices.
        if q['document']['discount']['enabled'] and q['document']['discount'].get('kind')=='fixed':factor=Decimal(0)
        if q['document']['tax']['mode']=='included':factor/=1+Decimal(q['document']['tax']['rate'])/100
        driver=rounded(suggested/factor) if suggested is not None and factor>0 and r['method']!='percent' else None
        result.append(dict(row,cost=cost,selling=sell,profit=profit,margin=margin,suggested=suggested,suggested_unit=driver,method=r['method'],quote_quantity=r['quantity'],billing=r['billing']))
        if row['id'] not in optional:costs.append(cost);selling.append(sell)
    total_cost=None if any(x is None for x in costs) else sum(costs,Decimal(0));total_selling=None if any(x is None for x in selling) else sum(selling,Decimal(0))
    profit=None if total_cost is None or total_selling is None else total_selling-total_cost
    margin=None if profit is None or total_selling==0 else rounded(profit/total_selling*100)
    return dict(rows=result,cost=total_cost,selling=total_selling,profit=profit,margin=margin,candidate=candidate)


def calculate_sheet(record,sheet):
    try:return _calculate_sheet(record,sheet)
    except ArithmeticError:raise ValidationError('Costing values exceed supported precision; reduce the values or target margin.') from None


def save(db,record,fields):
    if fields.get('quote_hash')!=fingerprint(record['data']):raise ValidationError('Quotation changed since this worksheet opened. Reload before saving.')
    sheet=load(db,record)
    try:version=int(fields.get('version',''))
    except ValueError:raise ValidationError('Invalid costing version.') from None
    if version!=sheet['version']:raise ValidationError('Costing changed in another session. Reload before saving.')
    try:payload=json.loads(fields.get('costing',''))
    except (ValueError,RecursionError):raise ValidationError('Invalid costing JSON.') from None
    rows=validate(payload,record)
    data=json.dumps(dict(rows=rows,orphaned=sheet['orphaned']))
    db.execute('INSERT INTO quote_costing VALUES (?,?,?,?,?) ON CONFLICT(quote_id) DO UPDATE SET version=excluded.version,data=excluded.data,updated=excluded.updated,updated_by=excluded.updated_by',(record['id'],version+1,data,stamp(),actor()))
    return dict(sheet,rows=rows,version=version+1)


@bp.route('/quotes/<ident>/costing',methods=['GET','POST'])
def page(ident):
    from .quote_routes import get_quote
    record=get_quote(ident)
    with store.connect(current_app.config['DATA_DIR']) as db:
        require_staff(db,record)
        if request.method=='POST':
            db.execute('BEGIN IMMEDIATE')
            record=get_quote(ident);require_staff(db,record);sheet=save(db,record,request.form)
            if request.form.get('action')=='suggest':
                result=calculate_sheet(record,sheet)
                for row in sheet['rows']:
                    calculated=next(x for x in result['rows'] if x['id']==row['id'])
                    if calculated['suggested_unit'] is not None:row['selling_unit']=str(calculated['suggested_unit'])
                db.execute('UPDATE quote_costing SET data=? WHERE quote_id=?',(json.dumps(dict(rows=sheet['rows'],orphaned=sheet['orphaned'])),ident))
                flash('Suggested selling prices saved only in this internal worksheet. Preview and explicitly apply to change the quotation.')
            else:flash('Internal costing saved. Customer quotation prices were not changed.')
            return redirect('/quotes/'+ident+'/costing')
        sheet=load(db,record);result=calculate_sheet(record,sheet)
    return render_template('costing.html',record=record,sheet=sheet,result=result,editable=EDITABLE,actual_quote_total=amount(record['data']))


@bp.route('/quotes/<ident>/costing/apply',methods=['GET','POST'])
def apply(ident):
    from .quote_routes import get_quote
    record=get_quote(ident)
    with store.connect(current_app.config['DATA_DIR']) as db:
        require_staff(db,record)
        if request.method=='POST':
            db.execute('BEGIN IMMEDIATE');record=get_quote(ident);require_staff(db,record)
        sheet=load(db,record);result=calculate_sheet(record,sheet);candidate=result['candidate']
        original=calculate(record['data']['document']);changed=calculate(candidate['document']);oldrows={r['id']:r for _,r in source_rows(record['data'])}
        changes=[]
        for _,r in source_rows(candidate):
            old=oldrows[r['id']];field='fixed_fee' if r['method']=='fixed' else 'unit_price'
            if old[field]!=r[field] or original['rows'][r['id']]!=changed['rows'][r['id']]:changes.append(dict(description=r['service']+' / '+r['sub_service'],before=old[field],after=r[field],old_total=original['rows'][r['id']],new_total=changed['rows'][r['id']]))
        if request.method=='POST':
            if request.form.get('quote_hash')!=fingerprint(record['data']) or request.form.get('version')!=str(sheet['version']):raise ValidationError('Quotation or costing changed after the preview. Reload and review the changes again.')
            if request.form.get('confirm')!='yes':raise ValidationError('Explicitly confirm the previewed selling price changes.')
            from .outcomes import get
            outcome=get(db,key(record['data']['number']))
            if outcome and outcome['status']=='Won' and outcome['accepted_quote_id']==ident:raise ValidationError('Create a new revision before repricing the accepted Won revision. The accepted value is frozen.')
            store.save(db,'quote',candidate,ident)
            event(db,key(record['data']['number']),ident,'Internal selling prices applied',dict(quote_total=str(amount(record['data']))),dict(quote_total=str(amount(candidate))))
            flash('Selling prices explicitly applied. Purchase costs, supplier data and margin were not copied into customer fields.')
            return redirect('/quotes/'+ident+'/edit')
    return render_template('costing_apply.html',record=record,sheet=sheet,changes=changes,old_total=amount(record['data']),new_total=amount(candidate))


@bp.post('/quotes/<ident>/costing/calculate')
def preview(ident):
    from .quote_routes import get_quote
    record=get_quote(ident)
    with store.connect(current_app.config['DATA_DIR']) as db:require_staff(db,record)
    if request.form.get('quote_hash')!=fingerprint(record['data']):raise ValidationError('Quotation changed; reload this worksheet.')
    try:payload=json.loads(request.form.get('costing',''))
    except (ValueError,RecursionError):raise ValidationError('Invalid costing JSON.') from None
    data=dict(rows=validate(payload,record));result=calculate_sheet(record,data)
    def value(x):return None if x is None else str(x)
    return dict(rows=[{k:value(r[k]) for k in ('id','cost','selling','profit','margin','suggested','suggested_unit')} for r in result['rows']],summary={k:value(result[k]) for k in ('cost','selling','profit','margin')})
