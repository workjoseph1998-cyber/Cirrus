"""Document workspace over existing records, ACLs, references and quotation workflow."""
import copy,json,re
from datetime import date,datetime,timezone
from urllib.parse import urlencode
from flask import Blueprint,abort,current_app,flash,redirect,render_template,request
from . import store,security,statistics
from .model import ValidationError,FIELDS
from .references import key,stamp,actor,overview,reserve,register_quote
from .commercial import fingerprint

bp=Blueprint('documents',__name__)
TYPES=('Agreement','BOQ','DN','Letter','PO','Proposal','Quotation','SLA','SOW')
DOC_STATUSES=('Draft','Internal Review','Approved','Sent','Cancelled')


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS document_management (
      record_id TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
      created_by TEXT, follow_date TEXT NOT NULL DEFAULT '',follow_note TEXT NOT NULL DEFAULT '',version INTEGER NOT NULL DEFAULT 1)''')
    db.execute('''CREATE TABLE IF NOT EXISTS document_links (
      source_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
      target_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
      PRIMARY KEY(source_id,target_id),CHECK(source_id<>target_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS document_activity (
      id INTEGER PRIMARY KEY AUTOINCREMENT,record_id TEXT NOT NULL,actor_id TEXT,at TEXT NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL)''')
    from .automation import schema as automation_schema
    automation_schema(db)
    # Older creators are unknown. The existing creation timestamp is authoritative.
    db.execute("INSERT OR IGNORE INTO document_management(record_id) SELECT id FROM records WHERE kind IN ('quote','document')")


def event(db,ident,action,details=''):
    db.execute('INSERT INTO document_activity(record_id,actor_id,at,action,details) VALUES (?,?,?,?,?)',(ident,actor(),stamp(),action,details))


def saved(db,ident,previous,inherited):
    db.execute('INSERT OR IGNORE INTO document_management(record_id,created_by) VALUES (?,?)',(ident,actor() if previous is None else None))
    if inherited:
        meta=db.execute('SELECT follow_date,follow_note FROM document_management WHERE record_id=?',(inherited['id'],)).fetchone()
        if meta:db.execute('UPDATE document_management SET follow_date=?,follow_note=? WHERE record_id=?',(meta['follow_date'],meta['follow_note'],ident))
        db.execute('INSERT OR IGNORE INTO document_links SELECT ?,target_id FROM document_links WHERE source_id=? AND target_id<>?',(ident,inherited['id'],ident))
    row=db.execute('SELECT kind,data FROM records WHERE id=?',(ident,)).fetchone()
    if row['kind']=='quote':
        from .automation import enqueue
        enqueue(db,ident,json.loads(row['data']))
    event(db,ident,'Edited' if previous else 'Created',('Revision of '+inherited['id']) if inherited else '')
    if previous and previous['data'].get('status')!=json.loads(db.execute('SELECT data FROM records WHERE id=?',(ident,)).fetchone()[0]).get('status'):
        event(db,ident,'Status changed')


def export_event(ident,kind):
    with store.connect(current_app.config['DATA_DIR']) as db:
        security.require_id(db,ident);event(db,ident,'Exported',kind)


def filename(title,extension):
    name=re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]','_',str(title)).strip(' .')[:150].rstrip(' .') or 'document'
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'{s}{i}' for s in ('COM','LPT') for i in range(1,10)]}:name='_'+name
    return name+'.'+extension


def generated_title(number,customer,subject,doctype='Quotation',revision=1):
    subject=subject.strip() or 'Cloud Services'
    if not subject.casefold().endswith(doctype.casefold()):subject+=' '+doctype
    return f'{number}_{customer.strip()}-{subject}_V{revision}.0'


def fetch(db,ident,write=False):
    security.require_id(db,ident,write)
    r=next((r for r in store.records(db) if r['id']==ident and r['kind'] in ('quote','document')),None)
    if not r:abort(404)
    return r


def latest(records):
    families={}
    for r in records:
        if r['kind'] not in ('quote','document'):continue
        k=key(r['data']['number'])
        if k not in families or (r['data']['revision'],r['updated'],r['id'])>(families[k]['data']['revision'],families[k]['updated'],families[k]['id']):families[k]=r
    return list(families.values())


def customer_key(record,records):
    data=record['data'];ident=data.get('customer_id','')
    if not ident and data.get('project_id'):
        project=next((r for r in records if r['id']==data['project_id'] and r['kind']=='project'),None)
        if project:ident=project['data'].get('customer_id','')
    return ident or 'legacy:'+data.get('customer','').strip().casefold()


def customer_options(records):
    choices={r['id']:r['data']['name'] for r in records if r['kind']=='customer'}
    for r in latest(records):
        if r['kind'] in ('quote','document'):
            key=customer_key(r,records)
            choices.setdefault(key,r['data'].get('customer','')+(' · legacy name' if key.startswith('legacy:') else ''))
    return [dict(id=key,name=name) for key,name in sorted(choices.items(),key=lambda x:(x[1].casefold(),x[0]))]


def workspace(db,args):
    from .archives import archived_keys
    from .outcomes import visible
    records=store.records(db);family_latest=latest(records);workflow=visible(db,records);archived=archived_keys(db)
    users={r['id']:r['username'] for r in db.execute('SELECT id,username FROM users')}
    owners={r['id']:r['owner_id'] for r in db.execute('SELECT id,owner_id FROM records')}
    view=args.get('archive','active');basis=args.get('basis','created')
    if view not in ('active','archived','all') or basis not in ('created','date','updated','sent'):raise ValidationError('Invalid visibility or date basis.')
    period=args.get('period','all');window=statistics.date_filter(dict(args,period=period),statistics.today_local())
    year=args.get('filter_year','all');month=args.get('filter_month','0')
    try:
        y=None if year in ('all','') else int(year);m=int(month or 0)
        if (y is not None and not 1<=y<=9999) or not 0<=m<=12:raise ValueError
    except ValueError:raise ValidationError('Invalid month/year.') from None
    from .sent_tracking import family_dates
    sent_dates=family_dates(db,{r['id'] for r in records})
    # Group once instead of rescanning every record for every latest family.
    families={}
    for item in records:
        if item['kind'] in ('quote','document'):
            families.setdefault((item['kind'],key(item['data']['number'])),[]).append(item)
    found=[];q=args.get('q','').strip().casefold()
    for raw in family_latest:
        r=copy.deepcopy(raw);d=r['data'];k=key(d['number']);doctype='Quotation' if r['kind']=='quote' else d['type'];state=workflow.get(k,{}).get('status',d['status'])
        is_archived=k in archived;owner=owners.get(r['id']);owner_name=users.get(owner,'Unassigned')
        family=families.get((r['kind'],k),[])
        # Family creation is the earliest reliably stored timestamp, not latest revision creation.
        known=[]
        for x in family:
            try:
                moment=datetime.fromisoformat(x.get('created') or '')
                if moment.tzinfo is None:moment=moment.replace(tzinfo=timezone.utc)
                known.append((moment.astimezone(timezone.utc),x['created']))
            except (ValueError,TypeError):pass
        created=min(known)[1] if known else ''
        created_display=statistics.local_date(created).isoformat() if created else 'Unknown'
        value=created if basis=='created' else r['updated'] if basis=='updated' else sent_dates.get(k,'') if basis=='sent' else d.get('date','')
        if basis=='sent' and not value:continue
        try:day=date.fromisoformat(value) if basis=='date' else statistics.local_date(value)
        except (ValueError,TypeError):day=None
        if view!='all' and is_archived!=(view=='archived'):continue
        if q and not any(q in str(d.get(f,'')).casefold() for f in ('title','customer','number')):continue
        if args.get('customer_id') and customer_key(r,records)!=args['customer_id']:continue
        if args.get('type') and args['type']!=doctype:continue
        if args.get('owner') and args['owner']!= (owner or 'unassigned'):continue
        if args.get('status') and args['status']!=state:continue
        if y is not None and (day is None or day.year!=y):continue
        if m and (day is None or day.month!=m):continue
        if window['period']!='all' and (day is None or window['start'] and day<window['start'] or window['end'] and day>window['end']):continue
        r.update(doctype=doctype,workflow_status=state,owner_name=owner_name,owner_id=owner or 'unassigned',family_created=created,family_created_display=created_display,sent_display=statistics.local_date(sent_dates[k]).isoformat() if k in sent_dates else 'Not recorded',filter_date=day,is_archived=is_archived,family_revisions=len(family))
        found.append(r)
    found.sort(key=lambda r:(r['filter_date'] or date.min,r['updated']),reverse=True)
    order=args.get('sort','activity')
    if order not in ('activity','title','customer','reference'):raise ValidationError('Invalid quotation list sort.')
    if order!='activity':found.sort(key=lambda r:r['data'][{'title':'title','customer':'customer','reference':'number'}[order]].casefold())
    # Financial scope is exactly the filtered quotation families, minus Cancelled.
    sales=[]
    for r in found:
        if r['kind']!='quote' or r['workflow_status']=='Cancelled':continue
        item=copy.deepcopy(r)
        if item['filter_date']:item['data']['date']=item['filter_date'].isoformat()
        sales.append(item)
    stats=statistics.quotations(sales,{'period':'all'},outcomes=workflow)
    # Unknown creation/modification dates stay unknown and do not acquire an
    # invented chart month. Financial all-time values can still be known.
    chart_sales=[r for r in sales if r['filter_date'] is not None]
    chart_args=dict(args,period=period)
    if y is not None:chart_args=dict(period='calendar',filter_year=str(y),filter_month=str(m))
    chart=statistics.quotations(chart_sales,chart_args,outcomes=workflow)
    from collections import Counter
    monthly_counts=Counter(r['filter_date'].strftime('%Y-%m') for r in found if r['kind']=='quote' and r['filter_date'] is not None)
    maximum=max((monthly_counts[m['label']] for m in chart['months']),default=0)
    for bucket in chart['months']:
        bucket['count']=monthly_counts[bucket['label']];bucket['count_width']=bucket['count']/maximum*100 if maximum else 0
    from .reporting import money
    from decimal import Decimal
    monthly_buckets={};once=Decimal(0)
    for r in sales:
        if r['data'].get('currency')!='USD':continue
        monthly,one_time=money(r['data'])
        if one_time is not None:once+=Decimal(one_time)
        if monthly is not None and r['filter_date']:
            label=r['filter_date'].strftime('%Y-%m');monthly_buckets[label]=monthly_buckets.get(label,Decimal(0))+Decimal(monthly)
    high=max(monthly_buckets.values(),default=Decimal(0))
    for bucket in chart['months']:
        value=monthly_buckets.get(bucket['label'],Decimal(0));bucket['value']=format(value,'.2f');bucket['value_width']=float(value/high*100) if high else 0
    stats['one_time_value']=format(once,'.2f')
    stats['months']=chart['months'];stats['unknown_chart_dates']=sum(r['filter_date'] is None for r in found if r['kind']=='quote')
    counts=dict(documents=len(found),drafts=sum(r['workflow_status']=='Draft' for r in found),sent=sum(r['kind']=='quote' and bool(sent_dates.get(key(r['data']['number']))) for r in found),won=sum(r['kind']=='quote' and r['workflow_status']=='Won' for r in found))
    # Read and count once. Previously each family reparsed the entire database.
    raw_counts=Counter(key(x['data']['number']) for x in store.records(db,unrestricted=True) if x['kind'] in ('quote','document'))
    for r in found:r['family_revisions']=raw_counts[key(r['data']['number'])]
    return found,stats,counts,users


@bp.get('/documents')
def listing():
    with store.connect(current_app.config['DATA_DIR']) as db:
        visible_records=store.records(db);customer_choices=customer_options(visible_records)
        rows,stats,counts,users=workspace(db,request.args);all_visible=latest(visible_records);info=overview(db,statistics.today_local())
        followups=[]
        for r in all_visible:
            meta=db.execute('SELECT follow_date,follow_note FROM document_management WHERE record_id=?',(r['id'],)).fetchone()
            if meta and meta['follow_date']:followups.append(dict(record=r,**dict(meta),overdue=meta['follow_date']<statistics.today_local().isoformat()))
    try:
        size=int(request.args.get('per_page','25'));page=max(1,int(request.args.get('page','1')))
        if size not in (25,50,100):raise ValueError
    except ValueError:raise ValidationError('Choose 25, 50 or 100 rows and a valid page.') from None
    pages=max(1,(len(rows)+size-1)//size);page=min(page,pages)
    urls=lambda **kw:'/list/quote?'+urlencode(dict(request.args,**kw))
    return render_template('documents.html',customer_choices=customer_choices,rows=rows[(page-1)*size:page*size],stats=stats,counts=counts,users=users,types=TYPES,workflow_statuses=DOC_STATUSES+('Under review','On hold','Won','Lost'),followups=sorted(followups,key=lambda f:f['follow_date'])[:8],choices=sorted([r for r in all_visible if r['kind']=='quote'],key=lambda r:r['updated'],reverse=True),ref_info=info,matching_families=len(rows),matching_revisions=sum(r['family_revisions'] for r in rows),pagination=[dict(number=n,url=urls(page=str(n))) for n in range(1,pages+1)],page=page,per_page=size,filter_url=urls,today=statistics.today_local(),years=range(statistics.today_local().year+1,1999,-1))


@bp.route('/documents/new',methods=['GET','POST'])
def new():
    if security.current_user() and security.current_user()['role']=='Viewer':abort(403)
    if request.method=='POST':
        typ=request.form.get('type');subject=request.form.get('subject','').strip()
        if typ not in TYPES or not subject or len(subject)>500:raise ValidationError('Choose a type and enter a subject up to 500 characters.')
        with store.connect(current_app.config['DATA_DIR']) as db:
            db.execute('BEGIN IMMEDIATE');customer_id=request.form.get('customer_id','');security.require_id(db,customer_id)
            customer=next((r for r in store.records(db) if r['id']==customer_id and r['kind']=='customer'),None)
            if not customer:raise ValidationError('Choose an accessible customer.')
            number=overview(db,statistics.today_local())['next'];reserve(db,number,'quotation' if typ=='Quotation' else 'proposal' if typ=='Proposal' else 'document')
            title=generated_title(number,customer['data']['name'],subject,typ)
            if typ=='Quotation':
                from .approvals import selection_from_form,reviewers_valid,defaults
                from uuid import uuid4
                chosen=selection_from_form(request.form,defaults(db));reviewers_valid(db,chosen,allow_empty=True)
                preparation=uuid4().hex
                db.execute('INSERT INTO approval_preparations VALUES (?,?,?,?,?,?)',(preparation,actor(),customer_id,number,json.dumps(chosen),stamp()))
                return redirect('/quotes/new?'+urlencode(dict(customer_id=customer_id,reference=number,title=title,subject=subject,preparation=preparation)))
            d={k:'' for k,_,_ in FIELDS['document']};d.update(title=title,type=typ,subject=subject,customer_id=customer_id,customer=customer['data']['name'],contact=customer['data'].get('contact',''),date=statistics.today_local().isoformat(),status='Draft',number=number,revision=1)
            ident=store.save(db,'document',d)
        return redirect('/documents/'+ident+'/edit')
    from .approval_routes import settings_for
    with store.connect(current_app.config['DATA_DIR']) as db:setup=settings_for(db,None)
    return render_template('document_new.html',types=TYPES,**setup)


@bp.route('/documents/<ident>/edit',methods=['GET','POST'])
def edit(ident):
    with store.connect(current_app.config['DATA_DIR']) as db:
        if request.method=='POST':db.execute('BEGIN IMMEDIATE')
        r=fetch(db,ident,True)
        if r['kind']=='quote':return redirect('/quotes/'+ident+'/edit')
        d=r['data']
        if request.method=='POST':
            if request.form.get('snapshot')!=fingerprint(d):raise ValidationError('Document changed in another session. Reload before saving.')
            for f in ('title','contact','date','subject','content','status','number'):d[f]=request.form.get(f,'')
            if request.form.get('regenerate')=='yes':d['title']=generated_title(d['number'],d['customer'],d['subject'],d['type'],d['revision'])
            store.save(db,'document',d,ident);flash('Document saved.');return redirect(request.path)
    return render_template('document_edit.html',r=r,d=d,statuses=DOC_STATUSES,snapshot=fingerprint(d))


@bp.post('/documents/<ident>/title')
def title(ident):
    with store.connect(current_app.config['DATA_DIR']) as db:
        db.execute('BEGIN IMMEDIATE');r=fetch(db,ident,True)
        if request.form.get('snapshot')!=fingerprint(r['data']):raise ValidationError('Document changed. Reload the list before renaming.')
        d=r['data'];d['title']=request.form.get('title','')
        if r['kind']=='quote':
            from .outcomes import get
            state=get(db,key(d['number']))
            if state:d['status']=state['status']
        store.save(db,r['kind'],d,ident)
    return redirect('/list/quote')


@bp.route('/documents/<ident>/manage',methods=['GET','POST'])
def manage(ident):
    with store.connect(current_app.config['DATA_DIR']) as db:
        if request.method=='POST':db.execute('BEGIN IMMEDIATE')
        r=fetch(db,ident);writable=security.can_read(db,r,write=True)
        meta=dict(db.execute('SELECT * FROM document_management WHERE record_id=?',(ident,)).fetchone())
        user_names={u['id']:u['username'] for u in db.execute('SELECT id,username FROM users')}
        owner=db.execute('SELECT owner_id FROM records WHERE id=?',(ident,)).fetchone()[0]
        # Only owner/admin can transfer ownership. An editor may manage follow-ups and links.
        can_transfer=not security.enabled() or security.admin() or owner==actor()
        if request.method=='POST':
            security.require_record(db,r,True)
            if request.form.get('version')!=str(meta['version']) or request.form.get('snapshot')!=fingerprint(r['data']):raise ValidationError('Management or document changed. Reload before saving.')
            follow=request.form.get('follow_date','');note=request.form.get('follow_note','').strip()
            if follow:
                try:date.fromisoformat(follow)
                except ValueError:raise ValidationError('Enter a valid follow-up date.') from None
            if len(note)>1000:raise ValidationError('Follow-up note is limited to 1,000 characters.')
            new_owner=request.form.get('owner',owner or '')
            if new_owner!=(owner or ''):
                if not can_transfer:abort(403)
                if not db.execute('SELECT 1 FROM users WHERE id=? AND active=1 AND role<>?',(new_owner,'Viewer')).fetchone():raise ValidationError('Choose an active staff owner.')
                db.execute('UPDATE records SET owner_id=? WHERE id=?',(new_owner,ident));event(db,ident,'Owner changed',user_names.get(new_owner,''))
                # Keep existing owner able to read the document after explicit transfer.
                if owner:db.execute('INSERT INTO record_acl VALUES (?,?,?) ON CONFLICT(record_id,user_id) DO UPDATE SET permission=excluded.permission',(ident,owner,'edit'))
            links=request.form.getlist('links')
            if len(links)>100:raise ValidationError('Maximum 100 related documents.')
            for target in links:
                if target==ident:raise ValidationError('Cannot link a document to itself.')
                fetch(db,target)
            visible_targets={d['id'] for d in store.records(db) if d['kind'] in ('quote','document')}
            for target in visible_targets:db.execute('DELETE FROM document_links WHERE source_id=? AND target_id=?',(ident,target))
            for target in set(links):db.execute('INSERT INTO document_links VALUES (?,?)',(ident,target))
            db.execute('UPDATE document_management SET follow_date=?,follow_note=?,version=version+1 WHERE record_id=?',(follow,note,ident))
            event(db,ident,'Management updated','Follow-up and related documents saved');flash('Management saved.');return redirect(request.path+('?'+urlencode({'panel':request.args['panel']}) if request.args.get('panel') else ''))
        visible=store.records(db);docs=[d for d in visible if d['kind'] in ('quote','document') and d['id']!=ident];ids={d['id'] for d in docs}
        related={x['target_id'] for x in db.execute('SELECT target_id FROM document_links WHERE source_id=?',(ident,)) if x['target_id'] in ids}
        incoming={x['source_id'] for x in db.execute('SELECT source_id FROM document_links WHERE target_id=?',(ident,)) if x['source_id'] in ids}
        cid=r['data'].get('customer_id');name=r['data']['customer'].casefold()
        history_docs=[d for d in latest(visible) if key(d['data']['number'])!=key(r['data']['number']) and ((cid and d['data'].get('customer_id')==cid) or (not cid and d['data'].get('customer','').casefold()==name))]
        from .outcomes import visible as visible_outcomes
        states=visible_outcomes(db,visible)
        for d in history_docs:
            d['workflow_status']=states.get(key(d['data']['number']),{}).get('status',d['data']['status'])
            m=db.execute('SELECT follow_date FROM document_management WHERE record_id=?',(d['id'],)).fetchone();d['follow_date']=m['follow_date'] if m else ''
        activity=[dict(a,username=user_names.get(a['actor_id'],'Unknown / system')) for a in db.execute('SELECT * FROM document_activity WHERE record_id=? ORDER BY id DESC LIMIT 100',(ident,))]
        # Existing workflow events are permission-safe summaries; never expose internal costing payloads.
        workflow_events=[]
        if r['kind']=='quote':
            allowed={d['id'] for d in visible}
            workflow_events=[dict(a,username=user_names.get(a['actor_id'],'Unknown / system')) for a in db.execute('SELECT at,actor_id,action,quote_id FROM quotation_activity WHERE reference_key=? ORDER BY id DESC LIMIT 100',(key(r['data']['number']),)) if not a['quote_id'] or a['quote_id'] in allowed]
        pdf_export=db.execute('SELECT * FROM pdf_exports WHERE record_id=?',(ident,)).fetchone()
        pdf_export=dict(pdf_export) if pdf_export else None
        attachments=db.execute('SELECT id,name FROM attachments WHERE record_id=?',(ident,)).fetchall() if security.can_read(db,r,include_workflow=False) else []
        file_writable=security.can_read(db,r,write=True,include_workflow=False)
    return render_template('document_manage.html',r=r,meta=meta,writable=writable,file_writable=file_writable,owner=owner,users=user_names,can_transfer=can_transfer,related=related,incoming=incoming,docs=docs,history_docs=history_docs,activity=activity,workflow_events=workflow_events,pdf_export=pdf_export,attachments=attachments,snapshot=fingerprint(r['data']))


@bp.get('/documents/<ident>/print')
def printable(ident):
    with store.connect(current_app.config['DATA_DIR']) as db:r=fetch(db,ident)
    if r['kind']=='quote':return redirect('/quotes/'+ident+'/print')
    export_event(ident,'Print / PDF view opened')
    return render_template('document_print.html',r=r,d=r['data'])


@bp.get('/documents/<ident>/txt')
def text_export(ident):
    import io
    from flask import send_file
    with store.connect(current_app.config['DATA_DIR']) as db:r=fetch(db,ident)
    if r['kind']!='document':abort(404)
    d=r['data'];export_event(ident,'Text')
    text='\n'.join([d['type'],d['title'],'Messrs.: '+d['customer'],'Contact: '+d['contact'],'Project: '+d['subject'],'Date: '+d['date'],'Ref: '+d['number'],'',d['content']])
    return send_file(io.BytesIO(text.encode('utf-8-sig')),as_attachment=True,download_name=filename(d['title'],'txt'),mimetype='text/plain')
