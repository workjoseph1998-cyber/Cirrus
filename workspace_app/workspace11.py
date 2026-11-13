"""Focused customer workspaces, attention lists, and guarded administration."""
import json
from flask import Blueprint,current_app,request,render_template,redirect,flash
from . import store,security,statistics
from .relationships import record
from .model import ValidationError
from .commercial import fingerprint
from .references import key
bp=Blueprint('workspace11',__name__)

def dependencies(db,ident):
 result=[]
 for r in store.records(db,unrestricted=True):
  if r['id']!=ident and ident in (r['data'].get('customer_id'),r['data'].get('project_id')):result.append(r['kind']+': '+r['data'].get('title',r['data'].get('name','')))
 for table,col in [('monthly_snapshots','customer_id'),('monthly_history','customer_id'),('agreed_prices','scope_id'),('customer_preferences','scope_id'),('customer_policy_history','scope_id'),('customer_document_spaces','customer_id'),('customer_document_audit','customer_id')]:
  if db.execute('SELECT 1 FROM '+table+' WHERE '+col+'=?',(ident,)).fetchone():result.append(table.replace('_',' '))
 if db.execute('SELECT 1 FROM attachments WHERE record_id=?',(ident,)).fetchone():result.append('attachments')
 return result

def customer_context(db,c):
 visible=store.records(db);projects={r['id'] for r in visible if r['kind']=='project' and (r['id']==c['id'] or r['data'].get('customer_id')==c['id'])}
 docs=[r for r in visible if r['data'].get('customer_id')==c['id'] or r['data'].get('project_id') in projects or r['id'] in projects]
 follow=[dict(r) for r in db.execute('SELECT m.*,r.data FROM document_management m JOIN records r ON r.id=m.record_id WHERE follow_date<>? ORDER BY follow_date',('',)) if any(d['id']==r['record_id'] for d in docs)]
 archived=db.execute('SELECT archived FROM customer_archives WHERE customer_id=?',(c['id'],)).fetchone()
 return dict(archived_customer=bool(archived and archived['archived']),customer_documents=docs,customer_followups=follow)

def dashboard():
 from .outcomes import visible
 with store.connect(current_app.config['DATA_DIR']) as db:
  from .approvals import my_work
  from .references import actor
  work=my_work(db,actor())
  email_failures=db.execute("SELECT count(*) FROM notification_emails WHERE status='failed'").fetchone()[0] if security.admin() else 0
  artifact_failures=db.execute("SELECT count(*) FROM approval_artifacts WHERE status='failed'").fetchone()[0] if security.admin() else 0
  rows=store.records(db);stats=statistics.quotations(rows,{'period':'all'},outcomes=visible(db,rows));ids={r['id'] for r in rows}
  follows=[dict(r) for r in db.execute('SELECT m.*,r.data FROM document_management m JOIN records r ON r.id=m.record_id WHERE follow_date<>? ORDER BY follow_date',('',)) if r['record_id'] in ids]
  failures=[dict(r) for r in db.execute("SELECT p.*,r.data FROM pdf_exports p JOIN records r ON r.id=p.record_id WHERE status IN ('failed','not_configured')") if r['record_id'] in ids]
  from .documents import latest
  from .v21 import validity
  quotes=[r for r in latest(rows) if r['kind']=='quote']
  active_quotes=sum(r['data'].get('status') not in ('Cancelled','Lost','Won') for r in quotes)
  expiring_quotes=sum(validity(r)['status']=='Expiring Soon' for r in quotes)
  month=statistics.today_local().isoformat()[:7]
  from .statistics import local_date
  sent_ids={r['quote_id'] for r in db.execute('SELECT quote_id,at FROM quotation_sent_events') if local_date(r['at']).isoformat().startswith(month)}
  sent_month=sum(r['id'] in sent_ids for r in quotes)
  from .automation import backup_state
  backup=backup_state(db) if security.admin() else {}
 return render_template('dashboard11.html',active_quotes=active_quotes,expiring_quotes=expiring_quotes,sent_month=sent_month,approval_work=work,email_failures=email_failures,artifact_failures=artifact_failures,stats=stats,recent=[r for r in rows if r['kind']=='quote'][:8],projects_active=[r for r in rows if r['kind']=='project' and r['data']['status']=='Active'],follows=follows,failures=failures,backup=backup,today=statistics.today_local().isoformat())

