"""Permission-filtered quotation statistics. Decimal money; no FX/revenue guesses."""
import os
from collections import Counter,defaultdict
from datetime import date,datetime,timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from .model import ValidationError,totals
from .quotation import validate_document,calculate
from .references import key


def zone():
    try:return ZoneInfo(os.environ.get('CIRRUS_TIMEZONE','Asia/Beirut'))
    except Exception:raise RuntimeError('Invalid CIRRUS_TIMEZONE; install requirements (tzdata) and use an IANA zone.') from None


def today_local():return datetime.now(zone()).date()


def local_date(value):
    moment=datetime.fromisoformat(value)
    if moment.tzinfo is None:moment=moment.replace(tzinfo=ZoneInfo('UTC'))
    return moment.astimezone(zone()).date()


def date_filter(args,today):
    period=args.get('period','year');start=end=None
    if period=='calendar':
        from calendar import monthrange
        try:
            year=int(args.get('filter_year',today.year));month=int(args.get('filter_month','0'))
            if not 1<=year<=9999 or not 0<=month<=12:raise ValueError
            start=date(year,month or 1,1);end=date(year,month or 12,monthrange(year,month or 12)[1])
        except (ValueError,TypeError):raise ValidationError('Select a valid month and year.') from None
    elif period=='month':start=today.replace(day=1);end=today
    elif period=='last_month':end=today.replace(day=1)-timedelta(days=1);start=end.replace(day=1)
    elif period=='year':start=today.replace(month=1,day=1);end=today
    elif period=='custom':
        try:start=date.fromisoformat(args.get('start',''));end=date.fromisoformat(args.get('end',''))
        except ValueError:raise ValidationError('Select valid custom start and end dates.') from None
        if start>end:raise ValidationError('Start date must be on or before end date.')
        if (end-start).days>3660:raise ValidationError('Custom range is limited to ten years.')
    elif period!='all':raise ValidationError('Invalid date filter.')
    return dict(period=period,start=start,end=end)


def money(value):return format(value.quantize(Decimal('.01')),',.2f')


