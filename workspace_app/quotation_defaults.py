"""Idempotent, additive quotation catalog defaults. Never touches quotations or VMs."""
from uuid import uuid5, NAMESPACE_URL
from decimal import Decimal
from . import store
from .model import FIELDS,ValidationError

# Stable codes map to the existing sanitized catalog identities.
DEFAULTS = [
 ('STORAGE','Storage as a Service','Storage','StaaS','TB','Per TB/Month','83.00','','0'),
 ('DCFW','Security','Datacenter FW','SecaaS','environment','Per Environment/Month','400.00','Dedicated VDOM','0'),
 ('PERIMETER','Security','Perimeter FW','SecaaS','Mbps','Per Mbps/Month','10.00','','0'),
 ('LB','Security','Load Balancer','SecaaS','environment','Per Environment/Month','100.00','','0'),
 ('WAF','Security','WAF','SecaaS','Mbps','Per Mbps/Month','30.00','','0'),
 ('VPN-USER','Security','VPN','VPNaaS','user','Per User/Month','8.00','MFA Included','0'),
 ('BACKUP','Backup as a Service','Managed Backup','BkaaS','agent','Per Agent/Month','16.00','','0'),
 ('BACKUP-STORAGE','Backup as a Service','Backup Storage','BkaaS','TB','Per TB/Month','68.00','15 days retention','0'),
 ('SIEM-COLLECTOR','Security','SIEM Collector VM','SecaaS','collector','Per Collector/Month','260.00','','0'),
 ('SIEM-ABS','Security','SIEM','SecaaS','IP','Per IP/Month','21.00','','0'),
 ('SOC','Security','SOC 24/7 Monitoring','SecaaS','EPS','Per EPS/Month','5.00','Minimum bundle: 250 EPS','250'),
 ('EDR','Security','EDR','SecaaS','VM','Per VM/Month','13.00','','0'),
 ('NOC','Performance','NOC','NOC CIR','IP','Per IP/Month','20.00','Minimum bundle: 50 IPs','50'),
 ('COMPUTE','Cirrus Compute','VM','IaaS','VM','Per VM/Month','','','0'),
 ('VPN-NODE','Security','VPN','VPNaaS','node','Per Node/Month','','','0'),
 ('INTERNET','Internet as a Service','Protected Internet','Internet','Mbps','Per Mbps/Month','','','0'),
 ('REPLICATION-LINK','Replication Link','Protected Link','Replication','Mbps','Per Mbps/Month','','','0'),
 ('SETUP','Connectivity Setup','One-Time fee','CaaS','service','One-Time Fee','','','0'),
 ('SUPPORT','Managed Services','Working hours Support','Support','service','Percentage of selected monthly services','','','0'),
]


def default_items():
    items=[]
    for code,name,sub,type_,unit,model,price,comments,minimum in DEFAULTS:
        values={k:'' for k,_,_ in FIELDS['catalog']}
        values.update(code='CIR-'+code,name=name+' — '+sub,service=name,sub_service=sub,description=sub,type=type_,unit=unit,pricing_model=model,price=price,
                      comments=comments,minimum_quantity=minimum,quantity='1',billing='one_time' if code=='SETUP' else 'monthly',
                      method='fixed' if code=='SETUP' else 'percent' if code=='SUPPORT' else 'unit',
                      support_percent='20' if code=='SUPPORT' else '',currency='USD',discount='0',status='Active')
        items.append(values)
    return items


def equivalent(data,values):
    import re
    def norm(value):return re.sub(r'[^a-z0-9]','',value.casefold().replace('×','x').replace('*','x'))
    if norm(data['code'])==norm(values['code']):return True
    code=values['code'];sub=norm(data.get('sub_service') or data.get('description',''))
    aliases={
      'CIR-BACKUP':{'managedbackup','managedbackupagent'},
      'CIR-SIEM-COLLECTOR':{'collectorvm','siemcollectorvm'},
      'CIR-SIEM-ABS':{'siem','siemabs'},
      'CIR-SUPPORT':{'workinghourssupport','workinghourssupport8x5requestfulfillment','8x5requestfulfillment'},
      'CIR-REPLICATION-LINK':{'protectedlink','replicationlink'},
      'CIR-VPN-USER':{'vpn'},'CIR-VPN-NODE':{'vpn'},
    }
    descriptions=aliases.get(code,{norm(values['sub_service'])})
    if sub not in descriptions:return False
    if code.startswith('CIR-VPN'):
        unit=norm(data.get('unit','unit'))
        if code=='CIR-VPN-NODE':return unit=='node'
        return unit in ('user','unit','')
    if code=='CIR-COMPUTE':
        return norm(data.get('service') or data['name']) in ('cirruscompute','cirruscomputevm')
    # Match the legacy combined Name/Code labels shown by older catalog pages.
    name=norm(data.get('service') or data['name'])
    service=norm(values['service'])
    return (name in (service,norm(values['name']),sub,service+sub) or
            code=='CIR-STORAGE' and name in ('cirruscompute','cirruscomputestorage','storageasaservice') or
            code=='CIR-BACKUP' and name in ('backupmanagedbackupagent','backupmanagedbackup') or
            code=='CIR-SIEM-COLLECTOR' and name in ('securitycollectorvm','securitysiem','securitysiemcollectorvm') or
            code=='CIR-SUPPORT' and name in ('managedservices','8x5requestfulfillment'))


