"""Customer-scoped file metadata and real external filesystem operations."""
import hashlib,json,os,re,time
from pathlib import Path,PurePosixPath
from uuid import uuid4
from . import document_storage as fs
from .model import ValidationError
from .commercial import fingerprint
from .references import actor,stamp


def schema(db):
    for sql in [
        '''CREATE TABLE IF NOT EXISTS customer_document_spaces(customer_id TEXT PRIMARY KEY REFERENCES records(id),folder TEXT NOT NULL,folder_key TEXT NOT NULL UNIQUE,created TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS customer_document_nodes(id TEXT PRIMARY KEY,customer_id TEXT NOT NULL REFERENCES records(id),parent_id TEXT REFERENCES customer_document_nodes(id),kind TEXT NOT NULL CHECK(kind IN ('file','folder')),name TEXT NOT NULL,name_key TEXT NOT NULL,size INTEGER NOT NULL DEFAULT 0,sha256 TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,uploaded TEXT NOT NULL,uploader TEXT REFERENCES users(id),version INTEGER NOT NULL DEFAULT 1)''',
        '''CREATE UNIQUE INDEX IF NOT EXISTS customer_document_names ON customer_document_nodes(customer_id,ifnull(parent_id,''),name_key)''',
        '''CREATE INDEX IF NOT EXISTS customer_document_parent ON customer_document_nodes(customer_id,parent_id)''',
        '''CREATE TABLE IF NOT EXISTS customer_document_uploads(id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,parent_id TEXT,name TEXT NOT NULL,staged TEXT NOT NULL,size INTEGER NOT NULL,sha256 TEXT NOT NULL,actor TEXT,expires REAL NOT NULL,target_id TEXT,target_version INTEGER)''',
        '''CREATE TABLE IF NOT EXISTS customer_document_commits(id TEXT PRIMARY KEY,at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS customer_document_audit(id TEXT PRIMARY KEY,customer_id TEXT NOT NULL,actor TEXT,at TEXT NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL)'''
    ]:db.execute(sql)
    for event in ('INSERT','UPDATE OF parent_id,customer_id'):
        db.execute('''CREATE TRIGGER IF NOT EXISTS customer_document_parent_'''+event.split()[0].lower()+''' BEFORE '''+event+''' ON customer_document_nodes
        WHEN NEW.parent_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM customer_document_nodes p WHERE p.id=NEW.parent_id AND p.customer_id=NEW.customer_id AND p.kind='folder')
        BEGIN SELECT RAISE(ABORT,'Parent folder must belong to the same customer'); END''')


def config(db):
    row=db.execute("SELECT value FROM settings WHERE key='customer_document_storage'").fetchone()
    return json.loads(row[0]) if row else ''


def validate_root(value,data_dir,db=None,create=False):
    from .isolation import require_path
    require_path(value, "documents")
    from .automation import path_kind,config as automation_config
    kind=path_kind(value)
    if kind=='windows' and os.name!='nt':raise ValidationError('A Windows/UNC document root must be configured/tested on the Windows Workplace server.')
    path=Path(value.strip()).absolute();fs.check_components(path,True);path=path.resolve(strict=False)
    for candidate in (path,*path.parents):
        if (candidate/'run.py').is_file() and (candidate/'workspace_app').is_dir():
            raise ValidationError('Customer documents cannot be stored inside any application release folder. Choose a persistent external root.')
    forbidden=[Path(data_dir).resolve(),Path(__file__).resolve().parents[1]]
    if db:
        cfg=automation_config(db)
        for key in ('pdf_folder','backup_folder'):
            if cfg[key] and (os.name=='nt' or path_kind(cfg[key])=='native'):forbidden.append(Path(cfg[key]).resolve())
    for other in forbidden:
        if path==other or path in other.parents or other in path.parents:raise ValidationError('Customer documents require a separate, non-nested storage root outside application, database, PDF-export and backup folders.')
    if not path.exists() and create:path.mkdir(parents=True)
    fs.check_components(path)
    if not path.is_dir():raise ValidationError('Document root is not an accessible folder.')
    return path


def root_path(db,data_dir):
    value=config(db)
    if not value:raise ValidationError('Customer document storage is not configured. Ask an administrator to configure it.')
    return validate_root(value,data_dir,db)


