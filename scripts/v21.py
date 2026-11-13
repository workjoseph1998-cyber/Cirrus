"""Explicit V21 data initialization/migration and race-safe loopback launcher."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import isolation, store
from workspace_app.backup import workspace_lock


def initialize(root, announce=True):
    # No existing DB, marker, or other files may be adopted implicitly.
    if root.exists() and any(root.iterdir()):
        raise RuntimeError('init requires an empty V21 data directory. Existing databases are never adopted or overwritten.')
    root.mkdir(parents=True,exist_ok=True)
    for key,path in isolation.PROFILE['roots'].items():
        if key!='data' and path.exists() and any(path.iterdir()):
            raise RuntimeError('Initialize with empty V21 storage roots only: '+str(path))
    with (root/'.cirrus-v21.json').open('x',encoding='utf-8') as f:json.dump({'version':21},f)
    with workspace_lock(root):
        store.migrate(root)
        for key,path in isolation.PROFILE['roots'].items():path.mkdir(parents=True,exist_ok=True)
        with store.connect(root) as db:
            from workspace_app.automation import DEFAULTS
            cfg=dict(DEFAULTS,pdf_folder=str(isolation.PROFILE['roots']['exports']),backup_folder=str(isolation.PROFILE['roots']['backups']))
            for key,value in [('automation',cfg),('customer_document_storage',str(isolation.PROFILE['roots']['documents']))]:
                db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value)))
    if announce:
        print('Initialized isolated V21 database. Next run manage.py init-admin with the same profile.')


def serve(root):
    # Reserve port BEFORE opening the database; no preflight check/bind race.
    listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    if os.name=='nt':listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    else:listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    try:
        listener.bind(('127.0.0.1',8000))
        listener.listen(128)
    except OSError:
        listener.close()
        raise RuntimeError('Port 8000 is occupied. Stop V20 (including any service auto-restart) first. No process was killed.') from None
    try:
        isolation.check_database(root)
        with workspace_lock(root):
            from workspace_app import create_app
            from workspace_app.network import configuration
            from waitress import create_server
            app=create_app(root)
            net=configuration()
            server=create_server(app,sockets=[listener],threads=4,clear_untrusted_proxy_headers=False,max_request_body_size=12*1024*1024)
            mode = 'LIVE · existing accounts and copied data' if isolation.PROFILE.get('mode') == 'production' else 'TEST · SMTP disabled'
            print('Cirrus Workplace Version 21 · 127.0.0.1:8000 · ' + mode,flush=True)
            try:server.run()
            finally:server.close()
    finally:listener.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('init','migrate','start','check'))
    args=parser.parse_args()
    root=isolation.activate()
    if args.action=='init':initialize(root)
    elif args.action=='migrate':
        isolation.check_database(root,require_schema=False)
        # Only an already marked V21 sandbox can be migrated, never a V20 root.
        with workspace_lock(root):
            from workspace_app.backup import online_safety_backup
            destination=isolation.PROFILE['roots']['backups']
            destination.mkdir(parents=True,exist_ok=True)
            from uuid import uuid4
            online_safety_backup(root,destination/('pre-migration-'+uuid4().hex+'.zip'))
            with store.connect(root) as db:isolation.validate_settings(db)
            store.migrate(root)
        print('Isolated V21 migration complete.')
    elif args.action=='check':
        isolation.check_database(root)
        print('V21 profile and schema validated; no migration performed.')
    else:serve(root)


if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError,ValueError) as exc:
        print('V21 refused: '+str(exc),file=sys.stderr)
        sys.exit(1)
