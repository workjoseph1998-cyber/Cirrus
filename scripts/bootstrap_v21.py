"""Prepare the isolated V21 sandbox as part of setup.bat; never migrate V20."""
import getpass
import json
import os
from pathlib import Path
import socket
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workspace_app import isolation, store
from workspace_app.security import create_user
from workspace_app.backup import workspace_lock
from scripts.v21 import initialize

NETWORK_KEYS = ('CIRRUS_ALLOWED_HOSTS', 'CIRRUS_INTERNAL_ACCESS', 'CIRRUS_HTTPS',
                'CIRRUS_TRUSTED_PROXY', 'CIRRUS_TIMEZONE', 'CIRRUS_PDF_BROWSER')


def default_profile_path(environ=None):
    env = os.environ if environ is None else environ
    base = Path(env.get('LOCALAPPDATA') or str(Path.home()))
    return base / 'CirrusWorkplaceV21Live' / 'Config' / 'profile.json'


def launch_profile_path():
    configured = os.environ.get('CIRRUS_V21_PROFILE')
    if configured and Path(configured).is_file():
        value = json.loads(Path(configured).read_text(encoding='utf-8-sig'))
        if value.get('version') == 21 and value.get('mode') == 'production':
            return Path(configured)
    # Earlier test profiles stay untouched and are never launched by this release.
    return default_profile_path()


def prepare():
    explicit = os.environ.get('CIRRUS_V21_PROFILE')
    profile = Path(explicit) if explicit else default_profile_path()
    if not profile.exists():
        if explicit:
            raise RuntimeError('The configured custom V21 profile is missing: ' + str(profile))
        base = profile.parent.parent
        roots = {key: str(base / name) for key, name in
                 [('data', 'Data'), ('documents', 'Documents'), ('exports', 'Exports'), ('backups', 'Backups')]}
        local = Path(os.environ.get('LOCALAPPDATA') or str(Path.home()))
        program = Path(os.environ.get('PROGRAMDATA') or os.environ.get('ProgramData') or (str(local / 'ProgramData')))
        protected = [str(local / 'CirrusWorkplace'), str(local / 'JosephWorkspace'), str(program / 'CirrusWorkplace')]
        network = {'CIRRUS_ALLOWED_HOSTS': 'localhost,127.0.0.1,172.18.69.10,' + socket.gethostname(),
                   'CIRRUS_INTERNAL_ACCESS': '1', 'CIRRUS_TRUSTED_PROXY': '127.0.0.1',
                   'CIRRUS_HTTPS': '0', 'CIRRUS_TIMEZONE': 'Asia/Beirut'}
        # Read only the old deployment's network policy. Never copy data or SMTP.
        legacy = Path(os.environ.get('CIRRUS_DEPLOYMENT_FILE') or str(program / 'CirrusWorkplace' / 'deployment.json'))
        old = {}
        if legacy.is_file():
            if legacy.stat().st_size > 65536:raise RuntimeError('Existing deployment configuration is too large.')
            old = json.loads(legacy.read_text(encoding='utf-8-sig'))
            if not isinstance(old, dict):raise RuntimeError('Existing deployment configuration is invalid.')
        for key in NETWORK_KEYS:
            value = os.environ.get(key, old.get(key))
            if value is not None:network[key] = value
        for key in ('CIRRUS_DATA_DIR', 'JOSEPH_DATA_DIR'):
            for value in (os.environ.get(key), old.get(key)):
                if value and Path(value).is_absolute():protected.append(str(Path(value)))
        # Never adopt preexisting files in any default V21 storage directory.
        for value in roots.values():
            p = Path(value)
            if p.exists() and any(p.iterdir()):
                raise RuntimeError('Unrecognized existing V21 storage; nothing overwritten: ' + str(p))
        from workspace_app.document_storage import check_components
        check_components(profile.parent, missing=True)
        profile.parent.mkdir(parents=True, exist_ok=True)
        with profile.open('x', encoding='utf-8') as handle:
            json.dump(dict(version=21, **roots, v20_protected_paths=list(dict.fromkeys(protected)), network=network), handle, indent=2)
    os.environ['CIRRUS_V21_PROFILE'] = str(profile)
    root = isolation.activate()
    if not root.exists() or not any(root.iterdir()):
        initialize(root, announce=False)
    else:
        isolation.check_database(root)  # Never silently migrate an existing database.
    print('V21 settings: ' + str(profile))
    print('V21 data: ' + str(root))
    return root


def setup():
    from scripts.live_copy_v21 import prepare_live
    profile = launch_profile_path()
    root = prepare_live(profile)
    with workspace_lock(root):
        with store.connect(root) as db:
            exists = db.execute('SELECT 1 FROM users LIMIT 1').fetchone()
        if not exists:
            print('\nCreate your V21 administrator. V20 accounts are not changed.')
            username = input('V21 username [admin]: ').strip() or 'admin'
            password = getpass.getpass('V21 password (at least 12 characters): ')
            if password != getpass.getpass('Confirm V21 password: '):
                raise RuntimeError('Passwords did not match. Run setup.bat again.')
            with store.connect(root) as db:
                db.execute('BEGIN IMMEDIATE')
                if not db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                    create_user(db, username, password, 'Administrator', initial=True)
    print('\nSetup complete. Run start.bat, then open your existing IIS URL or http://127.0.0.1:8000 (HTTP profiles).')
    print('Use your existing login. V20 data is unchanged. Existing SMTP settings are retained.')


if __name__ == '__main__':
    try:
        if len(sys.argv) > 1 and sys.argv[1] == 'profile':
            print(launch_profile_path())
        else:setup()
    except (OSError, ValueError, RuntimeError, EOFError, KeyboardInterrupt) as exc:
        print('V21 setup stopped: ' + str(exc), file=sys.stderr)
        sys.exit(1)
