"""Permission-checked customer Documents UI, downloads and administrator storage."""
import json,os
from pathlib import Path
from flask import Blueprint,abort,current_app,flash,redirect,render_template,request,send_file,url_for
from . import store,security,customer_documents as docs,document_storage as fs
from .customers import scope
from .model import ValidationError
from .commercial import fingerprint

bp=Blueprint('customer_documents',__name__)

@bp.errorhandler(OSError)
def storage_error(exc):
    return render_template('error.html',message='Document storage could not complete this operation. The saved records are retained. Check service-account folder permissions or locked files and retry.'),503


@bp.app_template_filter('document_size')
def document_size(value):
    return str(value)+' B' if value<1024 else ('%.1f KiB'%(value/1024)) if value<1024*1024 else ('%.2f MiB'%(value/(1024*1024)))

def connect():return store.connect(current_app.config['DATA_DIR'])

def base_for(db,customer,create=False):return docs.space(db,customer,current_app.config['DATA_DIR'],create)

def listing_url(ident,parent=None):return url_for('customer_documents.listing',ident=ident,**({'folder':parent} if parent else {}))


def page_context(db,customer,parent_id=None):
    folder=docs.parent(db,customer['id'],parent_id);crumbs=[];current=folder
    while current:
        crumbs.append(current);current=docs.parent(db,customer['id'],current['parent_id'])
    return dict(customer=customer,tab='documents',folder=folder,crumbs=list(reversed(crumbs)),writable=security.can_read(db,customer,write=True))


@bp.get('/customers/<ident>/documents')
def listing(ident):
    with connect() as db,fs.LOCK:
        customer=scope(db,ident);ctx=page_context(db,customer,request.args.get('folder') or None);configured=bool(docs.config(db));error=None;rows=[];base=None
        try:
            if configured:
                base=base_for(db,customer)
                if base:
                    if ctx['folder']:fs.safe_path(base,docs.relative(db,ident,ctx['folder']))
                    rows=docs.siblings(db,ident,(ctx['folder'] or {}).get('id'))
                    for row in rows:
                        path=fs.safe_path(base,docs.relative(db,ident,row));info=path.stat()
                        row['disk_changed']=row['kind']=='file' and info.st_size!=row['size']
        except (ValidationError,OSError) as exc:error=str(exc) if isinstance(exc,ValidationError) else 'The server could not access this customer’s document area. Ask an administrator to check its storage and permissions.'
        q=request.args.get('q','').strip().casefold()
        if q:rows=[r for r in rows if q in r['name'].casefold()]
        order=request.args.get('sort','name')
        if order not in ('name','newest','size'):raise ValidationError('Invalid document sort.')
        rows.sort(key=lambda r:(r['size'],r['name_key']) if order=='size' else (r['uploaded'],r['name_key']) if order=='newest' else (r['name_key'],r['id']),reverse=order in ('size','newest'))
        rows.sort(key=lambda r:r['kind']!='folder')
        from .listing_ui import paginate
        rows,pagination=paginate(rows)
    return render_template('customer_documents.html',**ctx,configured=configured,error=error,rows=rows,pagination=pagination,storage_ready=bool(base),storage_path=str(base) if base and security.admin() else None)


@bp.post('/customers/<ident>/documents/folders')
def create_folder(ident):
    with connect() as db,fs.LOCK:
        db.execute('BEGIN IMMEDIATE');customer=scope(db,ident,True);base=base_for(db,customer,True);parent=request.form.get('parent_id') or None
        docs.create_folder(db,base,ident,parent,request.form.get('name',''))
    flash('Folder created on the server.');return redirect(listing_url(ident,parent))


@bp.post('/customers/<ident>/documents/upload')
def upload(ident):
    with connect() as db,fs.LOCK:
        db.execute('BEGIN IMMEDIATE');customer=scope(db,ident,True);base=base_for(db,customer,True);parent=request.form.get('parent_id') or None
        file=request.files.get('file')
        if not file or not file.filename:raise ValidationError('Choose a document to upload.')
        draft_id=docs.stage(db,base,ident,parent,file.filename,file.stream)
        db.execute('BEGIN IMMEDIATE');draft=docs.upload_draft(db,ident,draft_id);conflict=docs.finish_upload(db,base,ident,draft,'')
        if conflict:return redirect(url_for('customer_documents.resolve_upload',ident=ident,upload_id=draft_id))
    flash('Document uploaded.');return redirect(listing_url(ident,parent))


@bp.route('/customers/<ident>/documents/uploads/<upload_id>',methods=['GET','POST'])
def resolve_upload(ident,upload_id):
    error=None
    with connect() as db,fs.LOCK:
        if request.method=='POST':db.execute('BEGIN IMMEDIATE')
        customer=scope(db,ident,True);base=base_for(db,customer);draft=docs.upload_draft(db,ident,upload_id)
        missing_parent=bool(draft['parent_id'] and not db.execute("SELECT 1 FROM customer_document_nodes WHERE id=? AND customer_id=? AND kind='folder'",(draft['parent_id'],ident)).fetchone())
        conflict=None if missing_parent else docs.available(db,base,ident,draft['parent_id'],draft['name'])
        if request.method=='POST':
            try:
                mode=request.form.get('mode','')
                if mode=='cancel':docs.cancel_upload(db,base,ident,draft);flash('Upload cancelled; the existing file was kept.');return redirect(listing_url(ident,None if missing_parent else draft['parent_id']))
                if missing_parent:raise ValidationError('The destination folder was removed. Cancel this upload and select another folder.')
                if mode not in ('replace','version','save'):raise ValidationError('Choose Replace, Save as a new version, or Cancel.')
                found=docs.finish_upload(db,base,ident,draft,mode,request.form.get('conflict_token',''))
                if found:raise ValidationError('Review the current filename conflict before saving.')
                flash('Document saved.');return redirect(listing_url(ident,draft['parent_id']))
            except ValidationError as exc:db.rollback();error=str(exc)
        ctx=page_context(db,customer,None if missing_parent else draft['parent_id']);conflict=docs.collision(db,ident,draft['parent_id'],draft['name'])
        conflict_token=docs.token(db,base,conflict) if conflict else ''
    return render_template('customer_document_upload.html',**ctx,draft=draft,conflict=conflict,conflict_token=conflict_token,missing_parent=missing_parent,error=error or ('The destination folder was removed. Cancel and upload into another folder.' if missing_parent else None)),(409 if error else 200)


