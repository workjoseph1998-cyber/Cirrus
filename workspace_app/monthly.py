"""Customer workbook snapshots. Raw values remain independent from reporting dates."""
import copy,hashlib,io,json,re
from collections import defaultdict
from datetime import date,datetime
from decimal import Decimal,InvalidOperation
from uuid import uuid4
from flask import Blueprint,current_app,request,render_template,redirect,flash,send_file
from . import store,security
from .model import ValidationError
from .references import stamp,actor
from .statistics import today_local
from .commercial import fingerprint
from .relationships import record
bp=Blueprint('monthly',__name__)
COLUMNS=['Item','VM','Date','Size','System','Remarks','Service Type','Qty','NB of Cores','OS','RAM','Unit Price','Total']
FIELDS=COLUMNS+['environment','category','billing_unit','vm_confirmed','resource_semantics','override','override_reason','percentage','base_ids','item_key','classification']

def schema(db):
 for sql in ["CREATE TABLE IF NOT EXISTS monthly_snapshots(customer_id TEXT REFERENCES records(id),month TEXT,version INTEGER,data TEXT,updated TEXT,actor TEXT,PRIMARY KEY(customer_id,month))", "CREATE TABLE IF NOT EXISTS monthly_history(id INTEGER PRIMARY KEY,customer_id TEXT,month TEXT,at TEXT,actor TEXT,filename TEXT,fingerprint TEXT,row_count INTEGER,before_data TEXT,after_data TEXT,attachment_id TEXT)","CREATE TABLE IF NOT EXISTS monthly_drafts(id TEXT PRIMARY KEY,customer_id TEXT,actor TEXT,data TEXT,workbook BLOB,filename TEXT)","CREATE TABLE IF NOT EXISTS customer_vm_catalog(customer_id TEXT REFERENCES records(id),entry_id TEXT,data TEXT,version INTEGER,PRIMARY KEY(customer_id,entry_id))","CREATE TABLE IF NOT EXISTS customer_archives(customer_id TEXT PRIMARY KEY,archived INTEGER)","CREATE TABLE IF NOT EXISTS pdf_file_owners(path_key TEXT PRIMARY KEY,record_id TEXT NOT NULL,path TEXT NOT NULL,revision INTEGER NOT NULL)"]:
  db.execute(sql)
 from .hosting import entries
 for c in db.execute("SELECT id FROM records WHERE kind='customer'").fetchall():initialize_catalog(db,c['id'])

def initialize_catalog(db,ident):
 from .hosting import entries
 if db.execute('SELECT 1 FROM customer_vm_catalog WHERE customer_id=?',(ident,)).fetchone():return
 for r in entries(db):
  d=copy.deepcopy(r['data'])
  for os,key in [('a','cost_a'),('b','cost_b')]:
   prices=db.execute("SELECT price FROM agreed_prices WHERE scope_id=? AND item_key=? AND active=1 AND billing='monthly' AND currency='USD' AND (start='' OR start<=?) AND (finish='' OR finish>=?)",(ident,'vm:'+r['id']+':'+os,today_local().isoformat(),today_local().isoformat())).fetchall()
   if len(prices)==1:d[key]=prices[0]['price']
  db.execute('INSERT INTO customer_vm_catalog VALUES (?,?,?,1)',(ident,r['id'],json.dumps(d)))

def number(value):
 if isinstance(value,bool):return None
 try:
  n=Decimal(str(value).strip().replace(',',''))
  return n if n.is_finite() and 0<=n<=Decimal('1000000000000') else None
 except (InvalidOperation,ValueError):return None

def row(raw=None):
 d={k:'' for k in FIELDS};d.update(id=uuid4().hex,vm_confirmed=False,base_ids=[]);d.update(raw or {});return d

