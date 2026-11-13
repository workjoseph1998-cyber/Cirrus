"""Fail-closed V21 profile. Never discover or inherit V20 deployment settings."""
import json
import os
from pathlib import Path
import sqlite3

PROFILE_ENV = 'CIRRUS_V21_PROFILE'
PROFILE = None


def overlap(a, b):
    return a == b or a in b.parents or b in a.parents


def read_profile():
    filename = os.environ.get(PROFILE_ENV)
    if not filename:
        from scripts.bootstrap_v21 import default_profile_path
        filename = str(default_profile_path())
    if not Path(filename).is_file():
        raise RuntimeError('V21 setup is not complete. Run setup.bat first.')
    path = Path(filename).resolve()
    values = json.loads(path.read_text(encoding='utf-8-sig'))
    if values.get('version') != 21:
        raise RuntimeError('Profile must explicitly identify version 21.')
    source = Path(__file__).resolve().parents[1]
    roots = {}
    for key in ('data', 'documents', 'exports', 'backups'):
        raw = values.get(key, '')
        if not raw or not Path(raw).is_absolute():
            raise RuntimeError('V21 profile requires an absolute ' + key + ' path.')
        candidate = Path(raw)
        # Refuse junctions, symbolic links and hard-linked database files.
        from .document_storage import check_components
        check_components(candidate, missing=True)
        roots[key] = candidate.resolve()
        if overlap(roots[key], source):
            raise RuntimeError('V21 storage must be outside application source.')
    protected = values.get('v20_protected_paths')
    if not isinstance(protected, list) or len(protected) < 2:
        raise RuntimeError('List the V20 application, data and all external storage in v20_protected_paths.')
    for raw in protected:
        if not raw or not Path(raw).is_absolute():
            raise RuntimeError('Protected V20 paths must be absolute.')
        p = Path(raw).resolve()
        if overlap(source, p) or any(overlap(p, r) for r in roots.values()):
            raise RuntimeError('V21 application/storage overlaps protected V20 paths.')
    if any(overlap(a, b) for k, a in roots.items() for j, b in roots.items() if k != j):
        raise RuntimeError('V21 data/documents/exports/backups must be separate, non-nested directories.')
    if any(overlap(path, p) for p in [source, *roots.values()]):
        raise RuntimeError('Keep the V21 profile outside application and storage folders.')
    values['roots'] = roots
    return values


def activate():
    global PROFILE
    PROFILE = read_profile()
    env = os.environ
    root = str(PROFILE['roots']['data'])
    # Ignore inherited legacy paths. The explicit V21 profile is authoritative.
    env['CIRRUS_DATA_DIR'] = env['JOSEPH_DATA_DIR'] = root
    env['CIRRUS_BIND'], env['CIRRUS_PORT'] = '127.0.0.1', '8000'
    if PROFILE.get('mode', 'test') not in ('test', 'production'):
        raise RuntimeError('Unsupported V21 profile mode.')
    env['CIRRUS_DISABLE_EMAIL'] = '0' if PROFILE.get('mode') == 'production' else '1'
    from .deployment_settings import KEYS
    network = PROFILE.get('network', {})
    allowed = {'CIRRUS_ALLOWED_HOSTS', 'CIRRUS_INTERNAL_ACCESS', 'CIRRUS_HTTPS',
               'CIRRUS_TRUSTED_PROXY', 'CIRRUS_TIMEZONE', 'CIRRUS_PDF_BROWSER'}
    if not isinstance(network, dict) or set(network) - allowed:
        raise RuntimeError('Unsupported V21 network setting.')
    for key in KEYS - {'CIRRUS_DATA_DIR', 'JOSEPH_DATA_DIR', 'CIRRUS_BIND', 'CIRRUS_PORT', 'CIRRUS_DISABLE_EMAIL'}:
        env.pop(key, None)
    for key, value in network.items():
        if not isinstance(value, str) or '\x00' in value or '\n' in value or '\r' in value:
            raise RuntimeError('Network profile values must be single-line strings.')
        env[key] = value
    return PROFILE['roots']['data']


def require_path(value, kind):
    """Constrain all runtime destinations, including settings restored/imported later."""
    if PROFILE is None:
        return  # Unit tests use disposable roots with testing=True.
    from .document_storage import check_components
    p = Path(value)
    if not p.is_absolute():
        raise RuntimeError('V21 storage paths must be absolute.')
    check_components(p, missing=True)
    p = p.resolve()
    expected = PROFILE['roots'][kind]
    if p != expected and expected not in p.parents:
        raise RuntimeError('V21 ' + kind + ' path is outside its isolated profile root.')


def check_database(root, require_schema=True):
    require_path(root, 'data')
    marker = Path(root) / '.cirrus-v21.json'
    if not marker.is_file() or json.loads(marker.read_text()) != {'version': 21}:
        raise RuntimeError('Uninitialized V21 data directory. Run scripts/v21.py init explicitly on an EMPTY directory.')
    target = Path(root) / 'workspace.sqlite'
    from .document_storage import check_components, file_info
    if target.exists():
        check_components(target); file_info(target)
    if require_schema:
        if not target.is_file():
            raise RuntimeError('V21 database missing; initialize explicitly.')
        with sqlite3.connect(target.as_uri() + '?mode=ro', uri=True) as db:
            if db.execute('PRAGMA user_version').fetchone()[0] != 18:
                raise RuntimeError('V21 requires schema 18. Run scripts/v21.py migrate explicitly on the isolated copy. Startup never migrates.')
            validate_settings(db)


def validate_settings(db):
    for key, raw in db.execute("SELECT key,value FROM settings WHERE key IN ('automation','customer_document_storage')"):
        value = json.loads(raw)
        if key == 'customer_document_storage' and value:
            require_path(value, 'documents')
        if key == 'automation':
            for field, kind in [('pdf_folder', 'exports'), ('backup_folder', 'backups')]:
                if value.get(field):require_path(value[field], kind)
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='customer_export_folders'").fetchone():
        for row in db.execute('SELECT folder FROM customer_export_folders'):
            require_path(row[0], 'exports')

    # Old PDF ownership/deletion metadata can outlive a settings change.
    # Reject it before workers start, including paths restored from a V20 copy.
    for table, column in [('pdf_file_owners','path'),('pdf_exports','destination')]:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone():
            for row in db.execute('SELECT '+column+' FROM '+table+' WHERE '+column+" IS NOT NULL AND "+column+"<>''"):
                require_path(row[0], 'exports')
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='quotation_deletions'").fetchone():
        for row in db.execute('SELECT files FROM quotation_deletions'):
            for entry in json.loads(row[0]):
                if not entry.get('done'):
                    require_path(entry['path'], 'exports' if entry['external'] else 'data')
