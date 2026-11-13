"""One discount basis for documents, exports, statistics and costing.

Percentages apply to eligible fees AFTER line discounts. A fixed amount is a
single budget across the selected recurring months plus selected one-time fees.
It is capped at that net basis, never applied twice. Cent remainders belong to
the initial promotional months and are explicitly disclosed in customer outputs.
"""
from decimal import Decimal, ROUND_DOWN
from .model import decimal, money


def apply(doc, values, monthly, once, selected):
    rule=doc['discount']; enabled=rule['enabled']
    duration=(doc['contract_months'] if rule.get('duration')=='full' else rule['months']) if enabled else 0
    billing=rule.get('billing','monthly')
    recurring=selected & monthly if billing in ('monthly','both') and duration else set()
    nonrecurring=selected & once if enabled and billing in ('one_time','both') else set()
    def total(ids):
        return None if any(values[i] is None for i in ids) else sum((values[i] for i in ids),Decimal('0.00'))
    m=total(recurring);o=total(nonrecurring)
    extra_months=0
    if rule.get('kind','percent')=='fixed':
        budget=money(decimal(rule.get('amount','0'),'Fixed discount'));basis=None if m is None or o is None else m*duration+o
        if basis is None and budget:
            md=od=rd=final=None
        else:
            budget=min(budget,basis or Decimal(0));rd=money(budget*m*duration/basis) if basis and duration else Decimal('0.00')
            od=budget-rd
            md=(rd/duration).quantize(Decimal('.01'),rounding=ROUND_DOWN) if duration else Decimal('0.00')
            final=md
            extra_months=int((rd-md*duration)/Decimal('.01')) if duration else 0
            if extra_months:md+=Decimal('.01')
    else:
        rate=decimal(rule['percent'],'Discount')/100 if enabled else Decimal(0)
        md=None if m is None and rate else money((m or Decimal(0))*rate)
        od=None if o is None and rate else money((o or Decimal(0))*rate)
        rd=None if md is None else md*duration;final=md
    if not enabled:md=od=rd=final=Decimal('0.00')
    return dict(monthly=md,once=od,recurring_total=rd,final=final,months=duration,extra_months=extra_months,recurring_ids=recurring,once_ids=nonrecurring)