def bindings(db):
    db.execute('CREATE TABLE IF NOT EXISTS standard_catalog_bindings (code TEXT PRIMARY KEY, record_id TEXT NOT NULL)')
    return {r['code']:r['record_id'] for r in db.execute('SELECT * FROM standard_catalog_bindings')}

def persist_default(db,data,ident):
    """Trusted additive initialization only; interactive edits still use store.save.

    Validate hardcoded migration values without impersonating an administrator in
    an editor's request. Never accepts request data or changes access/ownership.
    """
    import json
    from datetime import datetime,timezone
    from .model import validate
    records=store.records(db,unrestricted=True)
    clean=validate('catalog',data,records,ident)
    existing=next((r for r in records if r['id']==ident),None)
    now=datetime.now(timezone.utc).isoformat()
    db.execute('INSERT INTO records (id,kind,data,created,updated) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated',
               (ident,'catalog',json.dumps(clean),existing['created'] if existing else now,now))


def initialize(db):
    records=store.records(db,unrestricted=True);bound=bindings(db)
    for values in default_items():
        canonical=values['code'];code=canonical[4:]
        matches=[r for r in records if r['kind']=='catalog' and r['id']==bound.get(canonical)]
        if not matches:matches=[r for r in records if r['kind']=='catalog' and equivalent(r['data'],values)]
        if len(matches)>1:raise ValidationError('Ambiguous catalog equivalents for '+canonical+'; resolve duplicates before migration.')
        if matches:
            r=matches[0];data=dict(r['data'])
            if code=='SOC' and data.get('method','unit')=='unit' and data.get('price') and Decimal(data['price'])==Decimal('1250'):
                raise ValidationError('CIR-SOC has a bundle price stored as a per-EPS price. Review it in the catalog: use price 5 and minimum quantity 250, or an explicit fixed fee. No changes committed.')
            ident=r['id']
            if code=='SETUP':data['billing']='one_time'
            if code in ('SOC','NOC') and Decimal(data.get('minimum_quantity') or '0')==0:data['minimum_quantity']=values['minimum_quantity']
            if data.get('method')=='fixed' and not data.get('fixed_fee') and data.get('price'):data['fixed_fee']=data['price']
            # Customized values, including prices and intentional quantities, survive.
            for key,value in values.items():
                if key in ('price','fixed_fee') and data.get('currency','USD') not in ('','USD'):continue
                if not data.get(key) or key=='unit' and data.get(key)=='unit' and values['unit']!='unit':data[key]=value
            if data!=r['data']:persist_default(db,data,r['id'])
        else:
            data={k:'' for k,_,_ in FIELDS['catalog']};data.update(values)
            ident=str(uuid5(NAMESPACE_URL,canonical))
            if any(r['id']==ident for r in records):raise ValidationError('Catalog identity collision for '+canonical+'; no changes committed.')
            persist_default(db,data,ident)
        db.execute('INSERT INTO standard_catalog_bindings VALUES (?,?) ON CONFLICT(code) DO UPDATE SET record_id=excluded.record_id',(canonical,ident))

if __name__=='__main__':
    from . import data_directory
    from .backup import workspace_lock
    root=data_directory()
    with workspace_lock(root):
        store.migrate(root)
        with store.connect(root) as db:
            db.execute('BEGIN IMMEDIATE');initialize(db)
    print('Quotation defaults initialized; existing quotations and VM prices unchanged.')


def catalog_for_code(catalogs,code,db=None):
    if db is not None:
        ident=bindings(db).get(code.upper())
        found=next((r for r in catalogs if r['id']==ident),None)
        if found:return found
    values=next((v for v in default_items() if v['code'].casefold()==code.casefold()),None)
    matches=[r for r in catalogs if r['data']['code'].casefold()==code.casefold()]
    if not matches and values:matches=[r for r in catalogs if equivalent(r['data'],values)]
    return matches[0] if len(matches)==1 else None