@bp.get('/customers/<ident>/documents/<node_id>/download')
def download(ident,node_id):
    with connect() as db,fs.LOCK:
        customer=scope(db,ident);item=docs.node(db,ident,node_id,'file');base=base_for(db,customer)
        handle=fs.open_file(base,docs.relative(db,ident,item))
        try:
            if os.fstat(handle.fileno()).st_size!=item['size'] or fs.digest_file(handle)!=item['sha256']:
                raise ValidationError('This document changed outside Workplace. Ask an administrator to restore the matching copy or replace it through the portal.')
        except BaseException:handle.close();raise
    response=send_file(handle,as_attachment=True,download_name=item['name'],mimetype='application/octet-stream',max_age=0)
    response.call_on_close(handle.close);return response


@bp.route('/customers/<ident>/documents/<node_id>/edit',methods=['GET','POST'])
def edit(ident,node_id):
    error=None;conflict=None;conflict_token=''
    with connect() as db,fs.LOCK:
        if request.method=='POST':db.execute('BEGIN IMMEDIATE')
        customer=scope(db,ident,True);item=docs.node(db,ident,node_id);base=base_for(db,customer)
        values=dict(name=request.form.get('name',item['name']),parent_id=request.form.get('parent_id',item['parent_id'] or ''),version=request.form.get('version',str(item['version'])))
        if request.method=='POST':
            try:
                if request.form.get('mode')=='cancel':return redirect(listing_url(ident,item['parent_id']))
                conflict=docs.edit_node(db,base,item,values['parent_id'] or None,values['name'],values['version'],request.form.get('mode',''),request.form.get('conflict_token',''))
                if not conflict:flash('File/folder updated on disk.');return redirect(listing_url(ident,values['parent_id']))
                conflict_token=docs.token(db,base,conflict)
            except ValidationError as exc:db.rollback();error=str(exc)
        blocked={r['id'] for r in docs.descendants(db,ident,item)}
        folders=[dict(r) for r in db.execute("SELECT * FROM customer_document_nodes WHERE customer_id=? AND kind='folder' ORDER BY name_key",(ident,)) if r['id'] not in blocked]
        for folder in folders:folder['path']=docs.relative(db,ident,folder)
        ctx=page_context(db,customer,item['parent_id'])
    return render_template('customer_document_edit.html',**ctx,item=item,folders=folders,values=values,error=error,conflict=conflict,conflict_token=conflict_token),(409 if error or conflict else 200)


@bp.route('/customers/<ident>/documents/<node_id>/delete',methods=['GET','POST'])
def delete(ident,node_id):
    error=None
    with connect() as db,fs.LOCK:
        if request.method=='POST':db.execute('BEGIN IMMEDIATE')
        customer=scope(db,ident,True);item=docs.node(db,ident,node_id);base=base_for(db,customer);expected,affected=docs.deletion_snapshot(db,base,item)
        if request.method=='POST':
            try:
                if request.form.get('confirm')!='yes':raise ValidationError('Confirm deletion of the named file/folder and its contents.')
                docs.delete_node(db,base,item,request.form.get('snapshot',''));flash('File/folder deleted from the portal and disk.');return redirect(listing_url(ident,item['parent_id']))
            except ValidationError as exc:db.rollback();error=str(exc)
        ctx=page_context(db,customer,item['parent_id'])
    return render_template('customer_document_delete.html',**ctx,item=item,affected=affected,snapshot=expected,error=error),(409 if error else 200)


@bp.route('/administration/customer-documents',methods=['GET','POST'])
def settings():
    security.require_admin();error=None;tested=False
    with connect() as db,fs.LOCK:
        previous=docs.config(db);value=request.form.get('root',previous)
        if request.method=='POST':
            try:
                db.execute('BEGIN IMMEDIATE')
                if request.form.get('settings_hash')!=fingerprint(previous):raise ValidationError('Document storage settings changed. Reload before saving.')
                path=docs.validate_root(value,current_app.config['DATA_DIR'],db,create=request.form.get('create')=='yes')
                if request.form.get('action')=='test':
                    from .automation import test_access
                    test_access(str(path));tested=True
                elif request.form.get('action')=='save':
                    if previous and str(path)!=previous and db.execute('SELECT 1 FROM customer_document_spaces LIMIT 1').fetchone():raise ValidationError('Storage already has assigned customer folders. Restore/move the complete storage together with its matching database; the portal never switches existing customers into an empty root.')
                    db.execute("INSERT INTO settings VALUES ('customer_document_storage',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(str(path)),));flash('Customer document storage root saved.');return redirect(request.path)
                else:raise ValidationError('Choose Save or Test folder access.')
            except (OSError,ValidationError) as exc:db.rollback();error=str(exc) if isinstance(exc,ValidationError) else 'The Windows service account could not access/create the document root. Check the folder path and permissions.'
        allocated=db.execute('SELECT count(*) FROM customer_document_spaces').fetchone()[0]
    return render_template('customer_document_settings.html',value=value,settings_hash=fingerprint(previous),error=error,tested=tested,allocated=allocated,dirty=value!=previous)
