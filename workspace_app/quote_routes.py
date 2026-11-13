"""Structured quotation editor and shared customer document endpoints."""
import csv
import io
import json
from uuid import uuid4
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file
from . import store, hosting,security
from .model import FIELDS, ValidationError
from .references import actor
from .quotation import default_document, legacy_document, validate_document, calculate, public_document, discount_wording, new_row, new_section,is_support,clean_generated_notice

bp=Blueprint('quotes',__name__)


def connect(): return store.connect(current_app.config['DATA_DIR'])


def get_quote(ident):
    with connect() as db:
        r=next((r for r in store.records(db) if r['id']==ident and r['kind']=='quote'),None)
        cfg=store.settings(db)
    if not r: abort(404)
    if 'document' not in r['data']: r['data']['document']=legacy_document(r['data'],cfg['company'])
    return r


def render_customer(data, standalone=True):
    doc=validate_document(data['document'], enforce_minimum=standalone)
    calc=calculate(doc)
    # Explicit public projection. Costs and internal notes never enter the template.
    meta={k:data.get(k,'') for k in ('title','customer','contact','date','valid_until','currency','number','revision','scope','project_id')}
    from .documents import filename
    from .optional_services import section_ids as optional_sections
    from .quotation_presentation import dollars,price_input,column_heading,fee_heading,visible_totals
    return render_template('quotation_document.html',export_title=filename(data.get('title','Quotation'),'pdf')[:-4],q=meta,doc=public_document(doc,calc),c=calc,
                           visible_totals=visible_totals,dollars=dollars,price_input=price_input,column_heading=column_heading,fee_heading=fee_heading,
                           optional_sections=optional_sections(doc),support_ids={r['id'] for s in doc['sections'] for r in s['rows'] if is_support(r,s)},project_name=doc['project_name'],standalone=standalone,discount_text=discount_wording(doc))