def space(db,customer,data_dir,create=False):
    root=root_path(db,data_dir)
    saved=db.execute('SELECT * FROM customer_document_spaces WHERE customer_id=?',(customer['id'],)).fetchone()
    if not saved and not create:return None
    if not saved:
        slug=re.sub(r'[^\w -]','',customer['data']['name'],flags=re.UNICODE).strip(' .-')[:36] or 'Customer'
        suffix=hashlib.sha256(customer['id'].encode()).hexdigest()[:32];folder=slug+'--'+suffix
        candidate=fs.safe_path(root,folder,True)
        if not candidate.exists():
            candidate.mkdir()
            with (candidate/'.cw-owner.json').open('x',encoding='utf-8') as out:json.dump(dict(customer=customer['id']),out);out.flush();os.fsync(out.fileno())
        db.execute('INSERT INTO customer_document_spaces VALUES (?,?,?,?)',(customer['id'],folder,fs.name_key(folder),stamp()))
        saved=db.execute('SELECT * FROM customer_document_spaces WHERE customer_id=?',(customer['id'],)).fetchone()
    base=fs.safe_path(root,saved['folder']);owner=base/'.cw-owner.json';fs.check_components(owner);fs.file_info(owner)
    try:ownership=json.loads(owner.read_text(encoding='utf-8')) if owner.stat().st_size<=1024 else None
    except ValueError:ownership=None
    if ownership!={'customer':customer['id']}:raise ValidationError('Customer folder ownership marker is invalid. Access is blocked until an administrator restores the matching document area.')
    fs.recover(db,base,customer['id'])
    for expired in db.execute('SELECT id,staged FROM customer_document_uploads WHERE customer_id=? AND expires<?',(customer['id'],time.time())).fetchall():
        fs.safe_path(base,expired['staged'],True,True).unlink(missing_ok=True)
        db.execute('DELETE FROM customer_document_uploads WHERE id=?',(expired['id'],))
    return base


def node(db,customer_id,ident,kind=None):
    row=db.execute('SELECT * FROM customer_document_nodes WHERE id=? AND customer_id=?',(ident,customer_id)).fetchone()
    if not row or (kind and row['kind']!=kind):
        from flask import abort
        abort(404)
    return dict(row)


def parent(db,customer_id,ident):return node(db,customer_id,ident,'folder') if ident else None


def relative(db,customer_id,item):
    parts=[];seen=set()
    while item:
        if item['id'] in seen or len(parts)>30:raise ValidationError('Invalid or excessively deep document folder hierarchy.')
        seen.add(item['id']);parts.append(fs.filename(item['name']))
        item=node(db,customer_id,item['parent_id'],'folder') if item['parent_id'] else None
    return '/'.join(reversed(parts))


def target_relative(db,customer_id,parent_id,name):
    p=parent(db,customer_id,parent_id)
    return '/'.join(x for x in (relative(db,customer_id,p) if p else '',fs.filename(name)) if x)


def siblings(db,customer_id,parent_id):
    return [dict(r) for r in db.execute('''SELECT n.*,u.username FROM customer_document_nodes n LEFT JOIN users u ON u.id=n.uploader
        WHERE n.customer_id=? AND n.parent_id IS ? ORDER BY n.kind DESC,n.name_key,n.id''',(customer_id,parent_id or None))]


def collision(db,customer_id,parent_id,name,exclude=None):
    row=db.execute('''SELECT * FROM customer_document_nodes WHERE customer_id=? AND parent_id IS ? AND name_key=? AND id<>?''',(customer_id,parent_id or None,fs.name_key(name),exclude or '')).fetchone()
    return dict(row) if row else None


def available(db,base,customer_id,parent_id,name,exclude=None):
    found=collision(db,customer_id,parent_id,name,exclude)
    disk=fs.disk_match(base,target_relative(db,customer_id,parent_id,name))
    if disk and not found:
        current=node(db,customer_id,exclude) if exclude else None
        if not current or fs.name_key(relative(db,customer_id,current))!=fs.name_key(target_relative(db,customer_id,parent_id,name)):
            raise ValidationError('This filename exists on disk outside the portal metadata. Choose another name; unmanaged files are never overwritten.')
    return found


def next_version(db,base,customer_id,parent_id,name):
    leaf=Path(name);stem=leaf.stem;suffix=leaf.suffix
    for version in range(2,10000):
        tail=' (v'+str(version)+')'+suffix
        candidate=fs.filename(stem[:max(1,160-len(tail))]+tail)
        if not collision(db,customer_id,parent_id,candidate) and not fs.disk_match(base,target_relative(db,customer_id,parent_id,candidate)):return candidate
    raise ValidationError('No version filename is available. Rename the uploaded file.')


