"""Server-local queued customer PDF exports and consistent daily full backups.

Uses a maintained browser driver; no external service or listener/data changes.
Uses installed Edge/Chrome/Chromium headless printing in a disposable profile.
"""
import json,ntpath,os,re,shutil,tempfile,threading,time
from datetime import date,datetime,timezone
from pathlib import Path
from uuid import uuid4
from flask import Blueprint,abort,current_app,flash,g,redirect,render_template,request,send_file
from . import store,security
from .model import ValidationError
from .commercial import fingerprint
from .references import stamp

bp=Blueprint('automation',__name__)
DEFAULTS=dict(pdf_enabled=False,pdf_folder='',backup_enabled=False,backup_folder='',daily_retention=14,weekly_retention=8)


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS pdf_exports (
    record_id TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
    generation INTEGER NOT NULL,status TEXT NOT NULL,snapshot TEXT NOT NULL,
    requested TEXT NOT NULL,last_success TEXT,destination TEXT,error TEXT NOT NULL DEFAULT '')''')
    from .export_folders import schema as folder_schema
    folder_schema(db)
    db.execute('''CREATE TABLE IF NOT EXISTS automation_events (
    id INTEGER PRIMARY KEY,at TEXT NOT NULL,actor TEXT,action TEXT NOT NULL,details TEXT NOT NULL)''')


def config(db):
    row=db.execute("SELECT value FROM settings WHERE key='automation'").fetchone()
    return {**DEFAULTS,**(json.loads(row[0]) if row else {})}


def audit(db,action,details=''):
    db.execute('INSERT INTO automation_events(at,actor,action,details) VALUES (?,?,?,?)',(stamp(),(security.current_user() or {}).get('id'),action,details))


def path_kind(value):
    if not isinstance(value,str) or not value.strip() or len(value)>500 or '\x00' in value:raise ValidationError('Enter an absolute folder path up to 500 characters.')
    value=value.strip()
    if value.startswith(('\\\\?\\','\\\\.\\')):raise ValidationError('Use a regular absolute Windows or UNC folder path.')
    drive,tail=ntpath.splitdrive(value)
    windows=bool(drive and ntpath.isabs(value))
    if windows and drive.startswith('\\\\') and len(drive.strip('\\').split('\\'))!=2:raise ValidationError('UNC paths need both server and share names.')
    if not windows and not (os.name!='nt' and Path(value).is_absolute()):raise ValidationError(r'Use C:\CirrusExports or \\server\share\CirrusExports, not a relative path or mapped drive.')
    return 'windows' if windows else 'native'


def validate_paths(cfg,root):
    from .isolation import require_path
    for key, kind in [("pdf_folder", "exports"), ("backup_folder", "backups")]:
        if cfg[key]:require_path(cfg[key], kind)
    entries=[]
    for kind in ('pdf','backup'):
        value=cfg[kind+'_folder']
        if cfg[kind+'_enabled'] and not value:raise ValidationError('Set the '+kind+' folder before enabling it.')
        if value:
            style=path_kind(value);normalize=ntpath.normcase(ntpath.normpath(value)) if style=='windows' else str(Path(value).resolve())
            entries.append((kind,style,normalize))
            if style=='native' or os.name=='nt':
                p=Path(value).resolve();data=Path(root).resolve();source=Path(__file__).resolve().parents[1]
                if any(p==x or x in p.parents or p in x.parents for x in (data,source)):raise ValidationError('Export and backup folders must be outside and separate from application and data directories.')
    if len(entries)==2:
        _,a,x=entries[0];_,b,y=entries[1]
        separator='\\' if a=='windows' else '/'
        if a==b and (x==y or x.startswith(y.rstrip(separator)+separator) or y.startswith(x.rstrip(separator)+separator)):raise ValidationError('PDF exports and full backups require separate, non-nested folders.')


def native_folder(value):
    from .isolation import PROFILE, require_path
    if PROFILE is not None:
        kind = "exports" if Path(value).resolve() == PROFILE["roots"]["exports"] or PROFILE["roots"]["exports"] in Path(value).resolve().parents else "backups"
        require_path(value, kind)
    kind=path_kind(value)
    if kind=='windows' and os.name!='nt':raise RuntimeError('A Windows/UNC path can only be tested or used on the Windows Workplace server.')
    folder=Path(value)
    if not folder.is_dir():raise RuntimeError('Folder does not exist or is inaccessible to the Workplace server account.')
    return folder


def test_access(value):
    folder=native_folder(value)
    # Test subfolder creation, write, flush, rename and delete (needed by both jobs).
    with tempfile.TemporaryDirectory(prefix='.cirrus-access-test-',dir=folder) as temporary:
        first=Path(temporary)/'write.tmp';second=Path(temporary)/'rename.tmp'
        with first.open('xb') as handle:handle.write(b'Cirrus Workplace access test');handle.flush();os.fsync(handle.fileno())
        os.replace(first,second);second.unlink()


def enqueue(db,ident,data,force=False):
    if db.execute('SELECT 1 FROM deleted_quotation_ids WHERE record_id=?',(ident,)).fetchone():return
    if not config(db)['pdf_enabled'] and not force:return
    snapshot=fingerprint(data)
    db.execute("INSERT INTO pdf_exports(record_id,generation,status,snapshot,requested) VALUES (?,1,'pending',?,?) ON CONFLICT(record_id) DO UPDATE SET generation=generation+1,status='pending',snapshot=excluded.snapshot,requested=excluded.requested,error=''",(ident,snapshot,stamp()))


def browser_path():
    configured=os.environ.get('CIRRUS_PDF_BROWSER','')
    if configured:
        p=Path(configured)
        if not p.is_absolute() or not p.is_file():raise RuntimeError('CIRRUS_PDF_BROWSER must be an absolute path to an installed Edge/Chrome executable.')
        return str(p)
    choices=[]
    if os.name=='nt':
        for base in (os.environ.get('PROGRAMFILES',''),os.environ.get('PROGRAMFILES(X86)',''),os.environ.get('LOCALAPPDATA','')):
            if base:choices.extend([str(Path(base)/'Microsoft/Edge/Application/msedge.exe'),str(Path(base)/'Google/Chrome/Application/chrome.exe')])
    choices.extend(filter(None,(shutil.which(n) for n in ('microsoft-edge','google-chrome','chromium','chromium-browser'))))
    found=next((p for p in choices if Path(p).is_file()),None)
    if not found:raise RuntimeError('No supported PDF renderer found. Install Microsoft Edge/Chrome on the server, or set CIRRUS_PDF_BROWSER to its executable. Manual browser printing remains available.')
    return found


def render_pdf(app,data,destination):
    from .quote_routes import render_customer
    # No HTTP request to the live server: use the same public projection/template.
    with app.test_request_context('/internal-customer-pdf'):
        g.user=None
        html=render_customer(data)
    css=(Path(__file__).parent/'static/quotation.css').read_text()
    html=html.replace('<link rel="stylesheet" href="/static/quotation.css">','<style>'+css+'</style>')
    html=html.replace('<script defer src="/static/app.js"></script>','')
    print_html_pdf(app,html,destination)


def print_html_pdf(app,html,destination):
    executable=browser_path()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as driver:
        sandbox=not (os.environ.get('CIRRUS_PDF_NO_SANDBOX')=='1' and os.name!='nt')
        browser=driver.chromium.launch(executable_path=executable,headless=True,chromium_sandbox=sandbox,timeout=30000,args=['--disable-background-networking','--disable-extensions'])
        try:
            page=browser.new_page();page.set_default_timeout(45000)
            # No live-server or file navigation; policies can prohibit file URLs.
            # Everything is embedded, and outbound requests are denied.
            page.route('http://**/*',lambda route:route.abort());page.route('https://**/*',lambda route:route.abort())
            page.set_content(html,wait_until='load',timeout=45000)
            page.evaluate("async () => {await document.fonts.ready; await Promise.all([...document.images].map(image => image.decode().catch(() => {})));}")
            page.pdf(path=str(destination),print_background=True,prefer_css_page_size=True,display_header_footer=False)
        finally:browser.close()
    result=Path(destination)
    if not result.is_file() or result.stat().st_size<100 or not result.read_bytes().startswith(b'%PDF-'):raise RuntimeError('PDF renderer did not produce a valid PDF.')
    with result.open('r+b') as handle:os.fsync(handle.fileno())


def process_pdf(app,renderer=None):
    root=app.config['DATA_DIR'];renderer=renderer or render_pdf
    with store.connect(root) as db:
        db.execute('BEGIN IMMEDIATE');cfg=config(db)
        if not cfg['pdf_enabled']:return False
        row=db.execute("SELECT p.*,r.data FROM pdf_exports p JOIN records r ON r.id=p.record_id WHERE p.status='pending' ORDER BY requested LIMIT 1").fetchone()
        if not row:return False
        job=dict(row);data=json.loads(job['data']);db.execute("UPDATE pdf_exports SET status='running' WHERE record_id=?",(job['record_id'],))
    temporary=None
    try:
        from .export_folders import destination as customer_destination
        with store.connect(root) as db:folder=customer_destination(db,data,cfg)
        subfolder=folder
        from .documents import filename
        destination=subfolder/filename(data['title'],'pdf')
        fd,name=tempfile.mkstemp(prefix='.cirrus-pdf-',suffix='.tmp',dir=subfolder);os.close(fd);temporary=Path(name)
        renderer(app,data,temporary)
        with store.connect(root) as db:
            db.execute('BEGIN IMMEDIATE');current=db.execute('SELECT generation,snapshot FROM pdf_exports WHERE record_id=?',(job['record_id'],)).fetchone();record=db.execute('SELECT data FROM records WHERE id=?',(job['record_id'],)).fetchone();current_cfg=config(db)
            if not current or not record:return True
            if current['generation']!=job['generation']:return True
            if fingerprint(json.loads(record['data']))!=job['snapshot']:
                enqueue(db,job['record_id'],json.loads(record['data']),True);return True
            # A mapping may change while rendering. Never publish to a stale customer destination.
            current_folder=customer_destination(db,json.loads(record['data']),current_cfg)
            if not current_cfg['pdf_enabled'] or current_cfg['pdf_folder']!=cfg['pdf_folder'] or current_folder!=folder:
                db.execute("UPDATE pdf_exports SET status='pending' WHERE record_id=?",(job['record_id'],));return True
            import ntpath
            path_key=ntpath.normcase(str(destination).replace('/','\\')).casefold()
            owner=db.execute('SELECT record_id,revision,approved_hash FROM pdf_file_owners WHERE path_key=?',(path_key,)).fetchone()
            if owner and (owner['record_id']!=job['record_id'] or owner['revision']!=data['revision']):raise RuntimeError('PDF filename conflict: another quotation/revision owns this name. Edit the title and Retry.')
            from .approvals import content
            content_hash=fingerprint(content(data))
            if owner and owner['approved_hash'] and owner['approved_hash']!=content_hash:
                raise RuntimeError('PDF filename conflict: this name holds a previous approved/sent version. Edit the quotation title for the new version and Retry; the approved file will not be overwritten.')
            if owner and owner['approved_hash'] and not destination.exists():
                frozen=db.execute('''SELECT a.pdf FROM approval_artifacts a JOIN approval_rounds r ON r.id=a.round_id
                    WHERE r.quote_id=? AND r.hash=? AND a.pdf IS NOT NULL ORDER BY r.rowid DESC LIMIT 1''',(job['record_id'],content_hash)).fetchone()
                if not frozen:raise RuntimeError('The approved PDF is still being captured. Retry after approved PDF capture completes.')
                with temporary.open('wb') as handle:handle.write(frozen['pdf']);handle.flush();os.fsync(handle.fileno())
            if not owner and destination.exists():raise RuntimeError('PDF filename conflict: an untracked file already exists. Edit the title or review the file; it will not be overwritten.')
            db.execute('INSERT OR IGNORE INTO pdf_file_owners(path_key,record_id,path,revision) VALUES (?,?,?,?)',(path_key,job['record_id'],str(destination),data['revision']))
            approved=db.execute("SELECT 1 FROM approval_rounds WHERE quote_id=? AND hash=? AND completed_at IS NOT NULL",(job['record_id'],content_hash)).fetchone()
            if approved:
                db.execute("UPDATE pdf_file_owners SET approved_hash=? WHERE path_key=? AND approved_hash=''",(content_hash,path_key))
            # Same-directory atomic replace on local NTFS and SMB shares supporting rename.
            if not (owner and owner['approved_hash'] and destination.exists()):
                os.replace(temporary,destination);temporary=None
            db.execute("UPDATE pdf_exports SET status='success',last_success=?,destination=?,published_hash=?,error='' WHERE record_id=?",(stamp(),str(destination),content_hash,job['record_id']))
            audit(db,'Automatic customer PDF exported',job['record_id'])
            from .documents import event
            event(db,job['record_id'],'Exported','Automatic customer PDF (server)')
            # Old exports are external customer copies: never move or remove them
            # when title, customer assignment or folder mapping changes.
    except Exception as exc:
        with store.connect(root) as db:
            from .export_folders import MissingFolder
            db.execute("UPDATE pdf_exports SET status=?,error=? WHERE record_id=? AND generation=?",('not_configured' if isinstance(exc,MissingFolder) else 'failed',str(exc)[:2000],job['record_id'],job['generation']));audit(db,'Automatic PDF failed',job['record_id']+': '+str(exc)[:1000])
    finally:
        if temporary:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
    return True


def backup_state(db):
    row=db.execute("SELECT value FROM settings WHERE key='backup_state'").fetchone();return json.loads(row[0]) if row else {}


def set_backup_state(db,state):
    db.execute("INSERT INTO settings VALUES ('backup_state',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(state),))


def run_daily_backup(app,today=None):
    from .backup import online_safety_backup
    from .statistics import today_local
    today=today or today_local();root=app.config['DATA_DIR']
    with store.connect(root) as db:cfg=config(db);state=backup_state(db)
    if not cfg['backup_enabled'] or state.get('date')==today.isoformat() and state.get('status')=='success':return False
    try:
        folder=native_folder(cfg['backup_folder']);namespace=folder/'Cirrus-Workplace-full-backups'
        from .isolation import require_path
        require_path(namespace,'backups');namespace.mkdir(exist_ok=True)
        # Manifested backups in this dedicated namespace only; unrelated files never pruned.
        daily=namespace/('daily-'+today.isoformat()+'-'+uuid4().hex[:8]+'.zip');online_safety_backup(root,daily)
        iso=today.isocalendar();week=f'{iso.year}-W{iso.week:02d}';weekly_pattern=re.compile(r'^weekly-\d{4}-W\d{2}-[0-9a-f]{8}\.zip$');daily_pattern=re.compile(r'^daily-\d{4}-\d{2}-\d{2}-[0-9a-f]{8}\.zip$')
        if not any(namespace.glob('weekly-'+week+'-*.zip')):
            weekly=namespace/('weekly-'+week+'-'+uuid4().hex[:8]+'.zip');tmp=namespace/('.weekly-'+uuid4().hex+'.tmp')
            try:shutil.copyfile(daily,tmp);os.replace(tmp,weekly)
            finally:tmp.unlink(missing_ok=True)
        # Prune only after both the current daily and weekly copies succeeded.
        for prefix,pattern,keep in [('daily',daily_pattern,cfg['daily_retention']),('weekly',weekly_pattern,cfg['weekly_retention'])]:
            candidates=sorted((p for p in namespace.iterdir() if p.is_file() and pattern.fullmatch(p.name)),key=lambda p:p.name,reverse=True)
            for stale in candidates[keep:]:stale.unlink()
        with store.connect(root) as db:
            set_backup_state(db,dict(date=today.isoformat(),status='success',last_success=stamp(),destination=str(daily),error=''));audit(db,'Daily full backup completed',str(daily))
    except Exception as exc:
        with store.connect(root) as db:
            set_backup_state(db,{**state,'date':today.isoformat(),'status':'failed','error':str(exc)[:2000],'last_attempt':stamp()});audit(db,'Daily full backup failed',str(exc)[:1000])
    return True


def start(app):
    if app.config.get('AUTOMATION_STARTED'):return
    app.config['AUTOMATION_STARTED']=True;stop=threading.Event();app.extensions['automation_stop']=stop
    # Durable interrupted PDF jobs resume after a process restart.
    with store.connect(app.config['DATA_DIR']) as db:db.execute("UPDATE pdf_exports SET status='pending' WHERE status='running'")
    with store.connect(app.config['DATA_DIR']) as db:
        db.execute("UPDATE approval_artifacts SET status='pending' WHERE status='running' AND pdf IS NULL")
        db.execute("UPDATE notification_emails SET status='failed',error='Delivery interrupted; verify receipt before Retry.' WHERE status='running'")
    def worker():
        last_backup_check=0
        while not stop.is_set():
            try:
                with app.app_context():
                    process_pdf(app)
                    from .approval_routes import capture_pdf
                    from .notifications import process_email
                    capture_pdf(app)
                    process_email(app)
                    if app.config.pop('BACKUP_CONFIG_CHANGED',False) or time.monotonic()-last_backup_check>3600:
                        run_daily_backup(app);last_backup_check=time.monotonic()
            except Exception:app.logger.exception('Cirrus background automation failed')
            stop.wait(2)
    thread=threading.Thread(target=worker,name='cirrus-server-automation',daemon=True);thread.start()


@bp.route('/automation/settings',methods=['GET','POST'])
def settings():
    security.require_admin();root=current_app.config['DATA_DIR']
    with store.connect(root) as db:
        cfg=config(db);state=backup_state(db)
        if request.method=='POST':
            action=request.form.get('action','save')
            if action=='retry_backup':
                set_backup_state(db,{**state,'date':'','status':'pending'});current_app.config['BACKUP_CONFIG_CHANGED']=True;flash('Daily backup scheduled. The server will attempt it shortly.');return redirect('/automation/settings')
            candidate={k:request.form.get(k,'').strip() for k in ('pdf_folder','backup_folder')};candidate.update(pdf_enabled=request.form.get('pdf_enabled')=='yes',backup_enabled=request.form.get('backup_enabled')=='yes')
            try:candidate.update(daily_retention=int(request.form.get('daily_retention','14')),weekly_retention=int(request.form.get('weekly_retention','8')))
            except ValueError:raise ValidationError('Retention must be whole numbers.') from None
            if not 1<=candidate['daily_retention']<=3650 or not 1<=candidate['weekly_retention']<=520:raise ValidationError('Keep 1–3650 daily and 1–520 weekly backups.')
            validate_paths(candidate,root)
            if action.startswith('test_'):
                kind=action.removeprefix('test_')
                if kind not in ('pdf','backup'):raise ValidationError('Invalid folder test.')
                try:test_access(candidate[kind+'_folder']);flash('Folder access test passed: subfolder creation, write, rename and delete using the Workplace server account.')
                except Exception as exc:flash('Folder access test failed: '+str(exc))
                return render_template('automation_settings.html',automation=candidate,backup_state=state,renderer=renderer_status())
            db.execute('BEGIN IMMEDIATE');db.execute("INSERT INTO settings VALUES ('automation',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(candidate),));audit(db,'Automation settings changed')
            if candidate['backup_folder']!=cfg['backup_folder'] or not cfg['backup_enabled'] and candidate['backup_enabled']:set_backup_state(db,{**state,'date':'','status':'pending'})
            # Wake the worker's daily check without spawning per-save threads.
            current_app.config['BACKUP_CONFIG_CHANGED']=True
            flash('Server automation settings saved. Existing quotations export on their next save or Retry.');return redirect('/automation/settings')
    return render_template('automation_settings.html',automation=cfg,backup_state=state,renderer=renderer_status())


def renderer_status():
    try:return browser_path()
    except RuntimeError as exc:return str(exc)


@bp.post('/documents/<ident>/pdf-retry')
def retry_pdf(ident):
    from .documents import fetch
    with store.connect(current_app.config['DATA_DIR']) as db:
        db.execute('BEGIN IMMEDIATE');r=fetch(db,ident,True)
        if r['kind']!='quote':abort(404)
        if not config(db)['pdf_enabled']:raise ValidationError('Automatic PDF export is disabled. Ask an administrator to enable it.')
        enqueue(db,ident,r['data'],True)
    flash('PDF export queued. The saved quotation remains available.');return redirect('/documents/'+ident+'/manage')


@bp.post('/backups/download')
def download_backup():
    security.require_admin()
    from .backup import online_safety_backup
    fd,name=tempfile.mkstemp(prefix='cirrus-full-',suffix='.zip');os.close(fd);Path(name).unlink()
    try:online_safety_backup(current_app.config['DATA_DIR'],name)
    except Exception:
        Path(name).unlink(missing_ok=True);raise
    with store.connect(current_app.config['DATA_DIR']) as db:audit(db,'Full backup downloaded')
    response=send_file(name,as_attachment=True,download_name='Cirrus-Workplace-full-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'.zip',mimetype='application/zip')
    response.direct_passthrough=False;response.call_on_close(lambda:Path(name).unlink(missing_ok=True));return response


@bp.get('/documents/<ident>/pdf-status')
def pdf_status(ident):
    from .documents import fetch
    with store.connect(current_app.config['DATA_DIR']) as db:
        r=fetch(db,ident)
        if r['kind']!='quote':abort(404)
        row=db.execute('SELECT status,error,last_success,destination FROM pdf_exports WHERE record_id=?',(ident,)).fetchone()
        return dict(customer_config_url=('/customers/'+r['data']['customer_id']+'/quotation-folder') if security.admin() and r['data'].get('customer_id') else '/customers' if security.admin() else None,enabled=config(db)['pdf_enabled'],**(dict(row) if row else dict(status='not_requested',error='',last_success=None,destination=None)))
