"""Archive committed source with Windows line endings for CMD and PowerShell."""
from pathlib import Path
import subprocess
import json
import sys
import tempfile
import zipfile


def package(destination):
    source=Path(__file__).resolve().parents[1]
    destination=Path(destination).resolve()
    with tempfile.TemporaryDirectory() as temporary:
        archive=Path(temporary)/'source.zip'
        subprocess.run(['git','archive','--format=zip','--prefix=cirrus-workplace-v21/','--output='+str(archive),'HEAD'],cwd=source,check=True)
        with zipfile.ZipFile(archive) as original,zipfile.ZipFile(destination,'w') as output:
            output.comment=original.comment
            commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
            output.writestr('cirrus-workplace-v21/BUILD_INFO.json',json.dumps(dict(version=21,commit=commit),indent=2))
            for entry in original.infolist():
                data=original.read(entry.filename)
                if entry.filename.lower().endswith(('.bat','.ps1')):
                    data=data.replace(b'\r\n',b'\n').replace(b'\r',b'\n').replace(b'\n',b'\r\n')
                output.writestr(entry,data)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            if name.lower().endswith(('.bat','.ps1')):
                data=archive.read(name)
                assert b'\n' not in data.replace(b'\r\n',b''),name
    print('Verified Windows source package: '+str(destination))


if __name__=='__main__':package(sys.argv[1])
