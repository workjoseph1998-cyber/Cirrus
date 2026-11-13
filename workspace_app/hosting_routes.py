"""Hosting VM management independent of quotation snapshots."""
from collections import OrderedDict
from flask import Blueprint,abort,current_app,flash,redirect,render_template,request
from . import hosting,store
from .model import ValidationError

bp=Blueprint('hosting',__name__)
def connect():return store.connect(current_app.config['DATA_DIR'])

@bp.get('/hosting-vms/options')
def options():
    with connect() as db:
        cfg=store.settings(db)
        return {'profiles':hosting.entries(db),'config':{'a':cfg['hosting_cost_a_label'],'b':cfg['hosting_cost_b_label'],'default':cfg['hosting_default_basis']}}

@bp.route('/hosting-vms')
def listing():
    with connect() as db:rows=hosting.entries(db)
    groups=OrderedDict()
    search=request.args.get('q','').casefold()
    for item in rows:
        if search and search not in (item['data']['name']+' '+item['data']['family']).casefold():continue
        groups.setdefault(item['data']['family'],[]).append(item)
    kpis=[('VM configurations',len(rows)),('Families',len({r['data']['family'] for r in rows})),('Confirmed pricing',sum(r['data']['price_status']=='Confirmed' for r in rows)),('Both OS prices entered',sum(r['data']['cost_a']!='' and r['data']['cost_b']!='' for r in rows))]
    return render_template('hosting.html',groups=groups,kpis=kpis)

@bp.route('/hosting-vms/new',methods=['GET','POST'])
@bp.route('/hosting-vms/<ident>/edit',methods=['GET','POST'])
def edit(ident=None):
    with connect() as db:row=next((r for r in hosting.entries(db) if r['id']==ident),None) if ident else None
    if ident and not row:abort(404)
    d=row['data'] if row else dict(name='',family='Small',vcpu='2',ram_gb='',cost_a='',cost_b='',price_status='Confirmed')
    error=None
    if request.method=='POST':
        d={k:request.form.get(k,'') for k,_,_ in hosting.FIELDS}
        try:
            with connect() as db:
                db.execute('BEGIN IMMEDIATE');hosting.save(db,d,ident)
            flash('VM profile saved. Existing quotations keep their saved specifications and price.')
            return redirect('/hosting-vms')
        except ValidationError as exc:error=str(exc)
    return render_template('hosting_edit.html',d=d,row=row,fields=hosting.FIELDS,error=error)

@bp.post('/hosting-vms/prices')
def prices():
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for row in hosting.entries(db):
            prefix=row['id']+'-'
            if prefix+'cost_a' not in request.form:continue
            d=dict(row['data'])
            for k in ('cost_a','cost_b','price_status'):d[k]=request.form.get(prefix+k,'')
            hosting.save(db,d,row['id'])
    flash('Prices saved. Change Demo to Confirmed after reviewing your real costs.')
    return redirect('/hosting-vms')

@bp.post('/hosting-vms/settings')
def settings():
    with connect() as db:
        for k in hosting.CONFIG:
            v=request.form.get(k,'').strip()
            if not v or len(v)>80 or (k=='hosting_default_basis' and v not in ('a','b')):raise ValidationError('Invalid VM cost settings.')
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,v))
    return redirect('/hosting-vms')

@bp.post('/hosting-vms/<ident>/delete')
def delete(ident):
    with connect() as db:
        if not db.execute('SELECT 1 FROM hosting_vms WHERE id=?',(ident,)).fetchone():abort(404)
        db.execute('DELETE FROM hosting_vms WHERE id=?',(ident,))
    flash('VM profile removed. Saved quotation rows remain unchanged.')
    return redirect('/hosting-vms')
