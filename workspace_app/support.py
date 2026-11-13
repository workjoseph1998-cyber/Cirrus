"""Move existing 8x5 fees once, keeping row IDs and calculation bases intact."""
import copy
from uuid import uuid5,NAMESPACE_URL
from .quotation import calculate,is_support,new_section
from .model import ValidationError


def calculation_details(doc,calc):
    """Editor-only bases from the same target resolver used by exact calculation."""
    from decimal import Decimal
    from .quotation import percentage_targets
    rows={r['id']:(r,s) for s in doc['sections'] for r in s['rows']}
    result={}
    for ident,(r,s) in rows.items():
        if r['method']!='percent':continue
        selected=percentage_targets(doc,r,rows)
        amounts=[calc['rows'][i] for i in selected]
        base=None if any(x is None for x in amounts) else str(sum((Decimal(x) for x in amounts),Decimal('0.00')))
        result[ident]=dict(base=base,fee=calc['rows'][ident],percent=r['percent'],
            services=[dict(id=i,name=section['name']+' / '+candidate['service']+
                          (' / '+candidate['sub_service'] if candidate['sub_service'] else ''),amount=calc['rows'][i])
                      for i,(candidate,section) in rows.items() if i in selected])
    return result


def standalone(doc):
    from .quotation import validate_document
    d=validate_document(doc);sections={s['id']:s for s in d['sections']}
    moved=[s for s in d['sections'] if s['parent'] and ('8x5' in s['name'].casefold().replace('×','x').replace('*','x') or 'request fulfillment' in s['name'].casefold())]
    if not moved:return d,False
    before=calculate(d)
    ident=uuid5(NAMESPACE_URL,'cirrus-standalone-support:'+':'.join(sorted(s['id'] for s in moved))).hex
    top=new_section('8×5 Request Fulfillment',id=ident)
    # Every old target of a parent must retain eligibility of the moved rows.
    additions={}
    for s in moved:
        parent=sections[s['parent']];additions.setdefault('s:'+parent['id'],[]).extend('r:'+r['id'] for r in s['rows'])
        s.update(name=parent['name']+' support',parent=ident,hidden=s['hidden'] or parent['hidden'],excluded=s['excluded'] or parent['excluded'])
    for obj in [d['discount']]+[r for s in d['sections'] for r in s['rows']]:
        obj['targets']=list(dict.fromkeys(obj['targets']+[r for t in obj['targets'] for r in additions.get(t,[])]))
    d['sections'].append(top)
    after=calculate(d)
    if any(before[k]!=after[k] for k in ('rows','regular','discount','discounted','one_time','term','tax','combined')):
        raise ValidationError('Support layout conversion would change saved fees. Review the original quotation before converting.')
    return d,True


def defaults(db,scope):
    import json
    row=db.execute('SELECT data FROM customer_preferences WHERE scope_id=?',(scope,)).fetchone()
    return json.loads(row['data']) if row else dict(support_percent='',support_base=['category:Production','category:Disaster Recovery'],discount=dict(enabled=False,kind='percent',percent='0',amount='0',billing='monthly',duration='full',months=0,wording=''))


def apply_defaults(doc,prefs):
    d,_=standalone(doc)
    # New quotations use one customer policy. Historical quotations only go
    # through standalone(), which retains every existing row and fee unchanged.
    fees=[r for s in d['sections'] for r in s['rows'] if r['method']=='percent' and (r['type'].casefold()=='support' or 'support' in r['sub_service'].casefold() or 'request fulfillment' in s['name'].casefold())]
    if fees:
        first=copy.deepcopy(fees[0]);old_ids={r['id'] for r in fees}
        for s in d['sections']:s['rows']=[r for r in s['rows'] if r['id'] not in old_ids]
        top=next((s for s in d['sections'] if not s['parent'] and 'request fulfillment' in s['name'].casefold()),None)
        if top is None:
            top=new_section('8×5 Request Fulfillment');d['sections'].append(top)
        first['quantity']='1';first['state']='priced'
        if prefs['support_percent']!='':first['percent']=prefs['support_percent']
        first['targets']=['s:'+x['id'] for x in d['sections'] if 'category:'+x['name'] in prefs['support_base'] and x['id']!=top['id'] and not x['parent']]
        first['support_keys']=[v for v in prefs['support_base'] if not v.startswith('category:')]
        top['rows'].append(first)
        for obj in [d['discount']]+[r for s in d['sections'] for r in s['rows'] if r is not first]:
            obj['targets']=list(dict.fromkeys('r:'+first['id'] if t.startswith('r:') and t[2:] in old_ids else t for t in obj['targets']))
        for s in d['sections']:
            if s['parent']==top['id'] and not s['rows']:s['hidden']=True
    rule=prefs['discount']
    if rule['enabled']:
        d['discount'].update(rule,show_summary=True,targets=['s:'+s['id'] for s in d['sections'] if not s['parent']])
    return d
