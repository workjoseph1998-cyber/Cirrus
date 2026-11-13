"""Administrator-managed customer export destinations, keyed by immutable customer IDs."""
import ntpath,os
from pathlib import Path
from flask import Blueprint,current_app,flash,redirect,render_template,request
from . import store,security
from .model import ValidationError
from .references import stamp,actor
from .commercial import fingerprint

bp=Blueprint('export_folders',__name__)


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS customer_export_folders (
      customer_id TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
      folder TEXT NOT NULL,normalized_path TEXT NOT NULL UNIQUE,version INTEGER NOT NULL,
      updated TEXT NOT NULL,updated_by TEXT)''')


def mapping(db,customer_id):
    row=db.execute('SELECT * FROM customer_export_folders WHERE customer_id=?',(customer_id,)).fetchone()
    return dict(row) if row else None


def normalized(value):
    from .automation import path_kind
    kind=path_kind(value)
    return ('windows:'+ntpath.normcase(ntpath.normpath(value))) if kind=='windows' else 'native:'+str(Path(value).resolve())


def beneath_root(folder,root):
    from .isolation import require_path
    require_path(folder, "exports")
    from .automation import path_kind
    if not root:raise ValidationError('Configure the root quotation folder in administrator settings first.')
    style=path_kind(root)
    if path_kind(folder)!=style:raise ValidationError('Customer folder must be beneath the configured root quotation folder.')
    p=normalized(folder);base=normalized(root);separator='\\' if style=='windows' else '/'
    if p==base or not p.startswith(base.rstrip(separator)+separator):raise ValidationError('Customer folder must be a separate subfolder beneath the configured root quotation folder.')
    if style=='native' or os.name=='nt':
        resolved=Path(folder).resolve();resolved_root=Path(root).resolve()
        if resolved_root not in resolved.parents:raise ValidationError('Customer folder resolves outside the configured root quotation folder.')
    return p


def context(db,customer):
    from .automation import config
    from .documents import filename
    cfg=config(db);saved=mapping(db,customer['id'])
    return dict(folder_customer=customer,folder_mapping=saved,folder_mapping_hash=fingerprint(saved),folder_root=cfg['pdf_folder'],folder_root_hash=fingerprint(cfg['pdf_folder']),suggested_folder=filename(customer['data']['name'],'pdf')[:-4])


def destination(db,data,cfg):
    """Never infer customer identity from display text, project, or an old PDF path."""
    customer_id=data.get('customer_id')
    row=db.execute("SELECT id FROM records WHERE id=? AND kind='customer'",(customer_id,)).fetchone() if customer_id else None
    saved=mapping(db,customer_id) if row else None
    if not saved:raise MissingFolder('Customer export folder not configured')
    beneath_root(saved['folder'],cfg['pdf_folder'])
    from .automation import native_folder
    return native_folder(saved['folder'])


class MissingFolder(RuntimeError):pass


@bp.route('/customers/<ident>/quotation-folder',methods=['GET','POST'])
def page(ident):
    from .relationships import record
    from .automation import config,test_access,native_folder,audit
    security.require_admin();root=current_app.config['DATA_DIR'];created=None
    try:
        with store.connect(root) as db:
            if request.method=='POST':db.execute('BEGIN IMMEDIATE')
            customer=record(db,ident,'customer');ctx=context(db,customer)
            if request.method=='POST':
                cfg=config(db);saved=ctx['folder_mapping'];version=str(saved['version'] if saved else 0)
                if request.form.get('version')!=version or request.form.get('root_hash')!=ctx['folder_root_hash'] or request.form.get('mapping_hash')!=ctx['folder_mapping_hash']:raise ValidationError('Customer folder or root changed in another session. Reload before continuing.')
                action=request.form.get('action','save');folder=request.form.get('quotation_folder','').strip()
                if action=='create':
                    if saved:raise ValidationError('A customer folder is already mapped. Existing mappings are never replaced by folder creation; edit or explicitly clear the mapping first.')
                    try:parent=native_folder(cfg['pdf_folder'])
                    except (RuntimeError,OSError) as exc:raise ValidationError(str(exc)) from None
                    name=request.form.get('folder_name','').strip()
                    from .documents import filename
                    if not name or filename(name,'pdf')[:-4]!=name or name in ('.','..'):raise ValidationError('Use the suggested sanitized folder name or enter a plain folder name without unsupported characters.')
                    folder=str(parent/name)
                if folder:
                    norm=beneath_root(folder,cfg['pdf_folder'])
                    separator='\\' if norm.startswith('windows:') else '/'
                    others=[r['normalized_path'] for r in db.execute('SELECT normalized_path FROM customer_export_folders WHERE customer_id<>?',(ident,))]
                    if any(norm==other or norm.startswith(other.rstrip(separator)+separator) or other.startswith(norm.rstrip(separator)+separator) for other in others):raise ValidationError('This folder overlaps another customer mapping. Select a separate customer folder.')
                elif action!='save':raise ValidationError('Enter a customer quotation folder.')
                if action=='test':
                    try:test_access(folder);flash('Customer folder access test passed using the Workplace server account.')
                    except Exception as exc:flash('Customer folder access test failed: '+str(exc))
                    ctx['folder_mapping']={**(saved or {}),'folder':folder,'version':int(version)}
                    return render_template('customer_export_folder.html',**ctx)
                if action not in ('save','create'):raise ValidationError('Invalid customer folder action.')
                if folder:
                    if action=='create':
                        try:Path(folder).mkdir(exist_ok=False);created=Path(folder)
                        except FileExistsError:raise ValidationError('That folder already exists. Map it using Quotation folder instead of creating it.') from None
                        except OSError as exc:raise ValidationError('Cannot create customer folder using the Workplace server account: '+str(exc)) from None
                    else:
                        try:native_folder(folder) # Map existing folders; never create implicitly.
                        except (RuntimeError,OSError) as exc:raise ValidationError(str(exc)) from None
                    db.execute('INSERT INTO customer_export_folders VALUES (?,?,?,?,?,?) ON CONFLICT(customer_id) DO UPDATE SET folder=excluded.folder,normalized_path=excluded.normalized_path,version=customer_export_folders.version+1,updated=excluded.updated,updated_by=excluded.updated_by',(ident,folder,norm,1,stamp(),actor()))
                else:db.execute('DELETE FROM customer_export_folders WHERE customer_id=?',(ident,))
                audit(db,'Customer quotation folder '+('created and mapped' if action=='create' else 'mapping changed'),ident+': '+folder)
                flash('Customer quotation folder saved against the stable customer ID. Existing PDFs remain in place; next save or Retry uses this mapping.')
        if request.method=='POST':return redirect('/customers/'+ident)
        return render_template('customer_export_folder.html',**ctx)
    except Exception:
        if created:
            try:created.rmdir() # Roll back only an empty directory created by this request.
            except OSError:pass
        raise