@bp.route('/quotes/new',methods=['GET','POST'])
@bp.route('/quotes/<ident>/edit',methods=['GET','POST'])
def editor(ident=None):
    if ident is None and request.method=='GET' and request.args.get('blank')!='1':
        from .quotation_setup import ensure
        with connect() as db:db.execute('BEGIN IMMEDIATE');ensure(db)
    record=get_quote(ident) if ident else None
    if ident:
        with connect() as db:security.require_id(db,ident,True)
    elif security.current_user() and security.current_user()['role']=='Viewer':abort(403)
    with connect() as db:
        cfg=store.settings(db)
        catalogs=[r for r in store.records(db) if r['kind']=='catalog' and r['data']['status']=='Active']
        from .quotation_defaults import bindings
        standard_ids=bindings(db)
        for item in catalogs:item['standard_code']=next((code for code,record_id in standard_ids.items() if record_id==item['id']),'')
        vm_profiles=hosting.entries(db)
    d=dict(record['data']) if record else {k:'' for k,_,_ in FIELDS['quote']}
    if record:
        from .outcomes import get
        from .references import key
        with connect() as db:workflow=get(db,key(d['number']))
        if workflow:d['status']=workflow['status']
    if not record:
        from .references import overview
        from .statistics import today_local
        with connect() as db:
            if request.method=='GET' and not request.args.get('reference'):
                from .references import reserve
                db.execute('BEGIN IMMEDIATE');suggested=overview(db,today_local())['next'];reserve(db,suggested)
            else:suggested=overview(db,today_local())['next']
        d.update(number=request.args.get('reference') or suggested,revision=1,date=today_local().isoformat(),currency='USD',status='Draft',tax='0',lines=[],
                 project_id=request.args.get('project_id',''),document=default_document('CIRRUS SAL' if cfg['company']=='Joseph Workspace' else cfg['company'],cfg['payment_terms'],cfg['delivery_terms']))
    if not record:
        from .company import load_template
        with connect() as db:
            d['document']=load_template(db) if request.args.get('blank')!='1' else default_document(cfg['company'],cfg['payment_terms'],cfg['delivery_terms'])
        if request.args.get('blank')=='1':
            d['document']['sections']=[new_section('Services')];d['document']['discount'].update(targets=[],enabled=False,months=0)
    d.setdefault('customer_id','')
    if not record and d.get('project_id'):
        with connect() as db:
            from .relationships import record as linked_record
            project=linked_record(db,d['project_id'],'project')
            d['document']['project_name']=project['data']['name']
            d['customer']=project['data']['customer']
            d['customer_id']=project['data'].get('customer_id','')
    if not record:
        from .support import defaults,apply_defaults
        from .relationships import record as linked_record
        with connect() as db:
            if request.args.get('customer_id') and not d.get('project_id'):
                customer=linked_record(db,request.args['customer_id'],'customer')
                d.update(customer_id=customer['id'],customer=customer['data']['name'])
            scope_id=d.get('project_id') or d.get('customer_id')
            if d.get('project_id'):
                project=linked_record(db,d['project_id'],'project')
                scope_id=project['id'] if db.execute('SELECT 1 FROM customer_preferences WHERE scope_id=?',(project['id'],)).fetchone() else project['data'].get('customer_id') or project['id']
            prefs=defaults(db,scope_id or '')
            if request.args.get('blank')!='1':
                from .quotation_setup import ensure,materialize
                d['document']=materialize(db,ensure(db),prefs)
            else:d['document']=apply_defaults(d['document'],prefs)
            from .relationships import resolve
            from .quotation_defaults import catalog_for_code
            for section in d['document']['sections']:
                for row in section['rows']:
                    item=row.get('item_key','')
                    if item.startswith('code:'):
                        matched=catalog_for_code(catalogs,item[5:])
                        item='catalog:'+matched['id'] if matched else ''
                        row['item_key']=item
                    catalog=next((x['data'] for x in catalogs if item=='catalog:'+x['id']),None)
                    if catalog:
                        for field,key in [('service','service'),('sub_service','sub_service'),('type','type'),('unit','unit'),('pricing_model','pricing_model'),('comments','comments')]:row[field]=catalog.get(key,'')
                        row['minimum_quantity']=catalog.get('minimum_quantity','0') or '0'
                        row['quantity']=catalog.get('quantity') or '1'
                        row['discount']=catalog.get('discount') or '0'
                        row['method']=catalog.get('method') or 'unit';row['billing']=catalog.get('billing') or 'monthly'
                        if row.get('vm_selection_required'):continue
                        if row['method']=='percent' and not prefs.get('support_percent'):row['percent']=catalog.get('support_percent') or '20'
                    if item.startswith(('catalog:','vm:')) and row['method'] in ('unit','fixed'):
                        try:price=resolve(db,item,row['billing'],d['currency'],d['date'],d.get('project_id',''),d.get('customer_id',''))
                        except ValidationError:continue
                        row['fixed_fee' if row['method']=='fixed' else 'unit_price']=price['price'];row['price_source']=price['source'];row['unverified_price']=not price['verified']

    if d.get('customer_id'):
        from .tenant import profiles_for as tenant_entries
        with connect() as db:vm_profiles=tenant_entries(db,d['customer_id'],ident or '',d.get('project_id','')) or vm_profiles
    if not record:
        from .documents import generated_title
        d['title']=request.args.get('title') or generated_title(d['number'],d.get('customer',''),request.args.get('subject') or d['document']['project_name'] or 'Cloud Services')
    error=None
    from . import approvals
    from .approval_routes import settings_for
    with connect() as db:
        initial_setup=settings_for(db,record)
        if not record and request.args.get('preparation'):
            prepared=db.execute('SELECT * FROM approval_preparations WHERE id=? AND user_id=?',(request.args['preparation'],actor())).fetchone()
            if not prepared or prepared['reference']!=d['number'] or prepared['customer_id']!=d['customer_id']:
                raise ValidationError('Quotation preparation is unavailable or belongs to another account. Start a new quotation.')
            initial_setup['selected_approvers']=json.loads(prepared['data'])
    if request.method=='POST':
        try:
            d=json.loads(request.form.get('quotation','{}'))
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                from .commercial import fingerprint
                from . import approvals
                if ident:
                    current=get_quote(ident)
                    if request.form.get('base_hash')!=fingerprint(current['data']):
                        raise ValidationError('Quotation changed in another session. Your entered values are retained; open the updated quotation in another tab and compare before saving again.')
                chosen=approvals.selection_from_form(request.form,initial_setup['selected_approvers'])
                if 'approvers' in request.form and 'approvers_version' not in request.form:raise ValidationError('Reload the approver selection before saving.')
                selection_saved=False
                if ident and ('approvers' in request.form or any(s in request.form for s in approvals.SLOTS)):
                    from .approval_routes import fetch
                    selection_saved=approvals.save_selection(db,fetch(db,ident,True),chosen,request.form.get('approvers_version'))
                submitting=request.form.get('intent')=='submit_review'
                if not record:
                    generic=bindings(db).get('CIR-COMPUTE')
                    if generic and any(r.get('item_key')=='catalog:'+generic and r.get('state')=='priced' and float(r.get('quantity','0'))>0 for s in d['document']['sections'] for r in s['rows']):raise ValidationError('Choose a customer VM size before saving this new quotation.')
                ident=store.save(db,'quote',d,ident,review_submission=submitting or selection_saved)
                from .approval_routes import fetch
                saved=fetch(db,ident,True)
                if not record:approvals.save_selection(db,saved,chosen)
                if submitting:
                    saved=fetch(db,ident,True);version=approvals.current_version(db,ident)
                    approvals.submit(db,saved,chosen,version['version'],version['hash'])
                if not record and request.args.get('preparation'):
                    db.execute('DELETE FROM approval_preparations WHERE id=?',(request.args['preparation'],))
            flash('Quotation saved successfully. Your changes are saved.', 'quotation_saved')
            return redirect('/quotes/'+ident+'/edit')
        except (ValueError,TypeError,RecursionError) as exc:
            error=str(exc)
            # Preserve valid editor state while displaying errors.
            if not isinstance(d,dict) or not isinstance(d.get('document'),dict): d=record['data'] if record else {}
    if not d.get('document'): abort(400,'Invalid quotation document.')
    from .commercial import fingerprint
    from .approvals import overview,private_access
    with connect() as db:
        state=overview(db,record) if record else None
        setup=initial_setup if not record else settings_for(db,record) if state['can_manage'] else {}
        if error and (not record or state['can_manage']):
            try:setup['selected_approvers']=approvals.selection_from_form(request.form,setup['selected_approvers'])
            except ValidationError:pass
        margin_allowed=private_access(db,record) if record else True
    return render_template('quotation_editor.html',d=d,record=record,error=error,catalogs=catalogs,vm_profiles=vm_profiles,approval=state,margin_allowed=margin_allowed,base_hash=request.form.get('base_hash','') if error else fingerprint(record['data']) if record else '',**setup)


