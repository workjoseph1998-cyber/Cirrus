"""Version 2 quotations: ordered hierarchy, dependency DAG and exact money."""
import base64
import copy
import io
import re
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from .model import ValidationError, decimal, money
from .quotation_presentation import FEE_HEADINGS

COLUMNS = [('service','Service'),('sub_service','Sub Service'),('type','Type'),('quantity','Quantity'),
           ('pricing_model','Pricing Model'),('unit_price','Unit Price'),('amount','Monthly / One-Time Fee'),('comments','Comments')]
SUMMARY = [('sections','Section monthly subtotals'),('regular','Regular monthly total'),('discount','Monthly discount'),
 ('discounted','Discounted monthly total'),('yearly','Yearly recurring total (first 12 months)'),
 ('run_rate','Annualized regular run rate'),('one_time','One-time total'),('term','Contract recurring total'),
 ('tax','Contract tax'),('combined','Contract total incl. one-time and tax')]


def uid():
    return uuid4().hex


def new_row(service='New service', **overrides):
    r = dict(id=uid(),service=service,sub_service='',type='',quantity='0',unit='unit',pricing_model='',unit_price='',
             fixed_fee='',percent='20',method='unit',billing='monthly',state='priced',discount='0',
             targets=[],comments='',cost='',unverified_price=False,customer_percentage=False,item_key='',price_source='',support_keys=[],minimum_quantity='0',dr_mode='',dr_percent='100',dr_link='',dr_override=False)
    r.update(overrides)
    return r


def new_section(name,parent='',**overrides):
    s=dict(id=uid(),name=name,parent=parent,hidden=False,excluded=False,rows=[])
    s.update(overrides)
    return s


def default_document(company='CIRRUS SAL', terms='', delivery_terms=''):
    logo=base64.b64encode((Path(__file__).parent/'static/cirrus-logo.png').read_bytes()).decode()
    doc=dict(version=2,show_12_month=True,fee_headings=FEE_HEADINGS.copy(),optional_monitoring=False,monitoring_ids=[],sections=[],contract_months=12,discount=dict(percent='0',months=0,targets=[],enabled=False,wording='',kind='percent',amount='0',billing='monthly',duration='temporary',show_summary=False),
             tax=dict(mode='exclusive',rate='0',wording=''),columns=[dict(key=k,label=v,visible=True) for k,v in COLUMNS],
             summary=[dict(key=k,label=v,visible=k in ('sections','regular','one_time')) for k,v in SUMMARY],summary_title='Cost Summary',
             branding=dict(company=company,address='Holcom Bldg, 460 Corniche Al Nahr, POB: 17-5002 Beirut, Lebanon',
                           contact='Tel. 01-595569',vat='3166264-601',logo='data:image/png;base64,'+logo),
             company_signature=dict(heading='CIRRUS SAL',fields='Name:\nTitle:\nSignature:'),
             customer_signature=dict(heading='Customer',fields='Name:\nTitle:\nSignature:'),
             format=dict(font='Cambria',size='normal',orientation='landscape'),
             banner='CIRRUS — Domestic Cloud Services',project_name='',terms=[],bottom_order=[])
    for top,subs in [('Production',['Compute and storage','Security Services','Backup Services','8×5 Request Fulfillment']),
                     ('Disaster Recovery',['Compute and storage','Security Services','Backup Services','8×5 Request Fulfillment']),
                     ('Monitoring — 24×7 NOC Services',[]),('Cyber Security Services',[]),('Connectivity Services',[]),('Connectivity Setup — One-Time Fee',[])]:
        section=new_section(top);doc['sections'].append(section)
        children=[]
        for sub in subs:
            child=new_section(sub,section['id']);doc['sections'].append(child);children.append(child)
        if subs:
            support=children[-1]
            support['rows']=[new_row('Managed Services',sub_service='Working hours Support',type='Support',method='percent',quantity='1',targets=['s:'+x['id'] for x in children[:-1]])]
        else:
            section['rows']=[new_row('SOC',sub_service='SOC monitoring',unit='EPS',pricing_model='Per EPS',quantity='0')] if top=='Cyber Security Services' else []
        if top in ('Production','Disaster Recovery','Monitoring — 24×7 NOC Services'):
            doc['discount']['targets'].append('s:'+section['id'])
    reusable=[('Payment Terms',terms),('Delivery terms',delivery_terms),('Agreement and renewal','This is a yearly agreement based on consumption and will automatically renew at the end of each term unless either party gives the other written notice of termination at least 30 days prior to the end of the relevant term.'),
        ('Notice period','Either party gives the other written notice of termination at least 30 days prior to the end of the relevant term.'),
        ('Offer validity','Offer Validity: 2 weeks'),('Additional regulations, exclusions and notes','')]
    doc['terms']=[dict(id=uid(),title=title,text=text,visible=True) for title,text in reusable]
    doc['bottom_order']=[t['id'] for t in doc['terms']]+['company_signature','customer_signature','footer']
    from .support import standalone
    return standalone(doc)[0]


