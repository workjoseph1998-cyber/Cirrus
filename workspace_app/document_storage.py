"""External customer files: Windows-safe names, link checks and recoverable disk writes.

The application service and trusted administrators must be the only OS writers.
Portal writes are serialized by SQLite and the single-instance storage lock.
"""
import hashlib,json,os,re,shutil,stat,threading,unicodedata
from pathlib import Path,PurePosixPath
from uuid import uuid4
from .model import ValidationError

LOCK=threading.RLock()
MAX_BYTES=10*1024*1024
_INTERNAL=re.compile(r'^\.cw-(?:upload|backup|move|trash)-[0-9a-f]{32}$')


def name_key(value):return unicodedata.normalize('NFC',value).casefold()


def filename(value,internal=False):
    if internal and _INTERNAL.fullmatch(value):return value
    if not isinstance(value,str) or not value or len(value)>160 or value in ('.','..') or value[-1:] in (' ','.') or value.casefold().startswith('.cw-') or any(ord(c)<32 or ord(c)==127 or c in '<>:"/\\|?*' for c in value):
        raise ValidationError('Use a plain filename/folder name up to 160 characters, without paths, trailing dots/spaces or Windows-reserved characters.')
    stem=value.split('.')[0].rstrip(' .').casefold()
    if stem in ('con','prn','aux','nul','clock$') or re.fullmatch(r'(com|lpt)[1-9¹²³]',stem):raise ValidationError('This name is reserved by Windows.')
    return value


def check_components(path,missing=False):
    path=Path(path)
    if not path.is_absolute():raise ValidationError('Storage paths must be absolute.')
    current=Path(path.anchor)
    for part in path.parts[1:]:
        current/=part
        try:info=current.lstat()
        except FileNotFoundError:
            if missing:continue
            raise ValidationError('Storage path is missing. Restore the external document directory before continuing.') from None
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):
            raise ValidationError('Symbolic links, Windows junctions and reparse points are not allowed in customer document storage.')
    return path


def safe_path(base,relative='',missing=False,internal=False):
    check_components(base)
    rel=PurePosixPath(relative)
    if rel.is_absolute() or '..' in rel.parts:raise ValidationError('Path is outside the assigned customer folder.')
    for part in rel.parts:filename(part,internal=internal)
    path=Path(base).joinpath(*rel.parts)
    if os.name=='nt' and len(str(path))>245:raise ValidationError('This Windows path is too long. Shorten the file/folder names or folder hierarchy.')
    check_components(path,missing)
    try:path.resolve(strict=not missing).relative_to(Path(base).resolve())
    except ValueError:raise ValidationError('Path resolves outside the assigned customer folder.') from None
    return path


def file_info(path):
    info=Path(path).lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:raise ValidationError('Linked files and Windows reparse points are not allowed.')
    if not stat.S_ISREG(info.st_mode) or info.st_nlink>1:raise ValidationError('Only ordinary, unlinked document files are supported.')
    return info


def windows_handle_path(value):
    """Normalize the extended path prefix returned by a Win32 file handle."""
    if value.startswith('\\\\?\\UNC\\'):return '\\\\'+value[8:]
    return value[4:] if value.startswith('\\\\?\\') else value


def open_file(base,relative,internal=False):
    path=safe_path(base,relative,internal=internal);before=file_info(path)
    flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)
    descriptor=os.open(path,flags)
    try:
        actual=os.fstat(descriptor)
        if not stat.S_ISREG(actual.st_mode) or actual.st_nlink>1 or (before.st_ino and actual.st_ino!=before.st_ino):raise ValidationError('File changed while opening it. Retry.')
        if os.name=='nt':
            # Validate the opened handle too, including the final destination of
            # parent junctions. No Win32 handle/path escapes reach the downloader.
            import ctypes,msvcrt
            from ctypes import wintypes
            api=ctypes.WinDLL('kernel32',use_last_error=True).GetFinalPathNameByHandleW
            api.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD];api.restype=wintypes.DWORD
            buf=ctypes.create_unicode_buffer(32768);n=api(msvcrt.get_osfhandle(descriptor),buf,len(buf),0)
            if not n or n>=len(buf):raise ValidationError('Cannot verify the Windows document handle.')
            final=windows_handle_path(buf.value)
            if os.path.commonpath([os.path.normcase(str(Path(base).resolve())),os.path.normcase(final)])!=os.path.normcase(str(Path(base).resolve())):
                raise ValidationError('Opened file is outside the assigned customer folder.')
        return os.fdopen(descriptor,'rb')
    except BaseException:os.close(descriptor);raise


