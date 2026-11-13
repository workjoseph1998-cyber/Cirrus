"""Editable, local Cirrus VM library. Seed prices are synthetic demonstrations."""
from decimal import Decimal
import json
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from .model import ValidationError, decimal, money

FAMILIES = {'Small': (2, ['3.75','5','6.5','8','10','14']),
            'Medium': (4, ['7.5','10','12','16','20','24','32']),
            'Large': (8, ['15','20','26','32','40','52','64','128']),
            'Xlarge': (16, ['30','40','50','65','80','104']),
            'Xxlarge': (32, ['60','75','100','130','170','220'])}
CONFIG = {'hosting_cost_a_label':'Linux', 'hosting_cost_b_label':'Microsoft Windows', 'hosting_default_basis':'a'}
FIELDS = [('name','Machine name','text'),('family','Family','text'),('vcpu','vCPU cores','number'),
          ('ram_gb','RAM (GB)','number'),('cost_a','Linux monthly cost (USD)','number'),
          ('cost_b','Microsoft Windows monthly cost (USD)','number'),('price_status','Pricing status (Demo / Confirmed)','text')]


def seeds():
    result=[]
    for family,(cores,rams) in FAMILIES.items():
        for i,ram in enumerate(rams,1):
            name=f'{family} V{i}'
            result.append({'id':str(uuid5(NAMESPACE_URL,'cirrus-hosting-vm/'+name)),
                           'data':dict(name=name,family=family,vcpu=str(cores),ram_gb=ram,
                                       cost_a='',cost_b='',price_status='Demo')})
    return result


def validate_vm(data):
    if not isinstance(data,dict) or set(data)!={k for k,_,_ in FIELDS}:
        raise ValidationError('Invalid hosting VM fields.')
    d={}
    for k,_,_ in FIELDS:
        if not isinstance(data[k],str) or len(data[k])>200: raise ValidationError('VM fields must be text up to 200 characters.')
        d[k]=data[k].strip()
    if not d['name'] or not d['family'] or not d['name'].isprintable() or not d['family'].isprintable():
        raise ValidationError('Machine name and family are required printable text.')
    cpu=decimal(d['vcpu'],'vCPU cores',maximum=Decimal(4096))
    ram=decimal(d['ram_gb'],'RAM GB',maximum=Decimal(1000000))
    if cpu<1 or cpu!=cpu.to_integral_value() or ram<Decimal('0.001'): raise ValidationError('vCPU must be a positive integer and RAM must be at least 0.001 GB.')
    d['vcpu']=str(int(cpu));d['ram_gb']=format(ram.normalize(),'f')
    for key in ('cost_a','cost_b'):
        value=decimal(d[key],key,optional=True)
        d[key]='' if value is None else str(money(value))
    if d['price_status'] not in ('Demo','Confirmed'): raise ValidationError('Pricing status must be Demo or Confirmed.')
    return d


def entries(db):
    rows=[{'id':r['id'],'data':json.loads(r['data'])} for r in db.execute('SELECT * FROM hosting_vms')]
    order={name:i for i,name in enumerate(FAMILIES)}
    return sorted(rows,key=lambda r:(order.get(r['data']['family'],99),r['data']['family'],Decimal(r['data']['ram_gb']),r['data']['name']))


def save(db,data,ident=None):
    d=validate_vm(data);ident=ident or str(uuid4())
    if any(r['id']!=ident and r['data']['name'].casefold()==d['name'].casefold() for r in entries(db)):
        raise ValidationError('Machine name already exists.')
    db.execute('INSERT INTO hosting_vms VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',(ident,json.dumps(d)))
    return ident


def import_plan(db,incoming):
    if not isinstance(incoming,list) or len(incoming)>2000:raise ValidationError('VM import must be an array of at most 2,000 profiles.')
    current={r['id']:r['data'] for r in entries(db)}
    starter={r['id']:validate_vm(r['data']) for r in seeds()}
    seen=set();changes=[];names={}
    for r in incoming:
        if not isinstance(r,dict) or set(r)!={'id','data'}:raise ValidationError('Invalid VM import entry.')
        try:UUID(r['id'])
        except (ValueError,TypeError,AttributeError):raise ValidationError('Invalid hosting VM ID.') from None
        if r['id'] in seen:raise ValidationError('Duplicate hosting VM ID.')
        seen.add(r['id']);clean=validate_vm(r['data'])
        if r['id'] in current and clean!=current[r['id']] and current[r['id']]!=starter.get(r['id']):
            raise ValidationError('Conflicting edited hosting VM: '+clean['name']+'. Import does not overwrite your edited profiles.')
        if clean!=current.get(r['id']):changes.append({'id':r['id'],'data':clean})
        names[r['id']]=clean['name'].casefold()
    final={i:d['name'].casefold() for i,d in current.items()};final.update(names)
    if len(set(final.values()))!=len(final):raise ValidationError('Duplicate hosting VM name after import.')
    return changes
