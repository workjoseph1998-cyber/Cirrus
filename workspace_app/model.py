"""Version-one record schema, validation and exact quotation arithmetic."""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

KINDS = ('note', 'project', 'catalog', 'quote', 'category', 'customer', 'document')
NOTE_TYPES = ('Note', 'Question and answer', 'Procedure', 'Troubleshooting', 'Reference', 'Decision')
STATUSES = {'note': ('Open', 'Answered', 'Closed'), 'project': ('Planning', 'Active', 'On hold', 'Completed'),
            'quote': ('Draft', 'Internal Review', 'Approved', 'Under review', 'Sent', 'On hold', 'Won', 'Lost', 'Accepted', 'Rejected', 'Cancelled'), 'catalog': ('Active', 'Inactive')}
# name, label, control; shared by server-rendered forms and validation.
FIELDS = {
 'customer': [('name','Customer name','text'), ('contact','Contact details','area'), ('notes','Notes','area')],
 'note': [('title','Title','text'), ('visibility','Visibility','visibility'), ('content','Content / question','area'), ('answer','Answer','area'),
          ('type','Type','note_type'), ('status','Question status','status'), ('category','Category','category'),
          ('subcategory','Subcategory','subcategory'), ('tags','Tags (comma separated)','text'),
          ('project_id','Project','project'), ('source_url','Source URL','url')],
 'project': [('name','Project name','text'), ('customer','Customer text (preserved)','text'), ('customer_id','Linked customer','customer'), ('description','Description','area'),
             ('scope','Scope','area'), ('status','Status','status'), ('start_date','Start date','date'),
             ('end_date','End date','date'), ('requirements','Requirements','area'),
             ('assumptions','Assumptions and constraints','area'), ('architecture','Technical design / architecture','area'),
             ('sizing','Sizing notes','area'), ('bom','BOM items (one per line)','area'), ('references','Reference links (one URL per line)','area')],
 'catalog': [('code','Item code','text'), ('name','Name','text'), ('vendor','Vendor','text'), ('category','Category','text'),
             ('service','Service','text'), ('sub_service','Sub Service','text'), ('description','Quotation description','area'), ('unit','Unit (user, core, VM, device, node, agent, hour, day, month, year, or custom)','text'),
             ('cost','Default cost (optional)','money'), ('price','Selling price (optional)','money'), ('currency','Currency (three letters)','text'),
             ('duration','Subscription / support duration','text'),
             ('type','Quotation Type','text'), ('comments','Quotation comments / VM specifications','area'),
             ('pricing_model','Pricing model description','text'), ('billing','Billing (monthly / one_time)','text'),
             ('method','Method (unit / fixed / percent)','text'), ('support_percent','Default support percentage (percent method)','money'), ('fixed_fee','Fixed fee (optional)','money'),
             ('minimum_quantity','Minimum quantity (0 = none)','money'), ('quantity','Default quantity','money'), ('discount','Line discount %','money'), ('internal_notes','Internal notes','area'), ('status','Status','status')],
 'quote': [('customer_id','Linked customer','customer'), ('title','Quotation title','text'), ('customer','Customer','text'), ('contact','Contact details','area'),
           ('date','Date','date'), ('valid_until','Valid until','date'), ('currency','Currency (three letters)','text'),
           ('status','Status','status'), ('project_id','Project','project'), ('scope','Scope / introduction','area'),
           ('tax','Tax (%)','money'), ('payment_terms','Payment terms','area'), ('delivery_terms','Delivery terms','area'),
           ('exclusions','Exclusions','area'), ('notes','Customer notes','area'), ('internal_notes','Internal notes','area')],
 'document': [('title','Document title','text'),('type','Document type','text'),('customer_id','Linked customer','customer'),('customer','Customer','text'),('contact','Contact','area'),('project_id','Customer agreement','project'),('date','Document date','date'),('status','Status','text'),('subject','Subject','text'),('content','Document content','area')],
 'category': [('name','Category name','text'), ('parent','Parent category (blank for top level)','parent')]
}
REQUIRED = {'customer': ('name',), 'note': ('title','type'), 'project': ('name','customer','status'),
            'catalog': ('code','name','unit','currency','status'),
            'quote': ('title','customer','date','currency','status'), 'category': ('name',), 'document': ('title','type','customer','date','status')}

class ValidationError(ValueError):
    pass


def decimal(value, label, optional=False, maximum=Decimal('1000000000000')):
    if value in ('', None) and optional:
        return None
    try:
        if isinstance(value, bool):
            raise InvalidOperation
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > maximum:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise ValidationError(f'{label}: enter a nonnegative number up to {maximum}.') from None
    return result