def quotations(records,args=None,today=None,outcomes=None):
    today=today or today_local();args=args or {};window=date_filter(args,today);outcomes=outcomes or {}
    grouped=defaultdict(list);invalid=0;conflicts=0
    for r in records:
        if r['kind']!='quote':continue
        try:k=key(r['data']['number']);grouped[k].append(r)
        except (ValidationError,KeyError):invalid+=1
    latest=[]
    for family in grouped.values():
        ordered=sorted(family,key=lambda r:(r['data'].get('revision',0),r['updated'],r['id']),reverse=True)
        revisions=Counter(r['data'].get('revision',0) for r in family)
        conflicts+=sum(n-1 for n in revisions.values() if n>1)
        for r in ordered[:1]:
            d=r['data']
            try:issued=date.fromisoformat(d['date'])
            except (TypeError,ValueError,KeyError):
                invalid+=1
                latest.append(dict(record=r,created=None,value=None,monthly=None,family_key=key(d['number'])))
                break
            try:
                if 'document' in d:
                    calc=calculate(validate_document(d['document']));amount=calc['combined'];monthly=calc['discounted']
                else:amount=totals(d['lines'],d['tax'])['grand_total'];monthly='0'
                value=None if amount is None else Decimal(amount)
                if value is not None and not value.is_finite():raise ValueError
            except (ValidationError,ArithmeticError,ValueError,TypeError,KeyError):
                invalid+=1
                latest.append(dict(record=r,created=issued,value=None,monthly=None,family_key=key(d['number'])));break
            latest.append(dict(record=r,created=issued,value=value,monthly=None if monthly is None else Decimal(monthly),family_key=key(d['number'])));break
    search=args.get('q','').strip().casefold()
    latest=[x for x in latest if not search or any(search in str(x['record']['data'].get(k,'')).casefold() for k in ('number','customer','title'))]
    month_start=today.replace(day=1)
    def eligible(x):return x['value'] is not None and x['record']['data'].get('currency','').upper()=='USD'
    current=[x for x in latest if x['created'] and month_start<=x['created']<=today]
    selected=[x for x in latest if (window['period']=='all' or (x['created'] and (not window['start'] or x['created']>=window['start']) and (not window['end'] or x['created']<=window['end'])))]
    values=[x['value'] for x in selected if eligible(x)];total=sum(values,Decimal(0))
    from .outcomes import LEGACY
    for x in latest:
        state=outcomes.get(x['family_key']) or dict(status=LEGACY.get(x['record']['data'].get('status'),x['record']['data'].get('status')),outcome_date=None,accepted_value=None,accepted_currency=None)
        x['outcome']=state
        x['record']=dict(x['record'],workflow_status=state['status'])
    statuses=Counter(x['outcome']['status'] for x in selected)
    excluded_currency=Counter(x['record']['data'].get('currency','Unknown') for x in selected if x['record']['data'].get('currency','').upper()!='USD')
    def in_window(day):return (not window['start'] or day>=window['start']) and (not window['end'] or day<=window['end'])
    outcome_rows={'Won':[],'Lost':[]};undated=0
    for x in latest:
        state=x['outcome'];status=state['status']
        if status not in outcome_rows:continue
        when=state.get('outcome_date')
        if not when:undated+=1
        try:day=date.fromisoformat(when) if when else None
        except (TypeError,ValueError):day=None
        if day is None and window['period']!='all':continue
        if day and not in_window(day):continue
        outcome_rows[status].append(x)
    pending=[x for x in selected if x['outcome']['status'] in ('Under review','Sent','On hold')]
    def outcome_value(x,status):
        if status=='Won':
            state=x['outcome'];v=state.get('accepted_value')
            return Decimal(v) if v is not None and (state.get('accepted_currency') or '').upper()=='USD' else None
        return x['value'] if eligible(x) else None
    won_values=[outcome_value(x,'Won') for x in outcome_rows['Won']];lost_values=[outcome_value(x,'Lost') for x in outcome_rows['Lost']]
    won=len(outcome_rows['Won']);lost=len(outcome_rows['Lost'])
    reasons=Counter((x['outcome']['status'],x['outcome'].get('reason') or 'Legacy / unspecified') for kind in outcome_rows.values() for x in kind)
    extra=dict(won_count=won,won_value=money(sum((x for x in won_values if x is not None),Decimal(0))),lost_count=lost,lost_value=money(sum((x for x in lost_values if x is not None),Decimal(0))),pending_count=len(pending),pending_value=money(sum((x['value'] for x in pending if eligible(x)),Decimal(0))),win_rate=money(Decimal(won)/(won+lost)*100) if won+lost else '—',undated_outcomes=undated,reasons=reasons,won_excluded=sum(x is None for x in won_values),lost_excluded=sum(x is None for x in lost_values))
    native=defaultdict(lambda:dict(quoted=Decimal(0),monthly=Decimal(0),won=Decimal(0),lost=Decimal(0)))
    for x in selected:
        currency=x['record']['data'].get('currency','').upper()
        if currency!='USD' and x['value'] is not None:native[currency]['quoted']+=x['value']
        if currency!='USD' and x['monthly'] is not None:native[currency]['monthly']+=x['monthly']
    for x in outcome_rows['Won']:
        state=x['outcome'];currency=state.get('accepted_currency');value=state.get('accepted_value')
        if currency and currency!='USD' and value is not None:native[currency]['won']+=Decimal(value)
    for x in outcome_rows['Lost']:
        currency=x['record']['data'].get('currency','').upper()
        if currency!='USD' and x['value'] is not None:native[currency]['lost']+=x['value']
    extra['native_values']={cur:{name:money(value) for name,value in amounts.items()} for cur,amounts in sorted(native.items())}
    buckets=defaultdict(lambda:dict(count=0,value=Decimal(0)))
    for x in selected:
        if not x['created']:continue
        b=buckets[x['created'].strftime('%Y-%m')];b['count']+=1
        if eligible(x):b['value']+=x['value']
    # Month/year charts include zero months; all-time uses the latest 12 months.
    finish=window['end'] or today;begin=window['start'] or finish-timedelta(days=364)
    cursor=begin.replace(day=1);months=[]
    while cursor<=finish:
        label=cursor.strftime('%Y-%m');b=buckets[label];months.append(dict(label=label,count=b['count'],value=money(b['value']),raw=b['value']))
        cursor=(cursor.replace(day=28)+timedelta(days=4)).replace(day=1)
    months=months[-(12 if window['period']=='all' else 24):]
    maxvalue=max((m['raw'] for m in months),default=Decimal(0));maxcount=max((m['count'] for m in months),default=0)
    for m in months:
        m['value_width']=float(m['raw']/maxvalue*100) if maxvalue else 0;m['count_width']=m['count']/maxcount*100 if maxcount else 0
    for x in selected:x['record']=dict(x['record'],quoted_amount=None if x['value'] is None else str(x['value']),monthly_amount=None if x['monthly'] is None else str(x['monthly']))
    extra.update(monthly_value=money(sum((x['monthly'] for x in selected if x['monthly'] is not None and x['record']['data'].get('currency','').upper()=='USD'),Decimal(0))),monthly_missing=sum(x['monthly'] is None for x in selected),zero_count=sum(x['value']==0 for x in selected))
    return dict(**extra,total=len(selected),value=money(total),month_count=len(current),month_value=money(sum((x['value'] for x in current if eligible(x)),Decimal(0))),average=money(total/len(values)) if values else '—',priced_count=len(values),statuses=statuses,missing=sum(x['value'] is None for x in selected),non_usd=excluded_currency,invalid=invalid,conflicts=conflicts,months=months,window=window,rows=[x['record'] for x in sorted(selected,key=lambda x:(x['created'] or date.min,x['record']['updated']),reverse=True)])


def page_kpis(records,section,today=None):
    today=today or today_local();rows=[r for r in records if r['kind']==section]
    if section=='project':
        return [('Total projects',len(rows)),('Active',sum(r['data']['status']=='Active' for r in rows)),('Completed',sum(r['data']['status']=='Completed' for r in rows)),('Updated in last 30 days',sum(today-timedelta(days=29)<=local_date(r['updated'])<=today for r in rows))]
    if section=='catalog':
        counts=Counter(r['data'].get('billing','monthly') for r in rows)
        return [('Total services',len(rows)),('Categories',len({r['data'].get('category','').strip() for r in rows if r['data'].get('category','').strip()})),('Monthly services',counts['monthly']),('One-time services',counts['one_time'])]
    return []
