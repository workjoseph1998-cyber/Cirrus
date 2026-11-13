"""Stop the server first. Backup refuses overwrite; restore requires a new path."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workspace_app import data_directory
from workspace_app.backup import backup, restore

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['backup','restore'])
    parser.add_argument('archive',type=Path)
    parser.add_argument('--target',type=Path,help='Required new directory for restore')
    args=parser.parse_args()
    try:
        if args.action=='backup':
            backup(data_directory(),args.archive)
        else:
            if not args.target:
                parser.error('restore requires --target')
            restore(args.archive,args.target)
        print(args.action.title()+' completed and integrity verified.')
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1,str(exc)+'\n')
