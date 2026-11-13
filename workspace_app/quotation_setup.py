"""Default quotation structure contains catalog IDs and inclusion flags, never prices."""
import copy,hashlib,json,re
from uuid import uuid4
from flask import Blueprint,current_app,request,render_template,redirect,flash
from . import store,security
from .company import load_template
bp=Blueprint('quotation_setup',__name__)
from .model import ValidationError
from .quotation import new_section,new_row,validate_document
from .quotation_defaults import initialize,bindings,catalog_for_code,equivalent,persist_default

ROLES=('main','dr','monitoring','cyber','connectivity','setup','support','custom')

def schema(db):
 db.execute('CREATE TABLE IF NOT EXISTS quotation_default_setup (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')

def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def initial(db):
 codes=bindings(db);sections=[]
 def add(name,role,parent='',services=()):
  s=dict(id=uuid4().hex,name=name,role=role,parent=parent,enabled=True,items=[dict(catalog_id=codes['CIR-'+code],enabled=True) for code in services]);sections.append(s);return s['id']
 for name,role in [('Main Site','main'),('DR Site','dr')]:
  parent=add(name,role)
  add('Cirrus Compute','custom',parent,('COMPUTE','STORAGE'))
  add('Security Services','custom',parent,('DCFW','PERIMETER','LB','WAF','VPN-USER'))
  add('Backup Services','custom',parent,('BACKUP','BACKUP-STORAGE'))
 add('Monitoring','monitoring',services=('NOC',))
 add('Cybersecurity Services','cyber',services=('SIEM-COLLECTOR','SIEM-ABS','SOC','VPN-USER','VPN-NODE','EDR'))
 add('Connectivity Services','connectivity',services=('INTERNET','REPLICATION-LINK'))
 add('Connectivity Setup — One-Time Fee','setup',services=('SETUP',))
 add('8×5 Request Fulfillment','support',services=('SUPPORT',))
 # Retain catalog-bound services in the existing administrator template's standalone
 # categories. Saved quotations are never examined or modified by initialization.
 legacy=load_template(db);records=[r for r in store.records(db,unrestricted=True) if r['kind']=='catalog']
 for role,pattern in [('monitoring',r'^monitoring'),('cyber',r'^cyber'),('connectivity',r'^connectivity services'),('setup',r'^connectivity setup'),('support',r'8[×x*]5|request fulfillment')]:
  destination=next(s for s in sections if s['role']==role)
  sources=[s for s in legacy['sections'] if not s['parent'] and re.search(pattern,s['name'],re.I)]
  for source in sources:
   rows=[r for s in legacy['sections'] if s['id']==source['id'] or s['parent']==source['id'] for r in s['rows']]
   for row in rows:
    key=row.get('item_key','');item=None
    if key.startswith('catalog:'):item=next((r for r in records if r['id']==key[8:]),None)
    elif key.startswith('code:'):item=catalog_for_code(records,key[5:],db)
    if item is None:
     matching=[r for r in records if (r['data'].get('service') or r['data']['name']).casefold()==row['service'].casefold() and (r['data'].get('sub_service') or r['data']['description']).casefold()==row['sub_service'].casefold()]
     if len(matching)==1:item=matching[0]
    if item is None:
     for c in records:
      if (c['data'].get('sub_service') or c['data']['description']).casefold()==row['sub_service'].casefold():item=c;break
    if item is None and row['unit'].casefold()!='vm':
     # An explicitly saved global company template is an established default.
     # Never mine customer quotations or turn customer VM names into global items.
     from .model import FIELDS
     from uuid import uuid5,NAMESPACE_URL
     code='TPL-'+fingerprint([row['service'],row['sub_service'],row['type'],row['billing']])[:16].upper()
     ident=str(uuid5(NAMESPACE_URL,code));data={k:'' for k,_,_ in FIELDS['catalog']}
     data.update(code=code,name=row['service']+' — '+row['sub_service'],service=row['service'],sub_service=row['sub_service'],description=row['sub_service'],unit=row['unit'],type=row['type'],price=row['unit_price'] if not row.get('unverified_price') else '',fixed_fee=row['fixed_fee'] if not row.get('unverified_price') else '',quantity='1',billing=row['billing'],method=row['method'],support_percent=row['percent'] if row['method']=='percent' else '',minimum_quantity=row.get('minimum_quantity','0'),currency='USD',comments=row['comments'],pricing_model=row['pricing_model'],status='Active',discount='0')
     persist_default(db,data,ident);item=dict(id=ident,data=data);records.append(item)
    if item and not any(i['catalog_id']==item['id'] for i in destination['items']):destination['items'].append(dict(catalog_id=item['id'],enabled=True))
 return dict(version=1,sections=sections)

