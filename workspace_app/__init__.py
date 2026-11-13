"""Cirrus Workplace application with explicit local/internal access policy."""
import csv
from datetime import date
import io
import json
import os
from pathlib import Path
import secrets
import time
import ipaddress
import re
from urllib.parse import urlsplit
from uuid import uuid4

from flask import g, Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from . import store
from . import statistics
from .model import FIELDS, KINDS, NOTE_TYPES, STATUSES, ValidationError, totals


def data_directory():
    from .isolation import activate
    return activate()


def create_app(root=None, testing=False):
    if not testing:
        from .isolation import activate, check_database
        isolated_root = activate()
        if root is not None and Path(root).resolve() != isolated_root:
            raise RuntimeError('Explicit data directory differs from V21 profile.')
        root = isolated_root
        check_database(root)
    root = Path(root or data_directory()).resolve()
    source = Path(__file__).resolve().parents[1]
    if root == source or source in root.parents:
        raise RuntimeError('Data directory must be outside the application source.')
    if testing:
        store.migrate(root)
    app = Flask(__name__)
    from . import network,security
    from werkzeug.security import generate_password_hash
    net=network.configuration()
    app.wsgi_app=network.LocalProxy(app.wsgi_app,net['proxy'])
    # Cookies are ephemeral; restart invalidates forms without writing credentials to code.
    app.config.update(SECRET_KEY=secrets.token_hex(32), MAX_CONTENT_LENGTH=12*1024*1024,
                      SESSION_COOKIE_NAME='cirrus_workplace_v21',SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=net['https'], AUTH_TEST_BYPASS=False, DUMMY_PASSWORD_HASH=generate_password_hash(secrets.token_hex(20)), SESSION_COOKIE_SAMESITE='Strict', TESTING=testing, DATA_DIR=root)

    from .isolation import PROFILE
    app.config['V21_LIVE'] = bool(not testing and PROFILE and PROFILE.get('mode') == 'production')
    build_file = source / 'BUILD_INFO.json'
    app.config['V21_BUILD'] = json.loads(build_file.read_text()).get('commit', 'source')[:8] if build_file.is_file() else 'source'

    def db():
        return store.connect(root)

    def csrf():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(32)
        return session['csrf']

    @app.before_request
    def protect():
        raw_host=request.environ.get('HTTP_HOST','')
        if not re.fullmatch(r'[A-Za-z0-9.-]+(?::[0-9]{1,5})?',raw_host):abort(400,'Invalid Host header.')
        parts=urlsplit('//'+raw_host)
        try:port=parts.port
        except ValueError:abort(400,'Invalid port.')
        if port is not None and not 1<=port<=65535:abort(400,'Invalid port.')
        host=parts.hostname
        if not host or host.lower() not in net['hosts']:abort(400,'Host not allowed.')
        if not net['internal']:
            try:local=ipaddress.ip_address(request.remote_addr or '').is_loopback
            except ValueError:local=False
            if not local:abort(403)
        if net['https'] and not request.is_secure:abort(400,'HTTPS is required.')
        g.user=None
        if session.get('uid'):
            with db() as conn:user=conn.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
            if user and user['active'] and user['session_version']==session.get('version') and time.time()-session.get('seen',0)<1800 and time.time()-session.get('issued',0)<28800:
                g.user=dict(user);session['seen']=time.time()
            else:session.clear()
        if not app.config['AUTH_TEST_BYPASS'] and not g.user and request.endpoint not in ('accounts.login','static'):
            return redirect('/login')
        if re.match(r'^/(customers|projects)/[^/]+/consumption(?:/|$)',request.path) or (request.path.startswith('/customers/') and request.args.get('tab')=='consumption'):
            return render_template('error.html',message='Consumption has been retired from this portal. Existing records and workbooks are retained in backups; administrators can export them for handover from Settings.'),410
        if request.path.startswith('/legacy-customers/'):
            return redirect('/customers/'+request.path.rsplit('/',1)[-1])
        if g.user and g.user['role']=='Viewer' and request.method=='POST' and request.endpoint not in ('accounts.logout','import_data','notifications.read','notifications.preferences','approvals.read_discussion','reporting.page','v21.favorite'):
            abort(403)
        if request.endpoint in ('settings','accounts.accounts','company.template','company.replace_catalog') or (request.blueprint=='hosting' and request.method=='POST') or request.endpoint in ('hosting.edit','quotes.save_catalog'):
            security.require_admin()
        if request.method == 'POST' and not secrets.compare_digest(session.get('csrf','!'), request.form.get('csrf','')):
            abort(400, 'Invalid CSRF token. Reload the page and try again.')
        csrf()

    @app.after_request
    def headers(response):
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        if (request.path.startswith('/documents/') and request.path.endswith('/manage')) or (request.path.startswith('/quotes/') and (request.path.endswith('/outcome') or request.path.endswith('/approval'))):
            response.headers['Content-Security-Policy']=response.headers['Content-Security-Policy'].replace("frame-ancestors 'none'","frame-ancestors 'self'")
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    def allowed_edit(r):
        with db() as conn:return security.can_read(conn,r,write=True)

    def allowed_share(r):
        if not g.user or g.user['role']=='Viewer' or r['kind'] in ('category','catalog'):return False
        with db() as conn:
            row=conn.execute('SELECT owner_id,personal FROM records WHERE id=?',(r['id'],)).fetchone()
            return bool(row and not row['personal'] and not security.personal_flag(conn,r['kind'],r['data']) and (security.admin() or row['owner_id']==g.user['id']))

    @app.context_processor
    def context():
        from .approvals import my_work,private_access,progress
        from .notifications import visible as notifications_visible
        with db() as conn:
            all_records = store.records(conn) if g.user or app.config['AUTH_TEST_BYPASS'] else []
            cfg = store.settings(conn)
            support_issues=conn.execute('SELECT COUNT(*) FROM support_migration_issues').fetchone()[0] if security.admin() else 0
            preference=conn.execute('SELECT * FROM user_preferences WHERE user_id=?',((g.user or {}).get('id'),)).fetchone()
            pending_count=len(my_work(conn,(g.user or {}).get('id'),all_records)['pending']) if g.user else 0
            notifications=notifications_visible(conn,g.user['id'],all_records) if g.user else []
        from .commercial import fingerprint
        def can_margin(record):
            with db() as conn:return private_access(conn,record)
        progress_cache={}
        def approval_progress(record):
            if record['id'] not in progress_cache:
                with db() as conn:progress_cache[record['id']]=progress(conn,record)
            return progress_cache[record['id']]
        return dict(approval_progress=approval_progress,portal_theme=preference['theme'] if preference else 'system',sidebar_collapsed=bool(preference and preference['collapsed']),pending_approval_count=pending_count,notification_count=sum(not n['read_at'] for n in notifications),recent_notifications=notifications[:8],can_margin=can_margin,document_fingerprint=fingerprint,support_issues=support_issues,can_share=allowed_share,user=security.current_user(),is_admin=security.admin(),can_edit=lambda r:allowed_edit(r),csrf=csrf, kinds=KINDS, all_records=all_records, cfg=cfg,
                    label=lambda r:r['data'].get('title') or r['data'].get('name','Untitled'),
                    categories=[r for r in all_records if r['kind']=='category'],
                    projects=[r for r in all_records if r['kind']=='project'],customers=[r for r in all_records if r['kind']=='customer'], totals=totals,
                    note_types=NOTE_TYPES, statuses=STATUSES)

    def get_record(ident):
        with db() as conn:
            r = next((r for r in store.records(conn) if r['id']==ident), None)
        if not r:
            abort(404)
        return r

    @app.errorhandler(ValidationError)
    def validation_error(exc):
        return render_template('error.html', message=str(exc)), 400

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(exc):
        return render_template('error.html', message='Request too large. Files must be at most 10 MiB.'), 413

    @app.route('/')
    def dashboard():
        from .workspace11 import dashboard as upgraded_dashboard
        return upgraded_dashboard()

    @app.route('/list/<section>')
    def listing(section):
        if section=='customer':return redirect('/customers'+('?' + request.query_string.decode() if request.query_string else ''))
        if section in ('note','inbox','personal'):return redirect('/')
        if section not in (*KINDS, 'search'):
            abort(404)
        with db() as conn:
            if section=='catalog':
                from .quotation_setup import ensure
                try:conn.execute('BEGIN IMMEDIATE');ensure(conn)
                except ValidationError as exc:conn.rollback();flash('Default setup initialization needs review: '+str(exc))
            rows = store.records(conn)
        if section=='quote':
            from .documents import listing as documents_listing
            return documents_listing()
        q = request.args.get('q','').casefold()
        result = []
        for r in rows:
            d = r['data']
            if section=='search' and r['kind']=='note':continue
            if section in KINDS and r['kind'] != section:
                continue
            if q and q not in json.dumps(d, ensure_ascii=False).casefold():
                continue
            if any(request.args.get(k) and d.get(k) != request.args[k] for k in ('category','project_id','status')):
                continue
            if request.args.get('tag') and request.args['tag'].casefold() not in [x.strip().casefold() for x in d.get('tags','').split(',')]:
                continue
            result.append(r)
        kpis=statistics.page_kpis(rows,section)
        groups={}
        if section=='catalog':
            from collections import Counter
            groups=Counter((r['data'].get('category') or 'Uncategorized') for r in rows if r['kind']=='catalog')
        order=request.args.get('sort','updated')
        if order not in ('updated','name','status'):raise ValidationError('Invalid record sort.')
        result.sort(key=lambda r:r['updated'] if order=='updated' else r['data'].get('title',r['data'].get('name','')).casefold() if order=='name' else r['data'].get('status','').casefold(),reverse=order=='updated')
        from .listing_ui import paginate
        result,pagination=paginate(result)
        return render_template('list.html',pagination=pagination,section=section, rows=result,kpis=kpis,category_counts=groups)

    @app.route('/new/<kind>', methods=['GET','POST'])
    @app.route('/edit/<kind>/<ident>', methods=['GET','POST'])
    def edit(kind, ident=None):
        if kind not in KINDS or (kind=='note' and request.method=='GET'):
            abort(404)
        if kind=='document' and request.method=='GET':return redirect('/documents/'+ident+'/edit' if ident else '/documents/new')
        if kind in ('catalog','category'):security.require_admin()
        if ident:
            with db() as conn:security.require_id(conn,ident,True)
        elif g.user and g.user['role']=='Viewer':abort(403)
        if kind == 'quote':
            return redirect('/quotes/'+ident+'/edit' if ident else '/quotes/new'+('?' + request.query_string.decode() if request.query_string else ''))
        if kind=='catalog':
            from .quotation_setup import ensure
            with db() as conn:
                try:conn.execute('BEGIN IMMEDIATE');ensure(conn)
                except ValidationError as exc:conn.rollback();flash('Default setup initialization needs review: '+str(exc))
        record = get_record(ident) if ident else None
        if record and record['kind'] != kind:
            abort(404)
        with db() as conn:
            cfg = store.settings(conn)
        d = dict(record['data']) if record else {}
        if not record:
            d.update(status=STATUSES.get(kind, ('',))[0], type='Question and answer' if request.args.get('question') else 'Note',
                     project_id=request.args.get('project_id',''), date=date.today().isoformat(), currency='USD', tax='0',
                     payment_terms=cfg['payment_terms'], delivery_terms=cfg['delivery_terms'])
        if not record and kind=='catalog':d.update(type='',unit='unit',quantity='1',minimum_quantity='0',billing='monthly',method='unit',status='Active')
        if not record and kind=='project' and request.args.get('customer_id'):
            with db() as conn:
                from .relationships import record as related_record
                c=related_record(conn,request.args['customer_id'],'customer')
                d.update(customer_id=c['id'],customer=c['data']['name'])
        error = None
        if request.method == 'POST':
            d = {k:request.form.get(k,'') for k,_,_ in FIELDS[kind]}
            if kind == 'quote':
                d['number'] = record['data']['number'] if record else 'Q-' + uuid4().hex[:12].upper()
                d['revision'] = record['data']['revision'] if record else 1
                try:
                    d['lines'] = json.loads(request.form.get('lines','[]'))
                except ValueError:
                    raise ValidationError('Invalid line items JSON.')
            try:
                with db() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    ident = store.save(conn, kind, d, ident)
                    if kind=='customer' and record is None:
                        agreement={k:'' for k,_,_ in FIELDS['project']}
                        agreement.update(name=d['name'],customer=d['name'],customer_id=ident,status='Active')
                        store.save(conn,'project',agreement)
                flash('Saved successfully.')
                return redirect(url_for('detail', ident=ident))
            except ValidationError as exc:
                error = str(exc)
                if kind == 'quote' and not isinstance(d.get('lines'), list):
                    d['lines'] = []
        if kind=='catalog':return render_template('catalog_item.html',d=d,record=record,fields=FIELDS[kind],error=error,writable=True)
        return render_template('edit.html', kind=kind, d=d, fields=FIELDS[kind], error=error, record=record)

    @app.route('/record/<ident>')
    def detail(ident):
        r = get_record(ident)
        if r['kind']=='catalog':
            from .quotation_setup import ensure
            with db() as conn:
                try:conn.execute('BEGIN IMMEDIATE');ensure(conn)
                except ValidationError as exc:conn.rollback();flash('Default setup initialization needs review: '+str(exc))
            r=get_record(ident)
            return render_template('catalog_item.html',d=r['data'],record=r,fields=FIELDS['catalog'],error=None,writable=security.admin())
        with db() as conn:
            attachments = conn.execute('SELECT * FROM attachments WHERE record_id=?', (ident,)).fetchall()
            related = [x for x in store.records(conn) if x['data'].get('project_id')==ident]
        if r['kind']=='document':return redirect('/documents/'+ident+('/edit' if allowed_edit(r) else '/print'))
        if r['kind']=='customer':return redirect('/customers/'+ident)
        if r['kind']=='quote' and 'document' in r['data']:
            with db() as conn:writable=security.can_read(conn,r,write=True)
            return redirect('/quotes/'+ident+('/edit' if writable else '/print'))
        return render_template('detail.html', r=r, fields=FIELDS[r['kind']], attachments=attachments, related=related)

    @app.post('/record/<ident>/delete')
    def delete(ident):
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            security.require_id(conn,ident,True)
            rows = store.records(conn,unrestricted=True)
            r = next((r for r in rows if r['id']==ident),None)
            if not r:
                abort(404)
            if r['kind']=='quote':
                from .archives import archived_keys
                from .references import key
                if key(r['data']['number']) in archived_keys(conn):
                    # Reuse the family confirmation rather than deleting one revision.
                    return redirect('/quotes/'+ident+'/delete-review')
            if r['kind']=='customer':
                security.require_admin()
                return redirect('/customers/'+ident+'/delete-review')
            if any(any(x['data'].get(k)==ident for k in ('project_id','customer_id','category','subcategory','parent')) for x in rows):
                raise ValidationError('Record is linked. Unlink its notes, quotations, or subcategories first.')
            from .relationships import guard_delete
            guard_delete(conn,r)
            if r['kind']=='quote':
                from .outcomes import require_not_accepted
                require_not_accepted(conn,ident)
            files = conn.execute('SELECT stored FROM attachments WHERE record_id=?', (ident,)).fetchall()
            conn.execute('DELETE FROM attachments WHERE record_id=?', (ident,))
            conn.execute('DELETE FROM record_acl WHERE record_id=?',(ident,))
            conn.execute('DELETE FROM reference_conflicts WHERE record_id=?',(ident,))
            if r['kind'] in ('quote','document'):
                from .documents import event as document_event
                document_event(conn,ident,'Permanently deleted',r['data']['title'])
            conn.execute('DELETE FROM records WHERE id=?', (ident,))
            if r['kind']=='quote':
                from .references import after_delete,key
                after_delete(conn,key(r['data']['number']))
                conn.execute('DELETE FROM quote_costing WHERE quote_id=?',(ident,))
                conn.execute('DELETE FROM support_migrations WHERE quote_id=?',(ident,))
                conn.execute('DELETE FROM support_migration_issues WHERE quote_id=?',(ident,))
        for f in files:
            (root/'attachments'/f['stored']).unlink(missing_ok=True)
        flash('Deleted.')
        return redirect('/list/quote' if r['kind']=='document' else url_for('listing', section=r['kind']))

    @app.post('/record/<ident>/copy/<mode>')
    def copy_quote(ident, mode):
        if mode not in ('revision','duplicate'):
            abort(404)
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            security.require_id(conn,ident,True)
            r = next((r for r in store.records(conn) if r['id']==ident),None)
            if not r or r['kind'] not in ('quote','document'):
                abort(404)
            d = dict(r['data']);source_number=d['number']
            if mode=='revision':
                from .references import key
                family=[x for x in store.records(conn,unrestricted=True) if x['kind']==r['kind'] and key(x['data']['number'])==key(d['number'])]
                latest=max(family,key=lambda x:x['data']['revision'])
                if latest['data']['revision']>d['revision']:
                    security.require_record(conn,latest,True)
                    flash('A newer revision already exists. Open it to create the next revision.')
                    return redirect(url_for('detail',ident=latest['id']))
                d['revision'] = latest['data']['revision'] + 1
            else:
                from .references import overview
                d['number'], d['revision'] = overview(conn,statistics.today_local())['next'], 1
            d['status'] = 'Draft'
            if mode=='duplicate' and r['kind']=='quote' and 'document' in d and any(row.get('dr_link') for section in d['document']['sections'] for row in section['rows']):
                from .quotation import duplicate_document
                d['document']=duplicate_document(d['document'])
            # Preserve manually edited subjects/titles. Only recognized generated
            # version suffixes and the duplicate's leading reference are updated.
            if re.search(r'_V[0-9]+\.[0-9]+$',d['title']):d['title']=re.sub(r'_V[0-9]+\.[0-9]+$',f"_V{d['revision']}.0",d['title'])
            prefix=source_number+'_'
            if mode=='duplicate' and d['title'].casefold().startswith(prefix.casefold()):d['title']=d['number']+'_'+d['title'][len(prefix):]
            new_id = store.save(conn, r['kind'], d,inherit_from=ident if mode=='revision' else None)
        return redirect(url_for('detail', ident=new_id))

    @app.route('/quote/<ident>/print')
    def print_quote(ident):
        r = get_record(ident)
        if r['kind']!='quote':
            abort(404)
        if 'document' in r['data']:
            return redirect('/quotes/'+ident+'/print')
        # Explicit public projection: private fields never enter print template.
        private = {'internal_notes'}
        d = {k:v for k,v in r['data'].items() if k not in private}
        calc = totals(d['lines'], d['tax'])
        d['lines'] = [{k:v for k,v in line.items() if k!='cost'} for line in calc['lines']]
        public_totals = {k:calc[k] for k in ('subtotal','tax_amount','grand_total')}
        return render_template('print.html', d=d, calculation=public_totals)

    @app.route('/quote/<ident>/csv')
    def quote_csv(ident):
        r = get_record(ident)
        if r['kind']!='quote':
            abort(404)
        if 'document' in r['data']:
            return redirect('/quotes/'+ident+'/csv')
        out = io.StringIO(newline='')
        writer = csv.writer(out)
        writer.writerow(['Description','Unit','Quantity','Unit selling price','Discount %','Total','Currency'])
        def safe(value):
            s = str(value)
            return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s
        for line in totals(r['data']['lines'], r['data']['tax'])['lines']:
            writer.writerow([safe(line[k]) if line[k] is not None else '' for k in ('description','unit','quantity','price','discount','total')] + [r['data']['currency']])
        return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name=r['data']['number']+'.csv')

    @app.route('/record/<ident>/markdown')
    def markdown(ident):
        r = get_record(ident)
        if r['kind'] not in ('note','project'):
            abort(404)
        lines = ['# '+(r['data'].get('title') or r['data']['name']), '', f"Updated: {r['updated']}"]
        lines += [f'\n## {label}\n\n{r["data"].get(key, "")}' for key,label,_ in FIELDS[r['kind']]]
        if r['kind']=='project':
            with db() as conn:
                for child in store.records(conn):
                    if child['kind']=='note' and child['data'].get('project_id')==ident:
                        lines.append('\n## '+child['data']['title']+'\n\n'+child['data']['content']+'\n\n'+child['data']['answer'])
                    elif child['kind']=='quote' and child['data'].get('project_id')==ident:
                        q = child['data']
                        from .quotation import calculate
                        amount = calculate(q['document'])['combined'] if 'document' in q else totals(q['lines'], q['tax'])['grand_total']
                        lines.append(f"\n## Quotation: {q['title']}\n\n{q['number']} · Revision {q['revision']} · {q['status']}\n\nTotal: {amount or 'Unpriced'} {q['currency']}")
        return send_file(io.BytesIO('\n'.join(lines).encode()), as_attachment=True, download_name=r['kind']+'-'+ident+'.md', mimetype='text/markdown')

    @app.post('/record/<ident>/attachment')
    def upload(ident):
        get_record(ident)
        with db() as conn:security.require_id(conn,ident,True,include_workflow=False)
        f = request.files.get('file')
        if not f or not f.filename:
            raise ValidationError('Choose a file.')
        filename = secure_filename(f.filename)
        ext = Path(filename).suffix.lower()
        mime = {'.pdf':'application/pdf','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.txt':'text/plain','.md':'text/plain'}.get(ext)
        if not mime:
            raise ValidationError('Allowed files: PDF, PNG, JPEG, TXT, MD.')
        content = f.read(10*1024*1024+1)
        if len(content)>10*1024*1024:
            raise ValidationError('Maximum attachment size is 10 MiB.')
        if not content:
            raise ValidationError('Empty attachment.')
        if (ext=='.pdf' and not content.startswith(b'%PDF-')) or (ext=='.png' and not content.startswith(b'\x89PNG\r\n\x1a\n')) or (ext in ('.jpg','.jpeg') and not content.startswith(b'\xff\xd8\xff')):
            raise ValidationError('File signature does not match extension.')
        if ext in ('.txt','.md'):
            try:
                content.decode('utf-8')
            except UnicodeDecodeError:
                raise ValidationError('Text attachments must use UTF-8.') from None
        ident_file = str(uuid4())
        stored = ident_file+ext
        path = root/'attachments'/stored
        try:
            path.write_bytes(content)
            with db() as conn:
                conn.execute('INSERT INTO attachments VALUES (?,?,?,?,?)', (ident_file,ident,filename,stored,mime))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return redirect(url_for('detail', ident=ident))

    @app.route('/attachment/<ident_file>')
    def attachment(ident_file):
        with db() as conn:
            f = conn.execute('SELECT * FROM attachments WHERE id=?',(ident_file,)).fetchone()
        if not f:
            abort(404)
        with db() as conn:
            original=conn.execute('SELECT 1 FROM monthly_history WHERE attachment_id=?',(ident_file,)).fetchone()
            security.require_id(conn,f['record_id'],write=bool(original),include_workflow=False)
        return send_file(root/'attachments'/f['stored'], mimetype=f['mime'], as_attachment=True, download_name=f['name'])

    @app.post('/attachment/<ident_file>/delete')
    def delete_attachment(ident_file):
        with db() as conn:
            f = conn.execute('SELECT * FROM attachments WHERE id=?',(ident_file,)).fetchone()
            if not f:
                abort(404)
            security.require_id(conn,f['record_id'],True,include_workflow=False)
            if conn.execute('SELECT 1 FROM monthly_history WHERE attachment_id=?',(ident_file,)).fetchone():
                raise ValidationError('Original consumption import workbooks are retained for audit history.')
            if conn.execute('SELECT 1 FROM contract_documents WHERE attachment_id=?',(ident_file,)).fetchone():
                raise ValidationError('This file belongs to a historical contract version and must be retained.')
            conn.execute('DELETE FROM attachments WHERE id=?',(ident_file,))
        (root/'attachments'/f['stored']).unlink(missing_ok=True)
        return redirect(url_for('detail', ident=f['record_id']))

    @app.route('/settings', methods=['GET','POST'])
    def settings():
        if request.method=='POST':
            with db() as conn:
                for key in ('company','payment_terms','delivery_terms'):
                    value = request.form.get(key,'').strip()
                    if len(value)>10000 or (key=='company' and not value):
                        raise ValidationError('Company is required; settings have a 10,000 character limit.')
                    conn.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
            flash('Settings saved.')
            return redirect(url_for('settings'))
        return render_template('settings.html', data_dir=str(root))

    @app.route('/portability')
    def portability():return render_template('portability.html')

    @app.route('/export')
    def export():
        with db() as conn:
            payload = store.export_data(conn)
        return send_file(io.BytesIO(json.dumps(payload,indent=2).encode()), as_attachment=True, download_name='cirrus-workplace.json', mimetype='application/json')

    @app.post('/import')
    def import_data():
        if g.user and g.user['role']=='Viewer':abort(403)
        text = request.form.get('payload')
        if text is None:
            f = request.files.get('file')
            if not f:
                raise ValidationError('Choose a JSON file.')
            try:
                text = f.read().decode('utf-8-sig')
            except UnicodeError:
                raise ValidationError('Import file must be UTF-8.') from None
        def unique(pairs):
            obj={}
            for k,v in pairs:
                if k in obj:
                    raise ValidationError('Duplicate JSON key: '+k)
                obj[k]=v
            return obj
        try:
            payload = json.loads(text, object_pairs_hook=unique)
        except (ValueError, RecursionError):
            raise ValidationError('Invalid JSON document.') from None
        with db() as conn:
            if request.form.get('confirm')=='yes':
                conn.execute('BEGIN IMMEDIATE')
                count, skipped = store.apply_import(conn, payload)
                flash(f'Imported {count} records; skipped {skipped} identical records.')
                return redirect(url_for('settings'))
            new, skipped = store.preview_import(conn, payload)
        from .hosting import import_plan
        with db() as conn:
            vm_changes=len(import_plan(conn,payload['hosting_vms'])) if 'hosting_vms' in payload else 0
        return render_template('import.html', payload=text, new=new, skipped=skipped,vm_changes=vm_changes)

    from .customers import bp as customers_bp
    app.register_blueprint(customers_bp)
    from .relationships import bp as relationships_bp
    from .archives import bp as archives_bp
    app.register_blueprint(relationships_bp)
    app.register_blueprint(archives_bp)
    from .quotation_deletion import bp as deletion_bp
    from .reporting import bp as reporting_bp
    app.register_blueprint(deletion_bp);app.register_blueprint(reporting_bp)
    from .customer_document_routes import bp as customer_documents_bp
    app.register_blueprint(customer_documents_bp)
    from .accounts import bp as accounts_bp
    app.register_blueprint(accounts_bp)
    from .references import bp as references_bp
    app.register_blueprint(references_bp)
    from .outcomes import bp as outcomes_bp
    from .costing import bp as costing_bp
    from .comparison import bp as comparison_bp
    app.register_blueprint(outcomes_bp)
    app.register_blueprint(costing_bp)
    app.register_blueprint(comparison_bp)
    from .tenant import bp as tenant_bp
    app.register_blueprint(tenant_bp)
    from .approval_routes import bp as approvals_bp
    from .notifications import bp as notifications_bp
    from .retained_consumption import bp as retained_bp
    app.register_blueprint(approvals_bp);app.register_blueprint(notifications_bp);app.register_blueprint(retained_bp)
    from .workspace11 import bp as workspace11_bp
    app.register_blueprint(workspace11_bp)
    from .export_folders import bp as export_folders_bp
    app.register_blueprint(export_folders_bp)
    from .automation import bp as automation_bp
    app.register_blueprint(automation_bp)
    from .documents import bp as documents_bp
    app.register_blueprint(documents_bp)
    from .quote_routes import bp
    app.register_blueprint(bp)
    from .hosting_routes import bp as hosting_bp
    app.register_blueprint(hosting_bp)
    from .company import bp as company_bp
    app.register_blueprint(company_bp)
    from .quotation_setup import bp as setup_bp
    app.register_blueprint(setup_bp)
    from .excel_routes import bp as excel_bp
    app.register_blueprint(excel_bp)
    from .v21 import bp as v21_bp, install
    app.register_blueprint(v21_bp)
    install(app)
    if not testing:
        from .automation import start
        start(app)
    return app