def audit(db,job,customer_id,action,details):
    db.execute('INSERT INTO customer_document_audit VALUES (?,?,?,?,?,?)',(job,customer_id,actor(),stamp(),action,json.dumps(details)))


def token(db,base,item):
    path=fs.safe_path(base,relative(db,item['customer_id'],item));info=path.stat()
    return fingerprint(dict(node=item,bytes=info.st_size,mtime=info.st_mtime_ns))


def stage(db,base,customer_id,parent_id,name,stream):
    name=fs.filename(name);parent(db,customer_id,parent_id)
    ident=uuid4().hex;staged=fs.staging_name();path=fs.safe_path(base,staged,True,True);size=0;digest=hashlib.sha256()
    try:
        with path.open('xb') as out:
            for chunk in iter(lambda:stream.read(128*1024),b''):
                size+=len(chunk)
                if size>fs.MAX_BYTES:raise ValidationError('Document exceeds the 10 MiB upload limit.')
                out.write(chunk);digest.update(chunk)
            out.flush();os.fsync(out.fileno())
        found=collision(db,customer_id,parent_id,name)
        db.execute('INSERT INTO customer_document_uploads VALUES (?,?,?,?,?,?,?,?,?,?,?)',(ident,customer_id,parent_id or None,name,staged,size,digest.hexdigest(),actor(),time.time()+1800,found['id'] if found else None,found['version'] if found else None))
        db.commit();return ident
    except BaseException:path.unlink(missing_ok=True);raise


def upload_draft(db,customer_id,ident):
    row=db.execute('SELECT * FROM customer_document_uploads WHERE id=? AND customer_id=? AND actor IS ?',(ident,customer_id,actor())).fetchone()
    if not row:
        from flask import abort
        abort(404)
    if row['expires']<time.time():raise ValidationError('This upload preview expired. Upload the file again.')
    return dict(row)