def money(value):
    return value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def totals(lines, tax):
    if not isinstance(lines, list) or not lines or len(lines) > 500:
        raise ValidationError('A quotation needs 1–500 line items.')
    subtotal = Decimal(0)
    cost = Decimal(0)
    fully_priced = True
    cost_known = True
    output = []
    for line in lines:
        if not isinstance(line, dict) or set(line) - {'description','unit','quantity','price','cost','discount'}:
            raise ValidationError('Invalid quotation line fields.')
        if not str(line.get('description','')).strip() or not str(line.get('unit','')).strip():
            raise ValidationError('Each line needs a description and unit.')
        qty = decimal(line.get('quantity'), 'Quantity')
        if not qty or qty > 1000000:
            raise ValidationError('Quantity must be greater than zero and at most 1,000,000.')
        price = decimal(line.get('price'), 'Selling price', optional=True)
        unit_cost = decimal(line.get('cost'), 'Cost', optional=True)
        discount = decimal(line.get('discount', '0'), 'Discount', maximum=Decimal(100))
        amount = money(qty * price * (1 - discount / 100)) if price is not None else None
        if amount is None:
            fully_priced = False
        else:
            subtotal += amount
        if unit_cost is None:
            cost_known = False
        else:
            cost += money(qty * unit_cost)
        output.append({'description': str(line['description']).strip(), 'unit': str(line['unit']).strip(),
                       'quantity': str(qty), 'price': str(price) if price is not None else '',
                       'cost': str(unit_cost) if unit_cost is not None else '', 'discount': str(discount),
                       'total': str(amount) if amount is not None else None})
    rate = decimal(tax, 'Tax', maximum=Decimal(100))
    tax_amount = money(subtotal * rate / 100) if fully_priced else None
    grand = subtotal + tax_amount if fully_priced else None
    margin = money(subtotal - cost) if fully_priced and cost_known else None
    return {'lines': output, 'subtotal': str(subtotal) if fully_priced else None,
            'tax_amount': str(tax_amount) if tax_amount is not None else None,
            'grand_total': str(grand) if grand is not None else None,
            'internal_cost': str(cost) if cost_known else None,
            'internal_margin': str(margin) if margin is not None else None}


