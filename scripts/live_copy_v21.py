"""Copy a stopped V20 installation into independent V21 live storage.

The original database is opened read-only, never migrated. Publication happens
only after copied data, external files and rewritten destinations validate.
"""
from contextlib import contextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import tempfile
from uuid import uuid4

from workspace_app import isolation, store
from workspace_app import document_storage as fs


@contextmanager
def stopped_source(root):
    listener = socket.socket()
    if os.name == 'nt':listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    handle = None
    locked = False
    try:
        try:listener.bind(('127.0.0.1', 8000)); listener.listen(1)
        except OSError:raise RuntimeError('Stop V20 before setup: port 8000 is occupied.') from None
        lock = root / '.workspace.lock'
        if not lock.is_file():raise RuntimeError('This folder has no V20 storage lock. Select the data folder used by your running V20 installation.')
        fs.check_components(lock);fs.file_info(lock)
        # Open an EXISTING lock only. No file creation or byte writes in V20.
        handle = lock.open('r+b')
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        yield
    finally:
        if handle:
            if locked:
                if os.name == 'nt':
                    import msvcrt
                    handle.seek(0);msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()
        listener.close()


def legacy_settings():
    local = Path(os.environ.get('LOCALAPPDATA') or str(Path.home()))
    program = Path(os.environ.get('PROGRAMDATA') or os.environ.get('ProgramData') or str(local / 'ProgramData'))
    filename = Path(os.environ.get('CIRRUS_DEPLOYMENT_FILE') or str(program / 'CirrusWorkplace' / 'deployment.json'))
    cfg = {}
    if filename.is_file():
        if filename.stat().st_size > 65536:raise RuntimeError('V20 deployment file exceeds the supported size.')
        cfg = json.loads(filename.read_text(encoding='utf-8-sig'))
        if not isinstance(cfg, dict):raise RuntimeError('V20 deployment file is invalid.')
    return local, program, cfg


def find_source(cfg, local):
    explicit = os.environ.get('CIRRUS_V20_DATA_DIR')
    candidates = [explicit] if explicit else [os.environ.get('CIRRUS_DATA_DIR'), os.environ.get('JOSEPH_DATA_DIR'), cfg.get('CIRRUS_DATA_DIR'), cfg.get('JOSEPH_DATA_DIR')]
    for raw in candidates:
        if raw and (Path(raw) / 'workspace.sqlite').is_file():return Path(raw).resolve()
    found = [p for p in (local / 'JosephWorkspace', local / 'CirrusWorkplace') if (p / 'workspace.sqlite').is_file()]
    if len(found) == 1:return found[0].resolve()
    print('Locate the existing V20 DATA folder containing workspace.sqlite. Nothing in it will be overwritten.')
    raw = input('V20 data folder: ').strip().strip('"')
    root = Path(raw)
    if root.is_file() and root.name == 'workspace.sqlite':root = root.parent
    if not root.is_absolute() or not (root / 'workspace.sqlite').is_file():raise RuntimeError('The selected V20 data folder does not contain workspace.sqlite.')
    return root.resolve()


def copy_directory(source, target):
    source = Path(source)
    fs.checked_tree(source)
    shutil.copytree(source, target)


