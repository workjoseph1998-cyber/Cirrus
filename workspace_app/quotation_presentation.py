"""Saved headings and display-only money formatting; never changes price drivers."""
import re
from decimal import Decimal

FEE_HEADINGS = {'monthly': 'Monthly Fee', 'one_time': 'One-Time Fee'}
EXCEL_DOLLARS = '"$"#,##0.00'


def dollars(value):
    return 'Unpriced' if value is None or value == '' else '$' + format(Decimal(value), ',.2f')


def price_input(value):
    """At least two decimals, retaining any additional saved price precision."""
    if value is None or value == '':return ''
    plain=format(Decimal(value),'f')
    whole,_,fraction=plain.partition('.')
    return whole+'.'+fraction.ljust(2,'0')


def clean_heading(label):
    return re.sub(r'\s*\(USD\)\s*$', '', label, flags=re.I).strip()


def fee_heading(doc,billing):
    return clean_heading(doc.get('fee_headings',FEE_HEADINGS)[billing])


def column_heading(doc,key,top=None):
    label=clean_heading(next(c['label'] for c in doc['columns'] if c['key']==key))
    if key!='amount' or label.casefold() not in ('monthly / one-time fee','monthly fee','one-time fee'):
        return label
    sections=[s for s in doc['sections'] if top is None or s['id']==top['id'] or s['parent']==top['id']]
    periods={r['billing'] for s in sections for r in s['rows']}
    if not periods:
        periods={'one_time' if top and re.search(r'one[ -]time',top['name'],re.I) else 'monthly'}
    return ' / '.join(fee_heading(doc,k) for k in ('monthly','one_time') if k in periods)


def visible_totals(monthly,one_time):
    """Keep unpriced periods visible, suppress numeric zero alongside a charge."""
    result=[]
    for label,value in [('Monthly',monthly),('One-time',one_time)]:
        if value is None or Decimal(value)!=0:result.append((label,value))
    return result or [('Total','0.00')]