def legacy_document(data,company='CIRRUS SAL'):
    from .model import totals
    totals(data.get('lines'), data.get('tax','0'))
    doc=default_document(company)
    section=new_section('Services')
    section['rows']=[new_row(x['description'],billing='one_time',quantity=x['quantity'],unit=x['unit'],unit_price=x['price'],cost=x.get('cost',''),discount=x.get('discount','0')) for x in data.get('lines',[])]
    doc.update(sections=[section],discount=dict(percent='0',months=0,targets=[],enabled=False,wording='',kind='percent',amount='0',billing='monthly',duration='temporary',show_summary=False),
               tax=dict(mode='added',rate=data.get('tax','0'),wording=''),
               terms=[dict(id=uid(),title=label,text=data.get(key,''),visible=True) for key,label in [('payment_terms','Payment terms'),('delivery_terms','Delivery terms'),('exclusions','Exclusions'),('notes','Notes')]])
    # Deterministic IDs make repeated v1 imports identical after adaptation.
    from uuid import uuid5,NAMESPACE_URL
    seed=data.get('number','')+':'+str(data.get('revision',1))
    section['id']=uuid5(NAMESPACE_URL,seed+':section').hex
    for i,row in enumerate(section['rows']): row['id']=uuid5(NAMESPACE_URL,seed+':row:'+str(i)).hex
    for i,term in enumerate(doc['terms']): term['id']=uuid5(NAMESPACE_URL,seed+':term:'+str(i)).hex
    doc['bottom_order']=[t['id'] for t in doc['terms']]+['company_signature','customer_signature','footer']
    return doc