@bp.route('/customers/<ident>/delete-review',methods=['GET','POST'])
def delete_customer(ident):
 security.require_admin()
 with store.connect(current_app.config['DATA_DIR']) as db:
  db.execute('BEGIN IMMEDIATE');c=record(db,ident,'customer');deps=dependencies(db,ident);token=fingerprint(dict(customer=c,dependencies=deps))
  if request.method=='POST':
   if request.form.get('token')!=token:raise ValidationError('Dependencies changed; review again.')
   if request.form.get('action') in ('archive','restore'):
    db.execute('INSERT INTO customer_archives VALUES (?,?) ON CONFLICT(customer_id) DO UPDATE SET archived=excluded.archived',(ident,int(request.form['action']=='archive')));flash('Customer visibility updated; records and files retained.');return redirect('/customers')
   if deps:raise ValidationError('Business history prevents permanent deletion. Archive the customer or explicitly reassign records first.')
   if request.form.get('phrase')!='DELETE':raise ValidationError('Type DELETE to confirm.')
   for table,col in [('customer_vm_catalog','customer_id'),('customer_archives','customer_id'),('monthly_drafts','customer_id'),('record_acl','record_id')]:db.execute('DELETE FROM '+table+' WHERE '+col+'=?',(ident,))
   db.execute('DELETE FROM records WHERE id=?',(ident,));flash('Customer removed. External files were not deleted.');return redirect('/customers')
 return render_template('customer_delete.html',customer=c,dependencies=deps,token=token)

@bp.get('/customers/<ident>/consumption/pricing')
def prices(ident):
 from .tenant import entries
 with store.connect(current_app.config['DATA_DIR']) as db:
  record(db,ident,'customer',True);vm=entries(db,ident);items=[]
  for r in vm:
   for os,k in [('Linux','cost_a'),('Windows','cost_b')]:items.append(dict(key='vm:'+r['id']+':'+('a' if k=='cost_a' else 'b'),label=r['data']['name']+' / '+os,price=r['data'][k] if r['data']['price_status']=='Confirmed' else ''))
  from .relationships import item_options,resolve
  for item in item_options(db):
   if not item['key'].startswith('catalog:'):continue
   p=resolve(db,item['key'],'monthly','USD',statistics.today_local().isoformat(),customer_id=ident);items.append(dict(key=item['key'],label=item['label'],price=p['price']))
 return dict(items=items)

@bp.route('/quotes/<ident>/pricing-margin',methods=['GET','POST'])
def margin(ident):
 from .quote_routes import get_quote
 from . import costing
 r=get_quote(ident)
 with store.connect(current_app.config['DATA_DIR']) as db:
  costing.require_staff(db,r);sheet=costing.load(db,r)
  error=None
  if request.method=='POST':
   db.execute('BEGIN IMMEDIATE')
   for x in sheet['rows']:
    for k in ('unit_purchase','selling_unit'):x[k]=request.form.get(x['id']+'-'+k,x[k])
   try:
    fields=dict(request.form);fields['costing']=json.dumps(dict(rows=[{k:v for k,v in x.items() if k in ('id',*costing.EDITABLE)} for x in sheet['rows']]));fields['action']='save';costing.save(db,r,fields);flash('Private worksheet saved. Apply selling prices only after reviewing the existing preview.');return redirect(request.path)
   except ValidationError as exc:
    db.rollback();error=str(exc)
  if error:
   result=costing.calculate_sheet(r,costing.load(db,r));result.update(cost=None,selling=None,profit=None,margin=None)
   for displayed,pending in zip(result['rows'],sheet['rows']):
    displayed.update(unit_purchase=pending['unit_purchase'],selling_unit=pending['selling_unit'],profit=None,margin=None)
  else:result=costing.calculate_sheet(r,sheet)
 return render_template('margin_compact.html',error=error,record=r,sheet=sheet,result=result)
