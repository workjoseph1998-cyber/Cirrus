"""Stable-ID revision comparison; conservative unique semantic fallback for imports."""
from collections import Counter
from decimal import Decimal
from flask import Blueprint,render_template,request
from .model import ValidationError
from .references import key
from .quotation import calculate,validate_document,public_document
from .commercial import amount,percent_difference

bp=Blueprint('comparison',__name__)
FIELDS=('service','sub_service','type','quantity','pricing_model','unit_price','fixed_fee','billing','comments','total','group','method','unit','state','section_excluded','hidden','optional')


def rows(q,doc=None,calc=None):
    doc=doc or validate_document(q['document']);calc=calc or calculate(doc);public=public_document(doc,calc)
    names={s['id']:s['name'] for s in public['sections']};result=[]
    for section in public['sections']:
        parent=next((s for s in public['sections'] if s['id']==section['parent']),None)
        for row in section['rows']:
            group=(names[section['parent']]+' / ' if section['parent'] else '')+section['name']
            result.append(dict(row,group=group,total=calc['rows'][row['id']],optional=row['id'] in calc['optional']['rows'],hidden=section['hidden'] or bool(parent and parent['hidden']),section_excluded=section['excluded'] or bool(parent and parent['excluded'])))
    return result


def signature(r):return tuple(' '.join(str(r.get(k,'')).casefold().split()) for k in ('service','sub_service','type','unit','billing'))


def compare(left,right):
    ld=validate_document(left['document']);rd=validate_document(right['document']);lc=calculate(ld);rc=calculate(rd)
    public_left=public_document(ld,lc);public_right=public_document(rd,rc)
    before=rows(left,ld,lc);after=rows(right,rd,rc);matched={};remaining={r['id']:r for r in before}
    for r in after:
        if r['id'] in remaining:matched[r['id']]=remaining.pop(r['id'])
    ls=Counter(signature(r) for r in remaining.values());rs=Counter(signature(r) for r in after if r['id'] not in matched)
    for r in after:
        sig=signature(r)
        if r['id'] not in matched and ls[sig]==rs[sig]==1:
            source=next(v for v in remaining.values() if signature(v)==sig);matched[r['id']]=remaining.pop(source['id'])
    items=[]
    for r in after:
        old=matched.get(r['id']);changed=[k for k in FIELDS if old and old.get(k,'')!=r.get(k,'')]
        items.append(dict(kind='added' if old is None else 'modified' if changed else 'unchanged',before=old,after=r,changes=changed))
    items.extend(dict(kind='removed',before=r,after=None,changes=[]) for r in remaining.values())
    metadata=[]
    for k in ('title','customer','contact','scope','exclusions','notes','payment_terms','delivery_terms','date','valid_until','currency'):
        if left.get(k,'')!=right.get(k,''):metadata.append(dict(label=k.replace('_',' ').title(),before=left.get(k,''),after=right.get(k,'')))
    for label,k in [('Terms and signatures','bottom_order'),('Terms','terms'),('Contract duration','contract_months'),('Summary discount policy','discount')]:
        a=public_left;b=public_right
        if k=='bottom_order':
            a={x:a[x] for x in ('company_signature','customer_signature')};b={x:b[x] for x in ('company_signature','customer_signature')}
        else:a=a[k];b=b[k]
        if k=='terms':
            a='\n\n'.join(t['title']+(' (hidden)' if not t['visible'] else '')+'\n'+t['text'] for t in a)
            b='\n\n'.join(t['title']+(' (hidden)' if not t['visible'] else '')+'\n'+t['text'] for t in b)
        if k=='bottom_order':
            a='\n\n'.join(v['heading']+'\n'+v['fields'] for v in a.values());b='\n\n'.join(v['heading']+'\n'+v['fields'] for v in b.values())
        if a!=b:metadata.append(dict(label=label,before=a,after=b))
    def term_order(q):
        doc=public_document(validate_document(q['document']));labels={t['id']:t['title'] for t in doc['terms']}
        return [labels.get(k,k.replace('_',' ')) for k in doc['bottom_order']]
    if term_order(left)!=term_order(right):metadata.append(dict(label='Terms order',before=' → '.join(term_order(left)),after=' → '.join(term_order(right))))
    old=None if lc['combined'] is None else Decimal(lc['combined']);new=None if rc['combined'] is None else Decimal(rc['combined']);comparable=left['currency']==right['currency'];delta=new-old if comparable and old is not None and new is not None else None
    modes={}
    for basis,title,field in [('monthly','Quoted monthly fees','discounted'),('contract','Total contract','combined')]:
        previous=None if lc[field] is None else Decimal(lc[field]);current=None if rc[field] is None else Decimal(rc[field])
        difference=current-previous if comparable and previous is not None and current is not None else None
        percent=percent_difference(previous,current) if comparable else None
        modes[basis]=dict(labels=[title+' · Previous · '+left['currency'],title+' · New · '+right['currency'],'Difference · '+(left['currency'] if comparable else 'currency mismatch'),'Difference · %'],
            values=[('Unpriced' if previous is None else ('$' if left['currency']=='USD' else '')+format(previous,',.2f')),('Unpriced' if current is None else ('$' if right['currency']=='USD' else '')+format(current,',.2f')),('—' if difference is None else ('$' if left['currency']=='USD' else '')+format(difference,',.2f')),('N/A · previous is zero' if previous==0 else '—') if percent is None else format(percent,'.2f')+'%'])
    return dict(summary_modes=modes,before_monthly=lc['discounted'],after_monthly=rc['discounted'],before_once=lc['one_time'],after_once=rc['one_time'],items=items,metadata=metadata,before=old,after=new,delta=delta,percent=percent_difference(old,new) if comparable else None,usd_delta=delta if comparable and left['currency']=='USD' else None,ambiguous=any(n>1 for n in ls.values()) or any(n>1 for n in rs.values()))


@bp.get('/quotes/<ident>/compare')
def page(ident):
    from .quote_routes import get_quote,connect
    from . import store
    record=get_quote(ident);k=key(record['data']['number'])
    with connect() as db:family=sorted([r for r in store.records(db) if r['kind']=='quote'],key=lambda r:(r['data']['revision'],r['updated']),reverse=True)
    same=[r for r in family if key(r['data']['number'])==k]
    left=get_quote(request.args.get('before') or same[min(1,len(same)-1)]['id']);right=get_quote(request.args.get('after') or same[0]['id'])

    basis='monthly' # V17 compares recurring monthly fees, never contract-duration totals.
    if basis not in ('monthly','contract'):raise ValidationError('Choose Monthly comparison or Total Contract comparison.')
    result=compare(left['data'],right['data']);result['summary_modes']={'monthly':result['summary_modes']['monthly']};only=request.args.get('changes')=='yes'
    if only:result['items']=[i for i in result['items'] if i['kind']!='unchanged']
    return render_template('comparison.html',basis=basis,record=record,family=family,left=left,right=right,result=result,only=only)