def clean_logo(value):
    if value=='': return ''
    if not isinstance(value,str) or len(value)>600000 or not re.fullmatch(r'data:image/(png|jpeg);base64,[A-Za-z0-9+/=]+',value):
        raise ValidationError('Logo must be a PNG/JPEG data image up to 400 KiB.')
    try:
        from PIL import Image
        raw=base64.b64decode(value.split(',',1)[1],validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            if image.width>2000 or image.height>2000: raise ValueError
            image.verify()
    except Exception:
        raise ValidationError('Invalid or oversized logo image (maximum 2000 × 2000).') from None
    return value


def validate_document(raw, enforce_minimum=False):
    if not isinstance(raw,dict): raise ValidationError('Quotation document must be an object.')
    d=copy.deepcopy(raw)
    d.setdefault('show_12_month',True) # Legacy appearance remains unchanged.
    d.setdefault('fee_headings',FEE_HEADINGS.copy())
    d.setdefault('optional_monitoring',False);d.setdefault('monitoring_ids',[])
    if type(d['show_12_month']) is not bool:raise ValidationError('Show 12-month column must be a boolean.')
    expected={'optional_monitoring','monitoring_ids','fee_headings','show_12_month','version','sections','contract_months','discount','tax','columns','summary','summary_title','branding','company_signature','customer_signature','format','banner','project_name','terms','bottom_order'}
    if set(d)!=expected or type(d['version']) is not int or d['version']!=2: raise ValidationError('Invalid quotation document version or fields.')
    def text(v,label,maximum=100000):
        if not isinstance(v,str) or len(v)>maximum: raise ValidationError(label+': invalid text.')
    def obj(v,keys):
        if not isinstance(v,dict) or set(v)!=set(keys): raise ValidationError('Invalid object fields: '+str(keys))
    def boolean(v):
        if type(v) is not bool: raise ValidationError('Expected a boolean.')
    def integer(v,label,maximum):
        if type(v) is not int or not 0<=v<=maximum: raise ValidationError(label+': invalid duration.')
    boolean(d['optional_monitoring'])
    if not isinstance(d['monitoring_ids'],list) or len(d['monitoring_ids'])>200 or any(not isinstance(x,str) or not re.fullmatch('[a-zA-Z0-9_-]{1,80}',x) for x in d['monitoring_ids']):raise ValidationError('Invalid Monitoring section selection.')
    obj(d['fee_headings'],FEE_HEADINGS)
    for label in d['fee_headings'].values():
        text(label,'Fee heading',200)
        if not label.strip():raise ValidationError('Fee headings cannot be blank.')
    integer(d['contract_months'],'Contract months',1200)
    if d['contract_months']==0: raise ValidationError('Contract must last at least one month.')
    if not isinstance(d['discount'],dict):raise ValidationError('Invalid discount policy.')
    for k,v in dict(kind='percent',amount='0',billing='monthly',duration='temporary',show_summary=False).items():d['discount'].setdefault(k,v)
    obj(d['discount'],('percent','months','targets','enabled','wording','kind','amount','billing','duration','show_summary'));boolean(d['discount']['show_summary'])
    if d['discount']['kind'] not in ('percent','fixed') or d['discount']['billing'] not in ('monthly','one_time','both') or d['discount']['duration'] not in ('full','temporary'):raise ValidationError('Invalid summary discount policy.')
    text(d['discount']['amount'],'Fixed discount',80);decimal(d['discount']['amount'],'Fixed discount')
    if d['discount']['enabled'] and d['discount']['show_summary'] and d['discount']['duration']=='temporary' and not d['discount']['months'] and d['discount']['billing']!='one_time':raise ValidationError('Specify at least one promotional month or choose full contract.')
    boolean(d['discount']['enabled'])
    integer(d['discount']['months'],'Discount months',1200)
    if d['discount']['duration']=='temporary' and d['discount']['months']>d['contract_months']: raise ValidationError('Discount duration exceeds contract duration.')
    text(d['discount']['percent'],'Discount percentage',80);decimal(d['discount']['percent'],'Discount',maximum=Decimal(100));text(d['discount']['wording'],'Discount wording')
    obj(d['tax'],('mode','rate','wording'));text(d['tax']['wording'],'Tax wording')
    if d['tax']['mode'] not in ('exclusive','added','included'): raise ValidationError('Invalid tax mode.')
    text(d['tax']['rate'],'Tax rate',80);decimal(d['tax']['rate'],'Tax',maximum=Decimal(100))
    obj(d['branding'],('company','address','contact','vat','logo'))
    for k,v in d['branding'].items(): text(v,k,600000 if k=='logo' else 100000)
    clean_logo(d['branding']['logo'])
    for key in ('company_signature','customer_signature'):
        obj(d[key],('heading','fields'))
        for v in d[key].values(): text(v,key)
    obj(d['format'],('font','size','orientation'))
    if d['format']['font'] not in ('Cambria','Arial','Calibri') or d['format']['size'] not in ('normal','large') or d['format']['orientation'] not in ('landscape','portrait'):
        raise ValidationError('Invalid format options.')
    for k in ('banner','summary_title','project_name'): text(d[k],k)
    for key, options in [('columns',COLUMNS),('summary',SUMMARY)]:
        if not isinstance(d[key],list) or len(d[key])!=len(options): raise ValidationError('Invalid '+key)
        seen=set()
        for x in d[key]:
            obj(x,('key','label','visible'));text(x['label'],'Column label',200);boolean(x['visible']);text(x['key'],'Column key',80);seen.add(x['key'])
        if seen!={k for k,_ in options}: raise ValidationError('Invalid '+key+' keys.')
    if not any(x['visible'] for x in d['columns']): raise ValidationError('At least one column must be visible.')
    if not isinstance(d['terms'],list) or len(d['terms'])>100: raise ValidationError('Maximum 100 term blocks.')
    ids=set()
    def ident(value):
        if not isinstance(value,str) or not re.fullmatch('[a-zA-Z0-9_-]{1,80}',value) or value in ids: raise ValidationError('Invalid or duplicate document ID.')
        ids.add(value)
    for t in d['terms']:
        obj(t,('id','title','text','visible'));ident(t['id']);text(t['title'],'Term title');text(t['text'],'Terms');boolean(t['visible'])
    if not isinstance(d['bottom_order'],list) or any(not isinstance(x,str) for x in d['bottom_order']) or len(set(d['bottom_order']))!=len(d['bottom_order']) or any(k not in {t['id'] for t in d['terms']}|{'company_signature','customer_signature','footer'} for k in d['bottom_order']): raise ValidationError('Invalid bottom block order.')
    if not isinstance(d['sections'],list) or not 1<=len(d['sections'])<=200: raise ValidationError('Use 1–200 sections.')
    count=0;sections={};rowmap={}
    for s in d['sections']:
        obj(s,('id','name','parent','hidden','excluded','rows')+(('role',) if 'role' in s else ()));
        if 'role' in s and s['role'] not in ('main','dr','monitoring','cyber','connectivity','setup','support','custom'):raise ValidationError('Invalid environment role.')
        ident(s['id']);text(s['name'],'Section name',300)
        if not s['name'].strip(): raise ValidationError('Section name is required.')
        boolean(s['hidden']);boolean(s['excluded']);text(s['parent'],'Parent ID',80);sections[s['id']]=s
        if not isinstance(s['rows'],list): raise ValidationError('Invalid rows.')
        count+=len(s['rows'])
        for r in s['rows']:
            if isinstance(r,dict):
                r.setdefault('unverified_price','[DEMO PRICE' in str(r.get('comments','')));r.setdefault('customer_percentage',False);r.setdefault('item_key','');r.setdefault('price_source','');r.setdefault('support_keys',[])
            if not isinstance(r['support_keys'],list) or len(r['support_keys'])>2000 or any(not isinstance(k,str) or len(k)>150 for k in r['support_keys']):raise ValidationError('Invalid support service selection.')
            for key,value in dict(minimum_quantity='0',dr_mode='',dr_percent='100',dr_link='',dr_override=False).items():r.setdefault(key,value)
            boolean(r['dr_override'])
            if r['dr_mode'] not in ('','replication','running'):raise ValidationError('Invalid DR mode.')
            text(r['dr_link'],'Production link',80)
            decimal(r['dr_percent'],'DR percentage',maximum=Decimal(100))
            minimum=decimal(r['minimum_quantity'],'Minimum quantity',maximum=Decimal(1000000))
            if enforce_minimum and r['state']=='priced' and not s['excluded'] and decimal(r['quantity'],'Quantity')<minimum:
                raise ValidationError(r['sub_service']+': minimum quantity is '+str(minimum)+'. Correct quantity before saving or exporting.')
            boolean(r.get('unverified_price'));boolean(r.get('customer_percentage'))
            obj(r,tuple(new_row().keys())+(('vm_selection_required',) if 'vm_selection_required' in r else ()));
            if 'vm_selection_required' in r:
                boolean(r['vm_selection_required'])
                if enforce_minimum and r['vm_selection_required'] and r['state']=='priced' and decimal(r['quantity'],'Quantity')>0:raise ValidationError('Choose a customer VM size for '+r['sub_service']+' before saving.')
            ident(r['id']);rowmap[r['id']]=(r,s)
            for k in ('service','sub_service','type','unit','pricing_model','comments','cost','item_key','price_source'):
                text(r[k],k)
            if not r['service'].strip(): raise ValidationError('Row service is required.')
            if r['method'] not in ('unit','fixed','percent') or r['billing'] not in ('monthly','one_time') or r['state'] not in ('priced','excluded','included'):
                raise ValidationError('Invalid pricing method, billing or price state.')
            for key in ('quantity','unit_price','fixed_fee','percent','discount'): text(r[key],key,80)
            decimal(r['quantity'],'Quantity',maximum=Decimal(1000000));decimal(r['unit_price'],'Unit price',optional=True)
            decimal(r['fixed_fee'],'Fixed fee',optional=True);decimal(r['cost'],'Internal cost',optional=True)
            decimal(r['percent'],'Percentage',maximum=Decimal(100));decimal(r['discount'],'Line discount',maximum=Decimal(100))
    if count>2000: raise ValidationError('Maximum 2,000 quotation rows.')
    for s in d['sections']:
        if s['parent'] and (s['parent'] not in sections or sections[s['parent']]['parent'] or s['parent']==s['id']): raise ValidationError('Subsections need a top-level parent; only two levels are supported.')
    from .optional_services import monitoring_ids
    d['monitoring_ids']=list(dict.fromkeys(x for x in d['monitoring_ids'] if x in sections))
    if d['optional_monitoring']:
        d['monitoring_ids']=monitoring_ids(d)
        if not d['monitoring_ids']:raise ValidationError('Optional Monitoring is enabled but no Monitoring section was found. Restore its section or uncheck Optional Monitoring.')
    def targets(value):
        if not isinstance(value,list) or len(value)>2200 or any(not isinstance(x,str) or x not in {'s:'+i for i in sections}|{'r:'+i for i in rowmap} for x in value):
            raise ValidationError('An eligibility target no longer exists; remove or replace it.')
        if len(set(value))!=len(value): raise ValidationError('Duplicate eligibility target.')
    targets(d['discount']['targets'])
    for r,s in rowmap.values():
        targets(r['targets'])
        if r['dr_link']:
            linked=rowmap.get(r['dr_link'])
            top=sections.get(s['parent'],s)
            if not r['dr_mode'] or top.get('role')!='dr' and 'disaster' not in top['name'].lower() and not re.search(r'\bDR\b',top['name'],re.I):raise ValidationError('DR links require a DR environment.')
            if not linked or linked[0].get('dr_mode') or linked[0]['unit'].lower()!='vm' or linked[0]['method']!='unit':raise ValidationError('Choose an existing Production VM for the explicit link.')
            source_top=sections.get(linked[1]['parent'],linked[1])
            if source_top.get('role')!='main' and not re.search(r'production|main[ _-]*site',source_top['name'],re.I):raise ValidationError('The linked VM must be in Production.')
            if not r['dr_override']:r['unit_price']=linked[0]['unit_price']
    try:
        calculate(d) # Includes cycle detection and billing compatibility.
    except ArithmeticError:
        raise ValidationError('Calculation exceeds supported decimal range; reduce quantities or percentage dependencies.') from None
    return d


def expand_targets(d,targets,rowmap=None):
    rowmap=rowmap if rowmap is not None else {r['id']:(r,s) for s in d['sections'] for r in s['rows']}
    result=set()
    for target in targets:
        if target.startswith('r:'):result.add(target[2:])
        else:
            sid=target[2:];selected={sid}|{s['id'] for s in d['sections'] if s['parent']==sid}
            result.update(r['id'] for r,s in rowmap.values() if s['id'] in selected)
    return result


def percentage_targets(d,row,rowmap=None):
    rowmap=rowmap if rowmap is not None else {r['id']:(r,s) for s in d['sections'] for r in s['rows']}
    chosen=expand_targets(d,row['targets'],rowmap)|{
        i for i,(candidate,_) in rowmap.items() if candidate.get('item_key') and
        candidate['item_key'] in row.get('support_keys',[]) and candidate['billing']==row['billing']}
    from .optional_services import row_ids
    optional=row_ids(d)
    return chosen-optional if row['id'] not in optional else chosen


def calculate(d):
    sections={s['id']:s for s in d['sections']}
    rowmap={r['id']:(r,s) for s in d['sections'] for r in s['rows']}
    from .optional_services import row_ids,LABEL
    optional=row_ids(d)
    def descendants(sid):
        return {sid}|{s['id'] for s in d['sections'] if s['parent']==sid}
    def expand(targets):
        return expand_targets(d,targets,rowmap)
    def excluded(r,s):
        return r['state']=='excluded' or s['excluded'] or bool(s['parent'] and sections[s['parent']]['excluded'])
    values={};visiting=set()
    def amount(ident):
        if ident in values: return values[ident]
        if ident in visiting: raise ValidationError('Circular percentage dependency: choose eligible rows/sections that do not include this fee.')
        if len(visiting)>100: raise ValidationError('Percentage dependency chain exceeds 100 rows.')
        visiting.add(ident);r,s=rowmap[ident]
        # Validate dependencies even on excluded/zero rows to avoid latent cycles.
        selected=percentage_targets(d,r,rowmap) if r['method']=='percent' else set()
        for target in selected:
            if rowmap[target][0]['billing']!=r['billing']: raise ValidationError('Percentage fee and eligible rows must have the same billing period.')
            amount(target)
        quantity=decimal(r['quantity'],'Quantity')
        if excluded(r,s) or r['state']=='included' or quantity==0:
            result=Decimal('0.00')
        elif r.get('unverified_price'):
            result=None
        elif r['method']=='unit':
            p=decimal(r['unit_price'],'Price',optional=True);result=None if p is None else quantity*p*(decimal(r.get('dr_percent','100'),'DR percentage')/100 if r.get('dr_mode') else 1)
        elif r['method']=='fixed':
            p=decimal(r['fixed_fee'],'Fixed fee',optional=True);result=p
        else:
            base=[values[k] for k in selected]
            result=None if any(x is None for x in base) else sum(base,Decimal(0))*decimal(r['percent'],'Percent')/100
        if result is not None: result=money(result*(1-decimal(r['discount'],'Discount')/100))
        visiting.remove(ident);values[ident]=result;return result
    for ident in rowmap: amount(ident)
    def total(ids):
        amounts=[values[i] for i in ids]
        return None if any(x is None for x in amounts) else sum(amounts,Decimal('0.00'))
    monthly={i for i,(r,s) in rowmap.items() if r['billing']=='monthly' and i not in optional}
    once=set(rowmap)-monthly-optional
    section_totals={sid:total({i for i,(r,s) in rowmap.items() if s['id'] in descendants(sid) and i in monthly}) for sid in sections}
    section_once={sid:total({i for i,(r,s) in rowmap.items() if s['id'] in descendants(sid) and i in once}) for sid in sections}
    regular=total(monthly);one_time=total(once)
    from .summary_discounts import apply
    policy=apply(d,values,monthly,once,expand(d['discount']['targets']))
    deduction=policy['monthly'];discount_months=policy['months'];months=d['contract_months']
    discounted=None if regular is None or deduction is None else regular-deduction
    discounted_final=None if regular is None or policy['final'] is None else regular-policy['final']
    original_one_time=one_time
    one_time=None if one_time is None or policy['once'] is None else one_time-policy['once']
    def recurring(duration):
        n=min(duration,discount_months)
        if regular is None or (n and deduction is None): return None
        discount_total=(policy['final'] or Decimal(0))*n+Decimal('.01')*min(n,policy['extra_months'])
        if not policy['extra_months']:discount_total=(deduction or Decimal(0))*n
        if discount_months and n==discount_months:
            if policy['recurring_total'] is None:return None
            discount_total=policy['recurring_total']
        return regular*duration-discount_total
    term=recurring(months);yearly=recurring(min(12,months));run_rate=None if regular is None else regular*12
    base=None if term is None or one_time is None else term+one_time
    tax_rate=decimal(d['tax']['rate'],'Tax')/100
    tax=None if base is None else money(base*tax_rate/(1+tax_rate)) if d['tax']['mode']=='included' else money(base*tax_rate)
    combined=None if base is None else base+(tax if d['tax']['mode']=='added' else Decimal(0))
    def output(n): return str(n) if n is not None else None
    opt_monthly=total({i for i in optional if rowmap[i][0]['billing']=='monthly'})
    opt_once=total({i for i in optional if rowmap[i][0]['billing']=='one_time'})
    optional_totals=dict(sections={sid:dict(monthly=output(total({i for i in optional if rowmap[i][1]['id'] in descendants(sid) and rowmap[i][0]['billing']=='monthly'})),one_time=output(total({i for i in optional if rowmap[i][1]['id'] in descendants(sid) and rowmap[i][0]['billing']=='one_time'}))) for sid in sections},label=LABEL,rows=sorted(optional),monthly=output(opt_monthly),one_time=output(opt_once),yearly=output(opt_monthly*12) if opt_monthly is not None else None)
    return dict(rows={k:output(v) for k,v in values.items()},sections={k:output(v) for k,v in section_totals.items()},
                optional=optional_totals,
                sections_once={k:output(v) for k,v in section_once.items()},
                sections_yearly={k:output(v*min(12,months)) if v is not None else None for k,v in section_totals.items()},
                original_one_time=output(original_one_time),one_time_discount=output(policy['once']),recurring_discount_total=output(policy['recurring_total']),discount_months=str(discount_months),discount_extra_months=str(policy['extra_months']),discount_final=output(policy['final']),discounted_final=output(discounted_final),regular=output(regular),discount=output(deduction),discounted=output(discounted),yearly=output(yearly),
                run_rate=output(run_rate),one_time=output(one_time),term=output(term),tax=output(tax),combined=output(combined))


def is_support(row,section=None):
    group=(section or {}).get('name','').casefold().replace('×','x').replace('*','x')
    support=row.get('type','').casefold()=='support' or 'support' in row.get('sub_service','').casefold() or '8x5' in group or 'request fulfillment' in group
    return row.get('method')=='percent' and (support or not row.get('customer_percentage',False))


def clean_vm_comments(text):
    """Remove only the dedicated OS line emitted by the VM picker.

    Arbitrary manual text and OS-like VM names remain intact.
    """
    if re.search(r'^VM Size:',text,re.M) and re.search(r'^VM Specs:',text,re.M):
        return '\n'.join(line for line in text.splitlines() if not re.fullmatch(r'Operating system: [^\r\n]+',line))
    return text


def clean_generated_notice(text):
    return '\n'.join(line for line in text.splitlines() if not line.strip().startswith('[DEMO PRICE')).strip()


def public_document(doc,calc=None,retain_schema=False):
    d=customer_cleanup(copy.deepcopy(doc));calc=calc or calculate(d)
    for s in d['sections']:
        for r in s['rows']:
            r['comments']=clean_vm_comments(clean_generated_notice(r['comments']))
            if r.get('unverified_price'):r.update(unit_price='',fixed_fee='')
            if is_support(r,s):
                r['comments']=''
                if '%' in r['sub_service'] or any(x in r['sub_service'].casefold() for x in ('basis','eligible')):r['sub_service']='Working hours Support'
                r.update(method='fixed',fixed_fee=calc['rows'][r['id']] or '',unit_price='',percent='0',targets=[],discount='0',pricing_model='Monthly service fee',cost='')
            r.pop('item_key',None);r.pop('price_source',None);r.pop('support_keys',None)
            if retain_schema:r.update(item_key='',price_source='',support_keys=[])
            if not retain_schema:r.pop('cost',None)
            else:r['cost']=''
    return d


def discount_wording(d):
    rule=d['discount']
    if not rule['enabled'] or not rule.get('show_summary',False):return ''
    if rule['wording']: return rule['wording']
    amount=(rule.get('amount','0')+' fixed total') if rule.get('kind')=='fixed' else rule['percent']+'%'
    period='full contract' if rule.get('duration')=='full' else 'first '+str(rule['months'])+' month(s)'
    scope={'monthly':'selected recurring services','one_time':'selected one-time services','both':'selected recurring and one-time services'}[rule.get('billing','monthly')]
    return f"Discount: {amount} on {scope}; {period} for recurring charges. Applied to fees after line discounts."


def customer_cleanup(d):
    """Output policy applies to both blank/company cases and legacy snapshots."""
    for item in d['summary']:
        item['visible']=item['visible'] and item['key'] in ('sections','regular','one_time')
        if item['key']=='regular':item['label']='Total monthly fee'
        if item['key']=='one_time':item['label']='Total one-time fee'
    d['terms']=[t for t in d['terms'] if not deprecated_term(t)]
    valid={t['id'] for t in d['terms']}|{'company_signature','customer_signature','footer'}
    d['bottom_order']=[x for x in d['bottom_order'] if x in valid]
    return d


def deprecated_term(t):
    title=t['title'].strip().casefold();text=' '.join(t['text'].casefold().split())
    return title=='vat / tax conditions' or 'the due vat will be calculated at the current bdl' in text or text.startswith('prices provided exclude vat, and any other government taxes')


def duplicate_document(document):
    """Fresh row/section identities and explicit references within a copied quote."""
    result=copy.deepcopy(document)
    mapping={s['id']:uid() for s in result['sections']}
    mapping.update({r['id']:uid() for s in result['sections'] for r in s['rows']})
    for s in result['sections']:
        s['id']=mapping[s['id']];s['parent']=mapping.get(s['parent'],s['parent'])
        for r in s['rows']:
            r['id']=mapping[r['id']]
            r['targets']=[t[:2]+mapping.get(t[2:],t[2:]) for t in r['targets']]
            if r.get('dr_link'):r['dr_link']=mapping[r['dr_link']]
    result['discount']['targets']=[t[:2]+mapping.get(t[2:],t[2:]) for t in result['discount']['targets']]
    result['monitoring_ids']=[mapping.get(i,i) for i in result.get('monitoring_ids',[])]
    return result
