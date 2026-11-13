"""Commercial calculation basis shared by comparison, statistics and costing."""
import hashlib,json
from decimal import Decimal,ROUND_HALF_UP
from .quotation import calculate,validate_document
from .model import totals

CENT=Decimal('.01')
def rounded(x):return x.quantize(CENT,rounding=ROUND_HALF_UP)
def fingerprint(data):return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def amount(q):
    value=calculate(validate_document(q['document']))['combined'] if 'document' in q else totals(q['lines'],q['tax'])['grand_total']
    return None if value is None else Decimal(value)


def percent_difference(before,after):
    if before is None or after is None or before==0:return None
    return rounded((after-before)/abs(before)*100)


def eligible_rows(doc):
    ids=set()
    for target in doc['discount']['targets']:
        if target.startswith('r:'):ids.add(target[2:])
        else:
            sid=target[2:];sections={sid}|{s['id'] for s in doc['sections'] if s['parent']==sid}
            ids.update(r['id'] for s in doc['sections'] if s['id'] in sections for r in s['rows'])
    return ids


def line_values(q):
    """Full-contract selling amounts excluding sales tax, reconciled to canonical math."""
    doc=validate_document(q['document']);calc=calculate(doc);months=doc['contract_months']
    rows={r['id']:r for s in doc['sections'] for r in s['rows']}
    from .optional_services import row_ids
    optional=row_ids(doc)
    values={rid:Decimal(0) if rid in optional else None if calc['rows'][rid] is None else Decimal(calc['rows'][rid])*(months if r['billing']=='monthly' else 1) for rid,r in rows.items()}
    from .summary_discounts import apply
    monthly={rid for rid,r in rows.items() if r['billing']=='monthly' and rid not in optional}
    raw={rid:None if calc['rows'][rid] is None else Decimal(calc['rows'][rid]) for rid in rows}
    policy=apply(doc,raw,monthly,set(rows)-monthly-optional,eligible_rows(doc))
    for ids,deduction,periods in [(policy['recurring_ids'],policy['recurring_total'],policy['months']), (policy['once_ids'],policy['once'],1)]:
        if deduction is None:
            for rid in ids:
                if doc['discount'].get('kind')=='fixed':values[rid]=None
                elif values[rid] is not None:values[rid]-=rounded(raw[rid]*Decimal(doc['discount']['percent'])/100)*periods
        else:
            weighted=sorted(rid for rid in ids if raw[rid] is not None and raw[rid]>0)
            basis=sum((raw[rid] for rid in weighted),Decimal(0));remainder=deduction
            for i,rid in enumerate(weighted):
                share=remainder if i==len(weighted)-1 else rounded(deduction*raw[rid]/basis)
                values[rid]-=share;remainder-=share
    if doc['tax']['mode']=='included':
        rate=Decimal(doc['tax']['rate'])/100+1
        values={rid:None if v is None else rounded(v/rate) for rid,v in values.items()}
        if all(v is not None for v in values.values()) and values:
            target=Decimal(calc['term'])+Decimal(calc['one_time'])-Decimal(calc['tax'])
            nonzero=[rid for rid,value in values.items() if value]
            last=sorted(nonzero or values)[-1];values[last]+=target-sum(values.values(),Decimal(0))
    return values