def copy_live(profile, source, network, other_protected=()):
    """All targets are new; a failed import leaves no published profile or targets."""
    profile = Path(profile).resolve();source = Path(source).resolve()
    base = profile.parent.parent
    roots = {key: base / name for key, name in [('data','Data'),('documents','Documents'),('exports','Exports'),('backups','Backups')]}
    if profile.exists():raise RuntimeError('A live V21 profile already exists. Setup never replaces an installation.')
    for root in roots.values():
        if root.exists():raise RuntimeError('Existing live V21 storage is not overwritten: ' + str(root))
    fs.check_components(profile.parent, missing=True)
    fs.checked_tree(source)
    fs.file_info(source / 'workspace.sqlite')
    base.mkdir(parents=True, exist_ok=True)
    previous = isolation.PROFILE
    old_profile_env = os.environ.get('CIRRUS_V21_PROFILE')
    published = []
    candidate = profile.parent / ('candidate-' + uuid4().hex + '.json')
    profile.parent.mkdir(parents=True, exist_ok=True)
    try:
        with stopped_source(source), tempfile.TemporaryDirectory(prefix='.v21-copy-', dir=base) as temporary:
            stage = Path(temporary)
            data = stage / 'data'
            print('Copying V20 database and attachments into independent V21 storage...', flush=True)
            # Copy ordinary runtime files; snapshot SQLite separately, without writes to source.
            shutil.copytree(source, data, ignore=shutil.ignore_patterns('workspace.sqlite','workspace.sqlite-*','.workspace.lock','.cirrus-v21.json'))
            with closing(sqlite3.connect((source / 'workspace.sqlite').as_uri() + '?mode=ro', uri=True)) as old, closing(sqlite3.connect(data / 'workspace.sqlite')) as new:
                if old.execute('PRAGMA user_version').fetchone()[0] != 17:raise RuntimeError('The selected source is not the expected V20 schema 17. No original database was changed.')
                old.backup(new)
                if new.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':raise RuntimeError('The source database did not pass its integrity check.')
            with store.connect(data) as db:
                values = {r['key']: json.loads(r['value']) for r in db.execute("SELECT key,value FROM settings WHERE key IN ('automation','customer_document_storage')")}
                automation = values.get('automation', {})
                old_documents = Path(values['customer_document_storage']).resolve() if values.get('customer_document_storage') else None
                old_exports = Path(automation['pdf_folder']).resolve() if automation.get('pdf_folder') else None
                protected = [source, *map(Path, other_protected)]
                protected += [p for p in (old_documents, old_exports, Path(automation['backup_folder']).resolve() if automation.get('backup_folder') else None) if p]
                # Validate the final profile BEFORE copying any customer files.
                spec = dict(version=21, mode='production', **{k:str(v) for k,v in roots.items()}, network=network,
                            v20_protected_paths=list(dict.fromkeys(str(p.resolve()) for p in protected)))
                candidate.write_text(json.dumps(spec, indent=2), encoding='utf-8')
                os.environ['CIRRUS_V21_PROFILE'] = str(candidate)
                isolation.activate()
                for key, old_root in [('documents', old_documents), ('exports', old_exports)]:
                    target = stage / key
                    if old_root:
                        print('Copying existing ' + key + ' into V21; originals remain in place...', flush=True)
                        copy_directory(old_root, target)
                    else:target.mkdir()
                (stage / 'backups').mkdir()
                def mapped(value, old_root, kind, recover_file=False):
                    if not value:return value
                    p = Path(value).resolve()
                    try:relative = p.relative_to(old_root) if old_root else None
                    except ValueError:relative = None
                    if relative is not None:return str(roots[kind] / relative)
                    if recover_file and kind == 'exports':
                        # Preserve historical exports whose root changed in V20.
                        name = hashlib.sha256(str(p).encode()).hexdigest()[:20] + '-' + p.name
                        destination = stage / 'exports' / 'Recovered' / name
                        destination.parent.mkdir(exist_ok=True)
                        if p.exists():
                            fs.check_components(p);fs.file_info(p);shutil.copyfile(p, destination)
                        return str(roots['exports'] / 'Recovered' / name)
                    raise RuntimeError('An existing storage mapping is outside its configured root: ' + str(p))
                from workspace_app.export_folders import normalized
                for row in db.execute('SELECT customer_id,folder FROM customer_export_folders').fetchall():
                    folder = mapped(row['folder'], old_exports, 'exports')
                    db.execute('UPDATE customer_export_folders SET folder=?,normalized_path=? WHERE customer_id=?', (folder, normalized(folder), row['customer_id']))
                for row in db.execute("SELECT record_id,destination FROM pdf_exports WHERE destination IS NOT NULL AND destination<>''").fetchall():
                    db.execute('UPDATE pdf_exports SET destination=? WHERE record_id=?', (mapped(row['destination'],old_exports,'exports',True),row['record_id']))
                import ntpath
                for row in db.execute('SELECT path_key,path FROM pdf_file_owners').fetchall():
                    path = mapped(row['path'], old_exports, 'exports', True)
                    key = ntpath.normcase(path.replace('/','\\')).casefold()
                    db.execute('UPDATE pdf_file_owners SET path=?,path_key=? WHERE path_key=?', (path,key,row['path_key']))
                for row in db.execute('SELECT id,files FROM quotation_deletions').fetchall():
                    files = json.loads(row['files'])
                    for f in files:
                        if f.get('done'):continue
                        f['path'] = mapped(f['path'], old_exports if f['external'] else source, 'exports' if f['external'] else 'data', f['external'])
                        if f['external']:f['path_key'] = ntpath.normcase(f['path'].replace('/','\\')).casefold()
                    db.execute('UPDATE quotation_deletions SET files=? WHERE id=?', (json.dumps(files),row['id']))
                automation.update(pdf_folder=str(roots['exports']),backup_folder=str(roots['backups']))
                for key,value in [('automation',automation),('customer_document_storage',str(roots['documents']))]:
                    db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value)))
                db.execute("DELETE FROM settings WHERE key='backup_state'")
                db.execute("UPDATE notification_emails SET status='cancelled',error='Prior-version queue retained without replay during V21 copy.' WHERE status IN ('pending','running','failed')")
            # Only the NEW snapshot is migrated. No source connection exists here.
            store.migrate(data)
            (data / '.cirrus-v21.json').write_text(json.dumps({'version':21}))
            with store.connect(data) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():raise RuntimeError('Copied V21 database failed validation.')
                isolation.validate_settings(db)
            for key, target in roots.items():
                (stage / key).rename(target);published.append(target)
            candidate.rename(profile)
            published.clear()
        os.environ['CIRRUS_V21_PROFILE'] = str(profile)
        root = isolation.activate();isolation.check_database(root)
        print('V21 live copy ready. Use your existing V20 login. All new work goes to V21 storage.', flush=True)
        return root
    finally:
        candidate.unlink(missing_ok=True)
        for path in reversed(published):shutil.rmtree(path)
        if not profile.exists():
            isolation.PROFILE = previous
            if old_profile_env is None:os.environ.pop('CIRRUS_V21_PROFILE', None)
            else:os.environ['CIRRUS_V21_PROFILE'] = old_profile_env


def prepare_live(profile):
    profile = Path(profile)
    if profile.is_file():
        spec = json.loads(profile.read_text(encoding='utf-8-sig'))
        if spec.get('mode') != 'production':raise RuntimeError('This is an older test profile. It will not be reused for the live installation.')
        os.environ['CIRRUS_V21_PROFILE'] = str(profile)
        root = isolation.activate();isolation.check_database(root)
        print('Using existing V21 live data; no re-import or migration performed.')
        return root
    local, program, cfg = legacy_settings()
    source = find_source(cfg, local)
    from scripts.bootstrap_v21 import NETWORK_KEYS
    network = {'CIRRUS_ALLOWED_HOSTS':'localhost,127.0.0.1,172.18.69.10,'+socket.gethostname(),
               'CIRRUS_INTERNAL_ACCESS':'1','CIRRUS_TRUSTED_PROXY':'127.0.0.1','CIRRUS_HTTPS':'0','CIRRUS_TIMEZONE':'Asia/Beirut'}
    for key in NETWORK_KEYS:
        value = os.environ.get(key, cfg.get(key))
        if value is not None:network[key] = value
    return copy_live(profile, source, network, (local/'CirrusWorkplace',local/'JosephWorkspace',program/'CirrusWorkplace'))