@bp.post('/quotes/preview')
def preview():
    try:
        if security.current_user() and security.current_user()['role']=='Viewer':abort(403)
        d=json.loads(request.form.get('quotation','{}'))
        if not isinstance(d,dict): raise ValidationError('Invalid quotation.')
        if d.get('project_id'):
            with connect() as db:
                # A quote-only assignment may retain its private project snapshot.
                source_id=request.form.get('source_quote','')
                source=get_quote(source_id) if source_id else None
                if source:security.require_record(db,source,True)
                if not source or d['project_id']!=source['data'].get('project_id'):security.require_id(db,d['project_id'])
        html=render_customer(d,False)
        if request.form.get('editor_calculations')=='yes':
            # Keep internal percentage/base data out of customer HTML entirely.
            # This separate editor payload uses only the submitted draft and the
            # same access checks and exact calculator as the public preview.
            from .support import calculation_details
            doc=validate_document(d['document'])
            from .calculation_explanations import explanations
            return dict(html=html,fees=calculation_details(doc,calculate(doc)),explanations=explanations(doc))
        return html
    except (ValueError,TypeError,KeyError,RecursionError) as exc:
        return str(exc),400,{'Content-Type':'text/plain; charset=utf-8'}


@bp.route('/quotes/<ident>/print')
def printable(ident):
    d=get_quote(ident)['data']
    from .documents import export_event
    export_event(ident,'Print / PDF view opened')
    return render_customer(d)


