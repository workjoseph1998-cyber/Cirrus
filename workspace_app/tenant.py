"""Independent customer VM snapshots, with the general library left untouched."""
import json
from decimal import Decimal
from collections import OrderedDict
from flask import Blueprint,current_app,request,render_template,redirect,flash
from . import store,security,hosting
from .relationships import record
from .monthly import initialize_catalog
from .model import ValidationError
from uuid import uuid4
bp=Blueprint('tenant',__name__)

def entries(db,ident):
 rows=[dict(id=r['entry_id'],data=json.loads(r['data']),version=r['version']) for r in db.execute('SELECT * FROM customer_vm_catalog WHERE customer_id=?',(ident,))]
 order={name:i for i,name in enumerate(hosting.FAMILIES)}
 return sorted(rows,key=lambda r:(order.get(r['data']['family'],99),r['data']['family'],Decimal(r['data']['ram_gb']),r['data']['name']))

@bp.route('/customers/<ident>/tenant-pricing',methods=['GET','POST'])
def page(ident):
 with store.connect(current_app.config['DATA_DIR']) as db:
  if request.method=='POST':db.execute('BEGIN IMMEDIATE')
  c=record(db,ident,'customer',request.method=='POST');rows=entries(db,ident)
  error=None
  if request.method=='POST':
   for r in rows:r['data']={k:request.form.get(r['id']+'-'+k,r['data'][k]) for k,_,_ in hosting.FIELDS}
   try:
    cleaned=[]
    for r in rows:
     if str(r['version'])!=request.form.get(r['id']+'-version'):raise ValidationError('Customer catalog changed; reload before saving.')
     cleaned.append((r,hosting.validate_vm(r['data'])))
    for r,d in cleaned:db.execute('UPDATE customer_vm_catalog SET data=?,version=version+1 WHERE customer_id=? AND entry_id=?',(json.dumps(d),ident,r['id']))
    flash('Independent customer catalog saved. Historical prices remain unchanged.');return redirect(request.path)
   except ValidationError as exc:db.rollback();error=str(exc)
  groups=OrderedDict()
  for r in rows:groups.setdefault(r['data']['family'],[]).append(r)
  writable=security.can_read(db,c,write=True)
 return render_template('tenant.html',error=error,kpis=[('VM configurations',len(rows)),('Families',len(groups)),('Confirmed pricing',sum(r['data']['price_status']=='Confirmed' for r in rows)),('Both OS prices entered',sum(r['data']['cost_a']!='' and r['data']['cost_b']!='' for r in rows))],customer=c,groups=groups,writable=writable,fields=hosting.FIELDS)

def profiles_for(db,ident,source='',project=''):
 from flask import abort
 from . import hosting
 rows=store.records(db);customer=next((r for r in rows if r['kind']=='customer' and r['id']==ident),None)
 allowed=bool(customer) or any(r['kind']=='project' and r['id']==project and r['data'].get('customer_id')==ident for r in rows)
 if allowed:return entries(db,ident)
 source_row=next((r for r in rows if r['id']==source and r['kind']=='quote' and r['data'].get('customer_id')==ident),None)
 if source_row and security.can_read(db,source_row,write=True):return hosting.entries(db)
 abort(404)

@bp.get('/customers/<ident>/tenant-options')
def options(ident):
 with store.connect(current_app.config['DATA_DIR']) as db:
  profiles=profiles_for(db,ident,request.args.get('source_quote',''),request.args.get('project_id',''));cfg=store.settings(db)
  return dict(profiles=profiles,config=dict(a=cfg['hosting_cost_a_label'],b=cfg['hosting_cost_b_label'],default=cfg['hosting_default_basis']))

@bp.route('/customers/<ident>/tenant-pricing/new',methods=['GET','POST'])
@bp.route('/customers/<ident>/tenant-pricing/<entry>/edit',methods=['GET','POST'])
def edit(ident,entry=None):
 with store.connect(current_app.config['DATA_DIR']) as db:
  c=record(db,ident,'customer',True);existing=next((r for r in entries(db,ident) if r['id']==entry),None)
  if entry and not existing:raise ValidationError('Customer VM entry not found.')
  d=existing['data'] if existing else dict(name='',family='Small',vcpu='2',ram_gb='',cost_a='',cost_b='',price_status='Confirmed');error=None
  if request.method=='POST':
   d={k:request.form.get(k,'') for k,_,_ in hosting.FIELDS}
   try:
    db.execute('BEGIN IMMEDIATE')
    latest=db.execute('SELECT version FROM customer_vm_catalog WHERE customer_id=? AND entry_id=?',(ident,entry)).fetchone() if entry else None
    if existing and (not latest or request.form.get('version')!=str(latest['version'])):raise ValidationError('Entry changed; reload before saving.')
    clean=hosting.validate_vm(d)
    db.execute('INSERT INTO customer_vm_catalog VALUES (?,?,?,1) ON CONFLICT(customer_id,entry_id) DO UPDATE SET data=excluded.data,version=customer_vm_catalog.version+1',(ident,entry or str(uuid4()),json.dumps(clean)));return redirect('/customers/'+ident+'/tenant-pricing')
   except ValidationError as exc:db.rollback();error=str(exc)
 return render_template('tenant_edit.html',customer=c,d=d,row=existing,fields=hosting.FIELDS,error=error)
