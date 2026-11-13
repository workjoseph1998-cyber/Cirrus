"""Editor-only explanations built from the same Decimal inputs as the calculator."""
from .quotation import calculate, percentage_targets
from .model import decimal
from .quotation_presentation import dollars

def explanations(doc):
    calc=calculate(doc);rows={r['id']:(r,s) for s in doc['sections'] for r in s['rows']};result={}
    for ident,(r,s) in rows.items():
        fee=dollars(calc['rows'][ident]);lines=[]
        period='month' if r['billing']=='monthly' else 'one-time'
        top=next((x for x in doc['sections'] if x['id']==s['parent']),s)
        if r['state'] in ('excluded','included') or s['excluded'] or top['excluded'] or decimal(r['quantity'],'Quantity')==0:
            result[ident]=['Calculation: no charge ('+('quantity zero' if decimal(r['quantity'],'Quantity')==0 else 'included / excluded')+') = '+fee,'Quantity: '+r['quantity']]
            continue
        adjustment=(' × (1 − '+r['discount']+'%)') if decimal(r['discount'],'Discount') else ''
        if r['method']=='percent':
            selected=percentage_targets(doc,r,rows)
            for key in sorted(selected):lines.append(rows[key][0]['service']+' / '+rows[key][0]['sub_service']+': '+dollars(calc['rows'][key]))
            amounts=[calc['rows'][key] for key in selected]
            base=None if any(x is None for x in amounts) else sum(decimal(x,'Amount') for x in amounts)
            lines+=['Combined subtotal: '+dollars(base),'Percentage: '+r['percent']+'%','Calculation: '+dollars(base)+' × '+r['percent']+'%'+adjustment+' = '+fee]
        elif r['method']=='fixed':lines=['Fixed fee: '+dollars(r['fixed_fee']),'Result: '+fee]
        else:
            lines=['Quantity: '+r['quantity']+' '+r['unit'],('Base VM price (quotation override)' if r.get('dr_override') else 'Base VM price' if r.get('dr_mode') else 'Unit price')+': '+dollars(r['unit_price'])+'/'+r['unit']+'/'+period]
            rate=''
            if r.get('dr_mode'):
                lines+=['DR mode: '+('Replication only' if r['dr_mode']=='replication' else 'Running'),'Applied rate: '+r['dr_percent']+'%']
                rate=' × '+r['dr_percent']+'%'
            lines+=['Calculation: '+r['quantity']+' × '+dollars(r['unit_price'])+rate+adjustment+' = '+fee+'/'+period]
        if decimal(r.get('minimum_quantity','0'),'Minimum')>0:lines+=['Minimum quantity: '+r['minimum_quantity']+' '+r['unit']]
        if decimal(r['discount'],'Discount')>0:lines+=['Line discount: '+r['discount']+'% (included in result)']
        if r['state']!='priced' or s['excluded'] or r['quantity']=='0':lines+=['Price state / activation: '+r['state']+'; quantity '+r['quantity']]
        lines+=['Final amount rounded to cents.']
        result[ident]=lines
    return result