def ensure(db):
 schema(db)
 saved=db.execute('SELECT data FROM quotation_default_setup WHERE id=1').fetchone()
 if saved:return json.loads(saved['data'])
 initialize(db);value=initial(db)
 db.execute('INSERT INTO quotation_default_setup VALUES (1,?)',(json.dumps(value),));return value

def validate(value,db):
 if not isinstance(value,dict) or set(value)!={'version','sections'} or type(value['version']) is not int or value['version']!=1:raise ValidationError('Invalid default quotation setup.')
 if not isinstance(value['sections'],list) or not 1<=len(value['sections'])<=200:raise ValidationError('Use 1–200 sections.')
 ids=set();sections={};catalog={r['id']:r['data'] for r in store.records(db,unrestricted=True) if r['kind']=='catalog'}
 for s in value['sections']:
  if not isinstance(s,dict) or set(s)!={'id','name','parent','role','enabled','items'}:raise ValidationError('Setup stores structure and catalog assignments only; edit prices in Service Catalog.')
  if not isinstance(s['id'],str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}',s['id']) or s['id'] in ids:raise ValidationError('Invalid or duplicate section ID.')
  ids.add(s['id']);sections[s['id']]=s
  if not isinstance(s['name'],str) or not 1<=len(s['name'].strip())<=300:raise ValidationError('Every section needs a name.')
  if type(s['enabled']) is not bool or s['role'] not in ROLES:raise ValidationError('Invalid section inclusion or role.')
  if not isinstance(s['items'],list) or len(s['items'])>200:raise ValidationError('Maximum 200 assigned services per section.')
  seen=set()
  for item in s['items']:
   if not isinstance(item,dict) or set(item)!={'catalog_id','enabled'} or type(item['enabled']) is not bool:raise ValidationError('Invalid catalog assignment.')
   if item['catalog_id'] not in catalog or item['catalog_id'] in seen:raise ValidationError('Choose each existing catalog service once per section.')
   seen.add(item['catalog_id'])
   if item['enabled'] and s['enabled'] and catalog[item['catalog_id']]['status']!='Active':raise ValidationError('Activate the assigned catalog service or uncheck its inclusion.')
   if s['role']=='setup' and item['enabled'] and catalog[item['catalog_id']]['billing']!='one_time':raise ValidationError('Connectivity Setup accepts one-time catalog services only.')
 for s in sections.values():
  top=sections.get(s['parent'],s)
  for item in s['items']:
   if item['enabled'] and item['catalog_id']==bindings(db).get('CIR-EDR') and top['role']!='cyber':raise ValidationError('The standard EDR service belongs under Cybersecurity Services only.')
   if item['enabled'] and item['catalog_id']==bindings(db).get('CIR-SETUP') and top['role']!='setup':raise ValidationError('Connectivity Setup belongs in its standalone one-time category.')
  if not isinstance(s['parent'],str) or s['parent'] and (s['parent'] not in sections or sections[s['parent']]['parent'] or s['parent']==s['id']):raise ValidationError('Groups must belong to a top-level environment/category.')
 if not any(s['enabled'] and not s['parent'] for s in sections.values()):raise ValidationError('Include at least one environment/category.')
 if sum(len(s['items']) for s in sections.values())>2000:raise ValidationError('Maximum 2,000 default rows.')
 return value