def assess(rows):
 if not isinstance(rows,list) or len(rows)>3000:raise ValidationError('Use at most 3,000 consumption rows.')
 ids=set();clean=[]
 for raw in rows:
  if not isinstance(raw,dict) or set(raw)-set(FIELDS+['id']):raise ValidationError('Unknown consumption fields.')
  r=row(raw)
  if not re.fullmatch('[a-zA-Z0-9_-]{1,80}',r['id']) or r['id'] in ids:raise ValidationError('Duplicate/invalid row identity.')
  ids.add(r['id'])
  for k in FIELDS:
   if k in ('vm_confirmed','base_ids'):continue
   if not isinstance(r[k],str) or len(r[k])>10000:raise ValidationError('Invalid text in '+k)
  if type(r['vm_confirmed']) is not bool or not isinstance(r['base_ids'],list) or len(r['base_ids'])>3000 or any(not isinstance(x,str) for x in r['base_ids']):raise ValidationError('Invalid classification or support base.')
  r['environment']={'production':'Production','uat':'UAT','dr':'DR','disaster recovery':'DR'}.get(r['environment'].strip().casefold(),r['environment'].strip())
  categories={'security services':'Security Services','internet and wan services':'Internet and WAN Services','backup':'Backup','cyber security services':'Cyber Security Services','support services':'Support Services'}
  r['category']=categories.get(' '.join(r['category'].casefold().split()),r['category'].strip())
  clean.append(r)
 amounts={};warnings={r['id']:[] for r in clean};visiting=set()
 def amount(r):
  ident=r['id'];w=warnings[ident]
  if ident in amounts:return amounts[ident]
  if ident in visiting:raise ValidationError('Circular support charge base.')
  visiting.add(ident);qty=number(r['Qty']);price=number(r['Unit Price']);imported=number(r['Total']);override=number(r['override'])
  calc=None
  if r['percentage'] or r['billing_unit']=='%':
   pct=number(r['percentage']);targets=[x for x in clean if x['id'] in r['base_ids'] and x['id']!=ident]
   if pct is not None and pct<=100 and targets:
    values=[amount(x) for x in targets];calc=sum(values,Decimal(0))*pct/100 if all(x is not None for x in values) else None
   else:w.append('Support requires an explicit percentage and selected base rows.')
  elif qty is not None and price is not None:
   context=' '.join(r[k] for k in ('category','Service Type','System','Remarks')).casefold()
   if not r['billing_unit'] and ('support' in context or 'fulfillment' in context):w.append('Confirm ordinary support billing unit, or choose % with an explicit percentage and charge base.')
   else:calc=qty*price
  if r['override']:
   if override is None or not r['override_reason'].strip():w.append('Manual override needs a valid amount and reason.');value=None
   else:value=override
  else:
   value=imported if imported is not None else calc
   if r['Total'] and imported is None:w.append('Source Total is not numeric; clarify it.');value=None
   if imported is not None and calc is not None and abs(imported-calc)>Decimal('.005'):w.append('Imported Total differs from calculated charge; review or provide a reasoned override.')
  for key in ('Qty','Unit Price','NB of Cores','RAM'):
   if r[key] and number(r[key]) is None:w.append(key+' is unknown/non-numeric; original value retained.')
  if value is None:w.append('Unpriced')
  if qty is not None and not r['billing_unit']:w.append('Confirm billing unit.')
  if not r['environment'] or not r['category']:w.append('Confirm environment/category.')
  physical=r['classification']=='vm' if r['classification'] else r['vm_confirmed']
  if (r['VM'] or r['Size']) and not physical and r['classification']!='service':w.append('Confirm physical VM versus service/licensing classification.')
  if physical and (number(r['NB of Cores']) is None or number(r['RAM']) is None or r['resource_semantics'] not in ('per_vm','row_total')):w.append('Confirm cores, RAM in GB and resource semantics.')
  visiting.remove(ident);amounts[ident]=None if value is None else value.quantize(Decimal('.01'));return amounts[ident]
 for r in clean:
  if any(x not in ids or x==r['id'] for x in r['base_ids']):raise ValidationError('Support base references a removed or missing row.')
  amount(r)
 return clean,amounts,warnings

