"""Permission-scoped, monthly-fee reports and immutable server PDF snapshots."""
import base64,json,os,tempfile
from calendar import monthrange
from datetime import date,datetime,timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from flask import Blueprint,abort,current_app,flash,redirect,render_template,request,send_file
from . import store,security,statistics,approvals as flow,document_storage as fs
from .references import actor,stamp,key
from .model import ValidationError
from .quotation import calculate,validate_document
from .documents import latest,customer_key,customer_options
bp=Blueprint('reporting',__name__)
TYPES={'overview':'Management overview','register':'Quotation register','pending':'Pending approvals','sent':'Sent quotations & follow-up'}


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS report_files(id TEXT PRIMARY KEY,actor TEXT,at TEXT NOT NULL,
        path TEXT NOT NULL,sha256 TEXT NOT NULL,data TEXT NOT NULL)''')


def money(q):
    try:
        c=calculate(validate_document(q['document']));return c['discounted'],c['one_time']
    except (ValueError,TypeError,KeyError,RecursionError,ArithmeticError):return None,None


def window(args):
    today=statistics.today_local();period=args.get('period','month')
    try:
        year=int(args.get('year') or today.year);month=int(args.get('month') or today.month);quarter=int(args.get('quarter') or (today.month-1)//3+1)
        if not 2000<=year<=9998 or not 1<=month<=12 or not 1<=quarter<=4:raise ValueError()
        if period=='month':start=date(year,month,1);end=date(year,month,monthrange(year,month)[1])
        elif period=='quarter':m=3*(quarter-1)+1;start=date(year,m,1);end=date(year,m+2,monthrange(year,m+2)[1])
        elif period=='year':start=date(year,1,1);end=date(year,12,31)
        elif period=='custom':start=date.fromisoformat(args.get('start',''));end=date.fromisoformat(args.get('end',''))
        elif period=='all':start=end=None
        else:raise ValueError()
        if start and end<start:raise ValueError()
    except (ValueError,TypeError):raise ValidationError('Choose a valid report period, year/month/quarter or inclusive custom dates.') from None
    return dict(period=period,start=start,end=end,year=year,month=month,quarter=quarter)


def in_window(value,w):
    if not value:return w['period']=='all'
    try:day=statistics.local_date(value) if len(str(value))>10 else date.fromisoformat(value)
    except (ValueError,TypeError):return w['period']=='all'
    return not w['start'] or w['start']<=day<=w['end']


def age(value):
    try:return max(0,(statistics.today_local()-statistics.local_date(value)).days)
    except (ValueError,TypeError):return 'Unknown'


def public_row(db,r,users,sent_dates):
    q=r['data'];monthly,once=money(q);meta=db.execute('SELECT * FROM records WHERE id=?',(r['id'],)).fetchone()
    from .sent_tracking import creator
    progress=flow.progress(db,r);sent=sent_dates.get(key(q['number']),'')
    return dict(id=r['id'],client=q['customer'],customer_id=q.get('customer_id',''),reference=q['number'],revision=q['revision'],title=q['title'],
        creator=users.get(creator(db,r['id']),'Unknown — not recorded'),owner=users.get(meta['owner_id'],'Unassigned'),owner_id=meta['owner_id'] or 'unassigned',
        date=q.get('date',''),created=r['created'],monthly=monthly,one_time=once,currency=q.get('currency','USD'),approval=progress['status'],sent=sent or '',cancelled=q.get('status')=='Cancelled')


def build(db,args):
    w=window(args);typ=args.get('report','overview')
    if typ not in TYPES:raise ValidationError('Choose a supported report.')
    visible=[r for r in store.records(db) if r['kind']=='quote'];families=latest(visible);users={r['id']:r['username'] for r in db.execute('SELECT id,username FROM users')}
    from .sent_tracking import family_dates
    sent_dates=family_dates(db,{r['id'] for r in visible})
    all_records=store.records(db);choices=customer_options(all_records);owners={r['id']:r['owner_id'] for r in db.execute('SELECT id,owner_id FROM records')}
    owner_scoped={r['id'] for r in visible if not args.get('owner') or (owners[r['id']] or 'unassigned')==args['owner']}
    scoped=[r for r in visible if (not args.get('customer_id') or customer_key(r,all_records)==args['customer_id']) and (not args.get('owner') or (owners[r['id']] or 'unassigned')==args['owner'])]
    known_choices={c['id'] for c in choices}
    for event in db.execute('SELECT quote_id,snapshot FROM quotation_sent_events'):
        if event['quote_id'] not in owner_scoped:continue
        snapshot=json.loads(event['snapshot']);cid=snapshot.get('customer_id') or 'legacy:'+snapshot.get('customer','').strip().casefold()
        if cid not in known_choices:choices.append(dict(id=cid,name=snapshot.get('customer','')+' · sent history'));known_choices.add(cid)
    scoped_ids={r['id'] for r in scoped};latest_rows=latest(scoped);creation={}
    for r in scoped:
        k=key(r['data']['number']);creation[k]=min(creation.get(k,r['created']) or r['created'],r['created'] or creation.get(k,''))
    register=[]
    for r in latest_rows:
        if in_window(creation[key(r['data']['number'])],w):
            row=public_row(db,r,users,sent_dates);row['created']=creation[key(r['data']['number'])];register.append(row)
    # Pending quotations are unique families, using the latest active submitted
    # accessible revision, not one monetary/count row per approver.
    pending_by_family={}
    for r in scoped:
        round_=flow.current_round(db,r['id'])
        if not round_ or round_['status'] not in flow.ACTIVE:continue
        k=key(r['data']['number'])
        if k not in pending_by_family or round_['at']>pending_by_family[k][1]['at']:pending_by_family[k]=(r,round_)
    pending=[]
    for r,round_ in pending_by_family.values():
        if not in_window(round_['at'],w):continue
        row=public_row(db,r,users,sent_dates);reviewers=flow.decisions(db,round_['id'])
        row.update(submitted=round_['at'],reviewers=', '.join(x['username']+(' (waiting for operations)' if x['phase']=='commercial' and round_['status']==flow.ACTIVE[0] else '') for x in reviewers if x['decision']=='Pending'),days=age(round_['at']))
        pending.append(row)
    sent=[]
    for e in db.execute('SELECT * FROM quotation_sent_events ORDER BY at DESC,id DESC'):
        if e['quote_id'] not in owner_scoped or not in_window(e['at'],w):continue
        q=json.loads(e['snapshot']);monthly,once=money(q)
        if args.get('customer_id') and (q.get('customer_id') or 'legacy:'+q.get('customer','').strip().casefold())!=args['customer_id']:continue
        sent.append(dict(id=e['quote_id'],client=q['customer'],reference=q['number'],revision=e['revision'],actor=users.get(e['actor'],'Unknown'),sent=e['at'],
            recipient=(e['recipient_name']+' '+e['recipient_email']).strip() or 'Not recorded',method=e['method'] or 'Not recorded',days=age(e['at']),
            monthly=monthly,one_time=once,currency=q.get('currency','USD'),cancelled=False,followup=(db.execute('SELECT follow_date FROM document_management WHERE record_id=?',(e['quote_id'],)).fetchone() or [''])[0]))
    from .outcomes import visible as visible_outcomes
    outcomes=visible_outcomes(db,visible)
    for row in register+pending:
        row['cancelled']=row['cancelled'] or outcomes.get(key(row['reference']),{}).get('status')=='Cancelled'
    counts={state:sum(o['status']==state and in_window(o.get('outcome_date') or o.get('updated'),w) and any(key(r['data']['number'])==k for r in latest_rows) for k,o in outcomes.items()) for state in ('Won','Lost')}
    rows={'overview':register,'register':register,'pending':pending,'sent':sent}[typ]
    financial=rows
    if typ=='sent':
        unique={}
        for r in sent:unique.setdefault(key(r['reference']),r)
        financial=list(unique.values())
    summary=dict(monthly=Decimal(0),one_time=Decimal(0),missing=0,non_usd=0,cancelled=0,zero=0)
    for r in financial:
        if r.get('cancelled'):summary['cancelled']+=1;continue
        if r['currency']!='USD':summary['non_usd']+=1;continue
        if r['monthly'] is None or r['one_time'] is None:summary['missing']+=1
        if r['monthly'] is not None:summary['monthly']+=Decimal(r['monthly']);summary['zero']+=Decimal(r['monthly'])==0
        if r['one_time'] is not None:summary['one_time']+=Decimal(r['one_time'])
    basis={'overview':'Quotation activity/fees: family creation date. Pending: latest active submission date. Sent: recorded sent date. Won/Lost: outcome date.',
      'register':'Earliest accessible family creation date; amounts and status use the latest accessible revision.',
      'pending':'Latest active submitted approval round per accessible family; filter uses submission date.',
      'sent':'Recorded sent event date; details use the exact approved revision/PDF. Fees are summed once per family using its latest sent event in the range.'}[typ]
    used_owners={owners[r['id']] or 'unassigned' for r in visible}
    filters=dict(report=typ,**{k:str(args.get(k,'')) for k in ('customer_id','owner','start','end')},period=w['period'],year=str(w['year']),month=str(w['month']),quarter=str(w['quarter']))
    labels=[TYPES[typ],('All time' if not w['start'] else str(w['start'])+' through '+str(w['end'])),
            'Customer: '+next((c['name'] for c in choices if c['id']==args.get('customer_id')),'All customers'),
            'Owner: '+users.get(args.get('owner'),'Unassigned' if args.get('owner')=='unassigned' else 'All owners')]
    return dict(type=typ,title=TYPES[typ],basis=basis,filters=filters,filter_labels=labels,rows=rows,summary={k:format(v,'.2f') if isinstance(v,Decimal) else v for k,v in summary.items()},
        quotation_count=len(register),pending_count=len(pending),sent_count=len({key(r['reference']) for r in sent}),sent_events=len(sent),won=counts['Won'],lost=counts['Lost'],
        customer_choices=choices,owner_choices=[dict(id=i,name=users.get(i,'Unassigned')) for i in sorted(used_owners)],source_ids=sorted(owner_scoped if typ=='overview' else {r['id'] for r in rows}),generated=stamp(),generated_by=(security.current_user() or {}).get('username','Administrator'))


def folder(db):
    row=db.execute("SELECT value FROM settings WHERE key='reports_folder'").fetchone();return row[0] if row else ''


def validate_folder(value,root,db):
    from .customer_documents import validate_root
    p=validate_root(value,root,db)
    from .customer_documents import config as document_root
    other=document_root(db)
    if other:
        x=Path(other).resolve()
        if p==x or p in x.parents or x in p.parents:raise ValidationError('Reports require a folder separate from Customer Documents.')
    return p


@bp.route('/reports/settings',methods=['GET','POST'])
def settings():
    security.require_admin();error=None;tested=False
    with store.connect(current_app.config['DATA_DIR']) as db:
        value=request.form.get('reports_folder',folder(db))
        if request.method=='POST':
            try:
                validate_folder(value,current_app.config['DATA_DIR'],db)
                from .automation import test_access
                test_access(value)
                if request.form.get('action')=='test':tested=True
                else:
                    db.execute("INSERT INTO settings VALUES ('reports_folder',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(value.strip(),));flash('Reports folder saved.');return redirect('/reports/settings')
            except (ValueError,OSError,RuntimeError) as exc:error=str(exc)
    return render_template('reports_settings.html',value=value,error=error,tested=tested)


def document_html(data,inline=False):
    logo=base64.b64encode((Path(__file__).parent/'static/cirrus-logo.png').read_bytes()).decode()
    html=current_app.jinja_env.get_template('report_document.html').render(report=data,logo=logo)
    if inline:
        css=(Path(__file__).parent/'static/report_document.css').read_text()
        html=html.replace('<link rel="stylesheet" href="/static/report_document.css">','<style>'+css+'</style>')
    return html


@bp.route('/reports',methods=['GET','POST'])
def page():
    with store.connect(current_app.config['DATA_DIR']) as db:
        db.execute('BEGIN')
        data=build(db,request.form if request.method=='POST' else request.args);destination=folder(db)
        saved=[dict(r) for r in db.execute('SELECT id,actor,at,data FROM report_files WHERE actor=? ORDER BY at DESC LIMIT 100',(actor(),))]
    if request.method=='GET':return render_template('reports.html',report=data,types=TYPES,saved=saved,destination_configured=bool(destination),generated=request.args.get('generated') if request.args.get('generated') in {x['id'] for x in saved} else None)
    path=None;temporary=None;published=False
    try:
        with store.connect(current_app.config['DATA_DIR']) as db:
            if not destination:raise ValidationError('Reports folder is not configured. Ask an administrator to configure it in Settings.')
            base=validate_folder(destination,current_app.config['DATA_DIR'],db)
        from .automation import print_html_pdf
        ident=uuid4().hex;name='Cirrus-'+data['type']+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+ident[:8]+'.pdf'
        fd,temp=tempfile.mkstemp(prefix='.cirrus-report-',suffix='.tmp',dir=base);os.close(fd);temporary=Path(temp)
        print_html_pdf(current_app,document_html(data,inline=True),temporary)
        with store.connect(current_app.config['DATA_DIR']) as db:
            db.execute('BEGIN IMMEDIATE')
            # Permissions and configured root may have changed while rendering.
            if not set(data['source_ids'])<={r['id'] for r in store.records(db)} or folder(db)!=destination:raise ValidationError('Report access or destination changed; preview and generate again.')
            validate_folder(destination,current_app.config['DATA_DIR'],db);path=fs.safe_path(base,name,True)
            if path.exists():raise ValidationError('Report filename collision; generate again.')
            os.rename(temporary,path);temporary=None;published=True
            import hashlib
            db.execute('INSERT INTO report_files VALUES (?,?,?,?,?,?)',(ident,actor(),stamp(),str(path),hashlib.sha256(path.read_bytes()).hexdigest(),json.dumps(data)))
        from urllib.parse import urlencode
        flash('Report PDF saved successfully. Download it below.')
        return redirect('/reports?'+urlencode(dict(data['filters'],generated=ident)))
    except (OSError,RuntimeError,ValueError) as exc:
        if published:path.unlink(missing_ok=True)
        return render_template('reports.html',report=data,types=TYPES,saved=saved,destination_configured=bool(destination),error='Report PDF was not saved: '+str(exc)),400
    finally:
        if temporary:temporary.unlink(missing_ok=True)


@bp.get('/reports/preview')
def preview():
    with store.connect(current_app.config['DATA_DIR']) as db:
        db.execute('BEGIN');data=build(db,request.args)
    return document_html(data)


@bp.get('/reports/files/<ident>')
def download(ident):
    with store.connect(current_app.config['DATA_DIR']) as db:
        r=db.execute('SELECT * FROM report_files WHERE id=?',(ident,)).fetchone()
        if not r:abort(404)
        data=json.loads(r['data']);allowed={x['id'] for x in store.records(db)}
        if not set(data['source_ids'])<=allowed or (r['actor']!=actor() and not security.admin()):abort(403)
        p=Path(r['path']);fs.check_components(p);fs.file_info(p)
        handle=fs.open_file(p.parent,p.name)
        if fs.digest_file(handle)!=r['sha256']:handle.close();raise ValidationError('Report file changed; generate a new report.')
    return send_file(handle,as_attachment=True,download_name=p.name,mimetype='application/pdf')


@bp.app_template_filter('report_time')
def report_time(value):
    if not value:return 'Not recorded'
    from .approval_emails import format_time
    try:return format_time(value) if len(value)>10 else value
    except (ValueError,TypeError):return 'Unknown'


@bp.errorhandler(OSError)
def file_error(exc):
    return render_template('error.html',message='Report folder/file is unavailable to the Workplace server account. Ask an administrator to check the path and permissions, then retry.'),503
