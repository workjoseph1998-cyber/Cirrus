"""Windows console launcher; shared configuration also applies to direct run.py."""
from pathlib import Path
import runpy
import sys

source = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(source))
from workspace_app.deployment_settings import load

if __name__ == '__main__':
    settings = load()
    if settings:
        print('Persistent deployment settings: ' + str(settings), flush=True)
    runpy.run_path(str(source / 'run.py'), run_name='__main__')