def validate(kind, data, records, current_id=None, preserve_customer=False):
    if kind not in KINDS or not isinstance(data, dict):
        raise ValidationError('Invalid record type or data.')
    allowed = {f[0] for f in FIELDS[kind]} | ({'lines', 'number', 'revision', 'document'} if kind in ('quote','document') else set())
    if set(data) - allowed:
        raise ValidationError('Unknown fields: ' + ', '.join(sorted(set(data) - allowed)))
    d = {}
    for key, label, control in FIELDS[kind]:
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > 100000:
            raise ValidationError(f'{label}: expected text (maximum 100,000 characters).')
        d[key] = value.strip()
        if key=='customer' and kind in ('project','quote') and not d[key] and data.get('customer_id'):
            d[key]=next((r['data'].get('name','') for r in records if r['kind']=='customer' and r['id']==data['customer_id']), '')
        if key in REQUIRED[kind] and not d[key]:
            raise ValidationError(f'{label} is required.')
        if control == 'date' and value:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError:
                raise ValidationError(f'{label}: invalid ISO date.') from None
    if kind in STATUSES and d['status'] not in STATUSES[kind]:
        raise ValidationError('Invalid status.')
    if kind=='note':
        if not d['visibility']:d['visibility']='Work'
        if d['visibility'] not in ('Work','Personal'):raise ValidationError('Visibility must be Work or Personal.')
    if kind == 'note' and d['type'] not in NOTE_TYPES:
        raise ValidationError('Invalid note type.')
    if kind == 'note' and d['source_url'] and not re.match(r'^https?://[^\s]+$', d['source_url']):
        raise ValidationError('Source URL must use http or https.')
    if kind == 'project' and any(not re.match(r'^https?://[^\s]+$', x) for x in d['references'].splitlines() if x):
        raise ValidationError('Reference links must use http or https.')
    for start, end in (('start_date','end_date'), ('date','valid_until')):
        if d.get(start) and d.get(end) and d[start] > d[end]:
            raise ValidationError('End / validity date must not precede start date.')
    def exists(target, value):
        return any(r['kind'] == target and r['id'] == value for r in records)
    if d.get('customer_id') and not exists('customer', d['customer_id']):
        raise ValidationError('Linked customer does not exist or is not accessible.')
    if d.get('project_id') and not exists('project', d['project_id']):
        raise ValidationError('Linked project does not exist.')
    if kind=='quote' and not preserve_customer and d.get('project_id') and d.get('customer_id'):
        linked=next((r for r in records if r['kind']=='project' and r['id']==d['project_id']),None)
        if linked and linked['data'].get('customer_id') and linked['data']['customer_id']!=d['customer_id']:raise ValidationError('Linked customer must match the project customer. Customer display text remains an independent snapshot.')
    if kind == 'note':
        if d['category'] and not exists('category', d['category']):
            raise ValidationError('Category does not exist.')
        if d['subcategory']:
            child = next((r for r in records if r['kind'] == 'category' and r['id'] == d['subcategory']), None)
            if not child or not d['category'] or child['data'].get('parent') != d['category']:
                raise ValidationError('Subcategory must belong to the selected category.')
    if kind == 'category' and d['parent']:
        parent = next((r for r in records if r['kind'] == 'category' and r['id'] == d['parent']), None)
        if not parent or parent['data'].get('parent') or d['parent'] == current_id:
            raise ValidationError('Choose a top-level parent; categories support two levels.')
        if any(r['kind'] == 'category' and r['data'].get('parent') == current_id for r in records):
            raise ValidationError('A category with children must remain top-level.')
    if kind=='document':
        from .documents import TYPES,DOC_STATUSES
        if d['type'] not in TYPES or d['type']=='Quotation' or d['status'] not in DOC_STATUSES:raise ValidationError('Invalid document type or status.')
        d['number']=str(data.get('number',''));d['revision']=data.get('revision',1)
        from .references import key
        key(d['number'])
        if type(d['revision']) is not int or not 1<=d['revision']<=1000000:raise ValidationError('Invalid document revision.')
    if kind in ('catalog', 'quote'):
        d['currency'] = d['currency'].upper()
        if not re.fullmatch('[A-Z]{3}', d['currency']):
            raise ValidationError('Currency must be a three-letter code.')
    if kind == 'catalog':
        d['service']=d.get('service') or d['name']
        d['sub_service']=d.get('sub_service') or d['description']
        for k,v in {'billing':'monthly','method':'unit','quantity':'1','discount':'0'}.items():
            if not d[k]:d[k]=v
        if d['billing'] not in ('monthly','one_time') or d['method'] not in ('unit','fixed','percent'):
            raise ValidationError('Catalog billing must be monthly/one_time and method unit/fixed/percent.')
        d['support_percent']=d.get('support_percent') or ('20' if d['method']=='percent' else '')
        decimal(d['support_percent'],'Support percentage',optional=True,maximum=Decimal(100))
        if d['method']=='percent' and d['billing']!='monthly':raise ValidationError('Support percentage catalog defaults must use monthly billing.')
        d['minimum_quantity']=d.get('minimum_quantity') or '0'
        decimal(d['minimum_quantity'],'Minimum quantity',maximum=Decimal(1000000))
        decimal(d['quantity'],'Quantity',maximum=Decimal(1000000))
        decimal(d['discount'],'Discount',maximum=Decimal(100))
        decimal(d['fixed_fee'],'Fixed fee',optional=True)
        for key in ('cost','price'):
            n = decimal(d[key], key, optional=True)
            d[key] = '' if n is None else str(n)
        if any(r['kind'] == kind and r['id'] != current_id and r['data']['code'].casefold() == d['code'].casefold() for r in records):
            raise ValidationError('Catalog item code already exists.')
    if kind == 'quote':
        if 'document' in data:
            from .quotation import validate_document
            d['document'] = validate_document(data['document'], enforce_minimum=True)
            d['lines'] = data.get('lines', [])
            if not isinstance(d['lines'], list):
                raise ValidationError('Legacy lines must be an array.')
            if d['lines']:
                totals(d['lines'], d['tax'])
            d['tax'] = d['document']['tax']['rate']
        else:
            calculation = totals(data.get('lines'), d['tax'])
            d['lines'] = [{k:v for k,v in line.items() if k != 'total'} for line in calculation['lines']]
        d['number'] = str(data.get('number',''))
        d['revision'] = data.get('revision', 1)
        if not d['number'].strip() or len(d['number']) > 80 or not d['number'].isprintable() or type(d['revision']) is not int or not 1 <= d['revision'] <= 1000000:
            raise ValidationError('Invalid quotation number or revision.')
        if any(r['kind'] == kind and r['id'] != current_id and (r['data']['number'].strip().casefold(),r['data']['revision']) == (d['number'].strip().casefold(),d['revision']) for r in records):
            raise ValidationError('Quotation number / revision already exists.')
    return d