@bp.route('/quotes/<ident>/xlsx')
def excel(ident):
    from .quote_excel import export_excel
    d=get_quote(ident)['data']
    from .documents import filename,export_event
    result=export_excel(d);export_event(ident,'Excel')
    return send_file(result,as_attachment=True,download_name=filename(d['title'],'xlsx'),mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@bp.route('/quotes/<ident>/csv')
def export_csv(ident):
    d=get_quote(ident)['data'];original=validate_document(d['document'], enforce_minimum=True);calc=calculate(original);public=public_document(original,calc);out=io.StringIO(newline='');w=csv.writer(out)
    from .quotation_presentation import column_heading,fee_heading
    def safe(v):
        s=str(v) if v is not None else ''
        return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s
    w.writerow(['Section','Service','Sub Service','Type','Quantity','Pricing Model',safe(column_heading(public,'unit_price')),'Billing','State',safe(column_heading(public,'amount')),'Currency','Comments'])
    for s in public['sections']:
        if s['hidden'] or any(x['id']==s['parent'] and x['hidden'] for x in public['sections']): continue
        for r in s['rows']:
            w.writerow([safe(x) for x in [s['name'],r['service'],r['sub_service'],r['type'],r['quantity'],'' if is_support(r,s) else r['pricing_model'],'' if is_support(r,s) else r['unit_price'],r['billing'],r['state'],calc['rows'][r['id']],d['currency'],clean_generated_notice(r['comments'])]])
    w.writerow([])
    w.writerow(['Cost Summary',safe(fee_heading(public,'monthly'))]+([str(min(12,original['contract_months']))+' months'] if original['show_12_month'] else [])+[safe(fee_heading(public,'one_time'))])
    from .optional_services import section_ids as optional_sections
    for section in public['sections']:
        if not section['parent'] and not section['hidden'] and section['id'] not in optional_sections(original):
            w.writerow([safe(section['name']),calc['sections'][section['id']]]+([calc['sections_yearly'][section['id']]] if original['show_12_month'] else [])+[calc['sections_once'][section['id']]])
    if original['discount']['enabled'] and original['discount']['show_summary']:
        summary=[('Original monthly fee','regular'),('Original one-time fee','original_one_time')]
        if original['discount']['billing'] in ('monthly','both'):
            summary.extend([('Discount per promotional month (deduction)','discount'),('Promotional monthly fee','discounted')])
            if int(calc['discount_extra_months']):summary.append(('Later promotional monthly fee','discounted_final'))
            if int(calc['discount_months'])<original['contract_months']:summary.append(('Regular monthly fee afterward','regular'))
        if original['discount']['billing'] in ('one_time','both'):summary.append(('One-time discount (deduction)','one_time_discount'))
        summary.append(('Total one-time fee','one_time'))
        for label,key in summary:w.writerow([safe(x) for x in ['Cost Summary',label,'','','','','','','',calc[key],d['currency'],discount_wording(original)]])
    from .documents import filename,export_event
    export_event(ident,'CSV')
    if calc['optional']['rows']:
        w.writerow([]);w.writerow(['Optional service','Monthly fee','Yearly fee (12 months)','One-time fee'])
        w.writerow([calc['optional']['label'],calc['optional']['monthly'],calc['optional']['yearly'],calc['optional']['one_time']])
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')),as_attachment=True,download_name=filename(d['title'],'csv'),mimetype='text/csv')


@bp.post('/quotes/catalog')
def save_catalog():
    """Optional custom row → catalog snapshot; never modifies a quote implicitly."""
    security.require_admin()
    try:
        payload=json.loads(request.form['item']);r=payload['row']
        values={k:'' for k,_,_ in FIELDS['catalog']}
        if r['method']=='percent':raise ValidationError('Quotation-specific percentage dependencies cannot be stored in a catalog item. Use Copy row to preserve them.')
        values.update(code=payload['code'],name=r['service'],description=r['sub_service'],unit=r['unit'] or 'unit',
                      type=r['type'],comments=r['comments'],pricing_model=r['pricing_model'],billing=r['billing'],method=r['method'],
                      fixed_fee=r['fixed_fee'] if not r.get('unverified_price') else '',minimum_quantity=r.get('minimum_quantity','0'),quantity='1',discount=r['discount'],
                      price=r['unit_price'] if r['method']=='unit' and not r.get('unverified_price') else '',cost=r.get('cost',''),currency=payload['currency'],status='Active')
        with connect() as db:
            db.execute('BEGIN IMMEDIATE');ident=store.save(db,'catalog',values)
            clean=next(r for r in store.records(db) if r['id']==ident)['data']
        return {'id':ident,'item':{'id':ident,'data':clean},'message':'Catalog item saved, including Type, Comments and pricing settings. It is available in the picker now.'}
    except (ValueError,KeyError,TypeError) as exc:
        return {'error':str(exc)},400