def summary(rows):
 rows,amounts,warnings=assess(rows);groups=defaultdict(lambda:dict(total=Decimal(0),rows=0,unresolved=0));vms={};cpu=Decimal(0);ram=Decimal(0);incomplete=0;units=defaultdict(Decimal)
 for r in rows:
  g=groups[(r['environment'] or 'Unassigned',r['category'] or 'Unassigned')];g['rows']+=1;g['total']+=amounts[r['id']] or Decimal(0);g['unresolved']+=bool(warnings[r['id']])
  is_vm=r['classification']=='vm' if r['classification'] else r['vm_confirmed']
  if is_vm and r['VM'].strip():
   key=(r['environment'].casefold(),r['VM'].strip().casefold())
   values=(number(r['NB of Cores']),number(r['RAM']),r['resource_semantics'],number(r['Qty']))
   if key in vms and vms[key]!=values:vms[key]=None
   else:vms.setdefault(key,values)
  elif r['classification']!='service' and (r['VM'] or r['Size']):incomplete+=1
  if r['billing_unit'] and r['billing_unit'] not in ('%','VM') and number(r['Qty']) is not None:units[r['billing_unit']]+=number(r['Qty'])
 resource_missing=0;qualified=0
 for value in vms.values():
  if not value or value[2] not in ('per_vm','row_total') or value[0] is None or value[1] is None:resource_missing+=1;continue
  factor=value[3] if value[2]=='per_vm' else Decimal(1)
  if factor is None or value[2]=='per_vm' and factor!=factor.to_integral_value():resource_missing+=1;continue
  qualified+=1
  cpu+=value[0]*factor;ram+=value[1]*factor
 total=sum((x for x in amounts.values() if x is not None),Decimal(0));gaps=sum(bool(x) for x in warnings.values());envs=sorted({r['environment'] for r in rows if r['environment']});cats=sorted({r['category'] for r in rows if r['category']})
 return dict(total=str(total),unpriced=sum(x is None for x in amounts.values()),unresolved=gaps,vm_count=len(vms),incomplete=incomplete,cores=str(cpu) if qualified else 'Unknown',ram=str(ram) if qualified else 'Unknown',resource_missing=resource_missing,units=dict(units),groups=[dict(environment=e,category=c,**v) for (e,c),v in groups.items()],wording='Services across '+(', '.join(envs) or 'unassigned environments')+', including '+(', '.join(cats) or 'unclassified services')+'. Known monthly consumption charges are USD '+str(total)+'; '+str(gaps)+' rows require review. These are calculated consumption charges, not payments.',amounts=amounts,warnings=warnings)

def safe_summary(rows):
 try:return summary(rows)
 except ValidationError as exc:
  result=summary([]);result.update(total='Unavailable',unpriced=len(rows),unresolved=len(rows),wording='Calculations blocked: '+str(exc),amounts={r['id']:None for r in rows},warnings={r['id']:[str(exc)] for r in rows});return result

def parse(book,sheet,mapping,header_row=None):
 ws=book[sheet];rows=[];environment='';category='';header=False;header_values=None
 envs={'uat':'UAT','production':'Production','dr':'DR','disaster recovery':'DR'}
 cats={'security services','internet and wan services','backup','cyber security services','support services','hosting','database services'}
 for source in ws.iter_rows():
  vals=[str(c.value).strip() if c.value is not None else '' for c in source]
  if not any(vals):continue
  norm=[' '.join(x.casefold().split()) for x in vals]
  if source[0].row==header_row:
   header=True;header_values=norm;continue
  if header_values and norm==header_values:continue
  if len(set(norm)&{x.casefold() for x in COLUMNS})>=3:header=True;continue
  nonempty=[x for x in norm if x]
  if len(nonempty)==1 and (nonempty[0] in envs or nonempty[0] in cats or any(source[0].row in range(m.min_row,m.max_row+1) for m in ws.merged_cells.ranges)):
   if nonempty[0] in envs:environment=envs[nonempty[0]];category=''
   else:category=vals[next(i for i,x in enumerate(norm) if x)]
   continue
  if not header:continue
  raw={k:vals[int(mapping[k])-1] if mapping.get(k) and int(mapping[k])<=len(vals) else '' for k in COLUMNS}
  if not any(raw.values()):continue
  rows.append(row(dict(raw,environment=environment,category=category)))
 return rows

