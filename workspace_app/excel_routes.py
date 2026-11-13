"""Owned, expiring staged Excel imports with explicit atomic confirmation."""
import base64,json,secrets,time
from uuid import uuid4
from flask import Blueprint,abort,current_app,flash,g,redirect,render_template,request
from . import store,security,excel_import
from .model import ValidationError
from .references import key
from .quotation import validate_document,calculate

bp=Blueprint('excel',__name__)
def connect():return store.connect(current_app.config['DATA_DIR'])


def job(db,ident):
    row=db.execute('SELECT * FROM import_jobs WHERE id=? AND user_id=? AND created>?',(ident,g.user['id'],time.time()-3600)).fetchone()
    if not row:abort(404)
    return json.loads(row['data'])


@bp.route('/excel-import',methods=['GET','POST'])
def upload():
    if g.user['role']=='Viewer':abort(403)
    if request.method=='POST':
        f=request.files.get('file')
        if not f or not f.filename.lower().endswith('.xlsx'):raise ValidationError('Upload a Cirrus .xlsx quotation.')
        raw=f.read(excel_import.MAX_BYTES+1)
        book,_=excel_import.load(raw)
        ident=secrets.token_urlsafe(24)
        # Worksheet selection occurs explicitly before parsing when multiple sheets exist.
        payload={'raw':base64.b64encode(raw).decode(),'sheets':book.sheetnames,'selected':None,'parsed':None}
        if len(book.sheetnames)==1:
            payload['selected']=book.sheetnames[0]
            try:payload['parsed']=excel_import.parse(raw,book.sheetnames[0])
            except ValidationError as exc:
                payload['error']=str(exc)
                try:payload['mapping']=excel_import.mapping_for(book[book.sheetnames[0]])
                except ValidationError:payload['mapping']=None
        with connect() as db:
            db.execute('DELETE FROM import_jobs WHERE created<?',(time.time()-3600,))
            db.execute('INSERT INTO import_jobs VALUES (?,?,?,?,?)',(ident,g.user['id'],time.time(),None,json.dumps(payload)))
        return redirect('/excel-import/'+ident)
    return render_template('excel_upload.html')