def materialize(db,setup,prefs):
 from .quotation import default_document
 from .relationships import resolve
 doc=load_template(db);doc=copy.deepcopy(doc)
 doc['sections']=[];doc['discount'].update(targets=[],enabled=False,show_summary=False,percent='0',months=0)
 catalog={r['id']:r for r in store.records(db,unrestricted=True) if r['kind']=='catalog'}
 roles={s['id']:s['role'] for s in setup['sections']};enabled={s['id'] for s in setup['sections'] if s['enabled'] and not s['parent']}
 for item in setup['sections']:
  if not item['enabled'] or item['parent'] and item['parent'] not in enabled:continue
  section=new_section(item['name'],item['parent'],id=item['id']);section['role']=item['role'];doc['sections'].append(section)
  top_role=roles[item['parent']] if item['parent'] else item['role']
  for assignment in item['items']:
   if not assignment['enabled']:continue
   record=catalog.get(assignment['catalog_id'])
   if not record or record['data']['status']!='Active':raise ValidationError('Default quotation setup references an unavailable service; ask an administrator to review it.')
   c=record['data']
   if top_role=='setup' and c['billing']!='one_time':raise ValidationError('Connectivity Setup catalog billing must be one-time; ask an administrator to correct it.')
   row=new_row(c.get('service') or c['name'],sub_service=c.get('sub_service') or c['description'],type=c.get('type',''),unit=c['unit'],quantity=c.get('quantity') or '1',pricing_model=c.get('pricing_model',''),comments=c.get('comments',''),method=c.get('method') or 'unit',billing=c.get('billing') or 'monthly',unit_price=c.get('price',''),fixed_fee=c.get('fixed_fee',''),percent=c.get('support_percent') or '20',minimum_quantity=c.get('minimum_quantity') or '0',discount=c.get('discount') or '0',cost=c.get('cost',''),item_key='catalog:'+record['id'])
   if record['id']==bindings(db).get('CIR-COMPUTE'):
    row.update(unit_price='',fixed_fee='',unverified_price=True,vm_selection_required=True,price_source='VM size selection required')
    if top_role=='dr':row.update(dr_mode='replication',dr_percent='50')
   section['rows'].append(row)
 doc['monitoring_ids']=[s['id'] for s in doc['sections'] if s.get('role')=='monitoring']
 for section in doc['sections']:
  for row in section['rows']:
   if row['method']=='percent':
    if prefs.get('support_percent'):row['percent']=prefs['support_percent']
    bases=prefs.get('support_base',['category:Production','category:Disaster Recovery'])
    chosen=[s for s in doc['sections'] if not s['parent'] and ('category:'+s['name'] in bases or s.get('role')=='main' and any(k in bases for k in ('category:Production','category:Main Site')) or s.get('role')=='dr' and any(k in bases for k in ('category:Disaster Recovery','category:DR Site')))]
    selected={s['id'] for s in chosen}|{s['id'] for s in doc['sections'] if s['parent'] in {x['id'] for x in chosen}}
    row['targets']=['r:'+r['id'] for s in doc['sections'] if s['id'] in selected for r in s['rows'] if r['billing']==row['billing'] and r['method']!='percent']
    row['support_keys']=[k for k in bases if not k.startswith('category:')]
 if prefs.get('discount',{}).get('enabled'):
  doc['discount'].update(prefs['discount'],show_summary=True,targets=['s:'+s['id'] for s in doc['sections'] if not s['parent']])
 return doc

@bp.route('/quotation-defaults',methods=['GET','POST'])
def editor():
 security.require_admin();error=None
 with store.connect(current_app.config['DATA_DIR']) as db:
  db.execute('BEGIN IMMEDIATE');value=ensure(db);base=fingerprint(value)
  if request.method=='POST':
   try:
    if request.form.get('base_hash')!=base:raise ValidationError('Default setup changed in another session; reload before saving.')
    entered=json.loads(request.form.get('setup','{}'));validate(entered,db)
    db.execute('UPDATE quotation_default_setup SET data=? WHERE id=1',(json.dumps(entered),));flash('Default quotation setup saved. Future quotations copy current catalog defaults; saved quotations are unchanged.');return redirect(request.path)
   except (ValueError,TypeError,KeyError) as exc:error=str(exc)
  records=[r for r in store.records(db,unrestricted=True) if r['kind']=='catalog']
 return render_template('quotation_default_setup.html',setup=value,base_hash=base,error=error,catalogs=records)

if __name__=='__main__':
 from . import data_directory
 from .backup import workspace_lock
 root=data_directory()
 with workspace_lock(root):
  store.migrate(root)
  with store.connect(root) as db:
   db.execute('BEGIN IMMEDIATE');ensure(db)
 print('Version 20 catalog and default quotation setup initialized; saved quotations unchanged.')