def digest_file(handle):
    digest=hashlib.sha256()
    for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
    handle.seek(0);return digest.hexdigest()


def disk_match(base,relative):
    """Case-insensitive collisions are checked even on the Linux test filesystem."""
    rel=PurePosixPath(relative);parent=safe_path(base,str(rel.parent) if str(rel.parent)!='.' else '')
    matches=[p for p in parent.iterdir() if name_key(p.name)==name_key(rel.name)]
    if len(matches)>1:raise ValidationError('Case-insensitive filename collision on disk. Ask an administrator to resolve it.')
    return matches[0] if matches else None


def checked_tree(path):
    check_components(path)
    for root,dirs,files in os.walk(path,followlinks=False):
        for name in dirs+files:check_components(Path(root)/name)
        for name in files:file_info(Path(root)/name)


def _remove(path):
    if not path.exists():return
    check_components(path)
    if path.is_dir():checked_tree(path);shutil.rmtree(path)
    else:file_info(path);path.unlink()


def _journal_path(base,ident):return Path(base)/('.cw-job-'+ident+'.json')


def recover(db,base,customer_id):
    for path in sorted(Path(base).glob('.cw-job-*.json')):
        check_components(path);file_info(path)
        if path.stat().st_size>256*1024:raise ValidationError('Invalid document recovery journal; administrator recovery is required.')
        try:plan=json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,OSError):raise ValidationError('Unreadable document recovery journal; administrator recovery is required.') from None
        ident=path.name[8:-5]
        if not isinstance(plan,dict) or not re.fullmatch('[0-9a-f]{32}',ident) or set(plan)!={'customer','moves','mkdir','cleanup'} or plan['customer']!=customer_id:
            raise ValidationError('Invalid document recovery journal; administrator recovery is required.')
        if not isinstance(plan['moves'],list) or len(plan['moves'])>4 or any(not isinstance(pair,list) or len(pair)!=2 or any(not isinstance(x,str) for x in pair) for pair in plan['moves']) or any(not isinstance(plan[k],list) or len(plan[k])>4 or any(not isinstance(x,str) for x in plan[k]) for k in ('mkdir','cleanup')):raise ValidationError('Invalid document recovery operations; administrator recovery is required.')
        committed=db.execute('SELECT 1 FROM customer_document_commits WHERE id=?',(ident,)).fetchone()
        if not committed:
            for source,destination in reversed(plan['moves']):
                a=safe_path(base,source,True,True);b=safe_path(base,destination,True,True)
                if b.exists() and not a.exists():os.replace(b,a)
            for folder in reversed(plan['mkdir']):
                target=safe_path(base,folder,True)
                if target.is_dir():target.rmdir()
        for relative in plan['cleanup']:_remove(safe_path(base,relative,True,True))
        path.unlink()


def publish(db,base,customer_id,job_id,moves=(),mkdir=(),cleanup=(),change=None):
    """Journal first, disk rename, DB commit; startup/access replays interrupted work.

    The caller owns BEGIN IMMEDIATE and LOCK. Failed metadata writes reverse disk
    moves. A crash after DB commit only needs cleanup, never a destructive replay.
    """
    plan=dict(customer=customer_id,moves=list(moves),mkdir=list(mkdir),cleanup=list(cleanup))
    journal=_journal_path(base,job_id)
    with journal.open('x',encoding='utf-8') as out:json.dump(plan,out);out.flush();os.fsync(out.fileno())
    try:
        for relative in mkdir:safe_path(base,relative,True).mkdir()
        for source,destination in moves:
            a=safe_path(base,source,False,True);b=safe_path(base,destination,True,True)
            if b.exists():raise ValidationError('A destination appeared on disk. Nothing was overwritten; retry the operation.')
            os.replace(a,b)
        if change:change()
        db.execute('INSERT INTO customer_document_commits VALUES (?,?)',(job_id,__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()))
        db.commit()
    except BaseException:
        db.rollback();recover(db,base,customer_id);raise
    # Cleanup failure leaves the durable journal and old bytes for a later retry.
    try:recover(db,base,customer_id)
    except (OSError,ValidationError):return False
    return True


def staging_name(kind='upload'):return '.cw-'+kind+'-'+uuid4().hex