def finish_upload(db,base,customer_id,draft,mode,expected=''):
    with fs.open_file(base,draft['staged'],internal=True) as staged:
        if os.fstat(staged.fileno()).st_size!=draft['size'] or fs.digest_file(staged)!=draft['sha256']:raise ValidationError('Staged upload changed on disk. Cancel it and upload the original file again.')
    found=available(db,base,customer_id,draft['parent_id'],draft['name'])
    if found and found['kind']!='file':raise ValidationError('A folder has this name. Rename the upload or select another folder.')
    if found and mode not in ('replace','version'):return found
    if found and (not expected or expected!=token(db,base,found)):raise ValidationError('The duplicate file changed. Review the current duplicate before replacing it.')
    name=next_version(db,base,customer_id,draft['parent_id'],draft['name']) if found and mode=='version' else draft['name']
    job=uuid4().hex;moves=[];cleanup=[];replacing=bool(found and mode=='replace')
    if replacing:
        backup=fs.staging_name('backup');moves.append((relative(db,customer_id,found),backup));cleanup.append(backup)
    moves.append((draft['staged'],target_relative(db,customer_id,draft['parent_id'],name)))
    def change():
        now=stamp()
        if replacing:db.execute('UPDATE customer_document_nodes SET name=?,name_key=?,size=?,sha256=?,uploaded=?,uploader=?,version=version+1 WHERE id=?',(name,fs.name_key(name),draft['size'],draft['sha256'],now,actor(),found['id']))
        else:db.execute('INSERT INTO customer_document_nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(uuid4().hex,customer_id,draft['parent_id'],'file',name,fs.name_key(name),draft['size'],draft['sha256'],now,now,actor(),1))
        db.execute('DELETE FROM customer_document_uploads WHERE id=?',(draft['id'],));audit(db,job,customer_id,'Replace file' if replacing else 'Upload file',dict(name=name,size=draft['size'],previous=found if replacing else None))
    fs.publish(db,base,customer_id,job,moves=moves,cleanup=cleanup,change=change)
    return None


def cancel_upload(db,base,customer_id,draft):
    job=uuid4().hex;trash=fs.staging_name('trash')
    fs.publish(db,base,customer_id,job,moves=[(draft['staged'],trash)],cleanup=[trash],change=lambda:db.execute('DELETE FROM customer_document_uploads WHERE id=?',(draft['id'],)))


def create_folder(db,base,customer_id,parent_id,name):
    name=fs.filename(name)
    if available(db,base,customer_id,parent_id,name):raise ValidationError('A file/folder with this name already exists.')
    job=uuid4().hex;ident=uuid4().hex;now=stamp()
    def change():
        db.execute('INSERT INTO customer_document_nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(ident,customer_id,parent_id or None,'folder',name,fs.name_key(name),0,'',now,now,actor(),1));audit(db,job,customer_id,'Create folder',dict(id=ident,name=name))
    fs.publish(db,base,customer_id,job,mkdir=[target_relative(db,customer_id,parent_id,name)],change=change)


def descendants(db,customer_id,item):
    rows=[dict(r) for r in db.execute('SELECT * FROM customer_document_nodes WHERE customer_id=?',(customer_id,))];chosen={item['id']}
    while True:
        added={r['id'] for r in rows if r['parent_id'] in chosen}-chosen
        if not added:break
        chosen|=added
    return [r for r in rows if r['id'] in chosen]


def deletion_snapshot(db,base,item):
    rows=descendants(db,item['customer_id'],item)
    path=fs.safe_path(base,relative(db,item['customer_id'],item));stats=[]
    if item['kind']=='folder':
        fs.checked_tree(path)
        managed={relative(db,item['customer_id'],r) for r in rows}
        actual={str(p.relative_to(base)).replace(os.sep,'/') for p in path.rglob('*')}
        if actual- managed:raise ValidationError('Folder contains files/folders not managed by the portal. An administrator must resolve them before deleting this folder.')
    for row in rows:
        p=fs.safe_path(base,relative(db,item['customer_id'],row));info=p.stat();stats.append((row['id'],row['version'],info.st_size,info.st_mtime_ns))
    return fingerprint(stats),rows


def delete_node(db,base,item,expected):
    current,rows=deletion_snapshot(db,base,item)
    if current!=expected:raise ValidationError('The folder/files changed since confirmation. Review the affected documents again.')
    job=uuid4().hex;trash=fs.staging_name('trash')
    def change():
        for row in sorted(rows,key=lambda r:len(relative(db,item['customer_id'],r).split('/')),reverse=True):db.execute('DELETE FROM customer_document_nodes WHERE id=?',(row['id'],))
        audit(db,job,item['customer_id'],'Delete folder' if item['kind']=='folder' else 'Delete file',dict(items=[dict(id=r['id'],name=r['name'],sha256=r['sha256']) for r in rows]))
    fs.publish(db,base,item['customer_id'],job,moves=[(relative(db,item['customer_id'],item),trash)],cleanup=[trash],change=change)


def edit_node(db,base,item,parent_id,name,expected,mode='',collision_token=''):
    if str(item['version'])!=expected:raise ValidationError('This file/folder changed in another session. Reload before editing it.')
    parent(db,item['customer_id'],parent_id);name=fs.filename(name)
    subtree={r['id'] for r in descendants(db,item['customer_id'],item)}
    if parent_id in subtree:raise ValidationError('A folder cannot be moved into itself or its descendants.')
    found=available(db,base,item['customer_id'],parent_id,name,item['id'])
    if found:
        if item['kind']!='file' or found['kind']!='file':raise ValidationError('The destination name is already used by a folder. Choose another name.')
        if mode not in ('replace','version'):return found
        if collision_token!=token(db,base,found):raise ValidationError('The destination file changed. Review the conflict again.')
        if mode=='version':name=next_version(db,base,item['customer_id'],parent_id,name)
    job=uuid4().hex;transfer=fs.staging_name('move');cleanup=[];moves=[]
    if found and mode=='replace':
        backup=fs.staging_name('backup');moves.append((relative(db,item['customer_id'],found),backup));cleanup.append(backup)
    moves.extend([(relative(db,item['customer_id'],item),transfer),(transfer,target_relative(db,item['customer_id'],parent_id,name))])
    if item['kind']=='folder':fs.checked_tree(fs.safe_path(base,relative(db,item['customer_id'],item)))
    def change():
        if found and mode=='replace':db.execute('DELETE FROM customer_document_nodes WHERE id=?',(found['id'],))
        db.execute('UPDATE customer_document_nodes SET name=?,name_key=?,parent_id=?,version=version+1 WHERE id=?',(name,fs.name_key(name),parent_id or None,item['id']))
        audit(db,job,item['customer_id'],'Move / rename '+item['kind'],dict(id=item['id'],before=relative(db,item['customer_id'],item),after=target_relative(db,item['customer_id'],parent_id,name),replaced=found if found and mode=='replace' else None))
    fs.publish(db,base,item['customer_id'],job,moves=moves,cleanup=cleanup,change=change);return None
