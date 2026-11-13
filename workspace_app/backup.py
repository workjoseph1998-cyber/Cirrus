"""Offline, single-instance locking and verified archive backup/restore."""
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile


@contextmanager
def workspace_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.workspace.lock').open('a+b') as handle:
        handle.seek(0)
        if handle.read(1) == b'':
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            raise RuntimeError('Workspace is in use. Stop the application before backup or restore.') from None
        try:
            yield
        finally:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):result.update(chunk)
    return result.hexdigest()


def backup(root, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if root == destination or root in destination.parents:
        raise ValueError('Backup destination must be outside the data directory.')
    if not (root/'workspace.sqlite').is_file():
        raise ValueError('No workspace database found.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with workspace_lock(root), tempfile.TemporaryDirectory() as temp:
        stage = Path(temp)
        with closing(sqlite3.connect(root/'workspace.sqlite')) as source, closing(sqlite3.connect(stage/'workspace.sqlite')) as target:
            source.backup(target)
            schema=target.execute('PRAGMA user_version').fetchone()[0]
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('SQLite integrity check failed.')
        shutil.copytree(root/'attachments', stage/'attachments')
        files = sorted(p for p in stage.rglob('*') if p.is_file())
        manifest = {p.relative_to(stage).as_posix():digest(p) for p in files}
        # Exclusive creation guarantees that an existing archive is never overwritten.
        with destination.open('xb') as handle:
            try:
                with zipfile.ZipFile(handle,'w',zipfile.ZIP_DEFLATED) as archive:
                    for path in files:
                        archive.write(path,path.relative_to(stage).as_posix())
                    archive.writestr('manifest.json',json.dumps({'version':1,'application':'Cirrus Workplace','application_version':'21','schema':schema,'files':manifest}))
            except Exception:
                handle.close()
                destination.unlink(missing_ok=True)
                raise


def restore(archive_path, target):
    target = Path(target).resolve()
    if target.exists():
        raise ValueError('Restore target already exists. Choose a new directory.')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='cirrus-restore-',dir=target.parent))
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos=archive.infolist()
            if len({i.filename for i in infos}) != len(infos) or sum(i.file_size for i in infos)>5*1024**3:
                raise ValueError('Duplicate entries or backup exceeds 5 GiB restore limit.')
            manifest=json.loads(archive.read('manifest.json'))
            if manifest.get('version') != 1 or not isinstance(manifest.get('files'),dict):
                raise ValueError('Unsupported backup format.')
            expected=set(manifest['files'])|{'manifest.json'}
            if set(archive.namelist()) != expected or 'workspace.sqlite' not in expected:
                raise ValueError('Backup manifest does not match archive.')
            for filename, checksum in manifest['files'].items():
                if filename != 'workspace.sqlite' and not (filename.startswith('attachments/') and len(filename.split('/'))==2):
                    raise ValueError('Unsafe backup path.')
                if '\\' in filename or ':' in filename or '..' in filename.split('/') or Path(filename).is_absolute():
                    raise ValueError('Unsafe backup path.')
                path=stage/filename
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(archive.read(filename))
                if digest(path) != checksum:
                    raise ValueError('Backup checksum mismatch.')
        (stage/'attachments').mkdir(exist_ok=True)
        with closing(sqlite3.connect(stage/'workspace.sqlite')) as conn:
            if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or conn.execute('PRAGMA user_version').fetchone()[0] not in (1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18):
                raise ValueError('Database integrity or schema version mismatch.')
            for row in conn.execute('SELECT stored FROM attachments'):
                name=row[0]
                if Path(name).name != name or '\\' in name or not (stage/'attachments'/name).is_file():
                    raise ValueError('Backup has missing or unsafe attachment metadata.')
        # Reserve the name without replacing any pre-existing directory.
        target.mkdir(exist_ok=False)
        try:
            for path in stage.iterdir():
                shutil.move(str(path),target/path.name)
        except Exception:
            shutil.rmtree(target)
            raise
    finally:
        shutil.rmtree(stage,ignore_errors=True)


def online_safety_backup(root,destination,allow_internal=False):
    """Administrator operation: block SQLite writes while snapshotting DB + referenced files.

    Caller must enforce administrator access. Unlike offline backup(), the server
    already holds the process lock; BEGIN IMMEDIATE provides the write barrier.
    """
    root=Path(root).resolve();destination=Path(destination).resolve()
    if root==destination or root in destination.parents and not allow_internal:raise ValueError('Backup destination must be outside the data directory.')
    if destination.exists():raise FileExistsError('Backup destination already exists.')
    from . import store
    from datetime import datetime,timezone
    # The write barrier protects metadata + immutable referenced attachment files.
    # Compression happens after releasing it, so normal saves resume promptly.
    with tempfile.TemporaryDirectory(prefix='cirrus-backup-') as temporary:
        stage=Path(temporary)
        with store.connect(root) as barrier:
            barrier.execute('BEGIN IMMEDIATE')
            with closing(sqlite3.connect(root/'workspace.sqlite')) as source,closing(sqlite3.connect(stage/'workspace.sqlite')) as target:
                source.backup(target)
                schema=target.execute('PRAGMA user_version').fetchone()[0]
                if target.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Database integrity check failed.')
            (stage/'attachments').mkdir()
            for item in barrier.execute('SELECT stored FROM attachments'):
                name=item['stored']
                if Path(name).name!=name or '\\' in name or ':' in name:raise ValueError('Unsafe attachment metadata; backup aborted.')
                shutil.copyfile(root/'attachments'/name,stage/'attachments'/name)
        files=sorted(p for p in stage.rglob('*') if p.is_file())
        if sum(p.stat().st_size for p in files)>5*1024**3:raise ValueError('Full backup exceeds the supported 5 GiB uncompressed restore limit.')
        destination.parent.mkdir(parents=True,exist_ok=True)
        # Never return a partially written archive. The exclusive publication lock
        # prevents another caller from overwriting an existing full backup.
        descriptor,name=tempfile.mkstemp(prefix='.cirrus-backup-',suffix='.tmp',dir=destination.parent);os.close(descriptor)
        temporary_zip=Path(name);publication=destination.with_name('.'+destination.name+'.publishing');locked=False
        try:
            with zipfile.ZipFile(temporary_zip,'w',zipfile.ZIP_DEFLATED) as archive:
                for path in files:archive.write(path,path.relative_to(stage).as_posix())
                archive.writestr('manifest.json',json.dumps({'version':1,'application':'Cirrus Workplace','application_version':'21','schema':schema,'created_utc':datetime.now(timezone.utc).isoformat(),'files':{p.relative_to(stage).as_posix():digest(p) for p in files}}))
            with temporary_zip.open('r+b') as handle:os.fsync(handle.fileno())
            with publication.open('xb'):locked=True
            if destination.exists():raise FileExistsError('Backup destination already exists.')
            os.replace(temporary_zip,destination)
        finally:
            temporary_zip.unlink(missing_ok=True)
            if locked:publication.unlink(missing_ok=True)
