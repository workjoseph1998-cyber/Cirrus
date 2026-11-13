"""Persistent, data-only deployment settings; inherited environment wins.

Windows defaults live under ProgramData, never a version-specific source folder.
No shell snippets are evaluated and no web bindings are changed implicitly.
"""
import json
import os
from pathlib import Path

DEFAULT_HOSTS = 'localhost,127.0.0.1,172.18.69.10'
KEYS = frozenset(('CIRRUS_ALLOWED_HOSTS', 'CIRRUS_BIND', 'CIRRUS_PORT',
                 'CIRRUS_INTERNAL_ACCESS', 'CIRRUS_HTTPS', 'CIRRUS_TRUSTED_PROXY',
                 'CIRRUS_ALLOW_HTTP_LAN', 'CIRRUS_DATA_DIR', 'JOSEPH_DATA_DIR',
                 'CIRRUS_TIMEZONE', 'CIRRUS_PDF_BROWSER', 'CIRRUS_DISABLE_EMAIL'))


def path_for(environ=None, windows=None):
    env = os.environ if environ is None else environ
    if env.get('CIRRUS_DEPLOYMENT_FILE'):
        return Path(env['CIRRUS_DEPLOYMENT_FILE'])
    if (windows if windows is not None else os.name == 'nt'):
        return Path(env.get('PROGRAMDATA', r'C:\ProgramData')) / 'CirrusWorkplace' / 'deployment.json'
    return None  # Non-Windows deployments can opt in using the explicit path.


def load(environ=None, path=None, windows=None):
    env = os.environ if environ is None else environ
    if environ is None:
        return None  # V21 uses only its explicit profile; never read/write V20 deployment.json.
    destination = Path(path) if path is not None else path_for(env, windows)
    if destination is None:
        return None
    destination = destination.resolve()
    source = Path(__file__).resolve().parents[1]
    if destination == source or source in destination.parents:
        raise RuntimeError('CIRRUS_DEPLOYMENT_FILE must be outside the application folder.')
    if not destination.exists():
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation never replaces administrator settings.
            with destination.open('x', encoding='utf-8') as handle:
                json.dump({'CIRRUS_ALLOWED_HOSTS': DEFAULT_HOSTS}, handle, indent=2)
                handle.write('\n')
        except FileExistsError:
            pass
        except OSError as exc:
            raise RuntimeError('Cannot create persistent deployment settings at ' + str(destination) +
                               '. Create this file as an administrator and grant the Workplace service read access.') from exc
    try:
        if destination.stat().st_size > 65536:
            raise ValueError('File exceeds 64 KiB.')
        values = json.loads(destination.read_text(encoding='utf-8-sig'))
        if not isinstance(values, dict) or set(values) - KEYS:
            raise ValueError('Use only supported deployment setting names.')
        if any(not isinstance(v, str) or '\x00' in v or '\n' in v or '\r' in v for v in values.values()):
            raise ValueError('Deployment values must be single-line strings.')
    except (ValueError, OSError) as exc:
        raise RuntimeError('Invalid deployment settings at ' + str(destination) + ': ' + str(exc)) from exc
    for key, value in values.items():
        env.setdefault(key, value)
    return destination