def load_snapshot(db,ident,month):
 r=db.execute('SELECT * FROM monthly_snapshots WHERE customer_id=? AND month=?',(ident,month)).fetchone();return dict(r,data=json.loads(r['data'])) if r else dict(version=0,data=[])

def month_value(value):
 try:date.fromisoformat(value+'-01')
 except (ValueError,TypeError):raise ValidationError('Choose a valid reporting month.') from None
 return value

@bp.route('/customers/<ident>/consumption',methods=['GET','POST'])
def page(ident):
 month=month_value(request.values.get('month',today_local().strftime('%Y-%m')));error=None
 with store.connect(current_app.config['DATA_DIR']) as db:
  c=record(db,ident,'customer',request.method=='POST');saved=load_snapshot(db,ident,month);saved_rows=copy.deepcopy(saved['data']);rows=saved['data'];version=saved['version'];draft=None
  if request.method=='POST':
   try:
    rows=json.loads(request.form.get('rows','[]'));rows,_,_=assess(rows)
    if request.form.get('confirm')!='yes':raise ValidationError('Confirm the reviewed monthly snapshot before committing.')
    db.execute('BEGIN IMMEDIATE');latest=load_snapshot(db,ident,month)
    if str(latest['version'])!=request.form.get('version'):raise ValidationError('This month changed. Reload before replacing it.')
    mode=request.form.get('mode','replace');draft_id=request.form.get('draft','');source=db.execute('SELECT * FROM monthly_drafts WHERE id=? AND customer_id=? AND actor IS ?',(draft_id,ident,actor())).fetchone() if draft_id else None
    if draft_id and not source:raise ValidationError('Import draft is unavailable.')
    digest=hashlib.sha256(source['workbook']).hexdigest() if source else ''
    if digest and request.form.get('allow_duplicate')!='yes' and db.execute('SELECT 1 FROM monthly_history WHERE customer_id=? AND month=? AND fingerprint=?',(ident,month,digest)).fetchone():raise ValidationError('This workbook was already imported for this customer/month.')
    if mode=='merge':
     merged={r['id']:r for r in latest['data']};merged.update({r['id']:r for r in rows});rows=list(merged.values());assess(rows)
    elif mode!='replace':raise ValidationError('Choose Replace or Merge.')
    attachment=None
    if source:
     attachment=uuid4().hex;stored=attachment+'.xlsx';path=current_app.config['DATA_DIR']/'attachments'/stored;path.write_bytes(source['workbook'])
     db.execute('INSERT INTO attachments VALUES (?,?,?,?,?)',(attachment,ident,source['filename'],stored,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))
    db.execute('INSERT INTO monthly_history(customer_id,month,at,actor,filename,fingerprint,row_count,before_data,after_data,attachment_id) VALUES (?,?,?,?,?,?,?,?,?,?)',(ident,month,stamp(),actor(),(source['filename']+' · '+json.loads(source['data']).get('sheet','')+' · source rows '+str(len(json.loads(source['data'])['rows']))) if source else 'Manual edit',digest,len(rows),json.dumps(latest['data']),json.dumps(rows),attachment))
    db.execute('INSERT INTO monthly_snapshots VALUES (?,?,?,?,?,?) ON CONFLICT(customer_id,month) DO UPDATE SET version=excluded.version,data=excluded.data,updated=excluded.updated,actor=excluded.actor',(ident,month,version+1,json.dumps(rows),stamp(),actor()))
    if source:db.execute('DELETE FROM monthly_drafts WHERE id=?',(draft_id,))
    flash('Monthly consumption snapshot saved.');return redirect(request.path+'?month='+month)
   except (ValidationError,ValueError) as exc:
    db.rollback();error=str(exc)
    # Keep the actor-bound source workbook available when review/save fails.
    draft=db.execute('SELECT * FROM monthly_drafts WHERE id=? AND customer_id=? AND actor IS ?',(request.form.get('draft',''),ident,actor())).fetchone()
  if request.method=='GET' and request.args.get('draft'):
   draft=db.execute('SELECT * FROM monthly_drafts WHERE id=? AND customer_id=? AND actor IS ?',(request.args['draft'],ident,actor())).fetchone()
   if not draft:raise ValidationError('Import draft unavailable.')
   payload=json.loads(draft['data'])
   if payload['month']!=month:raise ValidationError('Draft reporting month mismatch.')
   rows=payload['rows']
  if request.method=='GET' and request.args.get('copy')=='previous':
   from datetime import timedelta
   previous=(date.fromisoformat(month+'-01')-timedelta(days=1)).strftime('%Y-%m');rows=copy.deepcopy(load_snapshot(db,ident,previous)['data'])
   identities={r['id']:uuid4().hex for r in rows}
   for r in rows:r['base_ids']=[identities[x] for x in r['base_ids'] if x in identities];r['id']=identities[r['id']]
  from datetime import timedelta
  previous=(date.fromisoformat(month+'-01')-timedelta(days=1)).strftime('%Y-%m');prev=load_snapshot(db,ident,previous);before=summary(prev['data']) if prev['version'] else None
  history=[dict(r) for r in db.execute('SELECT h.*,u.username FROM monthly_history h LEFT JOIN users u ON u.id=h.actor WHERE h.customer_id=? AND h.month=? ORDER BY h.id DESC',(ident,month))]
 return render_template('monthly.html',customer=c,month=month,rows=rows,version=version,summary=safe_summary(rows),previous=before,saved_rows=saved_rows,fields=['environment','category']+COLUMNS+['billing_unit','vm_confirmed','resource_semantics','override','override_reason','percentage','base_ids','item_key','classification'],error=error,draft=draft,history=history,writable=_write(c),dirty=bool(error or draft or request.args.get('copy')))

