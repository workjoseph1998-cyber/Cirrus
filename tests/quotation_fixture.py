"""Entirely synthetic prices and anonymous scenario; no customer workbook data."""
from workspace_app.quotation import default_document, new_row
from workspace_app.model import FIELDS


def fixture():
    d=default_document()
    # Explicit historical discount scenario; V5 defaults never seed a discount.
    d['discount'].update(percent='30',months=6,enabled=True)
    find=lambda name:next(s for s in d['sections'] if s['name']==name)
    prod=find('Production');dr=find('Disaster Recovery')
    child=lambda p,name:next(s for s in d['sections'] if s['parent']==p['id'] and s['name']==name)
    def add(s,service,price,qty='1',**kw):
        r=new_row(service,unit_price=price,quantity=qty,**kw);s['rows'].append(r);return r
    cpu=add(child(prod,'Compute and storage'),'Synthetic VM','100','2',comments='Synthetic specs\n4 vCPU / 16 GiB')
    add(child(prod,'Security Services'),'Synthetic firewall','50')
    add(child(prod,'Backup Services'),'Synthetic backup','25')
    add(child(dr,'Compute and storage'),'Synthetic DR VM','100')
    add(child(dr,'Security Services'),'Synthetic DR firewall','20')
    add(find('Monitoring — 24×7 NOC Services'),'Synthetic NOC','40')
    cyber=find('Cyber Security Services');cyber['rows']=[]
    soc=add(cyber,'Synthetic SOC','0.2','500',unit='EPS',pricing_model='Per EPS')
    add(cyber,'Synthetic VPN users','5','4')
    add(cyber,'Synthetic VPN nodes','3','2')
    add(find('Connectivity Services'),'Synthetic connection','30')
    add(find('Connectivity Setup — One-Time Fee'),'Synthetic setup','',method='fixed',fixed_fee='80',billing='one_time')
    d['tax'].update(mode='added',rate='11')
    q={k:'' for k,_,_ in FIELDS['quote']};q.update(title='Synthetic cloud quotation',customer='Example customer',date='2026-10-28',currency='USD',status='Draft',tax='11',number='SYNTHETIC-001',revision=1,lines=[],document=d,internal_notes='CONFIDENTIAL-NOTE-SENTINEL')
    cpu['cost']='19.37'
    return q