@bp.route('/excel-import/<ident>',methods=['GET','POST'])
def review(ident):
    if g.user['role']=='Viewer':abort(403)
    with connect() as db:payload=job(db,ident)
    if request.method=='POST':
        action=request.form.get('action')
        if action=='cancel':
            with connect() as db:db.execute('DELETE FROM import_jobs WHERE id=? AND user_id=?',(ident,g.user['id']))
            flash('Excel import cancelled; no quotation was saved.');return redirect('/list/quote')
        if action=='map':
            try:mapping=json.loads(request.form['mapping']) if request.form.get('mapping') else None
            except ValueError:raise ValidationError('Invalid mapping JSON.') from None
            selected=request.form.get('sheet')
            try:
                parsed=excel_import.parse(base64.b64decode(payload['raw']),selected,mapping)
                payload.update(selected=selected,parsed=parsed,error=None)
            except ValidationError as exc:payload.update(selected=selected,parsed=None,mapping=mapping,error=str(exc))
            with connect() as db:db.execute('UPDATE import_jobs SET data=? WHERE id=? AND user_id=?',(json.dumps(payload),ident,g.user['id']))
            return redirect('/excel-import/'+ident)
        if action=='confirm':
            if not payload['parsed']:raise ValidationError('Select and map a worksheet first.')
            parsed=payload['parsed']
            try:q=json.loads(request.form.get('quotation','{}'))
            except ValueError:raise ValidationError('Invalid quotation JSON.') from None
            if not isinstance(q,dict) or not isinstance(q.get('document'),dict):raise ValidationError('Invalid quotation structure.')
            doc=q['document'];rows={r['id']:r for s in doc.get('sections',[]) for r in s.get('rows',[])}
            for issue in parsed['issues']:
                answer=request.form.get('resolution-'+issue['id'])
                if issue['kind']=='price':
                    r=rows.get(issue['row_id'])
                    if not r:continue # Explicit row removal in the editor resolves that row.
                    if answer=='unpriced':r.update(method='unit',unit_price='',fixed_fee='',targets=[])
                    elif answer=='edited':
                        if r.get('method')=='fixed' and r.get('fixed_fee','')=='':raise ValidationError('Enter a fixed fee for '+issue['source'])
                        if r.get('method')=='unit' and r.get('unit_price','')=='':raise ValidationError('Enter a unit price for '+issue['source'])
                    elif answer=='excluded':r['state']='excluded'
                    else:raise ValidationError('Resolve pricing issue '+issue['source'])
                elif answer!='reviewed':raise ValidationError('Review issue '+issue['source'])
            selected=request.form.getlist('zero_unpriced')
            if selected and request.form.get('redacted')!='yes':raise ValidationError('Enable redacted-template treatment explicitly before converting zero prices.')
            for rid in selected:
                if rid not in parsed['zero_rows'] or rid not in rows:raise ValidationError('Invalid selected zero row.')
                r=rows[rid]
                if r.get('method')=='fixed' and r.get('fixed_fee')=='0':r['fixed_fee']=''
                elif r.get('unit_price')=='0':r['unit_price']=''
            q['document']=validate_document(doc)
            q['status']='Draft'
            fp=parsed['fingerprint']+':'+parsed['sheet']
            with connect() as db:
                db.execute('BEGIN IMMEDIATE');job(db,ident) # Defend against replay/concurrent confirmation.
                previous=db.execute('SELECT record_id FROM excel_imports WHERE fingerprint=? AND user_id=?',(fp,g.user['id'])).fetchall()
                mode=request.form.get('mode','new')
                if previous and request.form.get('duplicate_ack')!='yes':raise ValidationError('This worksheet was imported before. Acknowledge an intentional new draft/revision.')
                if mode=='revision':
                    base=request.form.get('revision_of')
                    security.require_id(db,base,True)
                    old=next((r for r in store.records(db) if r['id']==base and r['kind']=='quote'),None)
                    if not old:raise ValidationError('Select a quotation to revise.')
                    q['number']=old['data']['number'];q['project_id']=old['data'].get('project_id','')
                    q['revision']=max(r['data']['revision'] for r in store.records(db,unrestricted=True) if r['kind']=='quote' and key(r['data']['number'])==key(q['number']))+1
                elif mode=='new':
                    q['revision']=1
                    if any(r['kind']=='quote' and key(r['data']['number'])==key(q.get('number','')) for r in store.records(db,unrestricted=True)):q['number']='Q-'+uuid4().hex[:12].upper()
                else:raise ValidationError('Invalid import mode.')
                new_id=store.save(db,'quote',q,inherit_from=request.form.get('revision_of') if mode=='revision' else None,reference_import=True)
                db.execute('INSERT INTO excel_imports VALUES (?,?,?)',(fp,g.user['id'],new_id))
                db.execute('DELETE FROM import_jobs WHERE id=? AND user_id=?',(ident,g.user['id']))
            flash('Excel quotation imported as a new private draft. Company catalog/template unchanged.')
            return redirect('/quotes/'+new_id+'/edit')
        raise ValidationError('Invalid import action.')
    with connect() as db:
        quotes=[r for r in store.records(db) if r['kind']=='quote' and security.can_read(db,r,write=True)]
        previous=[]
        if payload['parsed']:previous=db.execute('SELECT record_id FROM excel_imports WHERE fingerprint=? AND user_id=?',(payload['parsed']['fingerprint']+':'+payload['parsed']['sheet'],g.user['id'])).fetchall()
    return render_template('excel_review.html',ident=ident,payload=payload,parsed=payload['parsed'],previous=previous,quotes=quotes)


@bp.route('/excel-import/<ident>/edit',methods=['GET','POST'])
def edit_stage(ident):
    if g.user['role']=='Viewer':abort(403)
    with connect() as db:
        payload=job(db,ident)
        if not payload['parsed']:raise ValidationError('Select a worksheet first.')
        parsed=payload['parsed'];cfg=store.settings(db)
        catalogs=[r for r in store.records(db) if r['kind']=='catalog' and r['data']['status']=='Active']
        from .hosting import entries
        profiles=entries(db)
        if request.method=='POST':
            try:q=json.loads(request.form.get('quotation','{}'))
            except ValueError:raise ValidationError('Invalid draft JSON.') from None
            from .model import validate
            reference=q.get('number','')
            validation=dict(q,number='STAGING-'+uuid4().hex[:12])
            clean=validate('quote',validation,store.records(db));clean['number']=reference
            payload['parsed']['quotation']=clean
            db.execute('UPDATE import_jobs SET data=? WHERE id=? AND user_id=?',(json.dumps(payload),ident,g.user['id']))
            flash('Import staging draft updated. Review/resolve issues and confirm to create a quotation.')
            return redirect('/excel-import/'+ident)
    return render_template('quotation_editor.html',d=parsed['quotation'],record=None,error=None,catalogs=catalogs,vm_profiles=profiles,
                           save_label='Update import draft',return_url='/excel-import/'+ident,staging=True)
