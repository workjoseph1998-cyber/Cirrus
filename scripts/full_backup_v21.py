"""Offline V21 backup including external customer documents and exports.
Run after stop-v21.bat. Never traverses V20 roots. Produces a separate ZIP format.
"""
import hashlib
import json
from pathlib import Path
import sys
import zipfile
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import isolation
from workspace_app.backup import workspace_lock
from workspace_app.document_storage import checked_tree


def backup():
    root=isolation.activate();isolation.check_database(root)
    destination=isolation.PROFILE['roots']['backups']
    destination.mkdir(parents=True,exist_ok=True)
    output=destination/('v21-complete-'+uuid4().hex+'.zip')
    pending=output.with_suffix('.partial')
    manifest={}
    try:
        with workspace_lock(root),pending.open('xb') as handle,zipfile.ZipFile(handle,'w',zipfile.ZIP_DEFLATED) as archive:
            for kind in ('data','documents','exports'):
                base=isolation.PROFILE['roots'][kind]
                checked_tree(base)
                for path in sorted(base.rglob('*')):
                    if not path.is_file() or path.name=='.workspace.lock':continue
                    name=kind+'/'+path.relative_to(base).as_posix()
                    digest=hashlib.sha256()
                    # Stream each file once, hashing exactly the bytes in the archive.
                    with path.open('rb') as source,archive.open(name,'w',force_zip64=True) as target:
                        for block in iter(lambda:source.read(1024*1024),b''):
                            digest.update(block);target.write(block)
                    manifest[name]=digest.hexdigest()
            archive.writestr('manifest-v21.json',json.dumps(dict(format='cirrus-v21-complete-1',files=manifest),indent=2))
        pending.rename(output)
        print(output)
    except BaseException:
        pending.unlink(missing_ok=True)
        raise


if __name__=='__main__':backup()