def _write(c):
 with store.connect(current_app.config['DATA_DIR']) as db:return security.can_read(db,c,write=True)

@bp.route('/customers/<ident>/consumption/import',methods=['GET','POST'])
def upload(ident):
 from .excel_import import load
 with store.connect(current_app.config['DATA_DIR']) as db:
  c=record(db,ident,'customer',True);month=month_value(request.values.get('month',today_local().strftime('%Y-%m')));book=None;mapping={};draft=None;sheet=None;header_row=1
  if request.method=='POST':
   if request.form.get('draft'):
    draft=db.execute('SELECT * FROM monthly_drafts WHERE id=? AND customer_id=? AND actor IS ?',(request.form['draft'],ident,actor())).fetchone()
    if not draft:raise ValidationError('Draft unavailable.')
    raw=draft['workbook'];name=draft['filename']
   else:
    f=request.files.get('file')
    if not f or not f.filename.lower().endswith('.xlsx'):raise ValidationError('Upload an XLSX workbook.')
    raw=f.read(10*1024*1024+1);name=f.filename
   book,_=load(raw);sheet=request.form.get('sheet',book.sheetnames[0])
   if sheet not in book.sheetnames:raise ValidationError('Choose a worksheet.')
   for source in book[sheet].iter_rows():
    values={' '.join(str(c.value or '').casefold().split()):str(c.column) for c in source}
    if len(set(values)&{x.casefold() for x in COLUMNS})>=3:
     mapping={k:values.get(k.casefold(),'') for k in COLUMNS};header_row=source[0].row;break
   if request.form.get('review')=='yes':
    mapping={k:request.form.get(k,'') for k in COLUMNS}
    if any(v and (not v.isdigit() or not 1<=int(v)<=64) for v in mapping.values()):raise ValidationError('Mappings are column numbers 1–64 or blank.')
    try:header_row=int(request.form.get('header_row',header_row))
    except ValueError:raise ValidationError('Header row must be a number.') from None
    if not 1<=header_row<=5000:raise ValidationError('Header row must be between 1 and 5000.')
    rows=parse(book,sheet,mapping,header_row);payload=dict(month=month,rows=rows,sheet=sheet,mapping=mapping,header_row=header_row)
    db.execute('UPDATE monthly_drafts SET data=? WHERE id=?',(json.dumps(payload),draft['id']));return redirect('/customers/'+ident+'/consumption?month='+month+'&draft='+draft['id'])
   did=draft['id'] if draft else uuid4().hex
   db.execute('INSERT INTO monthly_drafts VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(did,ident,actor(),json.dumps(dict(month=month,rows=[])),raw,name));draft=dict(id=did)
 return render_template('monthly_upload.html',customer=c,month=month,book=book,mapping=mapping,columns=COLUMNS,draft=draft,sheet=sheet,header_row=header_row)

@bp.get('/customers/<ident>/consumption/export/<kind>')
def export(ident,kind):
 from openpyxl import Workbook
 from .documents import filename
 with store.connect(current_app.config['DATA_DIR']) as db:
  c=record(db,ident,'customer');month=month_value(request.args.get('month',''));rows=load_snapshot(db,ident,month)['data']
 s=summary(rows)
 if kind=='xlsx':
  b=Workbook();w=b.active;w.title='Consumption';w.append(FIELDS+['Calculated charge','Warnings'])
  for r in rows:
   w.append([json.dumps(r[k]) if isinstance(r[k],(bool,list)) else r[k] for k in FIELDS]+[str(s['amounts'][r['id']]) if s['amounts'][r['id']] is not None else 'Unpriced','; '.join(s['warnings'][r['id']])])
  for line in w:
   for cell in line:
    if isinstance(cell.value,str):cell.data_type='s'
  w=b.create_sheet('Executive summary');w.append([c['data']['name'],month]);w.append([s['wording']]);w.append(['Environment','Category','Known monthly USD','Unresolved'])
  for g in s['groups']:w.append([g['environment'],g['category'],str(g['total']),g['unresolved']])
  for sheet in b:
   for line in sheet:
    for cell in line:
     if isinstance(cell.value,str):cell.data_type='s'
  out=io.BytesIO();b.save(out);out.seek(0);return send_file(out,as_attachment=True,download_name=filename(c['data']['name']+'-'+month,'xlsx'))
 if kind!='pdf':raise ValidationError('Unsupported export.')
 html=render_template('monthly_print.html',customer=c,month=month,rows=rows,summary=s,columns=COLUMNS)
 from playwright.sync_api import sync_playwright
 from .automation import browser_path
 import os
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=browser_path(),headless=True,chromium_sandbox=not(os.name!='nt' and os.environ.get('CIRRUS_PDF_NO_SANDBOX')=='1'))
  try:
   page=browser.new_page();page.route('**/*',lambda route:route.abort());page.set_content(html);content=page.pdf(print_background=True,landscape=True)
  finally:browser.close()
 return send_file(io.BytesIO(content),as_attachment=True,download_name=filename(c['data']['name']+'-'+month,'pdf'))

@bp.post('/customers/<ident>/consumption/calculate')
def preview(ident):
 with store.connect(current_app.config['DATA_DIR']) as db:record(db,ident,'customer',True)
 rows=json.loads(request.form.get('rows','[]'));s=summary(rows)
 return dict(wording=s['wording'],cores=s['cores'],ram=s['ram'],vm_count=s['vm_count'],groups=s['groups'],total=s['total'],unpriced=s['unpriced'],unresolved=s['unresolved'],amounts={k:str(v) if v is not None else None for k,v in s['amounts'].items()},warnings=s['warnings'])
